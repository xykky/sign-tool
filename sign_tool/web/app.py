from __future__ import annotations

import asyncio
import json
import random
import string
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse

from ..config import (
    load_config,
    Config,
    save_kuro_account,
    save_tajiduo_account,
    delete_account,
    update_schedule_config,
    update_notify_config,
    KuroAccount,
    TajiduoAccount,
)
from .. import db

app = FastAPI(title="签到工具", docs_url=None, redoc_url=None)
_config: Config = None  # type: ignore
_static_dir = Path(__file__).parent / "static"

KURO_SMS_URL = "https://api.kurobbs.com/user/getSmsCodeForH5"
KURO_CAPTCHA_ID = "ec4aa4174277d822d73f2442a165a2cd"


def _random_string(length: int = 32) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def _get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config("config.toml")
    return _config


def _reload_config(path: str) -> None:
    global _config
    _config = load_config(path)


# 注册路由
from .routes.auth import router as auth_router
from .routes.user import router as user_router
from .routes.admin import router as admin_router

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(admin_router)


@app.on_event("startup")
async def startup():
    global _config
    _config = load_config("config.toml")
    await db.init_db(_config.db_path)

    # 确保管理员账号存在
    import os
    from ..auth import hash_password
    admin_username = os.environ.get("ADMIN_USER", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin")
    
    admin_user = await db.get_user_by_username(admin_username)
    if not admin_user:
        password_hash = hash_password(admin_password)
        await db.create_user(admin_username, password_hash, is_admin=True)

    # Start background scheduler
    from ..scheduler import start_scheduler
    start_scheduler(_config.config_path)


@app.on_event("shutdown")
async def shutdown():
    await db.close_db()


# ===== 页面 =====

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = _static_dir / "index.html"
    return HTMLResponse(html_path.read_text("utf-8"))


# ===== 发送验证码 (塔吉多) =====

@app.post("/api/send-code")
async def send_code(req: Request):
    body = await req.json()
    platform = body.get("platform", "")
    phone = body.get("phone", "")

    if not phone:
        return JSONResponse({"ok": False, "msg": "请输入手机号"})

    if platform == "tajiduo":
        try:
            from ..tajiduo.laohu import LaohuClient, LaohuDevice
            device = LaohuDevice()
            client = LaohuClient(device=device)
            await client.send_sms_code(phone)
            return {"ok": True, "msg": "验证码已发送"}
        except Exception as e:
            return {"ok": False, "msg": f"发送失败: {e}"}
    elif platform == "kuro":
        return {"ok": False, "msg": "库洛请使用页面上的人机验证发送验证码"}
    else:
        return {"ok": False, "msg": f"不支持的平台: {platform}"}


# ===== 发送验证码 (库洛 - 代理 Geetest 验证后请求) =====

@app.post("/api/kuro-send-sms")
async def kuro_send_sms(req: Request):
    body = await req.json()
    mobile = body.get("mobile", "")
    gee_test_data = body.get("geeTestData", "")

    if not mobile:
        return JSONResponse({"ok": False, "msg": "请输入手机号"})
    if not gee_test_data:
        return JSONResponse({"ok": False, "msg": "请完成人机验证"})

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                KURO_SMS_URL,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                    "devcode": _random_string(32),
                    "source": "h5",
                    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) KuroGameBox/3.0.3",
                },
                data={"mobile": mobile, "geeTestData": gee_test_data},
            )
            result = resp.json()
            if result.get("success") or result.get("code") in (0, 200):
                return {"ok": True, "msg": "验证码已发送"}
            else:
                return {"ok": False, "msg": f"发送失败: {result.get('msg', '未知错误')}"}
    except Exception as e:
        return {"ok": False, "msg": f"请求失败: {e}"}


# ===== 登录 (旧版，保留兼容) =====

@app.post("/api/login")
async def login(req: Request):
    body = await req.json()
    platform = body.get("platform", "")
    phone = body.get("phone", "")
    code = body.get("code", "")

    if not phone or not code:
        return JSONResponse({"ok": False, "msg": "请输入手机号和验证码"})

    config = _get_config()

    try:
        if platform == "kuro":
            from ..kuro.login import login_kuro
            game = body.get("game", "waves")
            account = await login_kuro(phone, code, game, config)
            _reload_config(config.config_path)
            return {"ok": True, "msg": "登录成功", "uid": account.uid, "game": game}
        elif platform == "tajiduo":
            from ..tajiduo.login import login_tajiduo
            account = await login_tajiduo(phone, code, config)
            _reload_config(config.config_path)
            return {"ok": True, "msg": "登录成功", "center_uid": account.center_uid}
        else:
            return JSONResponse({"ok": False, "msg": f"不支持的平台: {platform}"})
    except Exception as e:
        return {"ok": False, "msg": f"登录失败: {e}"}


# ===== 账号列表 (旧版，保留兼容) =====

@app.get("/api/accounts")
async def accounts():
    config = _get_config()
    result = []
    for i, acc in enumerate(config.kuro_accounts):
        masked_cookie = acc.cookie[:8] + "..." if len(acc.cookie) > 8 else acc.cookie
        result.append({
            "platform": "kuro",
            "index": i,
            "uid": acc.uid,
            "game": acc.game,
            "game_label": "鸣潮" if acc.game == "waves" else "战双",
            "cookie_preview": masked_cookie,
        })
    for i, acc in enumerate(config.tajiduo_accounts):
        result.append({
            "platform": "tajiduo",
            "index": i,
            "center_uid": acc.center_uid,
            "dev_code": acc.dev_code[:8] + "..." if acc.dev_code else "",
        })
    return result


# ===== 删除账号 (旧版，保留兼容) =====

@app.delete("/api/accounts/{platform}/{index}")
async def delete_account_api(platform: str, index: int):
    config = _get_config()
    ok = delete_account(config.config_path, platform, index)
    if ok:
        global _config
        _config = load_config(config.config_path)
        return {"ok": True, "msg": "已删除"}
    return JSONResponse({"ok": False, "msg": "删除失败: 索引无效"})


# ===== 签到状态 (旧版，保留兼容) =====

@app.get("/api/status")
async def status(date: str = None):
    config = _get_config()
    await db.init_db(config.db_path)
    records = await db.get_today_records(date)

    grouped = {}  # type: dict[str, list]
    for r in records:
        ref = r["ref_id"]
        if ref not in grouped:
            grouped[ref] = []
        grouped[ref].append({"kind": r["kind"], "payload": r["payload"]})

    return {"date": date or db._today_cn(), "records": grouped}


# ===== 执行签到 (旧版，保留兼容) =====

@app.post("/api/sign")
async def sign():
    config = _get_config()

    async def event_stream():
        from ..kuro.sign import sign_one_kuro
        from ..tajiduo.sign import sign_one_tajiduo

        all_results = []

        for acc in config.kuro_accounts:
            if not acc.cookie or not acc.uid:
                yield f"data: {json.dumps({'msg': '跳过库洛账号: 未配置', 'type': 'skip'})}\n\n"
                continue

            yield f"data: {json.dumps({'msg': f'签到中: 库洛 {acc.uid} ({acc.game})', 'type': 'progress'})}\n\n"
            try:
                results = await sign_one_kuro(
                    cookie=acc.cookie,
                    uid=acc.uid,
                    game=acc.game,
                    did=acc.did,
                    bbs_enabled=config.kuro_bbs.enabled,
                )
                all_results.append(results)
                for line in results:
                    yield f"data: {json.dumps({'msg': line, 'type': 'result'})}\n\n"
            except Exception as e:
                err_msg = f"签到异常: {e}"
                all_results.append([f"[库洛] {err_msg}"])
                yield f"data: {json.dumps({'msg': err_msg, 'type': 'error'})}\n\n"

        for acc in config.tajiduo_accounts:
            if not acc.refresh_token or not acc.center_uid:
                yield f"data: {json.dumps({'msg': '跳过塔吉多账号: 未配置', 'type': 'skip'})}\n\n"
                continue

            yield f"data: {json.dumps({'msg': f'签到中: 塔吉多 {acc.center_uid}', 'type': 'progress'})}\n\n"
            try:
                results = await sign_one_tajiduo(
                    refresh_token=acc.refresh_token,
                    center_uid=acc.center_uid,
                    dev_code=acc.dev_code,
                    config=config,
                )
                all_results.append(results)
                for line in results:
                    yield f"data: {json.dumps({'msg': line, 'type': 'result'})}\n\n"
            except Exception as e:
                err_msg = f"签到异常: {e}"
                all_results.append(f"[塔吉多] {err_msg}")
                yield f"data: {json.dumps({'msg': err_msg, 'type': 'error'})}\n\n"

        # Send notification
        if config.notify.enabled and all_results:
            try:
                from ..notify.notify import notify_sign_results
                await notify_sign_results(config.notify, all_results)
                yield f"data: {json.dumps({'msg': '推送通知已发送', 'type': 'result'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'msg': f'推送通知失败: {e}', 'type': 'error'})}\n\n"

        yield f"data: {json.dumps({'msg': '全部签到完成', 'type': 'done', 'done': True})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ===== 推送配置 (旧版，保留兼容) =====

@app.get("/api/notify")
async def get_notify():
    config = _get_config()
    notify = config.notify
    return {
        "enabled": notify.enabled,
        "serverchan": {"sckey": notify.serverchan.sckey[:8] + "..." if len(notify.serverchan.sckey) > 8 else notify.serverchan.sckey},
        "telegram": {
            "bot_token": notify.telegram.bot_token[:8] + "..." if len(notify.telegram.bot_token) > 8 else notify.telegram.bot_token,
            "chat_id": notify.telegram.chat_id,
        },
    }


@app.post("/api/notify")
async def update_notify(req: Request):
    body = await req.json()
    enabled = body.get("enabled", False)
    sckey = body.get("sckey", "")
    bot_token = body.get("bot_token", "")
    chat_id = body.get("chat_id", "")

    config = _get_config()

    # Keep existing values if not provided
    if not sckey and config.notify.serverchan.sckey:
        sckey = config.notify.serverchan.sckey
    if not bot_token and config.notify.telegram.bot_token:
        bot_token = config.notify.telegram.bot_token
    if not chat_id and config.notify.telegram.chat_id:
        chat_id = config.notify.telegram.chat_id

    update_notify_config(config.config_path, enabled, sckey, bot_token, chat_id)

    global _config
    _config = load_config(config.config_path)

    return {"ok": True, "msg": "推送配置已保存"}


@app.post("/api/notify/test")
async def test_notify():
    """Send a test notification."""
    config = _get_config()
    if not config.notify.enabled:
        return {"ok": False, "msg": "推送未启用"}

    try:
        from ..notify.notify import send_notification
        ok = await send_notification(config.notify, "测试推送", "这是一条测试消息\n签到工具推送服务正常工作")
        if ok:
            return {"ok": True, "msg": "测试推送已发送"}
        else:
            return {"ok": False, "msg": "推送发送失败，请检查配置"}
    except Exception as e:
        return {"ok": False, "msg": f"推送测试失败: {e}"}


# ===== 更新 =====

@app.post("/api/update")
async def update_project():
    """Pull latest code from git and restart service."""
    import subprocess
    import sys
    import threading
    import time

    project_dir = str(Path(__file__).parent.parent.parent)

    try:
        # git pull
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        git_output = result.stdout.strip()
        if result.returncode != 0:
            subprocess.run(["git", "fetch", "origin"], cwd=project_dir, timeout=30)
            result = subprocess.run(
                ["git", "reset", "--hard", "origin/master"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            git_output = result.stdout.strip() if result.returncode == 0 else result.stderr.strip()

        if "Already up to date" in git_output or "已经是最新的" in git_output:
            return {"ok": True, "msg": f"已是最新版本\n{git_output}"}

        # pip install
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", ".", "-q"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )

        # delayed restart: give client time to receive response
        def _restart():
            time.sleep(5)
            subprocess.run(["systemctl", "restart", "sign-tool"])

        threading.Thread(target=_restart, daemon=True).start()

        return {"ok": True, "msg": f"更新成功！5秒后自动重启...\n{git_output}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "msg": "更新超时，请手动执行 update.sh"}
    except Exception as e:
        return {"ok": False, "msg": f"更新失败: {e}"}
