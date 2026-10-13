"""Duong dan, config.json, .env va logging dung chung cho ca bot."""
import json
import logging
import os
import re
import sys
from pathlib import Path

from .lead_filter import exclude_pattern

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config.json"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
DB_FILE = ROOT / "posts.sqlite3"
PROFILE_DIR = ROOT / "browser-profile"

# Facebook bat dang nhap lai: systemd khong tu khoi dong lai voi ma nay.
EXIT_SESSION_EXPIRED = 42

DEFAULTS = {
    "interval_seconds": 7200,  # 2 gio
    "lookback_days": 1,       # 24 gio
    "max_posts_per_group": 300,
    "max_scroll_rounds": 80,
    "article_selector": "[role='article']",
    "expand_labels": ["Xem thêm", "See more"],
    "exclude_keywords": [],   # bai chua mot trong cac tu nay thi bo (khong gui Zalo, khong binh luan)
}

# Binh luan AI (Ollama local): muc "ai" trong config.json ghi de tung khoa.
AI_DEFAULTS = {
    "enabled": True,              # chay chinh (python3 main.py) co binh luan that
    "model": "gemma4:e2b",        # model Ollama (ollama list)
    "business_file": "makerspace.md",  # thong tin makerspace cho AI (chi duoc noi dieu co trong file)
    "website": "infinitemakerspace.com",  # luon gan cuoi binh luan
    "facebook_page": "facebook.com/infinitestudiomakerspace",  # fanpage, gan cuoi binh luan ("" = khong gan)
    "facebook_page_name": "Infinite Makerspace",  # ten Trang trong goi y @ cua Facebook: tag that ("" = chi gan link)
    "temperature": 0.8,           # cao hon = binh luan sang tao/da dang hon (0.3-1.0)
    "max_posts_per_run": 20,      # so bai AI doc moi luot (CPU cham: ~20-60 giay/bai)
    "max_comments_per_run": 3,
    "max_comments_per_day": 8,    # tinh 24 gio gan nhat; tuan dau nen de 2-3
    "max_comments_per_group_per_day": 3,
    "comment_gap_seconds": [480, 1200],  # nghi ngau nhien 8-20 phut giua hai binh luan
    "active_hours": [8, 22],      # chi binh luan tu 8:00 den truoc 22:00 (gio may)
    "min_post_age_minutes": 10,   # khong tra loi ngay khi bai vua dang (giong bot)
    "blocked_cooldown_hours": 72, # Facebook bao gioi han -> ngung binh luan
    "max_comment_chars": 180,     # ngan gon: 1-2 cau
    "notify_zalo": True,          # bao vao nhom Zalo moi binh luan da dang
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
    if not isinstance(config["exclude_keywords"], list):
        raise ConfigError('config.json: "exclude_keywords" phai la danh sach ["HN", "in resin", ...]')
    config["exclude_re"] = exclude_pattern(config["exclude_keywords"])
    config["ai"] = load_ai_config(config.get("ai"))
    return config


def load_ai_config(data):
    if data is not None and not isinstance(data, dict):
        raise ConfigError('config.json: "ai" phai la mot object {...}')
    ai = {**AI_DEFAULTS, **(data or {})}
    try:
        for key in ("max_posts_per_run", "max_comments_per_run", "max_comments_per_day",
                    "max_comments_per_group_per_day", "max_comment_chars", "min_post_age_minutes",
                    "blocked_cooldown_hours"):
            ai[key] = max(0, int(ai[key]))
        gap = ai["comment_gap_seconds"]
        low, high = (gap, gap) if isinstance(gap, (int, float)) else gap
        ai["comment_gap_seconds"] = (max(30, float(low)), max(30, float(low), float(high)))
        start, end = ai["active_hours"]
        ai["active_hours"] = (int(start) % 24, int(end) % 24 or 24)
    except (TypeError, ValueError):
        raise ConfigError('config.json: muc "ai" co gia tri so khong hop le') from None
    ai["max_comment_chars"] = max(100, ai["max_comment_chars"])
    ai["model"] = str(ai["model"]).strip()
    ai["website"], ai["facebook_page"] = (re.sub(r"^(?:https?://)?(?:www\.)?", "", str(ai[key]).strip()).strip("/")
                                          for key in ("website", "facebook_page"))
    ai["facebook_page_name"] = str(ai["facebook_page_name"]).strip().lstrip("@")
    try:
        ai["temperature"] = min(1.5, max(0.0, float(ai["temperature"])))
    except (TypeError, ValueError):
        raise ConfigError('config.json: "ai.temperature" phai la so (vd 0.8)') from None
    if not ai["website"]:
        raise ConfigError('config.json: "ai.website" khong duoc de trong')
    return ai


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
    """Chi in ra man hinh (khong luu file): INFO, DEBUG neu --debug. Chay service: xem bang journalctl."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if debug else logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S"))
    root.addHandler(console)

    # Thu vien ben ngoai chi can canh bao.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    # Ctrl+C luc Playwright dang chay de lai "Task was destroyed..." vo hai: an di.
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)
