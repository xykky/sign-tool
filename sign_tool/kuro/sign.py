from __future__ import annotations

import random
import asyncio

from ..log import get_logger
from .. import db
from .api import KuroClient, KuroError, CODE_TOKEN_INVALID, CODE_BAT_TOKEN_INVALID
from .constants import PGR_GAME_ID

logger = get_logger()


async def sign_game(client: KuroClient) -> str:
    """Sign in for game. Returns status message."""
    ref_id = client.uid
    if await db.is_signed(ref_id, "game_sign"):
        return "游戏签到: 今日已签"

    try:
        result = await client.sign_in()
        if result.get("already_signed"):
            await db.record_sign(ref_id, "game_sign", {"path": "api_check"})
            return "游戏签到: 今日已签"
        await db.record_sign(ref_id, "game_sign", result)
        return "游戏签到: 成功"
    except KuroError as e:
        if e.code == CODE_TOKEN_INVALID:
            return f"游戏签到: 失败 (登录已过期)"
        logger.warning(f"游戏签到失败 uid={client.uid}: {e.message}")
        return f"游戏签到: 失败 ({e.message})"


async def sign_bbs(client: KuroClient, enabled_tasks: list[str]) -> list[str]:
    """Execute BBS community tasks. Returns list of status messages."""
    results = []
    uid = client.uid

    # BBS sign-in
    if "sign" in enabled_tasks:
        if await db.is_signed(f"kuro_bbs:{uid}", "bbs_sign"):
            results.append("BBS签到: 今日已签")
        else:
            try:
                r = await client.bbs_sign_in()
                if r.get("already_signed"):
                    await db.record_sign(f"kuro_bbs:{uid}", "bbs_sign")
                    results.append("BBS签到: 今日已签")
                else:
                    await db.record_sign(f"kuro_bbs:{uid}", "bbs_sign")
                    results.append("BBS签到: 成功")
            except KuroError as e:
                results.append(f"BBS签到: 失败 ({e.message})")

    # Get task list to check completion
    tasks_to_run = []
    if any(t in enabled_tasks for t in ("detail", "like", "share")):
        try:
            bbs_tasks = await client.get_bbs_tasks()
            for task in bbs_tasks:
                remark = task.get("remark", "")
                complete = task.get("completeTimes", 0)
                needed = task.get("needActionTimes", 1)

                if "浏览" in remark and "detail" in enabled_tasks:
                    if await db.is_signed(f"kuro_bbs:{uid}", "bbs_detail"):
                        results.append("浏览帖子: 今日已完成")
                    elif complete >= needed:
                        await db.record_sign(f"kuro_bbs:{uid}", "bbs_detail")
                        results.append("浏览帖子: 今日已完成")
                    else:
                        tasks_to_run.append(("detail", needed - complete))

                elif "点赞" in remark and "like" in enabled_tasks:
                    if await db.is_signed(f"kuro_bbs:{uid}", "bbs_like"):
                        results.append("点赞帖子: 今日已完成")
                    elif complete >= needed:
                        await db.record_sign(f"kuro_bbs:{uid}", "bbs_like")
                        results.append("点赞帖子: 今日已完成")
                    else:
                        tasks_to_run.append(("like", needed - complete))

                elif "分享" in remark and "share" in enabled_tasks:
                    if await db.is_signed(f"kuro_bbs:{uid}", "bbs_share"):
                        results.append("分享帖子: 今日已完成")
                    elif complete >= needed:
                        await db.record_sign(f"kuro_bbs:{uid}", "bbs_share")
                        results.append("分享帖子: 今日已完成")
                    else:
                        tasks_to_run.append(("share", 1))
        except KuroError as e:
            results.append(f"BBS任务查询: 失败 ({e.message})")
            return results

    # Execute pending tasks
    if tasks_to_run:
        try:
            posts = await client.get_forum_list()
            post_ids = [str(p.get("postId", "")) for p in posts if p.get("postId")]
            random.shuffle(post_ids)
        except KuroError:
            post_ids = []

        for task_type, count in tasks_to_run:
            done = 0
            for post_id in post_ids[:count * 2]:
                if done >= count:
                    break
                try:
                    if task_type == "detail":
                        await client.do_post_detail(post_id)
                        done += 1
                    elif task_type == "like":
                        post_info = next((p for p in posts if str(p.get("postId")) == post_id), {})
                        to_user = str(post_info.get("userId", "0"))
                        await client.do_like(post_id, to_user)
                        done += 1
                    elif task_type == "share":
                        await client.do_share()
                        done += 1
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                except KuroError:
                    continue

            kind = f"bbs_{task_type}"
            if done >= count:
                await db.record_sign(f"kuro_bbs:{uid}", kind)
                label = {"detail": "浏览帖子", "like": "点赞帖子", "share": "分享帖子"}[task_type]
                results.append(f"{label}: 成功 ({done}/{count})")
            else:
                label = {"detail": "浏览帖子", "like": "点赞帖子", "share": "分享帖子"}[task_type]
                results.append(f"{label}: 部分成功 ({done}/{count})")

    return results


async def sign_one_kuro(cookie: str, uid: str, game: str, did: str, bbs_enabled: list[str]) -> list[str]:
    """Sign one Kuro account. Returns list of status messages."""
    game_id = 3 if game == "waves" else 2
    client = KuroClient(cookie=cookie, uid=uid, game_id=game_id, did=did)

    results = [f"[库洛 {uid} ({game})]"]

    # Validate login (matching RoverSign: handle BAT token invalid)
    print(f"[DEBUG][sign] uid={uid} game={game} did={did}", flush=True)
    logger.info(f"[sign] uid={uid} game={game} did={did}")
    try:
        login_ok = await client.validate_login()
        print(f"[DEBUG][sign] validate_login result: {login_ok}", flush=True)
        logger.info(f"[sign] validate_login result: {login_ok}")
        if not login_ok:
            # Could be token expired or BAT invalid — try BAT refresh first
            try:
                logger.info(f"[sign] validate_login failed, trying BAT refresh...")
                await client.refresh_bat_token()
                logger.info(f"[sign] BAT refresh done, retrying validate_login...")
                if not await client.validate_login():
                    results.append("登录已过期，请重新登录")
                    return results
            except KuroError as bat_e:
                logger.error(f"[sign] BAT refresh failed: {bat_e.message}")
                results.append("登录已过期，请重新登录")
                return results
    except KuroError as e:
        results.append(f"验证登录失败: {e.message}")
        return results

    # Get role list to find the correct serverId
    try:
        roles = await client.find_role_list()
        print(f"[DEBUG][sign] find_role_list returned {len(roles)} roles", flush=True)
        logger.info(f"[sign] find_role_list returned {len(roles)} roles")
        for role in roles:
            rid = str(role.get("roleId", ""))
            sid = str(role.get("serverId", ""))
            rname = str(role.get("roleName", ""))
            print(f"[DEBUG][sign]   role: roleId={rid}, serverId={sid}, roleName={rname}", flush=True)
            logger.info(f"[sign]   role: roleId={rid}, serverId={sid}, roleName={rname}")
            if rid == uid:
                client.server_id = sid
                print(f"[DEBUG][sign] matched role! server_id set to: {sid}", flush=True)
                logger.info(f"[sign] matched role! server_id set to: {sid}")
                break
        if not client.server_id:
            print(f"[DEBUG][sign] no matching role found for uid={uid}, using default serverId", flush=True)
            logger.warning(f"[sign] no matching role found for uid={uid}, using default serverId")
    except KuroError as e:
        print(f"[DEBUG][sign] find_role_list failed: {e.message}", flush=True)
        logger.error(f"[sign] find_role_list failed: {e.message}")

    # Refresh data (and bat token if needed) — PGR 没有 aki refresh 接口，跳过
    if game_id != PGR_GAME_ID:
        try:
            logger.info(f"[sign] calling refresh_data...")
            await client.refresh_data()
            logger.info(f"[sign] refresh_data success")
        except KuroError as e:
            logger.error(f"[sign] refresh_data failed: code={e.code}, msg={e.message}")
            if "BAT" in e.message or e.code == CODE_BAT_TOKEN_INVALID:
                try:
                    logger.info(f"[sign] trying BAT refresh + retry refresh_data...")
                    await client.refresh_bat_token()
                    await client.refresh_data()
                    logger.info(f"[sign] refresh_data retry success")
                except KuroError as e2:
                    logger.error(f"[sign] refresh_data retry failed: {e2.message}")
                    results.append(f"刷新数据失败: {e2.message}")
                    return results
            else:
                results.append(f"刷新数据失败: {e.message}")
                return results

    # Game sign
    results.append(await sign_game(client))

    # BBS tasks
    if bbs_enabled:
        bbs_results = await sign_bbs(client, bbs_enabled)
        results.extend(bbs_results)

    return results
