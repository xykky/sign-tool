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

    client.cookie = token
    roles = await client.find_role_list()

    if not roles:
        raise KuroError(f"获取角色列表为空，请先在游戏中创建角色 (game={game}, gameId={game_id})")

    # Find the best matching role
    # Prefer a role with a non-empty roleId
    uid = ""
    selected_role = None
    for role in roles:
        rid = str(role.get("roleId", ""))
        if rid:
            uid = rid
            selected_role = role
            break

    if not uid:
        raise KuroError(f"角色列表中未找到 roleId，返回数据: {roles}")

    server_id = str(selected_role.get("serverId", "")) if selected_role else ""
    role_name = str(selected_role.get("roleName", "")) if selected_role else ""

    account = KuroAccount(cookie=token, uid=uid, game=game, did=did)
    save_kuro_account(config.config_path, account)
    logger.info(f"库洛登录成功: uid={uid} game={game} server={server_id} role={role_name} (共{len(roles)}个角色)")
    return account
