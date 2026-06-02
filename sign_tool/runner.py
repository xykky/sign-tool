from __future__ import annotations

import asyncio
import random
from typing import List, Tuple, Optional

from .log import get_logger
from .config import Config
from .kuro.sign import sign_one_kuro
from .tajiduo.sign import sign_one_tajiduo

logger = get_logger()


async def run_all(config: Config, platform: Optional[str] = None) -> None:
    """Run signing for all configured accounts (prints to stdout)."""
    results = await run_all_return(config, platform)
    print()
    print("=" * 50)
    print("签到结果")
    print("=" * 50)
    for result in results:
        if isinstance(result, Exception):
            print(f"异常: {result}")
        elif isinstance(result, list):
            for line in result:
                print(line)
        print("-" * 50)


async def run_all_return(config: Config, platform: Optional[str] = None) -> List:
    """Run signing for all configured accounts. Returns list of results."""
    tasks = []

    if platform != "tajiduo":
        for acc in config.kuro_accounts:
            if not acc.cookie or not acc.uid:
                logger.warning(f"跳过库洛账号: cookie 或 uid 为空")
                continue
            tasks.append(("kuro", acc))

    if platform != "kuro":
        for acc in config.tajiduo_accounts:
            if not acc.refresh_token or not acc.center_uid:
                logger.warning(f"跳过塔吉多账号: refresh_token 或 center_uid 为空")
                continue
            tasks.append(("tajiduo", acc))

    if not tasks:
        logger.warning("没有可执行的签到任务，请先登录或检查配置文件")
        return []

    logger.info(f"开始签到: 共 {len(tasks)} 个账号")
    semaphore = asyncio.Semaphore(config.concurrency)

    async def _process_one(platform_type: str, account):
        async with semaphore:
            await asyncio.sleep(random.uniform(*config.delay))
            try:
                if platform_type == "kuro":
                    return await sign_one_kuro(
                        cookie=account.cookie,
                        uid=account.uid,
                        game=account.game,
                        did=account.did,
                        bbs_enabled=config.kuro_bbs.enabled,
                    )
                else:
                    return await sign_one_tajiduo(
                        refresh_token=account.refresh_token,
                        center_uid=account.center_uid,
                        dev_code=account.dev_code,
                        config=config,
                    )
            except Exception as e:
                logger.error(f"签到异常 [{platform_type}]: {e}")
                return [f"[{platform_type}] 签到异常: {e}"]

    results = await asyncio.gather(
        *(_process_one(p, a) for p, a in tasks),
        return_exceptions=True,
    )
    return results


async def run_all_with_notify(config: Config, platform: Optional[str] = None) -> List:
    """Run signing and send notification if configured."""
    results = await run_all_return(config, platform)
    
    # Send notification
    if config.notify.enabled and results:
        try:
            from .notify.notify import notify_sign_results
            await notify_sign_results(config.notify, results)
        except Exception as e:
            logger.warning(f"推送通知失败: {e}")
    
    return results
