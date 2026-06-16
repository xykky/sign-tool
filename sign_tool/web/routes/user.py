from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from ... import db
from ...auth import get_current_user
from ...config import load_config

router = APIRouter(prefix="/api/my", tags=["用户"])


class AddAccountRequest(BaseModel):
    platform: str
    # 库洛
    cookie: Optional[str] = None
    uid: Optional[str] = None
    game: Optional[str] = "waves"
    did: Optional[str] = None
    # 塔吉多
    refresh_token: Optional[str] = None
    center_uid: Optional[str] = None
    dev_code: Optional[str] = None


class LoginRequest(BaseModel):
    platform: str
    phone: str
    code: str
    game: Optional[str] = "waves"


class NotifyRequest(BaseModel):
    enabled: bool = False
    serverchan_sckey: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None


class ScheduleRequest(BaseModel):
    enabled: bool
    time: str


# ========== 账号管理 ==========

@router.post("/login")
async def login_and_add_account(req: LoginRequest, current_user: dict = Depends(get_current_user)):
    """登录并添加账号到当前用户"""
    if req.platform not in ("kuro", "tajiduo"):
        return JSONResponse({"ok": False, "msg": f"不支持的平台: {req.platform}"})

    config = load_config("config.toml")

    try:
        if req.platform == "kuro":
            from ...kuro.login import login_kuro
            from ...config import KuroAccount

            # 临时修改 login_kuro 使其不保存到配置文件
            # 直接调用底层逻辑
            import uuid
            from ...kuro.api import KuroClient

            game_id = 3 if req.game == "waves" else 2
            did = f"CLI-{uuid.uuid4().hex[:8].upper()}"

            client = KuroClient(cookie="", uid="", game_id=game_id, did=did)
            result = await client.login(req.phone, req.code)

            token = result.get("token", "")
            if not token:
                return JSONResponse({"ok": False, "msg": "登录成功但未返回 token"})

            client.cookie = token
            roles = await client.find_role_list()

            if not roles:
                return JSONResponse({"ok": False, "msg": "获取角色列表为空，请先在游戏中创建角色"})

            uid = ""
            selected_role = None
            for role in roles:
                rid = str(role.get("roleId", ""))
                if rid:
                    uid = rid
                    selected_role = role
                    break

            if not uid:
                return JSONResponse({"ok": False, "msg": "角色列表中未找到 roleId"})

            # 保存到用户账号
            account_data = {"cookie": token, "uid": uid, "game": req.game or "waves", "did": did}
            account_id = await db.add_user_account(current_user["id"], "kuro", account_data)

            return {"ok": True, "msg": "登录成功", "id": account_id, "uid": uid, "game": req.game}

        elif req.platform == "tajiduo":
            from ...tajiduo.laohu import LaohuClient, LaohuDevice
            from ...tajiduo.api import TajiduoClient

            device = LaohuDevice()
            laohu = LaohuClient(device=device)

            # Step 1: 老虎 SMS 登录
            laohu_account = await laohu.login_by_sms(req.phone, req.code)

            # Step 2: 换取塔吉多 session
            client = TajiduoClient(device_id=device.device_id)
            session = await client.user_center_login(
                laohu_token=laohu_account.token,
                laohu_user_id=str(laohu_account.user_id),
            )

            # 保存到用户账号
            account_data = {
                "refresh_token": session.refresh_token,
                "center_uid": session.center_uid,
                "dev_code": device.device_id,
            }
            account_id = await db.add_user_account(current_user["id"], "tajiduo", account_data)

            return {"ok": True, "msg": "登录成功", "id": account_id, "center_uid": session.center_uid}

    except Exception as e:
        return {"ok": False, "msg": f"登录失败: {e}"}


@router.get("/accounts")
async def get_accounts(current_user: dict = Depends(get_current_user)):
    """获取当前用户的账号列表"""
    accounts = await db.get_user_accounts(current_user["id"])
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


@router.post("/accounts")
async def add_account(req: AddAccountRequest, current_user: dict = Depends(get_current_user)):
    """添加账号"""
    if req.platform not in ("kuro", "tajiduo"):
        return JSONResponse({"ok": False, "msg": f"不支持的平台: {req.platform}"})

    if req.platform == "kuro":
        if not req.cookie or not req.uid:
            return JSONResponse({"ok": False, "msg": "库洛账号需要 cookie 和 uid"})
        account_data = {"cookie": req.cookie, "uid": req.uid, "game": req.game or "waves", "did": req.did or ""}
    else:
        if not req.refresh_token or not req.center_uid:
            return JSONResponse({"ok": False, "msg": "塔吉多账号需要 refresh_token 和 center_uid"})
        account_data = {"refresh_token": req.refresh_token, "center_uid": req.center_uid, "dev_code": req.dev_code or ""}

    account_id = await db.add_user_account(current_user["id"], req.platform, account_data)
    return {"ok": True, "msg": "账号添加成功", "id": account_id}


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: int, current_user: dict = Depends(get_current_user)):
    """删除账号"""
    account = await db.get_user_account_by_id(account_id)
    if not account:
        return JSONResponse({"ok": False, "msg": "账号不存在"})
    if account["user_id"] != current_user["id"]:
        return JSONResponse({"ok": False, "msg": "无权删除此账号"})

    await db.delete_user_account(account_id)
    return {"ok": True, "msg": "账号已删除"}


# ========== 推送配置 ==========

@router.get("/notify")
async def get_notify(current_user: dict = Depends(get_current_user)):
    """获取推送配置"""
    notify = await db.get_user_notify(current_user["id"])
    if not notify:
        return {"enabled": False, "serverchan_sckey": "", "telegram_bot_token": "", "telegram_chat_id": ""}

    # 脱敏显示
    sckey = notify["serverchan_sckey"]
    bot_token = notify["telegram_bot_token"]
    return {
        "enabled": notify["enabled"],
        "serverchan_sckey": sckey[:8] + "..." if len(sckey) > 8 else sckey,
        "telegram_bot_token": bot_token[:8] + "..." if len(bot_token) > 8 else bot_token,
        "telegram_chat_id": notify["telegram_chat_id"],
    }


@router.post("/notify")
async def update_notify(req: NotifyRequest, current_user: dict = Depends(get_current_user)):
    """更新推送配置"""
    # 获取现有配置，保留未提供的字段
    existing = await db.get_user_notify(current_user["id"]) or {}

    notify_data = {
        "enabled": req.enabled,
        "serverchan_sckey": req.serverchan_sckey if req.serverchan_sckey is not None else existing.get("serverchan_sckey", ""),
        "telegram_bot_token": req.telegram_bot_token if req.telegram_bot_token is not None else existing.get("telegram_bot_token", ""),
        "telegram_chat_id": req.telegram_chat_id if req.telegram_chat_id is not None else existing.get("telegram_chat_id", ""),
    }

    await db.update_user_notify(current_user["id"], notify_data)
    return {"ok": True, "msg": "推送配置已保存"}


@router.post("/notify/test")
async def test_notify(current_user: dict = Depends(get_current_user)):
    """测试推送"""
    notify = await db.get_user_notify(current_user["id"])
    if not notify or not notify["enabled"]:
        return JSONResponse({"ok": False, "msg": "推送未启用"})

    try:
        from ...notify.notify import send_notification
        from ...config import NotifyConfig, ServerChanConfig, TelegramConfig

        config = NotifyConfig(
            enabled=True,
            serverchan=ServerChanConfig(sckey=notify["serverchan_sckey"]),
            telegram=TelegramConfig(bot_token=notify["telegram_bot_token"], chat_id=notify["telegram_chat_id"]),
        )
        ok = await send_notification(config, "测试推送", "这是一条测试消息\n签到工具推送服务正常工作")
        if ok:
            return {"ok": True, "msg": "测试推送已发送"}
        else:
            return {"ok": False, "msg": "推送发送失败，请检查配置"}
    except Exception as e:
        return {"ok": False, "msg": f"推送测试失败: {e}"}


# ========== 签到 ==========

@router.post("/sign")
async def sign(current_user: dict = Depends(get_current_user)):
    """执行当前用户的签到（SSE）"""
    user_id = current_user["id"]

    async def event_stream():
        from ...kuro.sign import sign_one_kuro
        from ...tajiduo.sign import sign_one_tajiduo
        from ...config import NotifyConfig, ServerChanConfig, TelegramConfig

        accounts = await db.get_user_accounts(user_id)
        if not accounts:
            yield f"data: {json.dumps({'msg': '没有配置账号，请先添加账号', 'type': 'error'})}\n\n"
            yield f"data: {json.dumps({'msg': '签到结束', 'type': 'done', 'done': True})}\n\n"
            return

        config = load_config("config.toml")
        all_results = []

        # 获取用户推送配置
        notify_config = await db.get_user_notify(user_id)

        for acc in accounts:
            if acc["platform"] == "kuro":
                if not acc["cookie"] or not acc["uid"]:
                    yield f"data: {json.dumps({'msg': '跳过库洛账号: 未配置完整', 'type': 'skip'})}\n\n"
                    continue

                yield f"data: {json.dumps({'msg': '签到中: 库洛 ' + acc['uid'] + ' (' + acc['game'] + ')', 'type': 'progress'})}\n\n"
                try:
                    results = await sign_one_kuro(
                        cookie=acc["cookie"],
                        uid=acc["uid"],
                        game=acc["game"],
                        did=acc["did"],
                        bbs_enabled=config.kuro_bbs.enabled,
                    )
                    all_results.append(results)
                    for line in results:
                        yield f"data: {json.dumps({'msg': line, 'type': 'result'})}\n\n"
                except Exception as e:
                    err_msg = f"签到异常: {e}"
                    all_results.append([f"[库洛] {err_msg}"])
                    yield f"data: {json.dumps({'msg': err_msg, 'type': 'error'})}\n\n"

            elif acc["platform"] == "tajiduo":
                if not acc["refresh_token"] or not acc["center_uid"]:
                    yield f"data: {json.dumps({'msg': '跳过塔吉多账号: 未配置完整', 'type': 'skip'})}\n\n"
                    continue

                yield f"data: {json.dumps({'msg': '签到中: 塔吉多 ' + acc['center_uid'], 'type': 'progress'})}\n\n"
                try:
                    results = await sign_one_tajiduo(
                        refresh_token=acc["refresh_token"],
                        center_uid=acc["center_uid"],
                        dev_code=acc["dev_code"],
                        config=config,
                        user_id=user_id,
                    )
                    all_results.append(results)
                    for line in results:
                        yield f"data: {json.dumps({'msg': line, 'type': 'result'})}\n\n"
                except Exception as e:
                    err_msg = f"签到异常: {e}"
                    all_results.append([f"[塔吉多] {err_msg}"])
                    yield f"data: {json.dumps({'msg': err_msg, 'type': 'error'})}\n\n"

        # 发送用户推送通知
        if notify_config and notify_config["enabled"] and all_results:
            try:
                from ...notify.notify import notify_sign_results
                user_notify = NotifyConfig(
                    enabled=True,
                    serverchan=ServerChanConfig(sckey=notify_config["serverchan_sckey"]),
                    telegram=TelegramConfig(bot_token=notify_config["telegram_bot_token"], chat_id=notify_config["telegram_chat_id"]),
                )
                await notify_sign_results(user_notify, all_results)
                yield f"data: {json.dumps({'msg': '推送通知已发送', 'type': 'result'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'msg': f'推送通知失败: {e}', 'type': 'error'})}\n\n"

        yield f"data: {json.dumps({'msg': '签到完成', 'type': 'done', 'done': True})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/status")
async def status(date: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """查看当前用户的签到状态"""
    records = await db.get_today_records(date, user_id=current_user["id"])

    grouped = {}
    for r in records:
        ref = r["ref_id"]
        if ref not in grouped:
            grouped[ref] = []
        grouped[ref].append({"kind": r["kind"], "payload": r["payload"]})

    return {"date": date or __import__("datetime").date.today().isoformat(), "records": grouped}


@router.get("/schedule")
async def get_my_schedule(current_user: dict = Depends(get_current_user)):
    """获取当前用户的定时配置"""
    schedule = await db.get_user_schedule(current_user["id"])
    if not schedule:
        return {"enabled": False, "time": "06:00"}
    return schedule


@router.put("/schedule")
async def update_my_schedule(req: ScheduleRequest, current_user: dict = Depends(get_current_user)):
    """更新当前用户的定时配置"""
    if not req.time or ":" not in req.time:
        return JSONResponse({"ok": False, "msg": "时间格式不正确"})
    await db.update_user_schedule(current_user["id"], req.enabled, req.time)
    return {"ok": True, "msg": "定时配置已保存"}
