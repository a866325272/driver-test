"""作答紀錄（SQLite 單一檔案）。

stats   : 每題累計，抽題權重直接讀這張表
answers : 每次作答的完整紀錄；全域練習序號 seq = answers 的筆數
"""
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS stats (
    qid       INTEGER PRIMARY KEY,
    attempts  INTEGER NOT NULL DEFAULT 0,
    correct   INTEGER NOT NULL DEFAULT 0,
    streak    INTEGER NOT NULL DEFAULT 0,   -- 目前連續答對次數
    last_seq  INTEGER,                      -- 上次作答時的全域序號
    last_at   TEXT                          -- 上次作答時間（本地時間 ISO）
);
CREATE TABLE IF NOT EXISTS answers (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    qid      INTEGER NOT NULL,
    choice   INTEGER NOT NULL,
    correct  INTEGER NOT NULL,
    seq      INTEGER NOT NULL,
    at       TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        # sqlite3 連線的 with 只負責 commit/rollback，不會關閉，所以自己包一層
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def seq(self):
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM answers").fetchone()[0]

    def all_stats(self):
        with self._conn() as c:
            return {r["qid"]: dict(r) for r in c.execute("SELECT * FROM stats")}

    def get_stat(self, qid):
        with self._conn() as c:
            r = c.execute("SELECT * FROM stats WHERE qid = ?", (qid,)).fetchone()
            return dict(r) if r else None

    def record(self, qid, choice, is_correct):
        now = datetime.now().isoformat(timespec="seconds")
        ok = 1 if is_correct else 0
        with self.lock, self._conn() as c:
            seq = c.execute("SELECT COUNT(*) FROM answers").fetchone()[0] + 1
            c.execute("INSERT INTO answers (qid, choice, correct, seq, at) VALUES (?, ?, ?, ?, ?)",
                      (qid, choice, ok, seq, now))
            c.execute("""
                INSERT INTO stats (qid, attempts, correct, streak, last_seq, last_at)
                VALUES (?, 1, ?, ?, ?, ?)
                ON CONFLICT(qid) DO UPDATE SET
                    attempts = attempts + 1,
                    correct  = correct + excluded.correct,
                    streak   = CASE WHEN excluded.correct = 1 THEN streak + 1 ELSE 0 END,
                    last_seq = excluded.last_seq,
                    last_at  = excluded.last_at
            """, (qid, ok, ok, seq, now))
        return self.get_stat(qid)
