"""SQLite riêng của HanSongLive: điểm người xem + cấu hình live."""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
DB_PATH = os.path.join(DATA_DIR, "live.db")
_lock = threading.RLock()
_conn = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS live_players (
  user_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  score INTEGER DEFAULT 0,
  correct INTEGER DEFAULT 0,
  answered INTEGER DEFAULT 0,
  best_streak INTEGER DEFAULT 0,
  gifts INTEGER DEFAULT 0,
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS live_config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS live_weekly (
  week TEXT NOT NULL,
  user_id TEXT NOT NULL,
  name TEXT NOT NULL,
  score INTEGER DEFAULT 0,
  diamonds INTEGER DEFAULT 0,
  PRIMARY KEY (week, user_id)
);
CREATE TABLE IF NOT EXISTS live_items (
  word_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  korean TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (word_id, kind)
);
CREATE TABLE IF NOT EXISTS live_rounds (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT DEFAULT (datetime('now')),
  word_id INTEGER,
  mode TEXT,
  special TEXT,
  answered INTEGER,
  correct INTEGER,
  comments INTEGER,
  viewers INTEGER
);
CREATE TABLE IF NOT EXISTS live_viewers (
  user_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  sessions INTEGER DEFAULT 0,
  joins INTEGER DEFAULT 0,
  comments INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  shares INTEGER DEFAULT 0,
  follows INTEGER DEFAULT 0,
  gifts INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS live_viewers_last ON live_viewers(last_seen);
"""


def _migrate(c):
    cols = {r[1] for r in c.execute("PRAGMA table_info(live_players)")}
    if "diamonds" not in cols:
        c.execute("ALTER TABLE live_players ADD COLUMN diamonds INTEGER DEFAULT 0")
        c.commit()


def conn():
    global _conn
    with _lock:
        if _conn is None:
            os.makedirs(DATA_DIR, exist_ok=True)
            _conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.executescript(SCHEMA)
            _migrate(_conn)
        return _conn


@contextmanager
def tx():
    with _lock:
        c = conn()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise


def q(sql, args=()):
    with _lock:
        return [dict(r) for r in conn().execute(sql, args).fetchall()]


def q1(sql, args=()):
    r = q(sql, args)
    return r[0] if r else None


def get_conf(key, default=None):
    r = q1("SELECT value FROM live_config WHERE key=?", (key,))
    return json.loads(r["value"]) if r else default


def set_conf(key, value):
    with tx() as c:
        c.execute("INSERT INTO live_config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, json.dumps(value)))
