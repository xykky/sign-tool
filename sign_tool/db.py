from __future__ import annotations

import json
from datetime import date, datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

import aiosqlite

_db: aiosqlite.Connection | None = None

_CN_TZ = timezone(timedelta(hours=8))


def _now_cn_str() -> str:
    """返回北京时间字符串，格式：YYYY-MM-DD HH:MM:SS"""
    return datetime.now(_CN_TZ).strftime("%Y-%m-%d %H:%M:%S")


_CREATE_SQL = """
-- 签到记录表
CREATE TABLE IF NOT EXISTS sign_records (
    ref_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    date TEXT NOT NULL,
    user_id INTEGER,
    payload TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now', '+8 hours')),
    UNIQUE(ref_id, kind, date, user_id)
);
CREATE INDEX IF NOT EXISTS ix_sign_records_lookup
    ON sign_records (ref_id, kind, date);
CREATE INDEX IF NOT EXISTS ix_sign_records_user
    ON sign_records (user_id, date);

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0,
    schedule_enabled INTEGER DEFAULT 0,
    schedule_time TEXT DEFAULT '06:00',
    created_at TEXT DEFAULT (datetime('now', '+8 hours'))
);

-- 用户账号表
CREATE TABLE IF NOT EXISTS user_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    cookie TEXT DEFAULT '',
    uid TEXT DEFAULT '',
    game TEXT DEFAULT 'waves',
    did TEXT DEFAULT '',
    refresh_token TEXT DEFAULT '',
    center_uid TEXT DEFAULT '',
    dev_code TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', '+8 hours')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_user_accounts_user
    ON user_accounts (user_id);

-- 用户推送配置表
CREATE TABLE IF NOT EXISTS user_notify (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    enabled INTEGER DEFAULT 0,
    serverchan_sckey TEXT DEFAULT '',
    telegram_bot_token TEXT DEFAULT '',
    telegram_chat_id TEXT DEFAULT '',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

_MIGRATE_SQL = [
    ("users", "schedule_enabled", "ALTER TABLE users ADD COLUMN schedule_enabled INTEGER DEFAULT 0"),
    ("users", "schedule_time", "ALTER TABLE users ADD COLUMN schedule_time TEXT DEFAULT '06:00'"),
]


async def init_db(path: str = "sign.db") -> None:
    global _db
    if _db is not None:
        return
    _db = await aiosqlite.connect(path)
    await _db.executescript(_CREATE_SQL)
    await _db.commit()
    await _migrate_db()


async def _migrate_db() -> None:
    """Add missing columns to existing tables."""
    assert _db is not None
    for table, column, sql in _MIGRATE_SQL:
        try:
            await _db.execute(sql)
        except Exception:
            pass  # column already exists
    await _db.commit()


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None


# ========== 签到记录 ==========

async def is_signed(ref_id: str, kind: str, d: str | None = None, user_id: int | None = None) -> bool:
    assert _db is not None
    if d is None:
        d = date.today().isoformat()
    if user_id is not None:
        async with _db.execute(
            "SELECT 1 FROM sign_records WHERE ref_id=? AND kind=? AND date=? AND user_id=?",
            (ref_id, kind, d, user_id),
        ) as cur:
            return (await cur.fetchone()) is not None
    else:
        async with _db.execute(
            "SELECT 1 FROM sign_records WHERE ref_id=? AND kind=? AND date=? AND user_id IS NULL",
            (ref_id, kind, d),
        ) as cur:
            return (await cur.fetchone()) is not None


async def record_sign(ref_id: str, kind: str, payload: dict | None = None, d: str | None = None, user_id: int | None = None) -> None:
    assert _db is not None
    if d is None:
        d = date.today().isoformat()
    await _db.execute(
        "INSERT OR IGNORE INTO sign_records (ref_id, kind, date, user_id, payload) VALUES (?, ?, ?, ?, ?)",
        (ref_id, kind, d, user_id, json.dumps(payload or {}, ensure_ascii=False)),
    )
    await _db.commit()


async def get_today_records(d: str | None = None, user_id: int | None = None) -> list[dict]:
    assert _db is not None
    if d is None:
        d = date.today().isoformat()
    if user_id is not None:
        async with _db.execute(
            "SELECT ref_id, kind, payload FROM sign_records WHERE date=? AND user_id=? ORDER BY ref_id, kind",
            (d, user_id),
        ) as cur:
            rows = await cur.fetchall()
            return [{"ref_id": r[0], "kind": r[1], "payload": r[2]} for r in rows]
    else:
        async with _db.execute(
            "SELECT ref_id, kind, payload FROM sign_records WHERE date=? ORDER BY ref_id, kind",
            (d,),
        ) as cur:
            rows = await cur.fetchall()
            return [{"ref_id": r[0], "kind": r[1], "payload": r[2]} for r in rows]


async def purge_before(d: str) -> int:
    assert _db is not None
    async with _db.execute("DELETE FROM sign_records WHERE date < ?", (d,)) as cur:
        deleted = cur.rowcount
    await _db.commit()
    return deleted


# ========== 用户管理 ==========

async def create_user(username: str, password_hash: str, is_admin: bool = False) -> int:
    """创建用户，返回用户 ID"""
    assert _db is not None
    now = _now_cn_str()
    async with _db.execute(
        "INSERT INTO users (username, password_hash, is_admin, created_at) VALUES (?, ?, ?, ?)",
        (username, password_hash, 1 if is_admin else 0, now),
    ) as cur:
        user_id = cur.lastrowid
    await _db.commit()

    # 自动创建推送配置记录
    await _db.execute(
        "INSERT INTO user_notify (user_id) VALUES (?)",
        (user_id,),
    )
    await _db.commit()

    return user_id


async def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """根据用户名获取用户"""
    assert _db is not None
    async with _db.execute(
        "SELECT id, username, password_hash, is_admin FROM users WHERE username=?",
        (username,),
    ) as cur:
        row = await cur.fetchone()
        if row:
            return {"id": row[0], "username": row[1], "password_hash": row[2], "is_admin": bool(row[3])}
        return None


async def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """根据用户 ID 获取用户"""
    assert _db is not None
    async with _db.execute(
        "SELECT id, username, password_hash, is_admin FROM users WHERE id=?",
        (user_id,),
    ) as cur:
        row = await cur.fetchone()
        if row:
            return {"id": row[0], "username": row[1], "password_hash": row[2], "is_admin": bool(row[3])}
        return None


async def get_all_users() -> List[Dict[str, Any]]:
    """获取所有用户"""
    assert _db is not None
    async with _db.execute(
        "SELECT id, username, is_admin, created_at FROM users ORDER BY id",
    ) as cur:
        rows = await cur.fetchall()
        return [{"id": r[0], "username": r[1], "is_admin": bool(r[2]), "created_at": r[3]} for r in rows]


async def delete_user(user_id: int) -> bool:
    """删除用户"""
    assert _db is not None
    async with _db.execute("DELETE FROM users WHERE id=?", (user_id,)) as cur:
        deleted = cur.rowcount > 0
    await _db.commit()
    return deleted


# ========== 用户账号管理 ==========

async def add_user_account(user_id: int, platform: str, account_data: dict) -> int:
    """添加或更新用户账号（相同平台+uid/center_uid 时覆盖）"""
    assert _db is not None
    if platform == "kuro":
        uid = account_data.get("uid", "")
        # 查找是否已存在
        async with _db.execute(
            "SELECT id FROM user_accounts WHERE user_id=? AND platform=? AND uid=?",
            (user_id, platform, uid),
        ) as cur:
            existing = await cur.fetchone()
        if existing:
            account_id = existing[0]
            await _db.execute(
                "UPDATE user_accounts SET cookie=?, game=?, did=? WHERE id=?",
                (account_data.get("cookie", ""), account_data.get("game", "waves"),
                 account_data.get("did", ""), account_id),
            )
        else:
            async with _db.execute(
                "INSERT INTO user_accounts (user_id, platform, cookie, uid, game, did) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, platform, account_data.get("cookie", ""), uid,
                 account_data.get("game", "waves"), account_data.get("did", "")),
            ) as cur:
                account_id = cur.lastrowid
    elif platform == "tajiduo":
        center_uid = account_data.get("center_uid", "")
        # 查找是否已存在
        async with _db.execute(
            "SELECT id FROM user_accounts WHERE user_id=? AND platform=? AND center_uid=?",
            (user_id, platform, center_uid),
        ) as cur:
            existing = await cur.fetchone()
        if existing:
            account_id = existing[0]
            await _db.execute(
                "UPDATE user_accounts SET refresh_token=?, dev_code=? WHERE id=?",
                (account_data.get("refresh_token", ""), account_data.get("dev_code", ""), account_id),
            )
        else:
            async with _db.execute(
                "INSERT INTO user_accounts (user_id, platform, refresh_token, center_uid, dev_code) VALUES (?, ?, ?, ?, ?)",
                (user_id, platform, account_data.get("refresh_token", ""),
                 center_uid, account_data.get("dev_code", "")),
            ) as cur:
                account_id = cur.lastrowid
    else:
        raise ValueError(f"不支持的平台: {platform}")
    await _db.commit()
    return account_id


async def get_user_accounts(user_id: int) -> List[Dict[str, Any]]:
    """获取用户的所有账号"""
    assert _db is not None
    async with _db.execute(
        "SELECT id, platform, cookie, uid, game, did, refresh_token, center_uid, dev_code FROM user_accounts WHERE user_id=?",
        (user_id,),
    ) as cur:
        rows = await cur.fetchall()
        accounts = []
        for r in rows:
            if r[1] == "kuro":
                accounts.append({
                    "id": r[0], "platform": r[1], "cookie": r[2], "uid": r[3],
                    "game": r[4], "did": r[5],
                })
            else:
                accounts.append({
                    "id": r[0], "platform": r[1], "refresh_token": r[6],
                    "center_uid": r[7], "dev_code": r[8],
                })
        return accounts


async def get_user_account_by_id(account_id: int) -> Optional[Dict[str, Any]]:
    """根据账号 ID 获取账号"""
    assert _db is not None
    async with _db.execute(
        "SELECT id, user_id, platform, cookie, uid, game, did, refresh_token, center_uid, dev_code FROM user_accounts WHERE id=?",
        (account_id,),
    ) as cur:
        row = await cur.fetchone()
        if row:
            if row[2] == "kuro":
                return {
                    "id": row[0], "user_id": row[1], "platform": row[2],
                    "cookie": row[3], "uid": row[4], "game": row[5], "did": row[6],
                }
            else:
                return {
                    "id": row[0], "user_id": row[1], "platform": row[2],
                    "refresh_token": row[7], "center_uid": row[8], "dev_code": row[9],
                }
        return None


async def delete_user_account(account_id: int) -> bool:
    """删除用户账号"""
    assert _db is not None
    async with _db.execute("DELETE FROM user_accounts WHERE id=?", (account_id,)) as cur:
        deleted = cur.rowcount > 0
    await _db.commit()
    return deleted


async def get_all_accounts() -> List[Dict[str, Any]]:
    """获取所有用户的账号（管理员用）"""
    assert _db is not None
    async with _db.execute(
        """SELECT ua.id, ua.user_id, ua.platform, ua.cookie, ua.uid, ua.game, ua.did,
                  ua.refresh_token, ua.center_uid, ua.dev_code, u.username
           FROM user_accounts ua JOIN users u ON ua.user_id = u.id ORDER BY ua.user_id, ua.id""",
    ) as cur:
        rows = await cur.fetchall()
        accounts = []
        for r in rows:
            base = {"id": r[0], "user_id": r[1], "platform": r[2], "username": r[10]}
            if r[2] == "kuro":
                base.update({"cookie": r[3], "uid": r[4], "game": r[5], "did": r[6]})
            else:
                base.update({"refresh_token": r[7], "center_uid": r[8], "dev_code": r[9]})
            accounts.append(base)
        return accounts


# ========== 用户推送配置 ==========

async def get_user_notify(user_id: int) -> Optional[Dict[str, Any]]:
    """获取用户的推送配置"""
    assert _db is not None
    async with _db.execute(
        "SELECT enabled, serverchan_sckey, telegram_bot_token, telegram_chat_id FROM user_notify WHERE user_id=?",
        (user_id,),
    ) as cur:
        row = await cur.fetchone()
        if row:
            return {
                "enabled": bool(row[0]),
                "serverchan_sckey": row[1] or "",
                "telegram_bot_token": row[2] or "",
                "telegram_chat_id": row[3] or "",
            }
        return None


async def update_user_notify(user_id: int, notify_data: dict) -> None:
    """更新用户的推送配置"""
    assert _db is not None
    await _db.execute(
        """INSERT INTO user_notify (user_id, enabled, serverchan_sckey, telegram_bot_token, telegram_chat_id)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
             enabled=excluded.enabled,
             serverchan_sckey=excluded.serverchan_sckey,
             telegram_bot_token=excluded.telegram_bot_token,
             telegram_chat_id=excluded.telegram_chat_id""",
        (user_id, 1 if notify_data.get("enabled") else 0,
         notify_data.get("serverchan_sckey", ""),
         notify_data.get("telegram_bot_token", ""),
         notify_data.get("telegram_chat_id", "")),
    )
    await _db.commit()


async def update_user_account_token(user_id: int, center_uid: str, new_refresh_token: str) -> None:
    """更新用户的塔吉多 refresh_token"""
    assert _db is not None
    await _db.execute(
        "UPDATE user_accounts SET refresh_token=? WHERE user_id=? AND center_uid=?",
        (new_refresh_token, user_id, center_uid),
    )
    await _db.commit()


# ========== 用户定时配置 ==========

async def get_user_schedule(user_id: int) -> Optional[Dict[str, Any]]:
    """获取用户的定时配置"""
    assert _db is not None
    async with _db.execute(
        "SELECT schedule_enabled, schedule_time FROM users WHERE id=?",
        (user_id,),
    ) as cur:
        row = await cur.fetchone()
        if row:
            return {"enabled": bool(row[0]), "time": row[1] or "06:00"}
    return None


async def update_user_schedule(user_id: int, enabled: bool, time: str) -> None:
    """更新用户的定时配置"""
    assert _db is not None
    await _db.execute(
        "UPDATE users SET schedule_enabled=?, schedule_time=? WHERE id=?",
        (1 if enabled else 0, time, user_id),
    )
    await _db.commit()


async def get_all_schedules() -> List[Dict[str, Any]]:
    """获取所有用户的定时配置"""
    assert _db is not None
    async with _db.execute(
        "SELECT id, username, schedule_enabled, schedule_time FROM users ORDER BY id",
    ) as cur:
        rows = await cur.fetchall()
        return [
            {"user_id": r[0], "username": r[1], "enabled": bool(r[2]), "time": r[3] or "06:00"}
            for r in rows
        ]


async def update_all_schedules(enabled: bool, time: str) -> int:
    """批量更新所有用户的定时配置，返回更新行数"""
    assert _db is not None
    async with _db.execute(
        "UPDATE users SET schedule_enabled=?, schedule_time=?",
        (1 if enabled else 0, time),
    ) as cur:
        updated = cur.rowcount
    await _db.commit()
    return updated
