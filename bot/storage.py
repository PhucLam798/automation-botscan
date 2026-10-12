"""SQLite: bai da doc, hang doi gui, link da gui (chong gui trung), bai da binh luan."""
import hashlib
import logging
import re
import sqlite3
import time

from .facebook import link_key
from .lead_filter import normalize

log = logging.getLogger(__name__)

MIN_TEXT_KEY_LENGTH = 30  # bai qua ngan ("can in ib") de trung noi dung giua nguoi khac nhau


def text_key(content):
    """Khoa theo noi dung: cung mot bai dang lai/dang o nhieu nhom chi gui mot lan."""
    text = normalize(re.sub(r"https?://\S+", "", content or ""))
    text = re.sub(r"[^a-z0-9 ]+", "", text).strip()
    if len(text) < MIN_TEXT_KEY_LENGTH:
        return None
    return "text:" + hashlib.sha1(text.encode()).hexdigest()


class Store:
    def __init__(self, path, chat_id=""):
        self.recipient = f"zalo:{chat_id}"
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self._create()

    def _create(self):
        with self.db:
            self.db.execute("""CREATE TABLE IF NOT EXISTS posts (
                post_id TEXT PRIMARY KEY, group_name TEXT, url TEXT, content TEXT,
                matched TEXT, pending INTEGER NOT NULL, first_seen REAL NOT NULL,
                category TEXT NOT NULL DEFAULT '', published_at REAL,
                published_label TEXT NOT NULL DEFAULT '')""")
            self.db.execute("""CREATE TABLE IF NOT EXISTS sent_links (
                chat_id TEXT NOT NULL, link_key TEXT NOT NULL, sent_at REAL NOT NULL,
                PRIMARY KEY (chat_id, link_key))""")
            # Moi bai mot dong (link_key); text_key de bai dang lai/nhieu nhom chi binh luan mot lan.
            self.db.execute("""CREATE TABLE IF NOT EXISTS ai_replies (
                link_key TEXT PRIMARY KEY, text_key TEXT, url TEXT NOT NULL, group_name TEXT,
                kind TEXT NOT NULL DEFAULT '', need TEXT NOT NULL DEFAULT '', comment TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL)""")
            self.db.execute("CREATE INDEX IF NOT EXISTS ai_replies_text ON ai_replies (text_key)")
            self.db.execute("CREATE TABLE IF NOT EXISTS bot_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    def close(self):
        self.db.close()

    # ------------------------------------------------------------ link Zalo

    def record(self, post, pending):
        """Luu bai moi; tra ve True neu la bai chua tung thay."""
        duplicate = self.db.execute("SELECT 1 FROM posts WHERE url=? AND post_id<>? LIMIT 1",
                                    (post["url"], post["id"])).fetchone()
        if duplicate:
            return False
        with self.db:
            cursor = self.db.execute(
                """INSERT OR IGNORE INTO posts (post_id, group_name, url, content, matched, pending,
                       first_seen, category, published_at, published_label)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (post["id"], post["group"], post["url"], post["text"], post["matched"], int(pending),
                 time.time(), post.get("category", ""), post.get("published_at"),
                 post.get("published_label", "")))
        if cursor.rowcount:
            log.debug("Luu bai moi %s (cho gui: %s)", post["url"], bool(pending))
        return bool(cursor.rowcount)

    def pending(self):
        return [dict(row) for row in self.db.execute(
            "SELECT post_id, group_name, url, content, category, published_at, published_label "
            "FROM posts WHERE pending=1")]

    def clear_pending(self, post_id):
        with self.db:
            self.db.execute("UPDATE posts SET pending=0 WHERE post_id=?", (post_id,))

    def was_sent(self, url, content=None):
        """Da gui link nay, hoac mot bai cung noi dung (vd dang o nhieu nhom)."""
        keys = [key for key in (link_key(url), text_key(content)) if key]
        marks = ",".join("?" * len(keys))
        return self.db.execute(f"SELECT 1 FROM sent_links WHERE chat_id=? AND link_key IN ({marks})",
                               (self.recipient, *keys)).fetchone() is not None

    def mark_sent(self, url, content=None):
        now = time.time()
        with self.db:
            for key in (link_key(url), text_key(content)):
                if key:
                    self.db.execute("INSERT OR IGNORE INTO sent_links VALUES (?, ?, ?)",
                                    (self.recipient, key, now))

    # ------------------------------------------------------------ binh luan AI

    def ai_reply(self, url, content=None):
        """Dong ai_replies cua bai nay, hoac cua bai cung noi dung da binh luan (dang lai/nhieu nhom)."""
        row = self.db.execute("SELECT * FROM ai_replies WHERE link_key=?", (link_key(url),)).fetchone()
        key = text_key(content)
        if row is None and key:
            row = self.db.execute("SELECT * FROM ai_replies WHERE text_key=? AND status='commented' LIMIT 1",
                                  (key,)).fetchone()
        return dict(row) if row else None

    def save_ai_reply(self, post, status, need="", comment="", detail="", attempt=False):
        """status: skip (AI khong tra loi), commented, failed (dang loi, thu lai), bootstrap (bai cu, bo qua)."""
        with self.db:
            self.db.execute(
                """INSERT INTO ai_replies (link_key, text_key, url, group_name, kind, need, comment, status,
                       detail, attempts, updated_at) VALUES (?, ?, ?, ?, 'service', ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(link_key) DO UPDATE SET text_key=excluded.text_key,
                       need=excluded.need, comment=excluded.comment, status=excluded.status,
                       detail=excluded.detail, attempts=attempts + excluded.attempts,
                       updated_at=excluded.updated_at""",
                (link_key(post["url"]), text_key(post["text"]), post["url"], post.get("group", ""),
                 need, comment, status, detail, int(attempt), time.time()))

    def comments_since(self, seconds, group_name=None):
        sql = "SELECT COUNT(*) FROM ai_replies WHERE status='commented' AND updated_at>=?"
        args = [time.time() - seconds]
        if group_name is not None:
            sql += " AND group_name=?"
            args.append(group_name)
        return self.db.execute(sql, args).fetchone()[0]

    def recent_comments(self, limit=30):
        return [row[0] for row in self.db.execute(
            "SELECT comment FROM ai_replies WHERE status='commented' ORDER BY updated_at DESC LIMIT ?", (limit,))]

    def get_state(self, key, default=""):
        row = self.db.execute("SELECT value FROM bot_state WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_state(self, key, value):
        with self.db:
            self.db.execute("INSERT INTO bot_state VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                            (key, str(value)))
