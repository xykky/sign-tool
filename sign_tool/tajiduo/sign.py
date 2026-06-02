from __future__ import annotations

import random
import asyncio

from ..log import get_logger
from .. import db
from ..config import TajiduoAccount, Config, update_tajiduo_refresh_token
from .laohu import make_device_id
from .api import (
    TajiduoClient,
    TajiduoError,
    TajiduoSession,
    UserTask,
)
from .constants import (
    GAME_ID_YIHUAN,
    GAME_ID_HUANTA,
    TAJIDUO_SIGNIN_COMMUNITY_ID,
    YIHUAN_TASK_COMMUNITY_IDS,
)

logger = get_logger()

TASK_LABELS = {
    "browse_post_c": "浏览帖子",
    "like_post_c": "点赞帖子",
    "share": "分享帖子",
}


def _is_already_signed(error: TajiduoError) -> bool:
    return any(hint in error.message for hint in ("重复", "已签", "已经签到"))


async def _app_sign(client: TajiduoClient, center_uid: str) -> str:
    label = "塔吉多签到"
    if await db.is_signed(center_uid, "app_sign"):
        return f"{label}: 今日已签"

    try:
        if await client.get_community_sign_state(TAJIDUO_SIGNIN_COMMUNITY_ID):
            await db.record_sign(center_uid, "app_sign", {"path": "state_hit"})
            return f"{label}: 今日已签"
        result = await client.app_signin(TAJIDUO_SIGNIN_COMMUNITY_ID)
    except TajiduoError as error:
        if _is_already_signed(error):
            await db.record_sign(center_uid, "app_sign", error.raw)
            return f"{label}: 今日已签"
        logger.warning(f"塔吉多签到失败: {error.message}")
        return f"{label}: 失败 ({error.message})"

    await db.record_sign(center_uid, "app_sign", {"exp": result.exp, "gold": result.gold_coin})
    rewards = []
    if result.exp:
        rewards.append(f"exp+{result.exp}")
    if result.gold_coin:
        rewards.append(f"金币+{result.gold_coin}")
    extra = " ".join(rewards)
    return f"{label}: 成功" + (f" ({extra})" if extra else "")


async def _game_sign(client: TajiduoClient, role_id: str, role_name: str, game_id: str, game_label: str) -> str:
    label = f"{role_name} {game_label}游戏签到"
    record_ref = f"{game_id}:{role_id}"
    if await db.is_signed(record_ref, "game_sign"):
        return f"{label}: 今日已签"

    try:
        data = await client.game_signin(role_id, game_id)
    except TajiduoError as error:
        if _is_already_signed(error):
            await db.record_sign(record_ref, "game_sign", error.raw)
            return f"{label}: 今日已签"
        logger.warning(f"游戏签到失败 role={role_id}: {error.message}")
        return f"{label}: 失败 ({error.message})"

    await db.record_sign(record_ref, "game_sign", data)
    return f"{label}: 成功"


async def _collect_post_ids(client: TajiduoClient, needed: int = 20) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for community_id in YIHUAN_TASK_COMMUNITY_IDS:
        for page in (1, 2):
            try:
                result = await client.list_recommend_posts(community_id, page=page)
            except TajiduoError:
                continue
            for post in result.posts:
                if post.post_id not in seen:
                    seen.add(post.post_id)
                    ids.append(post.post_id)
            if len(ids) >= needed:
                break
    return ids


async def _advance_task(
    client: TajiduoClient,
    task: UserTask,
    post_ids: list[str],
    max_failures: int,
    delay: tuple[float, float],
) -> tuple[int, int]:
    done = 0
    consecutive_fail = 0
    total_fail = 0
    for post_id in post_ids:
        if done >= task.remaining:
            break
        counted = False
        try:
            if task.task_key == "browse_post_c":
                await client.view_post(post_id)
                counted = True
            elif task.task_key == "like_post_c":
                counted = await client.like_post(post_id)
            elif task.task_key == "share":
                await client.share_post(post_id)
                counted = True
        except TajiduoError as error:
            consecutive_fail += 1
            total_fail += 1
            if consecutive_fail >= max_failures:
                logger.warning(f"任务 {task.task_key} 连续失败 {consecutive_fail} 次熔断")
                break
        else:
            if counted:
                done += 1
                consecutive_fail = 0
        await asyncio.sleep(random.uniform(*delay))
    return done, total_fail


async def _daily_tasks(
    client: TajiduoClient,
    center_uid: str,
    enabled_tasks: list[str],
    action_delay: tuple[float, float],
    max_failures: int,
) -> list[str]:
    results = []
    enabled_keys = [k for k in TASK_LABELS if k in enabled_tasks]
    if not enabled_keys:
        return results

    # Check local records first
    local_done: dict[str, bool] = {}
    for key in enabled_keys:
        local_done[key] = await db.is_signed(center_uid, f"task_{key}")

    pending_keys = [k for k in enabled_keys if not local_done[k]]
    if not pending_keys:
        for key in enabled_keys:
            results.append(f"{TASK_LABELS[key]}: 今日已完成")
        return results

    # Fetch remote task list
    try:
        tasks = await client.get_user_tasks()
    except TajiduoError as e:
        results.append(f"社区任务查询: 失败 ({e.message})")
        return results

    tasks_by_key = {t.task_key: t for t in tasks.daily if t.task_key in pending_keys}

    needed = sum(t.remaining for t in tasks_by_key.values() if not t.finished)
    post_ids: list[str] | None = None

    for key in enabled_keys:
        label = TASK_LABELS[key]
        if local_done[key]:
            results.append(f"{label}: 今日已完成")
            continue

        task = tasks_by_key.get(key)
        if task is None:
            results.append(f"{label}: 任务未开放")
            continue

        if task.finished:
            await db.record_sign(center_uid, f"task_{key}", {
                "path": "server_finished",
                "complete_times": task.complete_times,
            })
            results.append(f"{label}: 今日已完成 {task.complete_times}/{task.limit_times}")
            continue

        if post_ids is None:
            post_ids = await _collect_post_ids(client, needed=needed)
        if not post_ids:
            results.append(f"{label}: 暂无可处理帖子")
            continue

        shuffled = random.sample(post_ids, len(post_ids))
        done, failed = await _advance_task(client, task, shuffled, max_failures, action_delay)
        reached = task.complete_times + done
        if reached >= task.limit_times:
            await db.record_sign(center_uid, f"task_{key}", {
                "path": "local_completed",
                "done": done,
                "failed": failed,
            })
            results.append(f"{label}: 成功 {reached}/{task.limit_times}")
        else:
            detail = f"{reached}/{task.limit_times}" + (f" 失败{failed}" if failed else "")
            results.append(f"{label}: 部分成功 {detail}")

    return results


async def sign_one_tajiduo(
    refresh_token: str,
    center_uid: str,
    dev_code: str,
    config: Config,
) -> list[str]:
    """Sign one Tajiduo account. Returns list of status messages."""
    device_id = dev_code or make_device_id()
    client = TajiduoClient(
        device_id=device_id,
        refresh_token=refresh_token,
        center_uid=center_uid,
    )

    results = [f"[塔吉多 {center_uid}]"]

    # Refresh session
    try:
        session = await client.refresh_session()
        # Update refresh_token in config if it changed
        if session.refresh_token != refresh_token:
            update_tajiduo_refresh_token(config.config_path, center_uid, session.refresh_token)
            logger.debug(f"塔吉多 refresh_token 已更新")
    except TajiduoError as e:
        results.append(f"登录已过期，请重新登录 ({e.message})")
        return results

    # App sign
    results.append(await _app_sign(client, center_uid))

    # Game roles - sign for each game
    game_roles: list[tuple[str, str, str, str]] = []  # (role_id, role_name, game_id, game_label)

    for game_id, game_label in [(GAME_ID_YIHUAN, "异环"), (GAME_ID_HUANTA, "幻塔")]:
        try:
            role_list = await client.get_game_roles(game_id)
            for role in role_list.roles:
                if role.role_id and role.role_id != "0":
                    game_roles.append((role.role_id, role.role_name, game_id, game_label))
        except TajiduoError as e:
            logger.debug(f"获取{game_label}角色列表失败: {e.message}")

    for role_id, role_name, game_id, game_label in game_roles:
        results.append(await _game_sign(client, role_id, role_name, game_id, game_label))

    # Daily tasks
    task_config = config.tajiduo_tasks
    if task_config.enabled:
        task_results = await _daily_tasks(
            client, center_uid,
            task_config.enabled,
            task_config.action_delay,
            task_config.max_failures,
        )
        results.extend(task_results)

    return results
