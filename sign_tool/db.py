from __future__ import annotations

import json
from datetime import date

import aiosqlite

_db: aiosqlite.Connection | None = None

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS sign_records (
    ref_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    date TEXT NOT NULL,
    payload TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(ref_id, kind, date)
);
CREATE INDEX IF NOT EXISTS ix_sign_records_lookup
    ON sign_records (ref_id, kind, date);
"""


async def init_db(path: str = "sign.db") -> None:
    global _db
    _db = await aiosqlite.connect(path)
    await _db.executescript(_CREATE_SQL)
    await _db.commit()


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None


async def is_signed(ref_id: str, kind: str, d: str | None = None) -> bool:
    assert _db is not None
    if d is None:
        d = date.today().isoformat()
    async with _db.execute(
        "SELECT 1 FROM sign_records WHERE ref_id=? AND kind=? AND date=?",
        (ref_id, kind, d),
    ) as cur:
        return (await cur.fetchone()) is not None


async def record_sign(ref_id: str, kind: str, payload: dict | None = None, d: str | None = None) -> None:
    assert _db is not None
    if d is None:
        d = date.today().isoformat()
    await _db.execute(
        "INSERT OR IGNORE INTO sign_records (ref_id, kind, date, payload) VALUES (?, ?, ?, ?)",
        (ref_id, kind, d, json.dumps(payload or {}, ensure_ascii=False)),
    )
    await _db.commit()


async def get_today_records(d: str | None = None) -> list[dict]:
    assert _db is not None
    if d is None:
        d = date.today().isoformat()
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
