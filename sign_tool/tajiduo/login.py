from __future__ import annotations

from ..log import get_logger
from ..config import TajiduoAccount, Config, save_tajiduo_account
from .laohu import LaohuClient, LaohuDevice
from .api import TajiduoClient, TajiduoError

logger = get_logger()


async def login_tajiduo(mobile: str, code: str, config: Config) -> TajiduoAccount:
    """Login via SMS and return a TajiduoAccount."""
    device = LaohuDevice()
    laohu = LaohuClient(device=device)

    # Step 1: Laohu SMS login
    laohu_account = await laohu.login_by_sms(mobile, code)
    logger.info(f"老虎登录成功: userId={laohu_account.user_id}")

    # Step 2: Exchange for Tajiduo session
    client = TajiduoClient(device_id=device.device_id)
    session = await client.user_center_login(
        laohu_token=laohu_account.token,
        laohu_user_id=str(laohu_account.user_id),
    )
    logger.info(f"塔吉多登录成功: center_uid={session.center_uid}")

    # Get game roles
    for game_id, game_name in [("1289", "异环"), ("1256", "幻塔")]:
        try:
            roles = await client.get_game_roles(game_id)
            if roles.roles:
                names = ", ".join(r.role_name for r in roles.roles if r.role_name)
                logger.info(f"  {game_name}角色: {names or '(无名)'}")
        except TajiduoError:
            pass

    account = TajiduoAccount(
        refresh_token=session.refresh_token,
        center_uid=session.center_uid,
        dev_code=device.device_id,
    )
    save_tajiduo_account(config.config_path, account)
    logger.info(f"塔吉多账号已保存到配置文件")
    return account
