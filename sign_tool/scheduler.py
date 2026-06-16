"""Background scheduler for automatic sign-in."""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

from .log import get_logger
from .config import load_config

logger = get_logger()

# UTC+8 北京时间
_CN_TZ = timezone(timedelta(hours=8))


def _now_cn() -> datetime:
    return datetime.now(_CN_TZ)


def _get_next_delay(times: list[tuple[int, int]]) -> float:
    """Calculate seconds until the next scheduled time (UTC+8)."""
    now = _now_cn()
    current_hm = (now.hour, now.minute)

    for h, m in sorted(times):
        if (h, m) > current_hm:
            return (h - now.hour) * 3600 + (m - now.minute) * 60 - now.second

    # All times passed today, wait until first time tomorrow
    h, m = sorted(times)[0]
    return (24 - now.hour + h) * 3600 + (m - now.minute) * 60 - now.second


async def _sign_all_users(config_path: str):
    """执行所有用户的签到"""
    from . import db
    from .kuro.sign import sign_one_kuro
    from .tajiduo.sign import sign_one_tajiduo
    from .config import NotifyConfig, ServerChanConfig, TelegramConfig
    from .notify.notify import notify_sign_results

    config = load_config(config_path)
    users = await db.get_all_users()

    for user in users:
        user_id = user["id"]
        username = user["username"]
        logger.info(f"[定时] 签到用户: {username}")

        accounts = await db.get_user_accounts(user_id)
        if not accounts:
            logger.info(f"[定时]   用户 {username} 没有配置账号")
            continue

        user_results = []

        for acc in accounts:
            if acc["platform"] == "kuro":
                if not acc["cookie"] or not acc["uid"]:
                    logger.warning(f"[定时]   跳过库洛账号: 未配置完整")
                    continue

                try:
                    results = await sign_one_kuro(
                        cookie=acc["cookie"],
                        uid=acc["uid"],
                        game=acc["game"],
                        did=acc["did"],
                        bbs_enabled=config.kuro_bbs.enabled,
                    )
                    user_results.append(results)
                    for line in results:
                        logger.info(f"[定时]   {line}")
                except Exception as e:
                    logger.error(f"[定时]   库洛签到异常: {e}")
                    user_results.append([f"[库洛] 签到异常: {e}"])

            elif acc["platform"] == "tajiduo":
                if not acc["refresh_token"] or not acc["center_uid"]:
                    logger.warning(f"[定时]   跳过塔吉多账号: 未配置完整")
                    continue

                try:
                    results = await sign_one_tajiduo(
                        refresh_token=acc["refresh_token"],
                        center_uid=acc["center_uid"],
                        dev_code=acc["dev_code"],
                        config=config,
                    )
                    user_results.append(results)
                    for line in results:
                        logger.info(f"[定时]   {line}")
                except Exception as e:
                    logger.error(f"[定时]   塔吉多签到异常: {e}")
                    user_results.append([f"[塔吉多] 签到异常: {e}"])

        # 发送用户推送通知
        notify_config = await db.get_user_notify(user_id)
        if notify_config and notify_config["enabled"] and user_results:
            try:
                user_notify = NotifyConfig(
                    enabled=True,
                    serverchan=ServerChanConfig(sckey=notify_config["serverchan_sckey"]),
                    telegram=TelegramConfig(bot_token=notify_config["telegram_bot_token"], chat_id=notify_config["telegram_chat_id"]),
                )
                await notify_sign_results(user_notify, user_results)
                logger.info(f"[定时]   推送通知已发送")
            except Exception as e:
                logger.error(f"[定时]   推送通知失败: {e}")

    logger.info("[定时] 全部用户签到完成")


def _scheduler_loop(config_path: str):
    """Run in a background thread. Reads config each loop for hot-reload."""
    logger.info("[定时] 调度器已启动")

    while True:
        try:
            config = load_config(config_path)
        except Exception as e:
            logger.error(f"[定时] 加载配置失败: {e}")
            asyncio.run(asyncio.sleep(60))
            continue

        sched = config.schedule

        if not sched.enabled:
            logger.info("[定时] 定时签到未启用，60秒后重新检查")
            asyncio.run(asyncio.sleep(60))
            continue

        parts = sched.time.split(":")
        hour, minute = int(parts[0]), int(parts[1])

        times = [(hour, minute)]
        if sched.repeat:
            times.extend([
                ((hour + 9) % 24, minute),
                ((hour + 12) % 24, minute),
                ((hour + 13) % 24, minute),
                ((hour + 14) % 24, minute),
            ])

        delay = _get_next_delay(times)
        if delay < 0:
            delay += 86400

        hours = int(delay // 3600)
        minutes = int((delay % 3600) // 60)
        logger.info(f"[定时] 下次签到: {hour:02d}:{minute:02d} ({hours}小时{minutes}分钟后)")

        # Sleep in small increments so we can detect config changes
        slept = 0.0
        while slept < delay:
            chunk = min(30.0, delay - slept)
            asyncio.run(asyncio.sleep(chunk))
            slept += chunk

            # Check if config changed (re-read and compare time)
            try:
                fresh = load_config(config_path)
                fresh_parts = fresh.schedule.time.split(":")
                if int(fresh_parts[0]) != hour or int(fresh_parts[1]) != minute:
                    logger.info("[定时] 检测到配置变更，重新计算时间")
                    break
                if not fresh.schedule.enabled:
                    logger.info("[定时] 定时签到已关闭")
                    break
            except Exception:
                pass
        else:
            # Full sleep completed — time to sign
            logger.info("[定时] 开始执行签到...")
            try:
                from . import db

                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(db.init_db(config.db_path))
                    loop.run_until_complete(_sign_all_users(config_path))
                    logger.info("[定时] 签到完成")
                finally:
                    loop.run_until_complete(db.close_db())
                    loop.close()
            except Exception as e:
                logger.error(f"[定时] 签到异常: {e}")


_scheduler_thread: Optional[threading.Thread] = None


def start_scheduler(config_path: str):
    """Start the background scheduler thread if not already running."""
    global _scheduler_thread
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        return
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop,
        args=(config_path,),
        daemon=True,
        name="sign-scheduler",
    )
    _scheduler_thread.start()
