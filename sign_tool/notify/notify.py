from __future__ import annotations

from typing import List

from ..log import get_logger
from ..config import NotifyConfig
from .serverchan import send_serverchan
from .telegram import send_telegram

logger = get_logger()


def format_sign_results(results: List) -> str:
    """Format sign results into a readable message.
    
    Args:
        results: List of sign results (lists of strings or exceptions)
    
    Returns:
        Formatted message string
    """
    lines = []
    for result in results:
        if isinstance(result, Exception):
            lines.append(f"异常: {result}")
        elif isinstance(result, list):
            for line in result:
                lines.append(line)
        lines.append("---")
    
    # Remove trailing separator
    if lines and lines[-1] == "---":
        lines.pop()
    
    return "\n".join(lines)


def format_sign_title(results: List) -> str:
    """Generate a summary title from sign results.
    
    Args:
        results: List of sign results
    
    Returns:
        Summary title string
    """
    total = 0
    success = 0
    failed = 0
    
    for result in results:
        if isinstance(result, list):
            for line in result:
                if line.startswith("["):
                    total += 1
                elif "成功" in line or "已签" in line or "已完成" in line:
                    success += 1
                elif "失败" in line or "异常" in line:
                    failed += 1
    
    if failed > 0:
        return f"签到完成: {success}成功, {failed}失败"
    elif success > 0:
        return f"签到完成: 全部成功 ({success})"
    else:
        return "签到完成"


async def send_notification(config: NotifyConfig, title: str, content: str) -> bool:
    """Send notification to all configured services.
    
    Args:
        config: NotifyConfig with service configurations
        title: Message title
        content: Message content
    
    Returns:
        True if at least one service sent successfully
    """
    if not config.enabled:
        return False

    results = []

    # Server酱
    if config.serverchan.sckey:
        ok = await send_serverchan(config.serverchan.sckey, title, content)
        results.append(ok)

    # Telegram
    if config.telegram.bot_token and config.telegram.chat_id:
        ok = await send_telegram(config.telegram.bot_token, config.telegram.chat_id, content)
        results.append(ok)

    if not results:
        logger.debug("未配置任何推送服务")
        return False

    return any(results)


async def notify_sign_results(config: NotifyConfig, results: List) -> None:
    """Send sign results notification.
    
    Args:
        config: NotifyConfig
        results: List of sign results
    """
    if not config.enabled:
        return

    title = format_sign_title(results)
    content = format_sign_results(results)
    
    await send_notification(config, title, content)
