from __future__ import annotations

import logging
import sqlite3
import threading
import time
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.config import BASE_DIR, settings


sqlite3.register_adapter(bool, int)
sqlite3.register_converter("BOOLEAN", lambda v: bool(int(v)))

_conn: sqlite3.Connection | None = None
_conn_path: Path | None = None
_stats_cache: Dict[str, Tuple[float, Any]] = {}
_conn_lock = threading.RLock()


topups_logger = logging.getLogger("topups")



# ------------- Core -------------
def init(path: str | Path) -> None:
    global _conn, _conn_path
    _conn_path = Path(path) if isinstance(path, str) else path
    _conn_path.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(
        str(_conn_path),
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        check_same_thread=False,
    )
    _conn.row_factory = sqlite3.Row
    _migrate()


def close() -> None:
    global _conn
    with _conn_lock:
        if _conn is not None:
            _conn.close()
            _conn = None


def _exec(sql: str, params: Tuple | Dict | None = None) -> sqlite3.Cursor:

    with _conn_lock:
        assert _conn is not None

        cur = _conn.execute(sql, params or ())
        _conn.commit()
        return cur


def _q(sql: str, params: Tuple | Dict | None = None) -> sqlite3.Cursor:
    with _conn_lock:
        assert _conn is not None

        return _conn.execute(sql, params or ())


def query(sql: str, params: Tuple | Dict | None = None) -> List[sqlite3.Row]:
    """Execute a SELECT query and return all rows.

    This is a public helper that wraps :func:`_q` and exposes the results as a
    list of :class:`sqlite3.Row` objects instead of a cursor.
    """
    return _q(sql, params).fetchall()


# --- Simple cache for heavy stat queries ---
def _cache_get(key: str, ttl: int) -> Any | None:
    data = _stats_cache.get(key)
    if not data:
        return None
    ts, value = data
    if time.time() - ts > ttl:
        return None
    return value


def _cache_set(key: str, value: Any) -> None:
    _stats_cache[key] = (time.time(), value)


# ------------- Schema -------------
def _has_col(table: str, col: str) -> bool:
    with _conn_lock:
        assert _conn is not None

        cur = _conn.execute(f"PRAGMA table_info({table})")
        return any(r[1] == col for r in cur.fetchall())


def _migrate() -> None:
    # users
    _exec(
        """
    CREATE TABLE IF NOT EXISTS users (
        tg_id               INTEGER PRIMARY KEY,
        username            TEXT,
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
        banned              INTEGER DEFAULT 0,
        ban_reason          TEXT,

        subscription        TEXT DEFAULT 'free',
        sub_end             DATETIME,

        -- Баланс в «токах/токенах»
        free_toki           INTEGER DEFAULT 0,    -- бесплатные (ночной бонус)
        paid_tokens         INTEGER DEFAULT 0,    -- платные токены
        last_bonus_date     TEXT,

        tz_offset_min       INTEGER,
        default_chat_mode   TEXT DEFAULT 'rp',
        default_model       TEXT,

        -- Chat
        proactive_enabled    INTEGER DEFAULT 1,
        pro_per_day          INTEGER DEFAULT 2,      -- дефолт: 2 раза/сутки
        pro_min_gap_min      INTEGER DEFAULT 10,     -- дефолт: 10 минут
        pro_min_delay_min    INTEGER DEFAULT 60,     -- мин. задержка между нуджами
        pro_max_delay_min    INTEGER DEFAULT 240,    -- макс. задержка между нуджами
        pro_free_used        INTEGER DEFAULT 0,
        last_proactive_at    DATETIME,
        last_activity_at     DATETIME,
        is_chatting          INTEGER DEFAULT 0

    )"""
    )
    if not _has_col("users", "pro_free_used"):
        _exec("ALTER TABLE users ADD COLUMN pro_free_used INTEGER DEFAULT 0")
    if not _has_col("users", "last_bonus_date"):
        _exec("ALTER TABLE users ADD COLUMN last_bonus_date TEXT")
    if not _has_col("users", "last_daily_bonus_at"):
        _exec("ALTER TABLE users ADD COLUMN last_daily_bonus_at DATETIME")


    # characters
    # >>> storage.py — в _migrate(), блок characters:
    _exec(
        """
    CREATE TABLE IF NOT EXISTS characters (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        slug         TEXT UNIQUE,
        name         TEXT NOT NULL,
        fandom       TEXT,
        short_prompt TEXT,
        mid_prompt   TEXT,
        long_prompt  TEXT,
        keywords     TEXT,
        photo_id     TEXT,
        info_short   TEXT,   -- краткая инфа для карточки
        created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
    )"""
    )
    if not _has_col("characters", "slug"):
        _exec("ALTER TABLE characters ADD COLUMN slug TEXT UNIQUE")
    if not _has_col("characters", "photo_id"):
        _exec("ALTER TABLE characters ADD COLUMN photo_id TEXT")
    if not _has_col("characters", "info_short"):
        _exec("ALTER TABLE characters ADD COLUMN info_short TEXT")
    # +++
    if not _has_col("characters", "photo_path"):
        _exec("ALTER TABLE characters ADD COLUMN photo_path TEXT")

    # chats
    _exec(
        """
    CREATE TABLE IF NOT EXISTS chats (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id       INTEGER NOT NULL,
        char_id       INTEGER NOT NULL,
        mode          TEXT DEFAULT 'rp',
        min_delay_ms  INTEGER DEFAULT 0,
        seq_no        INTEGER,
        is_favorite   INTEGER DEFAULT 0,
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP

    )"""
    )

    _exec(
        """
    CREATE TABLE IF NOT EXISTS proactive_plan (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        chat_id     INTEGER NOT NULL,
        fire_at     INTEGER NOT NULL,        -- unix ts
        status      TEXT NOT NULL DEFAULT 'PENDING', -- PENDING|SENT|SKIPPED
        created_at  INTEGER NOT NULL,
        sent_at     INTEGER

    )"""
    )
    if not _has_col("chats", "is_favorite"):
        _exec("ALTER TABLE chats ADD COLUMN is_favorite INTEGER DEFAULT 0")


    # messages
    _exec(
        """
    CREATE TABLE IF NOT EXISTS messages (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id     INTEGER NOT NULL,
        is_user     INTEGER NOT NULL,
        content     TEXT NOT NULL,
        usage_in    INTEGER,
        usage_out   INTEGER,
        usage_cost_rub REAL,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    )"""
    )

    # Full-text search mirror for messages
    _exec(
        """
    CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
        content,
        chat_id UNINDEXED,
        is_user UNINDEXED
    )"""
    )
    # Initial backfill if the FTS table is empty
    r = _q("SELECT COUNT(*) AS c FROM messages_fts").fetchone()
    if int(r["c"] or 0) == 0:
        _exec(
            "INSERT INTO messages_fts(rowid, content, chat_id, is_user) "
            "SELECT id, content, chat_id, is_user FROM messages"
        )

    # favorites (characters)
    _exec(
        """
    CREATE TABLE IF NOT EXISTS fav_chars (
        user_id     INTEGER NOT NULL,
        char_id     INTEGER NOT NULL,
        PRIMARY KEY(user_id, char_id)
    )"""
    )

    # proactive log (для нуджей)
    _exec(
        """

    CREATE TABLE IF NOT EXISTS proactive_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        chat_id     INTEGER,
        char_id     INTEGER,
        kind        TEXT DEFAULT 'regular', -- 'regular'|'free'|'paid'
        sent_at     DATETIME DEFAULT CURRENT_TIMESTAMP
    )"""
    )

    _exec(
        """
    CREATE TABLE IF NOT EXISTS token_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        amount      INTEGER NOT NULL,
        meta        TEXT,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    )"""
    )

    # payments (каркас)
    _exec(
        """
    CREATE TABLE IF NOT EXISTS topups (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        provider    TEXT,           -- 'boosty'|'donationalerts'|'manual'
        amount      REAL NOT NULL,
        status      TEXT DEFAULT 'pending', -- 'pending'|'approved'|'declined'
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        approved_by INTEGER,
        approved_at DATETIME
    )"""
    )
    if not _has_col("topups", "created_at"):
        _exec(
            "ALTER TABLE topups ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        )
    if not _has_col("topups", "tokens"):
        _exec("ALTER TABLE topups ADD COLUMN tokens INTEGER")
    if not _has_col("topups", "price_rub"):
        _exec("ALTER TABLE topups ADD COLUMN price_rub REAL")


    # broadcast log
    _exec(
        """
    CREATE TABLE IF NOT EXISTS broadcast_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        status      TEXT NOT NULL,
        note        TEXT,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    )"""
    )


    _exec(
        """
    CREATE TABLE IF NOT EXISTS transactions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        topup_id    INTEGER,
        user_id     INTEGER NOT NULL,
        amount      REAL NOT NULL,
        provider    TEXT,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    )"""
    )


    _exec(
        """
    CREATE TABLE IF NOT EXISTS toki_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        amount      INTEGER NOT NULL,
        meta        TEXT,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
    )"""
    )

    # Rename legacy mode label
    _exec("UPDATE users SET default_chat_mode = 'chat' WHERE default_chat_mode = 'live'")
    _exec("UPDATE chats SET mode = 'chat' WHERE mode = 'live'")


# ------------- Users -------------

def ensure_user(user_id: int, username: Optional[str] = None) -> None:
    row = _q("SELECT tg_id FROM users WHERE tg_id=?", (user_id,)).fetchone()
    if row:
        if username:
            _exec("UPDATE users SET username=? WHERE tg_id=?", (username, user_id))
        return
    _exec(
        "INSERT INTO users(tg_id, username) VALUES (?,?)",
        (user_id, username),
    )




def get_user(user_id: int) -> Dict[str, Any] | None:
    r = _q("SELECT * FROM users WHERE tg_id=?", (user_id,)).fetchone()
    return dict(r) if r else None


def set_user_field(user_id: int, field: str, value: Any) -> None:
    allowed = {
        "username",
        "subscription",
        "sub_end",
        "tz_offset_min",
        "default_chat_mode",
        "default_model",
        "proactive_enabled",
        "pro_per_day",
        "pro_window_local",
        "pro_window_utc",
        "pro_min_gap_min",
        "pro_min_delay_min",
        "pro_max_delay_min",
        "pro_free_used",
    }
    if field not in allowed:
        raise ValueError("invalid field")
    _exec(f"UPDATE users SET {field}=? WHERE tg_id=?", (value, user_id))


def touch_activity(user_id: int) -> None:
    _exec(
        "UPDATE users SET last_activity_at=CURRENT_TIMESTAMP WHERE tg_id=?",
        (user_id,),
    )


    
# ------------- Characters -------------
def ensure_character(
    name: str,
    *,
    slug: str | None = None,
    fandom: str | None = None,
    info_short: str | None = None,
    photo_id: str | None = None,
    photo_path: str | None = None,
) -> int:
    r = _q(
        "SELECT id, slug, photo_path FROM characters WHERE name=?", (name,)
    ).fetchone()

    # --- auto photo search by slug ---
    slug_to_use = slug or (r["slug"] if r else None)
    if photo_path is None and slug_to_use and (not r or not r["photo_path"]):
        media_dir = Path(BASE_DIR) / "media" / "characters"
        for ext in ("jpg", "png"):
            fp = media_dir / f"{slug_to_use}.{ext}"
            if fp.exists():
                photo_path = fp.as_posix()
                break

    if r:
        fields: list[str] = []
        params: list[Any] = []
        if slug is not None and slug != r["slug"]:
            fields.append("slug=?")
            params.append(slug)
        if info_short is not None:
            fields.append("info_short=?")
            params.append(info_short)
        if fandom is not None:
            fields.append("fandom=?")
            params.append(fandom)
        if photo_id is not None:
            fields.append("photo_id=?")
            params.append(photo_id)
        if photo_path is not None and photo_path != r["photo_path"]:
            fields.append("photo_path=?")
            params.append(photo_path)
        if fields:
            params.append(r["id"])
            _exec(
                f"UPDATE characters SET {', '.join(fields)} WHERE id=?",
                tuple(params),
            )
        return int(r["id"])
    cur = _exec(
        "INSERT INTO characters(name, slug, fandom, info_short, photo_id, photo_path) VALUES (?,?,?,?,?,?)",
        (name, slug, fandom, info_short, photo_id, photo_path),
    )
    return int(cur.lastrowid)

  


def get_character(char_id: int) -> Dict[str, Any] | None:
    r = _q("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
    return dict(r) if r else None


def list_characters_for_user(
    user_id: int, *, page: int, page_size: int
) -> List[Dict[str, Any]]:
    offset = max(0, (page - 1) * page_size)
    rows = _q(
        """
        SELECT c.*,
               CASE WHEN f.user_id IS NULL THEN 0 ELSE 1 END AS is_fav,
               MAX(ch.updated_at) AS last_use
          FROM characters c
          LEFT JOIN fav_chars f ON f.char_id=c.id AND f.user_id=?
          LEFT JOIN chats ch ON ch.char_id=c.id AND ch.user_id=?
         GROUP BY c.id
         ORDER BY is_fav DESC, COALESCE(last_use, 0) DESC, c.id DESC
         LIMIT ? OFFSET ?
    """,
        (user_id, user_id, page_size, offset),
    ).fetchall()
    return [dict(r) for r in rows]


def set_character_prompts(
    char_id: int,
    *,
    short: str | None = None,
    mid: str | None = None,
    long: str | None = None,
    keywords: str | None = None,
) -> None:
    row = get_character(char_id)
    if not row:
        return
    short = short if short is not None else row.get("short_prompt")
    mid = mid if mid is not None else row.get("mid_prompt")
    long = long if long is not None else row.get("long_prompt")
    keywords = keywords if keywords is not None else row.get("keywords")
    _exec(
        "UPDATE characters SET short_prompt=?, mid_prompt=?, long_prompt=?, keywords=? WHERE id=?",
        (short, mid, long, keywords, row["id"]),
    )


def set_character_photo_path(char_id: int, file_path: str) -> None:
    _exec("UPDATE characters SET photo_path=? WHERE id=?", (file_path, char_id))


def set_character_photo(char_id: int, file_id: str | None) -> None:
    """Store Telegram file ID for a character photo."""
    _exec("UPDATE characters SET photo_id=? WHERE id=?", (file_id, char_id))



def toggle_fav_char(
    user_id: int, char_id: int, *, allow_max: int | None = None
) -> bool:
    r = _q(
        "SELECT 1 FROM fav_chars WHERE user_id=? AND char_id=?",
        (user_id, char_id),
    ).fetchone()
    if r:
        _exec("DELETE FROM fav_chars WHERE user_id=? AND char_id=?", (user_id, char_id))
        return False
    if allow_max is not None:
        cnt = (
            _q(
                "SELECT COUNT(*) AS c FROM fav_chars WHERE user_id=?", (user_id,)
            ).fetchone()["c"]
            or 0
        )
        if int(cnt) >= int(allow_max):
            return False
    _exec(
        "INSERT OR IGNORE INTO fav_chars(user_id, char_id) VALUES (?,?)",
        (user_id, char_id),
    )
    return True


def is_fav_char(user_id: int, char_id: int) -> bool:
    r = _q(
        "SELECT 1 FROM fav_chars WHERE user_id=? AND char_id=?",
        (user_id, char_id),
    ).fetchone()
    return bool(r)


# ------------- Chats & Messages -------------
def update_user_chats_mode(user_id: int, new_mode: str) -> None:
    _exec("UPDATE chats SET mode=? WHERE user_id=?", (new_mode, user_id))


def create_chat(
    user_id: int,
    char_id: int,
    *,
    mode: Optional[str] = None,
) -> int:
    u = get_user(user_id) or {}
    mode = mode or u.get("default_chat_mode") or "rp"
    r = _q(
        "SELECT COUNT(*) AS c FROM chats WHERE user_id=? AND char_id=?",
        (user_id, char_id),
    ).fetchone()
    seq_no = int((r["c"] or 0) + 1)
    params = (user_id, char_id, mode, seq_no)
    assert len(params) == 4
    cur = _exec(
        "INSERT INTO chats(user_id,char_id,mode,seq_no) VALUES (?,?,?,?)",
        params,
    )
    return int(cur.lastrowid)


def get_chat(chat_id: int) -> Dict[str, Any] | None:
    r = _q(
        """
        SELECT c.*, ch.name as char_name, ch.photo_id as char_photo, ch.fandom as char_fandom
          FROM chats c
          JOIN characters ch ON ch.id=c.char_id
         WHERE c.id=?
    """,
        (chat_id,),
    ).fetchone()
    return dict(r) if r else None


def list_user_chats(user_id: int, *, page: int, page_size: int) -> List[Dict[str, Any]]:
    offset = max(0, (page - 1) * page_size)
    rows = _q(
        """
        SELECT c.*, ch.name as char_name
          FROM chats c
          JOIN characters ch ON ch.id=c.char_id
         WHERE c.user_id=?
         ORDER BY c.is_favorite DESC, c.updated_at DESC
         LIMIT ? OFFSET ?
    """,
        (user_id, page_size, offset),
    ).fetchall()
    return [dict(r) for r in rows]


def list_user_chats_by_char(
    user_id: int, char_id: int, *, limit: int = 10
) -> List[Dict[str, Any]]:
    rows = _q(
        """
        SELECT c.*, ch.name as char_name
          FROM chats c
          JOIN characters ch ON ch.id=c.char_id
         WHERE c.user_id=? AND c.char_id=?
         ORDER BY c.updated_at DESC
         LIMIT ?
    """,
        (user_id, char_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_last_chat(user_id: int) -> Dict[str, Any] | None:
    r = _q(
        """
        SELECT c.*, ch.name as char_name
          FROM chats c
          JOIN characters ch ON ch.id=c.char_id
         WHERE c.user_id=?
         ORDER BY c.updated_at DESC
         LIMIT 1
    """,
        (user_id,),
    ).fetchone()
    return dict(r) if r else None


def toggle_fav_chat(user_id: int, chat_id: int, *, allow_max: int) -> bool:
    ch = get_chat(chat_id) or {}
    if not ch or int(ch["user_id"]) != user_id:
        return False
    if ch["is_favorite"]:
        _exec("UPDATE chats SET is_favorite=0 WHERE id=?", (chat_id,))
        return False
    r = _q(
        "SELECT COUNT(*) AS c FROM chats WHERE user_id=? AND is_favorite=1",
        (user_id,),
    ).fetchone()
    if int(r["c"] or 0) >= int(allow_max):
        return False
    _exec("UPDATE chats SET is_favorite=1 WHERE id=?", (chat_id,))
    return True


def add_message(
    chat_id: int,
    *,
    is_user: bool,
    content: str,
    usage_in: int | None = None,
    usage_out: int | None = None,
    usage_cost_rub: float | None = None,
    commit: bool = True,
) -> int:

    """Insert a message and update related tables.

    All DB statements are executed within a transaction. By default the
    transaction is committed, but callers may disable auto-commit and manage
    the transaction themselves by passing ``commit=False``.
    """

    assert _conn is not None
    with _conn_lock:
        try:
            cur = _conn.execute(
                "INSERT INTO messages(chat_id,is_user,content,usage_in,usage_out, usage_cost_rub) VALUES (?,?,?,?,?,?)",
                (chat_id, 1 if is_user else 0, content, usage_in, usage_out, usage_cost_rub),
            )
            msg_id = int(cur.lastrowid)
            _conn.execute(
                "INSERT INTO messages_fts(rowid, content, chat_id, is_user) VALUES (?,?,?,?)",
                (msg_id, content, chat_id, 1 if is_user else 0),
            )
            _conn.execute(
                "UPDATE chats SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (chat_id,),
            )
        except Exception:
            if commit:
                _conn.rollback()
            raise
        else:
            if commit:
                _conn.commit()
        return msg_id


def compress_history(

    chat_id: int,
    summary: str,
    *,
    usage_in: int | None = None,
    usage_out: int | None = None,
) -> None:
    """Удаляет сообщения чата и сохраняет краткое содержание."""

    assert _conn is not None
    with _conn_lock:
        with _conn:
            _conn.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
            _conn.execute("DELETE FROM messages_fts WHERE chat_id=?", (chat_id,))
            add_message(
                chat_id,
                is_user=False,
                content=summary,
                usage_in=usage_in,
                usage_out=usage_out,
                commit=False,
            )


def list_messages(chat_id: int, *, limit: int | None = None) -> List[Dict[str, Any]]:
    if limit:
        rows = _q(
            "SELECT * FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
        rows = list(reversed(rows))
    else:
        rows = _q(
            "SELECT * FROM messages WHERE chat_id=? ORDER BY id", (chat_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def search_messages(chat_id: int, query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Search messages of a chat using full-text search."""
    # Strip characters that commonly break FTS queries
    query = re.sub(r'["*]', '', query).strip()
    if not query:
        return []
    try:
        rows = _q(
            """
            SELECT rowid AS id, content, chat_id, is_user
              FROM messages_fts
             WHERE messages_fts MATCH ? AND chat_id=?
             ORDER BY bm25(messages_fts)
             LIMIT ?
        """,
            (query, chat_id, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def last_message_ts(chat_id: int) -> Optional[datetime]:
    r = _q(
        "SELECT created_at FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT 1",
        (chat_id,),
    ).fetchone()
    if not r:
        return None
    try:
        # SQLite returns string; assume UTC naive -> as UTC
        return datetime.fromisoformat(r["created_at"]).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def export_chat_txt(chat_id: int) -> str:
    msgs = list_messages(chat_id)
    ch = get_chat(chat_id)
    ai = ch["char_name"] if ch else "AI"
    lines: List[str] = []
    for m in msgs:
        who = "User" if m["is_user"] else ai
        lines.append(f"[{who}] {m['content']}")
    return "\n".join(lines)


def delete_chat(chat_id: int, user_id: int) -> bool:
    ch = get_chat(chat_id)
    if not ch or int(ch["user_id"]) != user_id:
        return False
    _exec("DELETE FROM messages WHERE chat_id=?", (chat_id,))
    _exec("DELETE FROM messages_fts WHERE chat_id=?", (chat_id,))
    _exec("DELETE FROM proactive_plan WHERE chat_id=?", (chat_id,))
    _exec("DELETE FROM proactive_log WHERE chat_id=?", (chat_id,))
    _exec("DELETE FROM chats WHERE id=?", (chat_id,))
    return True


# ------------- Stats -------------
def _cached_stat(key: str, ttl: int, fn: Callable[[], Any]) -> Any:
    now = time.time()
    cached = _stats_cache.get(key)
    if cached and now - cached[0] < ttl:
        return cached[1]
    val = fn()
    _stats_cache[key] = (now, val)
    return val


def usage_by_day(days: int = 7, ttl: int = 60) -> List[Dict[str, Any]]:
    def _calc():
        start = (datetime.utcnow() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
        rows = _q(
            """
            SELECT date(created_at) AS day,
                   SUM(COALESCE(usage_in,0)) AS in_tokens,
                   SUM(COALESCE(usage_out,0)) AS out_tokens
              FROM messages
             WHERE created_at >= ?
             GROUP BY day
             ORDER BY day
            """,
            (start,),
        ).fetchall()
        return [dict(r) for r in rows]

    return _cached_stat(f"usage_day:{days}", ttl, _calc)


def usage_by_week(weeks: int = 4, ttl: int = 60) -> List[Dict[str, Any]]:
    def _calc():
        start = (datetime.utcnow() - timedelta(weeks=weeks - 1)).strftime("%Y-%m-%d")
        rows = _q(
            """
            SELECT strftime('%Y-%W', created_at) AS week,
                   SUM(COALESCE(usage_in,0)) AS in_tokens,
                   SUM(COALESCE(usage_out,0)) AS out_tokens
              FROM messages
             WHERE created_at >= ?
             GROUP BY week
             ORDER BY week
            """,
            (start,),
        ).fetchall()
        return [dict(r) for r in rows]

    return _cached_stat(f"usage_week:{weeks}", ttl, _calc)


def top_characters(limit: int = 5, ttl: int = 60) -> List[Dict[str, Any]]:
    def _calc():
        rows = _q(
            """
            SELECT ch.name AS name, COUNT(*) AS cnt
              FROM messages m
              JOIN chats c ON c.id=m.chat_id
              JOIN characters ch ON ch.id=c.char_id
             WHERE m.is_user=0
             GROUP BY ch.id
             ORDER BY cnt DESC
             LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]

    return _cached_stat(f"top_chars:{limit}", ttl, _calc)


def active_users(limit: int = 5, ttl: int = 60) -> List[Dict[str, Any]]:
    def _calc():
        rows = _q(
            """
            SELECT u.tg_id AS user_id,
                   u.username AS username,
                   COUNT(*) AS cnt
              FROM messages m
              JOIN chats c ON c.id=m.chat_id
              JOIN users u ON u.tg_id=c.user_id
             GROUP BY u.tg_id, u.username
             ORDER BY cnt DESC
             LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]

    return _cached_stat(f"active_users:{limit}", ttl, _calc)


def user_totals(user_id: int) -> Dict[str, Any]:
    msgs = _q(
        """
        SELECT
          SUM(CASE WHEN is_user=1 THEN 1 ELSE 0 END) AS user_msgs,
          SUM(CASE WHEN is_user=0 THEN 1 ELSE 0 END) AS ai_msgs,
          SUM(COALESCE(usage_in,0)) AS in_tokens,
          SUM(COALESCE(usage_out,0)) AS out_tokens
        FROM messages m JOIN chats c ON c.id=m.chat_id
        WHERE c.user_id=?
    """,
        (user_id,),
    ).fetchone()
    top = _q(
        """
        SELECT ch.name AS name, COUNT(*) AS cnt
          FROM messages m
          JOIN chats c ON c.id=m.chat_id
          JOIN characters ch ON ch.id=c.char_id
         WHERE c.user_id=? AND m.is_user=0
         GROUP BY ch.name
         ORDER BY cnt DESC
         LIMIT 1
    """,
        (user_id,),
    ).fetchone()
    return dict(
        user_msgs=int(msgs["user_msgs"] or 0),
        ai_msgs=int(msgs["ai_msgs"] or 0),
        in_tokens=int(msgs["in_tokens"] or 0),
        out_tokens=int(msgs["out_tokens"] or 0),
        top_character=(top["name"] if top else None),
        top_count=int(top["cnt"] or 0) if top else 0,
    )


# ------------- Billing (toki/tokens) -------------
def _log_token(cur: sqlite3.Cursor, user_id: int, amount: int, meta: str) -> None:
    """Persist a token balance change inside an open transaction."""
    cur.execute(
        "INSERT INTO token_log(user_id, amount, meta) VALUES (?,?,?)",
        (user_id, int(amount), meta),
    )


def list_token_log(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    rows = _q(
        "SELECT amount, meta, created_at FROM token_log WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, int(limit)),
    ).fetchall()
    return [dict(r) for r in rows]


def add_toki(user_id: int, amount: int, meta: str = "bonus") -> None:
    """Increase user's free_toki balance."""
    if amount < 0:
        raise ValueError("amount must be >= 0")
    assert _conn is not None
    with _conn_lock:
        cur = _conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        cur.execute(
            "UPDATE users SET free_toki = free_toki + ? WHERE tg_id=?",
            (int(amount), user_id),
        )
        _log_token(cur, user_id, int(amount), meta)
        _conn.commit()


def add_paid_tokens(user_id: int, amount: int, meta: str = "topup") -> None:
    """Increase user's paid_tokens balance."""
    if amount < 0:
        raise ValueError("amount must be >= 0")
    assert _conn is not None
    with _conn_lock:
        cur = _conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        cur.execute(
            "UPDATE users SET paid_tokens = paid_tokens + ? WHERE tg_id=?",
            (int(amount), user_id),
        )
        _log_token(cur, user_id, int(amount), meta)
        _conn.commit()


def spend_tokens(user_id: int, amount: int) -> Tuple[int, int, int]:
    """
    Списать amount биллинговых токенов: сначала free_toki, затем paid_tokens.
    Возвращает (spent_free, spent_paid, deficit). Если не хватило — deficit > 0 (ответ всё равно отправляется).
    """
    assert _conn is not None
    with _conn_lock:
        cur = _conn.cursor()
        cur.execute("BEGIN IMMEDIATE")

        row = cur.execute(
            "SELECT free_toki, paid_tokens FROM users WHERE tg_id=?",
            (user_id,),
        ).fetchone()
        ft = int(row["free_toki"] if row else 0)
        pt = int(row["paid_tokens"] if row else 0)

        need = int(max(0, amount))
        use_free = min(ft, need)
        need -= use_free
        use_paid = min(pt, need)
        need -= use_paid

        if use_free:
            cur.execute(
                "UPDATE users SET free_toki = free_toki - ? WHERE tg_id=?",
                (use_free, user_id),
            )
            _log_token(cur, user_id, -use_free, "spend_free")
        if use_paid:
            cur.execute(
                "UPDATE users SET paid_tokens = paid_tokens - ? WHERE tg_id=?",
                (use_paid, user_id),
            )
            _log_token(cur, user_id, -use_paid, "spend_paid")

        _conn.commit()
        return use_free, use_paid, need  # need==deficit


# Ночной бонус «токов»
def nightly_bonus_toki(user_id: int, amount: int) -> None:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    add_toki(user_id, amount, meta=f"nightly:{today}")


def get_toki_log(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    rows = _q(
        "SELECT amount, meta, created_at FROM toki_log WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, int(limit)),
    ).fetchall()
    return [dict(r) for r in rows]


def daily_bonus_free_users() -> List[int]:
    amount = int(settings.subs.nightly_toki_bonus.get("free", 0))
    if amount <= 0:
        return []
    rows = _q(
        """
        SELECT tg_id FROM users
         WHERE subscription='free'
           AND (last_daily_bonus_at IS NULL OR date(last_daily_bonus_at) < date('now','utc'))
        """
    ).fetchall()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    uids: List[int] = []
    for r in rows:
        uid = int(r["tg_id"])
        add_toki(uid, amount, meta=f"daily:{today}")
        _exec(
            "UPDATE users SET last_daily_bonus_at=CURRENT_TIMESTAMP WHERE tg_id=?",
            (uid,),
        )
        uids.append(uid)
    return uids


def expire_subscriptions(col: str | None = None) -> List[int]:
    """Downgrade users whose subscription has expired.

    Parameters
    ----------
    col:
        Optional name of the column that stores subscription end timestamp.
        When provided, the value must be one of the supported column names.

    Returns
    -------
    list[int]
        A list of affected user IDs.
    """
    allowed_cols = ("sub_expires_at", "sub_end")
    if col is not None:
        if col not in allowed_cols:
            raise ValueError("Invalid column name")
        if not _has_col("users", col):
            raise ValueError(f"Column {col} does not exist")
    else:
        for c in allowed_cols:
            if _has_col("users", c):
                col = c
                break
        if col is None:
            return []

    rows = _q(
        f"""
        SELECT tg_id FROM users
         WHERE subscription <> 'free'
           AND {col} IS NOT NULL
           AND {col} < CURRENT_TIMESTAMP
        """
    ).fetchall()

    uids: List[int] = []
    for r in rows:
        uid = int(r["tg_id"])
        _exec(
            f"UPDATE users SET subscription='free', {col}=NULL WHERE tg_id=?",
            (uid,),
        )
        uids.append(uid)
    return uids


# ------------- Proactive helpers -------------
def select_proactive_candidates() -> List[int]:
    """Return IDs of users eligible for proactive actions.

    A user is considered a candidate if proactive nudges are enabled,
    the user is not banned and they have at least one chat.  Only the
    user identifier (``tg_id``) is returned.
    """

    rows = _q(
        """
        SELECT u.tg_id
          FROM users AS u
         WHERE u.proactive_enabled = 1
           AND COALESCE(u.banned, 0) = 0
           AND EXISTS (
                SELECT 1 FROM chats AS c WHERE c.user_id = u.tg_id
           )
        """
    ).fetchall()
    return [int(r["tg_id"]) for r in rows]


def proactive_count_today(user_id: int) -> int:
    r = _q(
        """
        SELECT COUNT(*) AS c
          FROM proactive_log
         WHERE user_id=? AND date(sent_at)=date('now','utc')
        """,
        (user_id,),
    ).fetchone()
    return int(r["c"] or 0)



def log_proactive(
    user_id: int, chat_id: int, char_id: int, kind: str = "regular"
) -> None:
    _exec(
        "INSERT INTO proactive_log(user_id, chat_id, char_id, kind) VALUES (?,?,?,?)",
        (user_id, chat_id, char_id, kind),
    )
    _exec(
        "UPDATE users SET last_proactive_at=CURRENT_TIMESTAMP WHERE tg_id=?", (user_id,)
    )



# ------------- Payments -------------
def create_topup_pending(user_id: int, amount: float, provider: str) -> int:
    tokens = int(float(amount) * 1000)
    cur = _exec(
        "INSERT INTO topups(user_id, amount, tokens, price_rub, provider, status) VALUES (?,?,?,?,?, 'pending')",
        (user_id, float(amount), tokens, float(amount), provider),
    )
    tid = int(cur.lastrowid)
    topups_logger.info(
        "user_id=%s tid=%s status=pending amount=%.3f tokens=%d",
        user_id,
        tid,
        float(amount),
        tokens,
    )
    return tid


def get_topup(topup_id: int):
    return _q("SELECT * FROM topups WHERE id=?", (topup_id,)).fetchone()


def delete_topup(topup_id: int) -> bool:
    cur = _exec("DELETE FROM topups WHERE id=? AND status='pending'", (topup_id,))
    return cur.rowcount > 0


def has_pending_topup(user_id: int) -> bool:
    r = _q(
        "SELECT 1 FROM topups WHERE user_id=? AND status='pending' LIMIT 1",
        (user_id,),
    ).fetchone()
    return r is not None



def get_active_topup(user_id: int) -> Dict[str, Any] | None:
    r = _q(
        "SELECT * FROM topups WHERE user_id=? AND status IN ('waiting_receipt','pending') ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    return dict(r) if r else None


def attach_receipt(topup_id: int, file_id: str) -> None:
    _exec(
        "UPDATE topups SET receipt_file_id=?, status='pending' WHERE id=?",
        (file_id, topup_id),
    )


def get_topup(topup_id: int) -> Dict[str, Any] | None:
    r = _q("SELECT * FROM topups WHERE id=?", (topup_id,)).fetchone()
    return dict(r) if r else None


def create_transaction(topup_id: int, user_id: int, amount: float, provider: str) -> int:
    cur = _exec(
        "INSERT INTO transactions(topup_id, user_id, amount, provider) VALUES (?,?,?,?)",
        (topup_id, user_id, float(amount), provider),
    )
    return int(cur.lastrowid)

def approve_topup(topup_id: int, admin_id: int) -> bool:
    r = _q(
        "SELECT user_id, amount, status, provider FROM topups WHERE id=?",
        (topup_id,),
    ).fetchone()
    if not r or r["status"] != "pending":
        return False
    uid = int(r["user_id"])
    amt = float(r["amount"] or 0)
    if amt <= 0:
        return False

    prov = str(r["provider"] or "")
    _exec(
        "UPDATE topups SET status='approved', approved_by=?, approved_at=CURRENT_TIMESTAMP WHERE id=?",
        (admin_id, topup_id),
    )
    tokens = int(amt * 1000)
    add_paid_tokens(uid, tokens)  # пример: 1 у.е. = 1000 токенов
    create_transaction(topup_id, uid, amt, prov)

    topups_logger.info(
        "user_id=%s tid=%s status=approved amount=%.3f tokens=%d",
        uid,
        topup_id,
        amt,

        tokens,
    )
    return True



def decline_topup(topup_id: int, admin_id: int) -> bool:
    r = _q("SELECT id, status FROM topups WHERE id=?", (topup_id,)).fetchone()
    if not r or r["status"] != "pending":
        return False
    _exec(
        "UPDATE topups SET status='declined', approved_by=?, approved_at=CURRENT_TIMESTAMP WHERE id=?",
        (admin_id, topup_id),
    )
    return True


def expire_old_topups(max_age_hours: int) -> List[int]:
    """Remove outdated topup requests and return affected user IDs."""
    if max_age_hours <= 0:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=int(max_age_hours))
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    rows = _q(
        """
        SELECT DISTINCT user_id FROM topups
         WHERE status IN ('waiting_receipt','pending')
           AND created_at < ?
        """,
        (cutoff_str,),
    ).fetchall()
    if not rows:
        return []
    uids = [int(r["user_id"]) for r in rows]
    _exec(
        "DELETE FROM topups WHERE status IN ('waiting_receipt','pending') AND created_at < ?",
        (cutoff_str,),
    )
    return uids




# ----- Chatting flag -----
def set_user_chatting(user_id: int, on: bool) -> None:
    _exec("UPDATE users SET is_chatting=? WHERE tg_id=?", (1 if on else 0, user_id))


def is_user_chatting(user_id: int) -> bool:
    r = _q("SELECT is_chatting FROM users WHERE tg_id=?", (user_id,)).fetchone()
    return bool(r and int(r["is_chatting"] or 0))


# ----- Proactive Plan -----
def get_user_settings(user_id: int) -> tuple[int, int]:
    u = get_user(user_id) or {}
    per_day = int(u.get("pro_per_day") or 2)
    min_gap_sec = int(u.get("pro_min_gap_min") or 10) * 60
    return per_day, min_gap_sec


def get_delay_range(user_id: int) -> tuple[int, int]:
    """Возвращает (min_delay_sec, max_delay_sec) с дефолтами."""
    u = get_user(user_id) or {}
    min_delay_sec = int(u.get("pro_min_delay_min") or 60) * 60
    max_delay_sec = int(u.get("pro_max_delay_min") or 240) * 60
    if max_delay_sec < min_delay_sec:
        max_delay_sec = min_delay_sec
    return min_delay_sec, max_delay_sec


def get_pending_plan(user_id: int) -> list[dict]:
    rows = _q(
        "SELECT * FROM proactive_plan WHERE user_id=? AND status='PENDING' ORDER BY fire_at",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def insert_plan(user_id: int, chat_id: int, fire_at: int) -> int:
    cur = _exec(
        "INSERT INTO proactive_plan(user_id,chat_id,fire_at,created_at) VALUES (?,?,?, strftime('%s','now'))",
        (user_id, chat_id, int(fire_at)),
    )
    return int(cur.lastrowid)


def delete_future_plan(user_id: int) -> None:
    _exec("DELETE FROM proactive_plan WHERE user_id=? AND status='PENDING'", (user_id,))


def get_due_plans(now_ts: int, limit: int = 100) -> list[dict]:
    rows = _q(
        "SELECT * FROM proactive_plan WHERE status='PENDING' AND fire_at<=? ORDER BY fire_at LIMIT ?",
        (int(now_ts), int(limit)),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_plan_sent(plan_id: int, ts: int) -> None:
    _exec(
        "UPDATE proactive_plan SET status='SENT', sent_at=? WHERE id=?",
        (int(ts), int(plan_id)),
    )


def skip_and_reschedule(plan_id: int, new_fire_at: int) -> None:
    _exec("UPDATE proactive_plan SET status='SKIPPED' WHERE id=?", (int(plan_id),))
    row = _q("SELECT user_id, chat_id FROM proactive_plan WHERE id=?", (int(plan_id),)).fetchone()
    if row:
        insert_plan(int(row["user_id"]), int(row["chat_id"]), int(new_fire_at))


# ------------- Broadcast log -------------

def log_broadcast_status(user_id: int, status: str, note: str | None = None) -> None:
    _exec(
        "INSERT INTO broadcast_log(user_id, status, note) VALUES (?,?,?)",
        (user_id, status, note),
    )


def log_broadcast_sent(user_id: int) -> None:
    log_broadcast_status(user_id, "sent")


def log_broadcast_error(user_id: int, note: str) -> None:
    log_broadcast_status(user_id, "error", note)

