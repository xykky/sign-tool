# AGENTS.md

## Project Overview

Independent sign-in tool for Kuro (鸣潮/战双) and Tajiduo (异环/幻塔) game platforms. Chinese-language UI. No dependency on gsuid_core.

## Tech Stack

- Python 3.8+, hatchling build
- FastAPI + Uvicorn (async)
- httpx, aiosqlite, pycryptodome, python-jose
- SQLite database, TOML config

## Key Commands

```bash
pip install -e .                  # Install in dev mode
sign-tool web                     # Start web UI (default 127.0.0.1:8080)
sign-tool run                     # Execute all sign-ins
sign-tool run --platform kuro     # Kuro only
sign-tool run --platform tajiduo  # Tajiduo only
sign-tool status                  # Today's sign-in records
```

No test suite, linter, or type checker is configured.

## Architecture

```
sign_tool/
├── cli.py          # CLI entry point (argparse, asyncio.run)
├── config.py       # TOML config loading + CRUD, dataclasses
├── db.py           # SQLite via aiosqlite (global connection)
├── auth.py         # JWT auth (python-jose), password hashing
├── runner.py       # Concurrent sign-in executor
├── scheduler.py    # Background thread scheduler (not async)
├── kuro/           # Kuro platform: api.py, login.py, sign.py
├── tajiduo/        # Tajiduo platform: api.py, laohu.py, login.py, sign.py
├── notify/         # Server酱 + Telegram push
└── web/
    ├── app.py      # FastAPI app, startup/shutdown, legacy routes
    └── routes/     # auth.py, user.py, admin.py (APIRouter)
```

## Critical Patterns

**Dual storage**: Legacy CLI writes accounts to `config.toml`; web users stored in SQLite `user_accounts` table. The scheduler reads from DB (all users), CLI reads from config file.

**Account upsert**: `db.add_user_account()` updates existing records when same user+platform+uid/center_uid is added again (no duplicates).

**Per-user scheduling**: Each user has `schedule_enabled` and `schedule_time` columns in `users` table. The scheduler groups users by time and signs each group at their scheduled time. The global `config.toml` schedule is only used as the default for new user registration.

**Scheduler**: Runs in a daemon thread (`scheduler.py`), not asyncio. Uses `asyncio.run()` inside thread. Re-reads user schedules from DB each loop for hot-reload. Sleeps in 30s chunks to detect schedule changes.

**Admin user**: Created on web startup from env vars `ADMIN_USER`/`ADMIN_PASSWORD` (defaults: `admin`/`admin`). JWT secret from `JWT_SECRET_KEY` env var (hardcoded fallback).

**Config auto-fix**: `config.py:_try_fix_corrupted_config()` repairs TOML files corrupted by old line-manipulation code (known issue with `[[tajiduo.accounts]]` inserted in wrong section).

**SSE streaming**: Sign-in progress uses Server-Sent Events (`StreamingResponse` with `text/event-stream`).

## Timezone

All datetime operations use UTC+8 (Beijing time). See `scheduler.py:_CN_TZ`.

## Dependencies

- `tomli` for TOML reading (Python 3.8-3.10), `tomllib` (3.11+)
- `tomli-w` for TOML writing
- No pinned versions in lockfile

## Deployment

Linux systemd service + Nginx reverse proxy. Scripts: `install.sh`, `update.sh`, `uninstall.sh`. Service runs on port 2087 by default.
