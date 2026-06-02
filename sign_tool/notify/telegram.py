from __future__ import annotations

import httpx
from ..log import get_logger

logger = get_logger()

TELEGRAM_API = "https://api.telegram.org"


async def send_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    """Send notification via Telegram Bot.
    
    Args:
        bot_token: Telegram Bot Token
        chat_id: Telegram Chat ID
        text: Message text (supports HTML parse_mode)
    
    Returns:
        True if sent successfully
    """
    if not bot_token or not chat_id:
        logger.warning("Telegram Bot Token 或 Chat ID 未配置")
        return False

    url = f"{TELEGRAM_API}/bot{bot_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=data)
            result = resp.json()
            if result.get("ok"):
                logger.info("Telegram推送成功")
                return True
            else:
                logger.warning(f"Telegram推送失败: {result.get('description', '未知错误')}")
                return False
    except Exception as e:
        logger.error(f"Telegram推送异常: {e}")
        return False
