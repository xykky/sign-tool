from __future__ import annotations

import httpx
from ..log import get_logger

logger = get_logger()

SERVERCHAN_API = "https://sctapi.ftqq.com"


async def send_serverchan(sckey: str, title: str, content: str) -> bool:
    """Send notification via Server酱 (ServerChan).
    
    Args:
        sckey: Server酱 SCKEY
        title: Message title (max 256 chars)
        content: Message content (markdown supported)
    
    Returns:
        True if sent successfully
    """
    if not sckey:
        logger.warning("Server酱 SCKEY 未配置")
        return False

    url = f"{SERVERCHAN_API}/{sckey}.send"
    data = {
        "title": title[:256],
        "desp": content,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, data=data)
            result = resp.json()
            if result.get("code") == 0:
                logger.info("Server酱推送成功")
                return True
            else:
                logger.warning(f"Server酱推送失败: {result.get('message', '未知错误')}")
                return False
    except Exception as e:
        logger.error(f"Server酱推送异常: {e}")
        return False
