"""SQLite: bai da doc, hang doi gui, link da gui (chong gui trung)."""
import logging
import sqlite3
import time

from .facebook import link_key

log = logging.getLogger(__name__)


class Store:
    def __init__(self, path, chat_id=""):
        self.recipient = f"zalo:{chat_id}"
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self):
        db = self.db
        db.execute("""CREATE TABLE IF NOT EXISTS posts (
            post_id TEXT PRIMARY KEY, group_name TEXT, url TEXT, content TEXT,
            matched TEXT, pending INTEGER NOT NULL, first_seen REAL NOT NULL)""")
        columns = {row[1] for row in db.execute("PRAGMA table_info(posts)")}
        for name, ddl in (("category", "TEXT NOT NULL DEFAULT ''"),
                          ("published_at", "REAL"),
                          ("published_label", "TEXT NOT NULL DEFAULT ''")):
            if name not in columns:
                db.execute(f"ALTER TABLE posts ADD COLUMN {name} {ddl}")
        db.execute("""CREATE TABLE IF NOT EXISTS sent_links (
            chat_id TEXT NOT NULL, link_key TEXT NOT NULL, sent_at REAL NOT NULL,
            PRIMARY KEY (chat_id, link_key))""")
        db.commit()

    def close(self):
        self.db.close()

    def record(self, post, pending, recheck=False):
        """Luu bai moi; tra ve True neu la bai chua tung thay.

        recheck=True: bai da biet nhung nay khop bo loc -> dua lai vao hang doi.
        """
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
            if recheck and pending and not cursor.rowcount:
                self.db.execute(
                    """UPDATE posts SET content=?, matched=?, category=?, published_at=?,
                           published_label=?, pending=1 WHERE post_id=?""",
                    (post["text"], post["matched"], post.get("category", ""),
                     post.get("published_at"), post.get("published_label", ""), post["id"]))
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

    def was_sent(self, url):
        return self.db.execute("SELECT 1 FROM sent_links WHERE chat_id=? AND link_key=?",
                               (self.recipient, link_key(url))).fetchone() is not None

    def mark_sent(self, url):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO sent_links VALUES (?, ?, ?)",
                            (self.recipient, link_key(url), time.time()))
