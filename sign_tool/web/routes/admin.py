from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from ... import db
from ...auth import get_admin_user
from ...config import load_config

router = APIRouter(prefix="/api/admin", tags=["管理员"])


class ScheduleUpdateRequest(BaseModel):
    enabled: bool
    time: str


class BatchScheduleRequest(BaseModel):
    enabled: bool
    time: str


class NotifyUpdateRequest(BaseModel):
    enabled: bool
    serverchan_sckey: Optional[str] = ""
    telegram_bot_token: Optional[str] = ""
    telegram_chat_id: Optional[str] = ""


@router.get("/users")
async def get_users(current_user: dict = Depends(get_admin_user)):
    """获取所有用户"""
    users = await db.get_all_users()
    return users


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, current_user: dict = Depends(get_admin_user)):
    """删除用户"""
    if user_id == current_user["id"]:
        return JSONResponse({"ok": False, "msg": "不能删除自己"})

    user = await db.get_user_by_id(user_id)
    if not user:
        return JSONResponse({"ok": False, "msg": "用户不存在"})

    await db.delete_user(user_id)
    return {"ok": True, "msg": "用户已删除"}


@router.get("/users/{user_id}/accounts")
async def get_user_accounts(user_id: int, current_user: dict = Depends(get_admin_user)):
    """获取指定用户的账号"""
    user = await db.get_user_by_id(user_id)
    if not user:
        return JSONResponse({"ok": False, "msg": "用户不存在"})

    accounts = await db.get_user_accounts(user_id)
    result = []
    for acc in accounts:
        if acc["platform"] == "kuro":
            masked_cookie = acc["cookie"][:8] + "..." if len(acc["cookie"]) > 8 else acc["cookie"]
            result.append({
                "id": acc["id"],
                "platform": "kuro",
                "uid": acc["uid"],
                "game": acc["game"],
                "game_label": "鸣潮" if acc["game"] == "waves" else "战双",
                "cookie_preview": masked_cookie,
            })
        else:
            result.append({
                "id": acc["id"],
                "platform": "tajiduo",
                "center_uid": acc["center_uid"],
                "dev_code": acc["dev_code"][:8] + "..." if acc["dev_code"] else "",
            })
    return result


@router.delete("/users/{user_id}/accounts/{account_id}")
async def delete_user_account(user_id: int, account_id: int, current_user: dict = Depends(get_admin_user)):
    """删除指定用户的账号"""
    account = await db.get_user_account_by_id(account_id)
    if not account:
        return JSONResponse({"ok": False, "msg": "账号不存在"})
    if account["user_id"] != user_id:
        return JSONResponse({"ok": False, "msg": "账号不属于该用户"})

    await db.delete_user_account(account_id)
    return {"ok": True, "msg": "账号已删除"}


@router.get("/users/{user_id}/notify")
async def get_user_notify(user_id: int, current_user: dict = Depends(get_admin_user)):
    """获取指定用户的推送配置"""
    user = await db.get_user_by_id(user_id)
    if not user:
        return JSONResponse({"ok": False, "msg": "用户不存在"})

    notify = await db.get_user_notify(user_id)
    if not notify:
        return {"enabled": False, "serverchan_sckey": "", "telegram_bot_token": "", "telegram_chat_id": ""}
    return notify


@router.put("/users/{user_id}/notify")
async def update_user_notify(user_id: int, req: NotifyUpdateRequest, current_user: dict = Depends(get_admin_user)):
    """更新指定用户的推送配置"""
    user = await db.get_user_by_id(user_id)
    if not user:
        return JSONResponse({"ok": False, "msg": "用户不存在"})

    notify_data = {
        "enabled": req.enabled,
        "serverchan_sckey": req.serverchan_sckey or "",
        "telegram_bot_token": req.telegram_bot_token or "",
        "telegram_chat_id": req.telegram_chat_id or "",
    }
    await db.update_user_notify(user_id, notify_data)
    return {"ok": True, "msg": f"已更新 {user['username']} 的推送配置"}


@router.get("/accounts")
async def get_all_accounts(current_user: dict = Depends(get_admin_user)):
    """获取所有用户的账号"""
    accounts = await db.get_all_accounts()
    result = []
    for acc in accounts:
        if acc["platform"] == "kuro":
            masked_cookie = acc["cookie"][:8] + "..." if len(acc["cookie"]) > 8 else acc["cookie"]
            result.append({
                "id": acc["id"],
                "user_id": acc["user_id"],
                "username": acc["username"],
                "platform": "kuro",
                "uid": acc["uid"],
                "game": acc["game"],
                "game_label": "鸣潮" if acc["game"] == "waves" else "战双",
                "cookie_preview": masked_cookie,
            })
        else:
            result.append({
                "id": acc["id"],
                "user_id": acc["user_id"],
                "username": acc["username"],
                "platform": "tajiduo",
                "center_uid": acc["center_uid"],
                "dev_code": acc["dev_code"][:8] + "..." if acc["dev_code"] else "",
            })
    return result


@router.post("/sign")
async def sign_all(current_user: dict = Depends(get_admin_user)):
    """执行所有用户的签到（SSE）"""

    async def event_stream():
        from ...kuro.sign import sign_one_kuro
        from ...tajiduo.sign import sign_one_tajiduo
        from ...config import NotifyConfig, ServerChanConfig, TelegramConfig

        users = await db.get_all_users()
        config = load_config("config.toml")

        for user in users:
            user_id = user["id"]
            username = user["username"]
            yield f"data: {json.dumps({'msg': f'===== 用户: {username} =====', 'type': 'progress'})}\n\n"

            accounts = await db.get_user_accounts(user_id)
            if not accounts:
                yield f"data: {json.dumps({'msg': '  没有配置账号', 'type': 'skip'})}\n\n"
                continue

            user_results = []
            for acc in accounts:
                if acc["platform"] == "kuro":
                    if not acc["cookie"] or not acc["uid"]:
                        yield f"data: {json.dumps({'msg': '  跳过库洛账号: 未配置完整', 'type': 'skip'})}\n\n"
                        continue

                    yield f"data: {json.dumps({'msg': '  签到中: 库洛 ' + acc['uid'] + ' (' + acc['game'] + ')', 'type': 'progress'})}\n\n"
                    try:
                        results = await sign_one_kuro(
                            cookie=acc["cookie"],
                            uid=acc["uid"],
                            game=acc["game"],
                            did=acc["did"],
                            bbs_enabled=config.kuro_bbs.enabled,
                        )
                        user_results.append(results)
                        for line in results:
                            yield f"data: {json.dumps({'msg': f'  {line}', 'type': 'result'})}\n\n"
                    except Exception as e:
                        err_msg = f"  签到异常: {e}"
                        user_results.append([f"[库洛] {err_msg}"])
                        yield f"data: {json.dumps({'msg': err_msg, 'type': 'error'})}\n\n"

                elif acc["platform"] == "tajiduo":
                    if not acc["refresh_token"] or not acc["center_uid"]:
                        yield f"data: {json.dumps({'msg': '  跳过塔吉多账号: 未配置完整', 'type': 'skip'})}\n\n"
                        continue

                    yield f"data: {json.dumps({'msg': '  签到中: 塔吉多 ' + acc['center_uid'], 'type': 'progress'})}\n\n"
                    try:
                        results = await sign_one_tajiduo(
                            refresh_token=acc["refresh_token"],
                            center_uid=acc["center_uid"],
                            dev_code=acc["dev_code"],
                            config=config,
                            user_id=user_id,
                            access_token=acc.get("access_token", ""),
                            access_token_updated_at=acc.get("access_token_updated_at", ""),
                        )
                        user_results.append(results)
                        for line in results:
                            yield f"data: {json.dumps({'msg': f'  {line}', 'type': 'result'})}\n\n"
                    except Exception as e:
                        err_msg = f"  签到异常: {e}"
                        user_results.append([f"[塔吉多] {err_msg}"])
                        yield f"data: {json.dumps({'msg': err_msg, 'type': 'error'})}\n\n"

            # 发送用户推送通知
            notify_config = await db.get_user_notify(user_id)
            if notify_config and notify_config["enabled"] and user_results:
                try:
                    from ...notify.notify import notify_sign_results
                    user_notify = NotifyConfig(
                        enabled=True,
                        serverchan=ServerChanConfig(sckey=notify_config["serverchan_sckey"]),
                        telegram=TelegramConfig(bot_token=notify_config["telegram_bot_token"], chat_id=notify_config["telegram_chat_id"]),
                    )
                    await notify_sign_results(user_notify, user_results)
                    yield f"data: {json.dumps({'msg': f'  推送通知已发送', 'type': 'result'})}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'msg': f'  推送通知失败: {e}', 'type': 'error'})}\n\n"

        yield f"data: {json.dumps({'msg': '全部签到完成', 'type': 'done', 'done': True})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/status")
async def get_all_status(date: Optional[str] = None, current_user: dict = Depends(get_admin_user)):
    """查看所有用户的签到状态"""
    d = date or db._today_cn()

    users = await db.get_all_users()
    result = {}

    for user in users:
        records = await db.get_today_records(d, user_id=user["id"])
        grouped = {}
        for r in records:
            ref = r["ref_id"]
            if ref not in grouped:
                grouped[ref] = []
            grouped[ref].append({"kind": r["kind"], "payload": r["payload"]})
        result[user["username"]] = {"user_id": user["id"], "records": grouped}

    return {"date": d, "users": result}


# ========== 定时管理 ==========

@router.get("/schedules")
async def get_all_schedules(current_user: dict = Depends(get_admin_user)):
    """获取所有用户的定时配置"""
    schedules = await db.get_all_schedules()
    return schedules


@router.put("/schedules/{user_id}")
async def update_user_schedule(user_id: int, req: ScheduleUpdateRequest, current_user: dict = Depends(get_admin_user)):
    """更新指定用户的定时配置"""
    user = await db.get_user_by_id(user_id)
    if not user:
        return JSONResponse({"ok": False, "msg": "用户不存在"})

    await db.update_user_schedule(user_id, req.enabled, req.time)
    return {"ok": True, "msg": f"已更新 {user['username']} 的定时配置"}


@router.post("/schedules/batch")
async def batch_update_schedules(req: BatchScheduleRequest, current_user: dict = Depends(get_admin_user)):
    """批量更新所有用户的定时配置"""
    updated = await db.update_all_schedules(req.enabled, req.time)
    return {"ok": True, "msg": f"已更新 {updated} 个用户的定时配置"}
