"""Zalo Bot Platform (https://bot.zaloplatforms.com).

Gui tin bang sendMessage, nhan lenh bang getUpdates (long polling),
nen KHONG can webhook, cloudflared hay URL cong khai.
Chi dung thu vien chuan cua Python.

API: POST https://bot-api.zaloplatforms.com/bot<TOKEN>/<method>
Tra ve {"ok": bool, "result": ..., "error_code": int, "description": str}.
getUpdates tra ve MOT update moi lan goi; ma 408 = het thoi gian cho, chua co tin.
"""
import json
import logging
import os
import queue
import re
import threading
import time
import urllib.error
import urllib.request
from collections import deque

log = logging.getLogger(__name__)

API_BASE = "https://bot-api.zaloplatforms.com"
TEXT_LIMIT = 2000          # gioi han ky tu moi tin cua Zalo Bot
SAFE_LIMIT = 1900          # chua khoang trong de an toan
SCAN_WORDS = {"scan", "/scan", "quét", "/quét", "quet", "/quet"}

ERROR_HINTS = {
    401: "token sai hoac da bi thu hoi; lay lai token tai bot.zaloplatforms.com",
    403: "bot khong co quyen gui vao cuoc tro chuyen nay (bot con trong nhom khong?)",
    404: "khong tim thay chat; kiem tra ZALO_CHAT_ID",
    429: "vuot gioi han/quota gui tin cua goi Zalo Bot; tin duoc giu lai de gui sau",
}


class ZaloError(RuntimeError):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def token():
    value = os.environ.get("ZALO_BOT_TOKEN", "").strip()
    if not value:
        raise ZaloError("Thieu ZALO_BOT_TOKEN trong .env")
    return value


def chat_id():
    value = os.environ.get("ZALO_CHAT_ID", "").strip()
    if not value:
        raise ZaloError("Thieu ZALO_CHAT_ID trong .env; chay: python3 main.py --chat-id")
    return value


def api(method, payload=None, timeout=40):
    request = urllib.request.Request(
        f"{API_BASE}/bot{token()}/{method}",
        data=json.dumps(payload or {}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        try:
            data = json.loads(error.read().decode("utf-8", "replace"))
        except Exception:
            data = {"ok": False, "error_code": error.code}
    except Exception:
        # Khong in exception goc: URL co chua token.
        raise ZaloError("Khong ket noi duoc Zalo Bot API") from None
    if not data.get("ok"):
        code = data.get("error_code")
        hint = ERROR_HINTS.get(code) or str(data.get("description") or "Zalo tu choi yeu cau")[:200]
        raise ZaloError(f"Zalo {method} loi {code}: {hint}", code)
    return data.get("result")


def get_me():
    return api("getMe")


def delete_webhook():
    """getUpdates khong chay khi con webhook, nen xoa webhook truoc khi poll."""
    try:
        api("deleteWebhook")
    except ZaloError as error:
        log.warning("deleteWebhook: %s", error)


def split_text(text, limit=SAFE_LIMIT):
    """Chia tin dai theo dong, khong cat ngang link."""
    text = text.strip()
    if len(text) <= limit:
        return [text]
    parts, current = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            parts.append(current)
            current = line
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def send_text(text, target=None):
    target = target or chat_id()
    for index, part in enumerate(split_text(text)):
        if index:
            time.sleep(1)
        api("sendMessage", {"chat_id": target, "text": part})
        log.debug("Da gui tin Zalo (%d ky tu)", len(part))


def get_update(timeout=30):
    """Mot update hoac None neu het thoi gian cho."""
    try:
        result = api("getUpdates", {"timeout": str(timeout)}, timeout=timeout + 10)
    except ZaloError as error:
        if error.code == 408:
            return None
        raise
    if isinstance(result, list):  # phong khi API doi sang tra ve danh sach
        return result
    return [result] if result else None


def parse_update(update):
    """(message_id, chat_id, chat_type, sender_id, sender_name, is_bot, date_seconds, text)."""
    message = (update or {}).get("message") or {}
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    date = message.get("date") or 0
    try:
        date = float(date)
        if date > 1e12:  # mili giay
            date /= 1000
    except (TypeError, ValueError):
        date = 0
    return (str(message.get("message_id", "")), str(chat.get("id", "")),
            str(chat.get("chat_type", "")), str(sender.get("id", "")),
            str(sender.get("display_name") or sender.get("name") or ""),
            bool(sender.get("is_bot")), date, str(message.get("text") or "").strip())


def is_scan_command(text):
    words = re.findall(r"[/\w]+", text.lower())
    return len(words) <= 8 and any(word in SCAN_WORDS for word in words)


class Listener:
    """Luong phu: poll getUpdates, dua lenh 'scan' cua dung chat vao hang doi."""

    def __init__(self, target_chat):
        self.target = str(target_chat)
        self.commands = queue.Queue()
        self.started = time.time()
        self._seen = deque(maxlen=500)
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="zalo-poll", daemon=True)

    def start(self):
        delete_webhook()
        self.thread.start()
        return self

    def stop(self):
        self._stop.set()

    def _run(self):
        failures = 0
        while not self._stop.is_set():
            try:
                updates = get_update(30) or []
                failures = 0
            except ZaloError as error:
                failures += 1
                log.warning("Loi nhan tin Zalo (lan %d): %s", failures, error)
                time.sleep(min(60, 5 * failures))
                continue
            for update in updates:
                self.handle(update)

    def handle(self, update):
        message_id, chat, _, _, _, is_bot, date, text = parse_update(update)
        if chat != self.target or is_bot or not text:
            return
        if message_id and message_id in self._seen:
            return
        self._seen.append(message_id)
        if date and date < self.started - 60:
            return  # tin gui luc bot tat; khong chay lai lenh cu
        if is_scan_command(text):
            log.debug("Lenh tu Zalo: %r", text)
            self.commands.put(text)

    def wait(self, seconds):
        """Ngu toi da `seconds`; tra ve True neu co lenh scan thi thuc som."""
        try:
            self.commands.get(timeout=max(1, seconds))
        except queue.Empty:
            return False
        while True:  # gop nhieu lan go 'scan' lien tiep thanh mot
            try:
                self.commands.get_nowait()
            except queue.Empty:
                return True


def discover_chats(seconds=120):
    """Cho tin nhan moi va tra ve cac chat da thay: {chat_id: (loai, ten nguoi gui, noi dung)}."""
    delete_webhook()
    found = {}
    deadline = time.time() + seconds
    while time.time() < deadline:
        updates = get_update(min(30, max(1, int(deadline - time.time())))) or []
        for update in updates:
            _, chat, chat_type, _, name, is_bot, _, text = parse_update(update)
            if chat and not is_bot and chat not in found:
                found[chat] = (chat_type or "?", name, text[:60])
                print(f"  Thay chat {chat} ({chat_type}) tu {name}: {text[:60]}", flush=True)
    return found
