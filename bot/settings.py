"""Duong dan, config.json, .env va logging dung chung cho ca bot."""
import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config.json"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
DB_FILE = ROOT / "posts.sqlite3"
PROFILE_DIR = ROOT / "browser-profile"
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "bot.log"

# Facebook bat dang nhap lai: systemd khong tu khoi dong lai voi ma nay.
EXIT_SESSION_EXPIRED = 42

DEFAULTS = {
    "interval_seconds": 3600,
    "lookback_days": 7,
    "max_posts_per_group": 300,
    "max_scroll_rounds": 80,
    "article_selector": "[role='article']",
    "expand_labels": ["Xem thêm", "See more"],
}

log = logging.getLogger(__name__)


class ConfigError(RuntimeError):
    """Loi cau hinh nguoi dung tu sua duoc (config.json, .env)."""


# ---------------------------------------------------------------- config.json

def load_config(path=CONFIG_FILE):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"Khong thay {path.name}") from None
    except json.JSONDecodeError as error:
        raise ConfigError(f"{path.name} sai cu phap JSON o dong {error.lineno}: {error.msg}") from None

    config = {**DEFAULTS, **data}
    groups = config.get("groups") or []
    if not groups:
        raise ConfigError("Hay them it nhat mot group vao config.json")
    for index, group in enumerate(groups, start=1):
        missing = [key for key in ("name", "url", "group_keys") if not group.get(key)]
        if missing:
            raise ConfigError(f"config.json: group thu {index} thieu {', '.join(missing)}")
        if "THAY_" in group["url"]:
            raise ConfigError("Thay URL/group_keys mau trong config.json")
        group["group_keys"] = [str(key) for key in group["group_keys"]]
        group.setdefault("is_3d_group", True)

    config["interval_seconds"] = max(60, int(config["interval_seconds"]))
    config["lookback_days"] = max(1 / 24, float(config["lookback_days"]))
    return config


# ----------------------------------------------------------------------- .env

def load_env(path=ENV_FILE):
    """Nap .env vao os.environ (bien da dat san trong moi truong duoc giu nguyen)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def env(key):
    return os.environ.get(key, "").strip()


def save_env_value(key, value, path=ENV_FILE):
    """Ghi/cap nhat mot dong KEY=value trong .env (tao tu .env.example neu chua co)."""
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    elif ENV_EXAMPLE.exists():
        lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    else:
        lines = []
    for index, line in enumerate(lines):
        if not line.lstrip().startswith("#") and line.split("=", 1)[0].strip() == key:
            lines[index] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)  # o NTFS/exFAT co the khong co tac dung
    except OSError:
        pass
    os.environ[key] = value


# -------------------------------------------------------------------- logging

def setup_logging(debug=False):
    """Man hinh: INFO (DEBUG neu --debug). logs/bot.log: luon DEBUG, kem traceback day du."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if debug else logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S"))
    root.addHandler(console)

    try:
        LOG_DIR.mkdir(exist_ok=True)
        file = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    except OSError as error:
        log.warning("Khong ghi duoc file log %s: %s", LOG_FILE, error)
    else:
        file.setLevel(logging.DEBUG)
        file.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
        root.addHandler(file)

    # Thu vien ben ngoai chi can canh bao.
    for name in ("asyncio", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
