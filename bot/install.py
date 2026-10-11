"""Cai dat va cau hinh lan dau: .venv + thu vien, token Zalo, ID nhom, service systemd.

Chi dung thu vien chuan, vi chay truoc khi .venv ton tai.
"""
import getpass
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

from . import zalo
from .settings import EXIT_SESSION_EXPIRED, PROFILE_DIR, ROOT, ConfigError, env, save_env_value

VENV = ROOT / ".venv"
VENV_PYTHON = VENV / "bin" / "python"
MAIN = ROOT / "main.py"
SERVICE_NAME = "zalo-bot"
UNIT_FILE = Path.home() / ".config" / "systemd" / "user" / f"{SERVICE_NAME}.service"


def _run(*command, check=True):
    print("$", " ".join(str(part) for part in command), flush=True)
    return subprocess.run([str(part) for part in command], check=check).returncode == 0


def _confirm(question):
    return sys.stdin.isatty() and input(f"{question} (y/N): ").strip().lower() == "y"


# ------------------------------------------------------------ moi truong Python

def ensure_venv():
    """Bao dam dang chay trong .venv co du thu vien; lan dau tu tao. Co the chay lai main.py."""
    if Path(sys.prefix).resolve() != VENV.resolve():
        if not VENV_PYTHON.exists():
            if sys.version_info < (3, 10):
                raise SystemExit("Can Python 3.10 tro len")
            print("== Lan dau chay: tao moi truong .venv", flush=True)
            try:
                # --copies: o NTFS/exFAT khong ho tro symlink
                _run(sys.executable, "-m", "venv", "--copies", VENV)
            except subprocess.CalledProcessError:
                raise SystemExit("Khong tao duoc .venv. Tren Ubuntu: sudo apt install python3-venv") from None
        os.execv(VENV_PYTHON, [str(VENV_PYTHON), str(MAIN), *sys.argv[1:]])
    if importlib.util.find_spec("playwright") is None:
        install_dependencies()


def install_dependencies():
    print("== Cai thu vien Python", flush=True)
    _run(VENV_PYTHON, "-m", "pip", "install", "--upgrade", "pip")
    _run(VENV_PYTHON, "-m", "pip", "install", "-r", ROOT / "requirements.txt")
    print("== Cai trinh duyet Chromium cho Playwright", flush=True)
    _run(VENV_PYTHON, "-m", "playwright", "install", "chromium")
    if sys.stdin.isatty():
        print("== Cai thu vien he thong cho Chromium (can mat khau sudo)", flush=True)
        if not _run("sudo", VENV_PYTHON, "-m", "playwright", "install-deps", "chromium", check=False):
            print("Canh bao: chua cai duoc thu vien he thong; neu Chromium loi hay chay lai --setup")


# ------------------------------------------------------------------ Zalo

def ask_token():
    """Hoi ZALO_BOT_TOKEN (an ky tu khi go) va luu vao .env."""
    if env("ZALO_BOT_TOKEN"):
        print("ZALO_BOT_TOKEN: da co, giu nguyen")
        return
    if not sys.stdin.isatty():
        return
    print("\nCan token bot Zalo: https://bot.zaloplatforms.com > dang nhap Zalo > tao bot > copy token")
    while True:
        value = getpass.getpass("Dan token (ky tu bi an khi go; Enter de bo qua): ").strip()
        if not value:
            print("Bo qua. Nho dien ZALO_BOT_TOKEN vao .env truoc khi chay bot")
            return
        if re.fullmatch(r"\d+:\S+", value) or _confirm("Token thuong co dang 123456789:abc... Van luu?"):
            break
    save_env_value("ZALO_BOT_TOKEN", value)
    print("Da luu token vao .env")


def choose_chat_id():
    """Cho tin nhan trong nhom Zalo, cho nguoi dung chon nhom va luu ZALO_CHAT_ID vao .env."""
    me = zalo.get_me() or {}
    name = me.get("account_name") or me.get("display_name") or me.get("name") or "bot"
    print(f"Bot Zalo: {name}")
    print("Trong 2 phut toi: vao NHOM Zalo da them bot, nhan tin co nhac ten bot")
    print("(go @ roi chon bot), vi du: @TenBot hello. Hoac nhan rieng cho bot.\n")
    found = zalo.discover_chats(120)
    if not found:
        print("Khong thay tin nao. Kiem tra bot da duoc them vao nhom, roi chay lai --chat-id.")
        return
    chats = list(found.items())
    print()
    for index, (chat, (kind, sender, text)) in enumerate(chats, start=1):
        print(f"  {index}. {chat}  [{kind}]  {sender}: {text}")
    choice = "1"
    if len(chats) > 1:
        choice = input("Chon so cua nhom muon nhan link (Enter = 1): ").strip() or "1"
    try:
        chat = chats[int(choice) - 1][0]
    except (ValueError, IndexError):
        print("Lua chon khong hop le; chua luu.")
        return
    save_env_value("ZALO_CHAT_ID", chat)
    print(f"Da luu ZALO_CHAT_ID={chat} vao .env")
    zalo.send_text("✅ Đã kết nối nhóm này với bot tìm khách in 3D. "
                   "Bot sẽ gửi từng link bài cần in vào đây.", chat)


def ensure_zalo_ready():
    """Can token va ID nhom de gui; neu thieu va dang o terminal thi hoi/tim ngay."""
    if not env("ZALO_BOT_TOKEN"):
        ask_token()
    if not env("ZALO_BOT_TOKEN"):
        raise ConfigError("Thieu ZALO_BOT_TOKEN trong .env; chay: python3 main.py --setup")
    if not env("ZALO_CHAT_ID") and sys.stdin.isatty():
        print("Chua co ID nhom Zalo. Them bot vao nhom roi lam theo huong dan:")
        choose_chat_id()
    if not env("ZALO_CHAT_ID"):
        raise ConfigError("Thieu ZALO_CHAT_ID trong .env; chay: python3 main.py --chat-id")


def setup():
    """--setup: cai/cap nhat thu vien, hoi token, in buoc tiep theo."""
    install_dependencies()
    print("== Token bot Zalo")
    ask_token()
    print("""
=== CAI DAT XONG ===
Tiep theo:
  1. Them bot vao nhom Zalo (trong nhom: Them thanh vien > tim ten bot)
  2. Lay ID nhom:          python3 main.py --chat-id
  3. Dang nhap Facebook:   python3 main.py --login
  4. Gui tin thu:          python3 main.py --send-test
  5. Chay bot:             python3 main.py""")


# --------------------------------------------------------------- systemd

def _unit_text():
    return f"""[Unit]
Description=Facebook 3D printing leads -> Zalo group
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={ROOT}
ExecStart="{VENV_PYTHON}" -u "{MAIN}"
Restart=on-failure
RestartSec=60
# Facebook bat dang nhap lai: khong tu khoi dong lai, bot da bao vao nhom Zalo
RestartPreventExitStatus={EXIT_SESSION_EXPIRED}
TimeoutStopSec=30
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""


def install_service():
    """Cai bot thanh service systemd --user: tu chay khi bat may, tu khoi dong lai khi loi."""
    if not env("ZALO_BOT_TOKEN"):
        raise ConfigError("Thieu ZALO_BOT_TOKEN trong .env; chay: python3 main.py --setup")
    if not env("ZALO_CHAT_ID"):
        raise ConfigError("Thieu ZALO_CHAT_ID; chay: python3 main.py --chat-id")
    if not PROFILE_DIR.is_dir():
        raise ConfigError("Chua dang nhap Facebook; chay: python3 main.py --login")
    if str(ROOT).startswith(("/run/media/", "/media/")):
        print(f"CANH BAO: thu muc dang o o gan ngoai ({ROOT}).")
        print("Khi khoi dong may, o nay co the chua duoc gan, service se loi.")
        print(f'Nen chuyen ve thu muc nha:  mv "{ROOT}" ~/zalo-bot && rm -rf ~/zalo-bot/.venv')
        if not _confirm("Van cai o vi tri nay?"):
            return
    UNIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    UNIT_FILE.write_text(_unit_text(), encoding="utf-8")
    _run("systemctl", "--user", "daemon-reload")
    _run("systemctl", "--user", "enable", "--now", SERVICE_NAME)
    # Cho service chay ca khi chua dang nhap / da dang xuat khoi Ubuntu.
    user = os.environ.get("USER") or getpass.getuser()
    if not _run("loginctl", "enable-linger", user, check=False):
        _run("sudo", "loginctl", "enable-linger", user, check=False)
    print(f"""
Da cai va bat service {SERVICE_NAME}.
  Xem log truc tiep : journalctl --user -u {SERVICE_NAME} -f   (hoac logs/bot.log)
  Trang thai        : systemctl --user status {SERVICE_NAME}
  Dung              : systemctl --user stop {SERVICE_NAME}
  Chay lai          : systemctl --user restart {SERVICE_NAME}   (sau khi sua config.json/.env)
  Go bo             : python3 main.py --remove-service""")


def remove_service():
    _run("systemctl", "--user", "disable", "--now", SERVICE_NAME, check=False)
    UNIT_FILE.unlink(missing_ok=True)
    _run("systemctl", "--user", "daemon-reload", check=False)
    print(f"Da go service {SERVICE_NAME}.")
