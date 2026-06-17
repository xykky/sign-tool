"""Background scheduler for automatic sign-in (per-user schedule)."""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

from .log import get_logger
from .config import load_config

logger = get_logger()

# UTC+8 北京时间
_CN_TZ = timezone(timedelta(hours=8))


def _now_cn() -> datetime:
    return datetime.now(_CN_TZ)


def _parse_hm(time_str: str) -> tuple[int, int]:
    parts = time_str.split(":")
    return int(parts[0]), int(parts[1])


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


async def _sign_users(config_path: str, user_ids: list[int]):
    """执行指定用户的签到"""
    from . import db
    from .kuro.sign import sign_one_kuro
    from .tajiduo.sign import sign_one_tajiduo
    from .config import NotifyConfig, ServerChanConfig, TelegramConfig
    from .notify.notify import notify_sign_results

    config = load_config(config_path)

    for user_id in user_ids:
        user = await db.get_user_by_id(user_id)
        if not user:
            continue
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


def _scheduler_loop(config_path: str):
    """Run in a background thread. Uses its own DB connection per iteration."""
    from . import db

    logger.info("[定时] 调度器已启动")

    async def _read_schedules():
        """用独立连接读取定时配置"""
        import aiosqlite
        config = load_config(config_path)
        conn = await aiosqlite.connect(config.db_path)
        try:
            await conn.executescript(db._CREATE_SQL)
            await conn.commit()
            async with conn.execute(
                "SELECT id, username, schedule_enabled, schedule_time FROM users ORDER BY id",
            ) as cur:
                rows = await cur.fetchall()
                return [
                    {"user_id": r[0], "username": r[1], "enabled": bool(r[2]), "time": r[3] or "06:00"}
                    for r in rows
                ]
        finally:
            await conn.close()

    while True:
        # 读取所有用户的定时配置
        try:
            schedules = asyncio.run(_read_schedules())
        except Exception as e:
            logger.error(f"[定时] 读取用户定时配置失败: {e}")
            asyncio.run(asyncio.sleep(60))
            continue

        # 按时间分组已启用的用户
        time_users: dict[tuple[int, int], list[int]] = defaultdict(list)
        for s in schedules:
            if s["enabled"]:
                hm = _parse_hm(s["time"])
                time_users[hm].append(s["user_id"])

        if not time_users:
            logger.info("[定时] 没有用户启用定时签到，60秒后重新检查")
            asyncio.run(asyncio.sleep(60))
            continue

        # 计算所有启用的时间点
        all_times = list(time_users.keys())
        delay = _get_next_delay(all_times)
        if delay < 0:
            delay += 86400

        # 找到即将执行的时间点
        now = _now_cn()
        current_hm = (now.hour, now.minute)
        target_time = None
        for h, m in sorted(all_times):
            if (h, m) > current_hm:
                target_time = (h, m)
                break
        if target_time is None:
            target_time = sorted(all_times)[0]

        hours = int(delay // 3600)
        minutes = int((delay % 3600) // 60)
        logger.info(f"[定时] 下次签到: {target_time[0]:02d}:{target_time[1]:02d} ({hours}小时{minutes}分钟后)")

        # Sleep in small increments so we can detect schedule changes
        slept = 0.0
        schedule_changed = False
        while slept < delay:
            chunk = min(30.0, delay - slept)
            asyncio.run(asyncio.sleep(chunk))
            slept += chunk

            # Check if schedules changed (re-read and compare)
            try:
                fresh_schedules = asyncio.run(_read_schedules())

                fresh_time_users: dict[tuple[int, int], list[int]] = defaultdict(list)
                for s in fresh_schedules:
                    if s["enabled"]:
                        hm = _parse_hm(s["time"])
                        fresh_time_users[hm].append(s["user_id"])

                if fresh_time_users != time_users:
                    logger.info("[定时] 检测到定时配置变更，重新计算时间")
                    schedule_changed = True
                    break
            except Exception:
                pass

        if schedule_changed:
            continue

        # Full sleep completed — time to sign
        logger.info("[定时] 开始执行签到...")
        try:
            user_ids = time_users.get(target_time, [])
            if user_ids:
                async def _run_sign():
                    from . import db
                    config = load_config(config_path)
                    await db.init_db(config.db_path)
                    await _sign_users(config_path, user_ids)
                asyncio.run(_run_sign())
            logger.info("[定时] 签到完成")
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
