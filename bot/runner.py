"""Vong quet: doc tung nhom, luu bai, gui moi bai can in thanh mot tin Zalo."""
import json
import logging
import re
import time
from datetime import datetime

from . import facebook, zalo
from .lead_filter import analyze

log = logging.getLogger(__name__)

SEND_GAP_SECONDS = 2  # gian cach giua cac tin de khong bi Zalo gioi han


def format_post_date(timestamp):
    if not timestamp:
        return "Ngày đăng không rõ"
    return datetime.fromtimestamp(timestamp).astimezone().strftime("%d/%m/%Y %H:%M")


def format_link_message(category, group_name, published_label, published_at, content, url):
    """Mot tin Zalo cho mot bai, gon trong gioi han ky tu."""
    date = f"Facebook hiển thị: {published_label}" if published_label else format_post_date(published_at)
    head = f"🔔 {category or 'CẦN IN 3D'} · {group_name}\n🕒 {date}\n\n"
    tail = f"\n\n🔗 {url}"
    room = zalo.SAFE_LIMIT - len(head) - len(tail)
    preview = re.sub(r"https?://\S+", "", content or "").strip()
    preview = re.sub(r"\n{3,}", "\n\n", preview)
    if len(preview) > room:
        preview = preview[:max(0, room - 1)].rstrip() + "…"
    return head + preview + tail


def short_error(error):
    """Mot dong loi ngan, an link (co the chua token/ID)."""
    text = str(error).strip().splitlines()[0] if str(error).strip() else ""
    return re.sub(r"https?://\S+", "[link]", text)[:300]


class Runner:
    """mode: "send" gui Zalo, "dry-run" chi in ra man hinh, "bootstrap" luu lam moc khong gui."""

    def __init__(self, page, config, store, groups, mode="send", recheck=False, debug=False):
        self.page = page
        self.config = config
        self.store = store
        self.groups = groups
        self.mode = mode
        self.recheck = recheck
        self.debug = debug
        self.sent = 0           # so link da gui trong luot quet hien tai
        self._printed = set()   # dry-run: link da in

    @property
    def sending(self):
        return self.mode == "send"

    # ------------------------------------------------------------- quet

    def scan_all(self, keep_going=False):
        """Quet tat ca nhom mot luot; tra ve danh sach loi theo nhom.

        keep_going=False: loi o mot nhom duoc nem ra ngay (che do --once, --dry-run).
        keep_going=True: ghi loi va quet tiep nhom khac (che do chay lien tuc).
        """
        started = time.monotonic()
        self.sent = self.flush_pending() if self.sending else 0
        errors = []
        for group in self.groups:
            try:
                posts = facebook.scan_group(self.page, group, self.config, on_post=self._on_found)
            except facebook.SessionExpired:
                raise
            except Exception as error:
                if self.debug:
                    facebook.save_snapshot(self.page, group["name"])
                if not keep_going:
                    raise
                reason = short_error(error)
                log.error("Loi nhom %s: %s: %s", group["name"], type(error).__name__, reason)
                log.debug("Traceback loi nhom %s", group["name"], exc_info=True)
                errors.append(f"{group['name']}: {reason}")
                continue
            self._store(group, posts)
        if self.sending:
            self.sent += self.flush_pending()
            log.info("Xong luot quet sau %.0f giay: da gui %d link moi vao Zalo",
                     time.monotonic() - started, self.sent)
        return errors

    def run_forever(self, listener):
        """Quet ngay, roi cu interval_seconds quet lai; nhan "scan" trong Zalo de quet som."""
        interval = self.config["interval_seconds"]
        manual = False
        while True:
            errors = self.scan_all(keep_going=True)
            if manual:
                self._send_summary(errors)
            next_at = datetime.fromtimestamp(time.time() + interval).strftime("%H:%M")
            log.info("Luot quet tiep theo luc %s (hoac nhan \"scan\" trong nhom Zalo)", next_at)
            manual = listener.wait(interval)
            if manual:
                log.info("Nhan lenh scan tu Zalo: quet ngay")

    def _store(self, group, posts):
        added = 0
        for post in posts:
            if self.mode == "dry-run":
                self._print_post(post)
            else:
                added += self.store.record(post, pending=post["candidate"] and self.sending,
                                           recheck=self.recheck)
        log.info("%s: %d bai trong khung thoi gian, %d bai moi, %d can in",
                 group["name"], len(posts), added, sum(p["candidate"] for p in posts))

    def _on_found(self, post):
        """Gui ngay bai can in vua tim thay, khong doi quet xong ca nhom."""
        log.info("Tim thay bai can in: %s", post["url"])
        if self.mode == "dry-run":
            self._print_post(post)
            return
        self.store.record(post, pending=self.sending, recheck=self.recheck)
        if self.sending:
            self.sent += self.flush_pending()

    def _print_post(self, post):
        key = facebook.link_key(post["url"])
        if key in self._printed:
            return
        self._printed.add(key)
        tag = post["category"] or f"bo qua: {post['reason']}"
        date = post["published_label"] or format_post_date(post["published_at"])
        preview = " ".join(post["text"].split())[:150]
        print(f"[{tag}] {date} | {post['url']}\n    {preview}", flush=True)
        log.debug("Bai: %s", json.dumps(post, ensure_ascii=False))

    # ------------------------------------------------------------- gui

    def _skip_reason(self, row, seen):
        if not facebook.is_recent(row, self.config["lookback_days"]):
            return "cu hon khung thoi gian hoac khong ro ngay"
        if not any(facebook.canonical_link(row["url"], group) for group in self.config["groups"]):
            return "link khong thuoc nhom trong config.json"
        if not analyze(row["content"])["category"]:
            return "khong con khop bo loc"
        if facebook.link_key(row["url"]) in seen:
            return "trung link"
        if self.store.was_sent(row["url"]):
            return "da gui truoc do"
        return None

    def flush_pending(self):
        """Gui cac bai dang cho trong DB. Zalo loi -> dung, giu hang doi cho luot sau."""
        sent = 0
        seen = set()
        for row in self.store.pending():
            reason = self._skip_reason(row, seen)
            if reason:
                log.debug("Bo bai trong hang doi %s: %s", row["url"], reason)
                self.store.clear_pending(row["post_id"])
                continue
            seen.add(facebook.link_key(row["url"]))
            category = analyze(row["content"])["category"]
            message = format_link_message(category, row["group_name"], row["published_label"],
                                          row["published_at"], row["content"], row["url"])
            try:
                zalo.send_text(message)
            except zalo.ZaloError as error:
                log.warning("Chua gui duoc, giu trong hang doi: %s", error)
                break
            self.store.mark_sent(row["url"])
            self.store.clear_pending(row["post_id"])
            sent += 1
            log.info("Da gui vao Zalo: %s", row["url"])
            time.sleep(SEND_GAP_SECONDS)
        return sent

    def _send_summary(self, errors):
        note = (f"Quét xong: {self.sent} link mới." if self.sent else
                "Quét xong: chưa có bài cần in mới trong phạm vi đã đọc.")
        if errors:
            note += " Lỗi đọc nhóm: " + "; ".join(errors)
        try:
            zalo.send_text(note)
        except zalo.ZaloError as error:
            log.warning("Khong gui duoc tom tat: %s", error)
