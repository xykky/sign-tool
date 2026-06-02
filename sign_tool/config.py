from __future__ import annotations

import sys
from pathlib import Path
from copy import deepcopy

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

import tomli_w

from dataclasses import field, dataclass


@dataclass
class KuroAccount:
    cookie: str = ""
    uid: str = ""
    game: str = "waves"  # "waves" | "pgr"
    did: str = ""


@dataclass
class TajiduoAccount:
    refresh_token: str = ""
    center_uid: str = ""
    dev_code: str = ""


@dataclass
class KuroBbsConfig:
    enabled: list[str] = field(default_factory=lambda: ["sign", "detail", "like", "share"])


@dataclass
class TajiduoTaskConfig:
    enabled: list[str] = field(default_factory=lambda: ["browse_post_c", "like_post_c", "share"])
    action_delay: tuple[float, float] = (0.5, 1.5)
    max_failures: int = 3


@dataclass
class ScheduleConfig:
    enabled: bool = False
    time: str = "06:00"  # HH:MM
    repeat: bool = False  # 5 times per day


@dataclass
class ServerChanConfig:
    sckey: str = ""


@dataclass
class TelegramConfig:
    bot_token: str = ""
    chat_id: str = ""


@dataclass
class NotifyConfig:
    enabled: bool = False
    serverchan: ServerChanConfig = field(default_factory=ServerChanConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)


@dataclass
class Config:
    concurrency: int = 3
    delay: tuple[float, float] = (1.0, 3.0)
    log_level: str = "INFO"
    db_path: str = "sign.db"
    config_path: str = "config.toml"
    kuro_accounts: list[KuroAccount] = field(default_factory=list)
    tajiduo_accounts: list[TajiduoAccount] = field(default_factory=list)
    kuro_bbs: KuroBbsConfig = field(default_factory=KuroBbsConfig)
    tajiduo_tasks: TajiduoTaskConfig = field(default_factory=TajiduoTaskConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)


# ===== TOML I/O helpers =====

def _read_toml(path: str) -> dict:
    """Read a TOML file and return as dict. Returns empty dict if not found."""
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, "rb") as f:
        return tomllib.load(f)


def _write_toml(path: str, data: dict) -> None:
    """Write a dict to a TOML file."""
    p = Path(path)
    p.write_text(tomli_w.dumps(data), "utf-8")


# ===== Config loading =====

def _try_fix_corrupted_config(path: str) -> bool:
    """Try to fix a corrupted config.toml caused by old line-manipulation code.

    Known corruption: [[tajiduo.accounts]] inserted inside [tajiduo.tasks],
    with task keys appearing as account keys and account credentials appended
    at file end outside any section.

    Returns True if the file was fixed (needs re-parse), False if unfixable.
    """
    p = Path(path)
    text = p.read_text("utf-8")

    # Quick check: if TOML parses fine, nothing to fix
    try:
        tomllib.loads(text)
        return False
    except tomllib.TOMLDecodeError:
        pass

    lines = text.splitlines()

    # Strategy: extract all sections and key-value pairs, rebuild valid TOML
    # Parse sections and their content manually
    sections: dict[str, list[tuple[str, str]]] = {}
    current_section = "__top__"
    sections[current_section] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Detect section headers
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped.startswith("[[") and stripped.endswith("]]"):
                # Array of tables
                current_section = stripped
            else:
                current_section = stripped
            if current_section not in sections:
                sections[current_section] = []
            continue

        # Key-value pair
        if "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            value_part = stripped.split("=", 1)[1].strip()
            sections[current_section].append((key, value_part))

    # Now rebuild: find all tajiduo accounts entries
    tajiduo_accounts = []
    tajiduo_tasks_keys = []
    stray_keys = []  # keys that appeared outside any section

    for section, kvs in sections.items():
        if section == "[[tajiduo.accounts]]":
            tajiduo_accounts.append(kvs)
        elif section == "[tajiduo.tasks]":
            tajiduo_tasks_keys = kvs
        elif section == "__top__":
            stray_keys = kvs

    # If stray keys look like account fields, add them as an account
    stray_account = {}
    for key, val in stray_keys:
        if key in ("refresh_token", "center_uid", "dev_code"):
            stray_account[key] = val
    if stray_account:
        tajiduo_accounts.append(list(stray_account.items()))

    # Rebuild the config using _read_toml / _write_toml approach
    # First, parse what we can from the original file
    data = {}

    # Parse general, kuro, schedule, notify from sections
    for section, kvs in sections.items():
        if section in ("__top__", "[[tajiduo.accounts]]", "[tajiduo.tasks]"):
            continue
        # Simplified: just collect key-value pairs
        # We'll use a different approach: parse the original file excluding corrupted parts

    # Better approach: build clean dict and write it
    # Read what we can from the non-corrupted parts
    try:
        # Try parsing individual sections by building a clean TOML string
        clean_parts = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                clean_parts.append(line)
                continue
            # Skip the misplaced [[tajiduo.accounts]] and its content
            # Skip stray key-value pairs at top level that belong to accounts
            clean_parts.append(line)

        # Actually, let's just build a clean config from what we can extract
        # Parse the original file line by line, skip corrupted parts
        pass
    except Exception:
        pass

    # Simplest robust approach: extract values and write clean TOML
    import re

    def extract_value(lines_list: list[str], key: str) -> str:
        for ln in lines_list:
            s = ln.strip()
            if s.startswith(key + "="):
                return s.split("=", 1)[1].strip()
        return ""

    # Extract kuro account info
    kuro_accounts = []
    in_kuro_account = False
    current_kuro = {}
    for line in lines:
        stripped = line.strip()
        if stripped == "[[kuro.accounts]]":
            if current_kuro:
                kuro_accounts.append(current_kuro)
            current_kuro = {}
            in_kuro_account = True
            continue
        if stripped.startswith("[") and in_kuro_account:
            if current_kuro:
                kuro_accounts.append(current_kuro)
            current_kuro = {}
            in_kuro_account = False
            continue
        if in_kuro_account and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            val = stripped.split("=", 1)[1].strip().strip('"')
            current_kuro[key] = val
    if current_kuro:
        kuro_accounts.append(current_kuro)

    # Extract tajiduo account info (from the corrupted structure)
    tajiduo_acc_list = []
    in_tajiduo_account = False
    current_td = {}
    # Also collect from stray end-of-file keys
    stray_td = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "[[tajiduo.accounts]]":
            if current_td:
                tajiduo_acc_list.append(current_td)
            current_td = {}
            in_tajiduo_account = True
            continue
        if stripped.startswith("[") and in_tajiduo_account and stripped != "[[tajiduo.accounts]]":
            if current_td:
                tajiduo_acc_list.append(current_td)
            current_td = {}
            in_tajiduo_account = False
            continue
        if in_tajiduo_account and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            val = stripped.split("=", 1)[1].strip().strip('"')
            if key in ("refresh_token", "center_uid", "dev_code"):
                current_td[key] = val
    if current_td:
        tajiduo_acc_list.append(current_td)

    # Collect stray account fields at end of file
    for line in lines[-10:]:
        stripped = line.strip()
        if "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            val = stripped.split("=", 1)[1].strip().strip('"')
            if key in ("refresh_token", "center_uid", "dev_code"):
                stray_td[key] = val
    if stray_td and not any(td.get("refresh_token") for td in tajiduo_acc_list):
        tajiduo_acc_list.append(stray_td)

    # Extract other sections
    def get_section_values(section_name: str) -> dict:
        result = {}
        in_section = False
        for line in lines:
            stripped = line.strip()
            if stripped == section_name:
                in_section = True
                continue
            if stripped.startswith("[") and in_section:
                in_section = False
                continue
            if in_section and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                val = stripped.split("=", 1)[1].strip()
                result[key] = val
        return result

    general = get_section_values("[general]")
    kuro_bbs = get_section_values("[kuro.bbs]")
    tajiduo_tasks = get_section_values("[tajiduo.tasks]")
    schedule = get_section_values("[schedule]")
    notify = get_section_values("[notify]")
    serverchan = get_section_values("[notify.serverchan]")
    telegram = get_section_values("[notify.telegram]")

    # Build clean TOML data
    clean = {}

    if general:
        gen = {}
        for k, v in general.items():
            if k == "concurrency":
                gen[k] = int(v)
            elif k == "delay":
                gen[k] = [float(x) for x in v.strip("[]").split(",")]
            elif k == "db_path":
                gen[k] = v.strip('"')
            elif k == "log_level":
                gen[k] = v.strip('"')
        clean["general"] = gen

    if kuro_bbs:
        bbs = {}
        for k, v in kuro_bbs.items():
            if k == "enabled":
                import ast
                try:
                    bbs[k] = ast.literal_eval(v)
                except Exception:
                    bbs[k] = ["sign", "detail", "like", "share"]
        clean.setdefault("kuro", {})["bbs"] = bbs

    if kuro_accounts:
        clean.setdefault("kuro", {})["accounts"] = kuro_accounts

    if tajiduo_tasks:
        tasks = {}
        for k, v in tajiduo_tasks.items():
            if k == "enabled":
                import ast
                try:
                    tasks[k] = ast.literal_eval(v)
                except Exception:
                    tasks[k] = ["browse_post_c", "like_post_c", "share"]
            elif k == "action_delay":
                tasks[k] = [float(x) for x in v.strip("[]").split(",")]
            elif k == "max_failures":
                tasks[k] = int(v)
        clean.setdefault("tajiduo", {})["tasks"] = tasks

    if tajiduo_acc_list:
        clean.setdefault("tajiduo", {})["accounts"] = tajiduo_acc_list

    if schedule:
        sched = {}
        for k, v in schedule.items():
            if k == "enabled":
                sched[k] = v.lower() == "true"
            elif k == "repeat":
                sched[k] = v.lower() == "true"
            elif k == "time":
                sched[k] = v.strip('"')
        clean["schedule"] = sched

    if notify:
        n = {}
        n["enabled"] = notify.get("enabled", "false").lower() == "true"
        if serverchan:
            n["serverchan"] = {k: v.strip('"') for k, v in serverchan.items()}
        if telegram:
            n["telegram"] = {k: v.strip('"') for k, v in telegram.items()}
        clean["notify"] = n

    # Write clean config
    _write_toml(path, clean)

    # Verify it parses
    try:
        _read_toml(path)
        return True
    except Exception:
        return False


def load_config(path: str = "config.toml") -> Config:
    p = Path(path)
    if not p.exists():
        print(f"配置文件不存在: {path}")
        print(f"请先创建配置文件，参考 config.toml.example")
        sys.exit(1)

    try:
        with open(p, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError:
        print(f"配置文件格式错误，尝试自动修复...")
        if _try_fix_corrupted_config(path):
            print(f"配置文件已自动修复")
            with open(p, "rb") as f:
                raw = tomllib.load(f)
        else:
            print(f"自动修复失败，请手动检查配置文件: {path}")
            print(f"或删除后重新创建: cp config.toml.example config.toml")
            sys.exit(1)

    cfg = Config(config_path=path)

    # general
    gen = raw.get("general", {})
    cfg.concurrency = gen.get("concurrency", 3)
    cfg.delay = tuple(gen.get("delay", [1.0, 3.0]))
    cfg.log_level = gen.get("log_level", "INFO")
    cfg.db_path = gen.get("db_path", "sign.db")

    # kuro accounts
    for acc in raw.get("kuro", {}).get("accounts", []):
        cfg.kuro_accounts.append(KuroAccount(
            cookie=acc.get("cookie", ""),
            uid=acc.get("uid", ""),
            game=acc.get("game", "waves"),
            did=acc.get("did", ""),
        ))

    # tajiduo accounts
    for acc in raw.get("tajiduo", {}).get("accounts", []):
        cfg.tajiduo_accounts.append(TajiduoAccount(
            refresh_token=acc.get("refresh_token", ""),
            center_uid=acc.get("center_uid", ""),
            dev_code=acc.get("dev_code", ""),
        ))

    # kuro bbs
    bbs = raw.get("kuro", {}).get("bbs", {})
    cfg.kuro_bbs = KuroBbsConfig(
        enabled=bbs.get("enabled", ["sign", "detail", "like", "share"]),
    )

    # tajiduo tasks
    tasks = raw.get("tajiduo", {}).get("tasks", {})
    cfg.tajiduo_tasks = TajiduoTaskConfig(
        enabled=tasks.get("enabled", ["browse_post_c", "like_post_c", "share"]),
        action_delay=tuple(tasks.get("action_delay", [0.5, 1.5])),
        max_failures=tasks.get("max_failures", 3),
    )

    # schedule
    sched = raw.get("schedule", {})
    cfg.schedule = ScheduleConfig(
        enabled=sched.get("enabled", False),
        time=sched.get("time", "06:00"),
        repeat=sched.get("repeat", False),
    )

    # notify
    notify = raw.get("notify", {})
    cfg.notify = NotifyConfig(
        enabled=notify.get("enabled", False),
        serverchan=ServerChanConfig(
            sckey=notify.get("serverchan", {}).get("sckey", ""),
        ),
        telegram=TelegramConfig(
            bot_token=notify.get("telegram", {}).get("bot_token", ""),
            chat_id=notify.get("telegram", {}).get("chat_id", ""),
        ),
    )

    return cfg


# ===== Account CRUD =====

def save_kuro_account(path: str, account: KuroAccount) -> None:
    """Append a kuro account to config.toml."""
    data = _read_toml(path)

    kuro = data.setdefault("kuro", {})
    accounts = kuro.setdefault("accounts", [])

    entry = {
        "cookie": account.cookie,
        "uid": account.uid,
        "game": account.game,
    }
    if account.did:
        entry["did"] = account.did

    accounts.append(entry)
    _write_toml(path, data)


def save_tajiduo_account(path: str, account: TajiduoAccount) -> None:
    """Append a tajiduo account to config.toml."""
    data = _read_toml(path)

    tajiduo = data.setdefault("tajiduo", {})
    accounts = tajiduo.setdefault("accounts", [])

    entry = {
        "refresh_token": account.refresh_token,
        "center_uid": account.center_uid,
    }
    if account.dev_code:
        entry["dev_code"] = account.dev_code

    accounts.append(entry)
    _write_toml(path, data)


def delete_account(path: str, platform: str, index: int) -> bool:
    """Delete an account from config.toml by platform and index. Returns True if deleted."""
    data = _read_toml(path)
    if not data:
        return False

    accounts = data.get(platform, {}).get("accounts", [])
    if index < 0 or index >= len(accounts):
        return False

    accounts.pop(index)

    if not accounts:
        data.get(platform, {}).pop("accounts", None)

    _write_toml(path, data)
    return True


# ===== Config updates =====

def update_schedule_config(path: str, time: str, repeat: bool, enabled: bool) -> None:
    """Update [schedule] section in config.toml."""
    data = _read_toml(path)
    data["schedule"] = {
        "enabled": enabled,
        "time": time,
        "repeat": repeat,
    }
    _write_toml(path, data)


def update_notify_config(path: str, enabled: bool, sckey: str = "", bot_token: str = "", chat_id: str = "") -> None:
    """Update [notify] section in config.toml."""
    data = _read_toml(path)
    data["notify"] = {
        "enabled": enabled,
        "serverchan": {"sckey": sckey},
        "telegram": {"bot_token": bot_token, "chat_id": chat_id},
    }
    _write_toml(path, data)


def update_tajiduo_refresh_token(path: str, center_uid: str, new_token: str) -> None:
    """Update the refresh_token for a tajiduo account in config.toml."""
    data = _read_toml(path)
    for acc in data.get("tajiduo", {}).get("accounts", []):
        if str(acc.get("center_uid", "")) == str(center_uid):
            acc["refresh_token"] = new_token
            _write_toml(path, data)
            return
