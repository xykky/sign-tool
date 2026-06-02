from __future__ import annotations

import uuid

from ..log import get_logger
from ..config import KuroAccount, Config, save_kuro_account
from .api import KuroClient, KuroError

logger = get_logger()


async def login_kuro(mobile: str, code: str, game: str, config: Config) -> KuroAccount:
    """Login via SMS and return a KuroAccount."""
    game_id = 3 if game == "waves" else 2
    did = f"CLI-{uuid.uuid4().hex[:8].upper()}"

    client = KuroClient(cookie="", uid="", game_id=game_id, did=did)
    result = await client.login(mobile, code)

    token = result.get("token", "")
    if not token:
        raise KuroError("登录成功但未返回 token")

    # Now get the role list to find uid
    client.cookie = token
    roles = await client.find_role_list()

    uid = ""
    if roles:
        # Use the first role
        uid = str(roles[0].get("roleId", ""))
        if not uid:
            raise KuroError("获取角色列表成功但未找到 roleId")

    account = KuroAccount(cookie=token, uid=uid, game=game, did=did)
    save_kuro_account(config.config_path, account)
    logger.info(f"库洛登录成功: uid={uid} game={game}")
    return account
