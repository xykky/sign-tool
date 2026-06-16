from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ... import db
from ...auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["认证"])


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/register")
async def register(req: RegisterRequest):
    """用户注册"""
    if len(req.username) < 2 or len(req.username) > 20:
        return JSONResponse({"ok": False, "msg": "用户名长度应为 2-20 个字符"})
    if len(req.password) < 6:
        return JSONResponse({"ok": False, "msg": "密码长度至少 6 个字符"})

    existing = await db.get_user_by_username(req.username)
    if existing:
        return JSONResponse({"ok": False, "msg": "用户名已存在"})

    password_hash = hash_password(req.password)
    user_id = await db.create_user(req.username, password_hash, is_admin=False)

    # 用默认定时配置初始化新用户
    from ...config import load_config
    config = load_config("config.toml")
    await db.update_user_schedule(user_id, config.schedule.enabled, config.schedule.time)

    token = create_access_token({"sub": str(user_id), "username": req.username, "is_admin": False})
    return {"ok": True, "msg": "注册成功", "token": token, "username": req.username}


@router.post("/login")
async def login(req: LoginRequest):
    """用户登录"""
    user = await db.get_user_by_username(req.username)
    if not user:
        return JSONResponse({"ok": False, "msg": "用户名或密码错误"})

    if not verify_password(req.password, user["password_hash"]):
        return JSONResponse({"ok": False, "msg": "用户名或密码错误"})

    token = create_access_token({
        "sub": str(user["id"]),
        "username": user["username"],
        "is_admin": user["is_admin"],
    })
    return {
        "ok": True,
        "msg": "登录成功",
        "token": token,
        "username": user["username"],
        "is_admin": user["is_admin"],
    }


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """获取当前用户信息"""
    return {
        "ok": True,
        "user": {
            "id": current_user["id"],
            "username": current_user["username"],
            "is_admin": current_user["is_admin"],
        },
    }
