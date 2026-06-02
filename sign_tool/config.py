from __future__ import annotations

import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
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


def load_config(path: str = "config.toml") -> Config:
    p = Path(path)
    if not p.exists():
        print(f"配置文件不存在: {path}")
        print(f"请先创建配置文件，参考 config.toml.example")
        sys.exit(1)

    with open(p, "rb") as f:
        raw = tomllib.load(f)

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


def save_kuro_account(path: str, account: KuroAccount) -> None:
    """Append a kuro account to config.toml."""
    p = Path(path)
    lines = p.read_text("utf-8").splitlines() if p.exists() else []

    # Find or create [kuro] section
    kuro_section_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "[kuro]" or line.strip().startswith("[kuro."):
            kuro_section_idx = i
            break

    if kuro_section_idx is None:
        lines.append("")
        lines.append("[[kuro.accounts]]")
    else:
        # Find last [[kuro.accounts]] or insert after [kuro]
        last_account_idx = kuro_section_idx
        for i in range(kuro_section_idx, len(lines)):
            if lines[i].strip() == "[[kuro.accounts]]":
                last_account_idx = i
        # Find end of last account block
        insert_idx = last_account_idx + 1
        while insert_idx < len(lines) and lines[insert_idx].strip() and not lines[insert_idx].strip().startswith("["):
            insert_idx += 1
        lines.insert(insert_idx, "")
        lines.insert(insert_idx + 1, "[[kuro.accounts]]")
        insert_idx += 2

        lines.insert(insert_idx, f'cookie = "{account.cookie}"')
        lines.insert(insert_idx + 1, f'uid = "{account.uid}"')
        lines.insert(insert_idx + 2, f'game = "{account.game}"')
        if account.did:
            lines.insert(insert_idx + 3, f'did = "{account.did}"')
        p.write_text("\n".join(lines), "utf-8")
        return

    lines.append(f'cookie = "{account.cookie}"')
    lines.append(f'uid = "{account.uid}"')
    lines.append(f'game = "{account.game}"')
    if account.did:
        lines.append(f'did = "{account.did}"')
    p.write_text("\n".join(lines), "utf-8")


def save_tajiduo_account(path: str, account: TajiduoAccount) -> None:
    """Append a tajiduo account to config.toml."""
    p = Path(path)
    lines = p.read_text("utf-8").splitlines() if p.exists() else []

    # Find [[tajiduo.accounts]] sections
    last_account_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "[[tajiduo.accounts]]":
            last_account_idx = i

    if last_account_idx is None:
        # Find [tajiduo] section or append
        tajiduo_section_idx = None
        for i, line in enumerate(lines):
            if line.strip() == "[tajiduo]" or line.strip().startswith("[tajiduo."):
                tajiduo_section_idx = i
                break
        if tajiduo_section_idx is None:
            lines.append("")
            lines.append("[[tajiduo.accounts]]")
        else:
            insert_idx = tajiduo_section_idx + 1
            lines.insert(insert_idx, "")
            lines.insert(insert_idx + 1, "[[tajiduo.accounts]]")
    else:
        # Find end of last account block
        insert_idx = last_account_idx + 1
        while insert_idx < len(lines) and lines[insert_idx].strip() and not lines[insert_idx].strip().startswith("["):
            insert_idx += 1
        lines.insert(insert_idx, "")
        lines.insert(insert_idx + 1, "[[tajiduo.accounts]]")
        insert_idx += 2

        lines.insert(insert_idx, f'refresh_token = "{account.refresh_token}"')
        lines.insert(insert_idx + 1, f'center_uid = "{account.center_uid}"')
        if account.dev_code:
            lines.insert(insert_idx + 2, f'dev_code = "{account.dev_code}"')
        p.write_text("\n".join(lines), "utf-8")
        return

    lines.append(f'refresh_token = "{account.refresh_token}"')
    lines.append(f'center_uid = "{account.center_uid}"')
    if account.dev_code:
        lines.append(f'dev_code = "{account.dev_code}"')
    p.write_text("\n".join(lines), "utf-8")


def delete_account(path: str, platform: str, index: int) -> bool:
    """Delete an account from config.toml by platform and index. Returns True if deleted."""
    p = Path(path)
    if not p.exists():
        return False
    lines = p.read_text("utf-8").splitlines()

    # Find all account blocks for the platform
    marker = f"[[{platform}.accounts]]"
    block_starts = []
    for i, line in enumerate(lines):
        if line.strip() == marker:
            block_starts.append(i)

    if index < 0 or index >= len(block_starts):
        return False

    start = block_starts[index]
    # Find end of block
    end = start + 1
    while end < len(lines):
        stripped = lines[end].strip()
        if stripped == "" or stripped.startswith("["):
            break
        end += 1

    # Also remove the marker line and any blank line before it
    del lines[start:end]

    # Remove trailing blank line before the block if exists
    if start > 0 and lines[start - 1].strip() == "":
        del lines[start - 1]

    p.write_text("\n".join(lines), "utf-8")
    return True


def update_schedule_config(path: str, time: str, repeat: bool, enabled: bool) -> None:
    """Update [schedule] section in config.toml."""
    p = Path(path)
    if not p.exists():
        return
    lines = p.read_text("utf-8").splitlines()

    # Find [schedule] section
    sched_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "[schedule]":
            sched_idx = i
            break

    if sched_idx is None:
        # Append new section
        lines.append("")
        lines.append("[schedule]")
        lines.append(f'enabled = {str(enabled).lower()}')
        lines.append(f'time = "{time}"')
        lines.append(f'repeat = {str(repeat).lower()}')
    else:
        # Replace existing section content
        end = sched_idx + 1
        while end < len(lines):
            stripped = lines[end].strip()
            if stripped == "" or stripped.startswith("["):
                break
            end += 1
        new_lines = [
            f'enabled = {str(enabled).lower()}',
            f'time = "{time}"',
            f'repeat = {str(repeat).lower()}',
        ]
        lines[sched_idx + 1:end] = new_lines

    p.write_text("\n".join(lines), "utf-8")


def update_notify_config(path: str, enabled: bool, sckey: str = "", bot_token: str = "", chat_id: str = "") -> None:
    """Update [notify] section in config.toml."""
    p = Path(path)
    if not p.exists():
        return
    lines = p.read_text("utf-8").splitlines()

    # Find [notify] section
    notify_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "[notify]":
            notify_idx = i
            break

    # Build new section content
    new_section = [
        "[notify]",
        f'enabled = {str(enabled).lower()}',
        "",
        "[notify.serverchan]",
        f'sckey = "{sckey}"',
        "",
        "[notify.telegram]",
        f'bot_token = "{bot_token}"',
        f'chat_id = "{chat_id}"',
    ]

    if notify_idx is None:
        # Append new section
        lines.append("")
        lines.extend(new_section)
    else:
        # Find end of notify section (including subsections)
        end = notify_idx + 1
        while end < len(lines):
            stripped = lines[end].strip()
            # Skip subsections too
            if stripped.startswith("[") and stripped != "[notify.serverchan]" and stripped != "[notify.telegram]":
                break
            if stripped == "" and end + 1 < len(lines) and lines[end + 1].strip().startswith("["):
                break
            end += 1
        lines[notify_idx:end] = new_section

    p.write_text("\n".join(lines), "utf-8")


def update_tajiduo_refresh_token(path: str, center_uid: str, new_token: str) -> None:
    """Update the refresh_token for a tajiduo account in config.toml."""
    p = Path(path)
    if not p.exists():
        return
    content = p.read_text("utf-8")
    lines = content.splitlines()

    # Find the account block matching center_uid
    in_block = False
    block_start = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "[[tajiduo.accounts]]":
            if in_block and block_start >= 0:
                # Previous block ended, check if it had our center_uid
                pass
            in_block = True
            block_start = i
        elif stripped.startswith("[") and in_block:
            # End of block without finding center_uid
            in_block = False
        elif in_block and stripped.startswith("center_uid") and center_uid in stripped:
            # Found the right block, now find refresh_token line
            for j in range(block_start, min(i + 10, len(lines))):
                if lines[j].strip().startswith("refresh_token"):
                    lines[j] = f'refresh_token = "{new_token}"'
                    p.write_text("\n".join(lines), "utf-8")
                    return
            return
