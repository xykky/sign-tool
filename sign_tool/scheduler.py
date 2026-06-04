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
                    from .runner import run_all
                    loop.run_until_complete(run_all(config, platform=None))
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
