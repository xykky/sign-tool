# Sign Tool - Agent Instructions

## Quick Start

```bash
pip install -e .
cp config.toml.example config.toml
sign-tool web  # http://127.0.0.1:8080
```

## Architecture

- **Entry point**: `sign_tool/cli.py:main()` → CLI command `sign-tool`
- **Web app**: FastAPI at `sign_tool/web/app.py` (uvicorn)
- **Platforms**: `kuro/` (库洛: 鸣潮/战双) and `tajiduo/` (塔吉多: 异环/幻塔)
- **Config**: `config.toml` (TOML format, copy from `.example`)
- **Database**: SQLite `sign.db`

## User System

- **Authentication**: JWT token (stored in localStorage)
- **User routes**: `sign_tool/web/routes/auth.py`, `user.py`, `admin.py`
- **Admin**: xyk/xyk666 (configurable via `ADMIN_USER`/`ADMIN_PASSWORD` env vars)
- **User data**: Each user has independent accounts and notify config in DB

## Key Commands

```bash
sign-tool web                           # Start web UI
sign-tool run                           # Run all sign-ins (legacy)
sign-tool run --platform kuro           # Only kuro (legacy)
sign-tool login kuro --phone X --code Y # Login kuro (legacy)
sign-tool send-code tajiduo --phone X   # Send SMS code (tajiduo only)
sign-tool status --date 2026-06-01      # Check sign-in records
```

## Dependencies

Python 3.8+. Key packages: httpx, pydantic, aiosqlite, pycryptodome, fastapi, uvicorn, python-jose, passlib

## File Structure

```
sign_tool/
├── auth.py           # JWT auth, password hashing
├── cli.py            # CLI entry (argparse)
├── config.py         # Config loading/saving (dataclasses)
├── runner.py         # Sign-in executor (asyncio.gather)
├── db.py             # SQLite (aiosqlite) - users, accounts, notify, records
├── scheduler.py      # Background scheduler (all users)
├── kuro/             # 库洛 platform
├── tajiduo/          # 塔吉多 platform
├── notify/           # Push notifications (Server酱/Telegram)
└── web/
    ├── app.py        # FastAPI app + legacy routes
    ├── routes/
    │   ├── auth.py   # /api/auth/* (register, login, me)
    │   ├── user.py   # /api/my/* (accounts, notify, sign, status)
    │   └── admin.py  # /api/admin/* (users, accounts, sign, status)
    └── static/
        └── index.html  # Frontend with login/register UI
```

## API Routes

### Auth (`/api/auth/`)
- `POST /register` - Register new user
- `POST /login` - Login, returns JWT token
- `GET /me` - Get current user info

### User (`/api/my/`) - Requires login
- `POST /login` - Login game account and save to user
- `GET /accounts` - List user's game accounts
- `DELETE /accounts/{id}` - Delete game account
- `GET /notify` - Get user's notify config
- `POST /notify` - Update notify config
- `POST /notify/test` - Test notify
- `POST /sign` - Execute user's sign-in (SSE)
- `GET /status` - Get user's sign-in status

### Admin (`/api/admin/`) - Requires admin
- `GET /users` - List all users
- `DELETE /users/{id}` - Delete user
- `GET /accounts` - List all accounts
- `DELETE /users/{id}/accounts/{aid}` - Delete user's account
- `POST /sign` - Execute all users' sign-in (SSE)
- `GET /status` - Get all users' sign-in status

## Notes

- No test suite exists
- Config auto-fixes corrupted TOML (line-manipulation bugs)
- Web uses SSE for real-time sign-in progress
- Server deploy: `sudo bash install.sh domain.com` (systemd + nginx)
- Admin account must be set during install via `ADMIN_USER`/`ADMIN_PASSWORD` env vars (no defaults)
