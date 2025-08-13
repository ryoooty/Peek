from __future__ import annotations


import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings


sqlite3.register_adapter(bool, int)
sqlite3.register_converter("BOOLEAN", lambda v: bool(int(v)))

_conn: sqlite3.Connection | None = None
_conn_path: Path | None = None
_stats_cache: Dict[str, Tuple[float, Any]] = {}


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


def _exec(sql: str, params: Tuple | Dict | None = None) -> sqlite3.Cursor:
    assert _conn is not None
    cur = _conn.execute(sql, params or ())
    _conn.commit()
    return cur


def _q(sql: str, params: Tuple | Dict | None = None) -> sqlite3.Cursor:
    assert _conn is not None
    return _conn.execute(sql, params or ())


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
        cache_tokens        INTEGER DEFAULT 0,    -- накопленные «кэш-токены» (повторные отправки)

        tz_offset_min       INTEGER,
        default_chat_mode   TEXT DEFAULT 'rp',
        default_resp_size   TEXT DEFAULT 'auto',
        default_model       TEXT,

        -- Live
        proactive_enabled    INTEGER DEFAULT 1,
        pro_per_day          INTEGER DEFAULT 2,      -- дефолт: 2 раза/сутки
        pro_min_gap_min      INTEGER DEFAULT 10,     -- дефолт: 10 минут
        pro_min_delay_min    INTEGER DEFAULT 60,     -- нижняя граница случайного интервала
        pro_max_delay_min    INTEGER DEFAULT 720,    -- верхняя граница случайного интервала
        pro_free_used        INTEGER DEFAULT 0,
        last_proactive_at    DATETIME,
        last_activity_at     DATETIME,
        is_chatting          INTEGER DEFAULT 0
    )"""
    )


    if not _has_col("messages", "usage_cost_rub"):
        _exec("ALTER TABLE messages ADD COLUMN usage_cost_rub REAL")

    if not _has_col("users", "pro_free_used"):
        _exec("ALTER TABLE users ADD COLUMN pro_free_used INTEGER DEFAULT 0")
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
        resp_size     TEXT DEFAULT 'auto',
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

    # broadcast log
    _exec(
        """
    CREATE TABLE IF NOT EXISTS broadcast_log (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id     TEXT NOT NULL,
        user_id    INTEGER NOT NULL,
        status     TEXT NOT NULL,
        error      TEXT,
        sent_at    DATETIME DEFAULT CURRENT_TIMESTAMP
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
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        approved_by INTEGER,
        approved_at DATETIME
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
    fandom: str | None = None,
    info_short: str | None = None,
    photo_id: str | None = None,
    photo_path: str | None = None,
) -> int:
    r = _q("SELECT id FROM characters WHERE name=?", (name,)).fetchone()
    if r:
        fields = []
        params: list[Any] = []
        if info_short is not None:
            fields.append("info_short=?")
            params.append(info_short)
        if fandom is not None:
            fields.append("fandom=?")
            params.append(fandom)
        if photo_id is not None:
            fields.append("photo_id=?")
            params.append(photo_id)
        if photo_path is not None:
            fields.append("photo_path=?")
            params.append(photo_path)
        if fields:
            params.append(r["id"])
            _exec(f"UPDATE characters SET {', '.join(fields)} WHERE id=?", tuple(params))
        return int(r["id"])
    cur = _exec(
        "INSERT INTO characters(name, fandom, info_short, photo_id, photo_path) VALUES (?,?,?,?,?)",
        (name, fandom, info_short, photo_id, photo_path),
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
    _exec("UPDATE characters SET photo_id=? WHERE id=?", (file_id, char_id))


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
def create_chat(
    user_id: int,
    char_id: int,
    *,
    mode: Optional[str] = None,
    resp_size: Optional[str] = None,
) -> int:
    u = get_user(user_id) or {}
    mode = mode or u.get("default_chat_mode") or "rp"
    resp_size = resp_size or u.get("default_resp_size") or "auto"
    r = _q(
        "SELECT COUNT(*) AS c FROM chats WHERE user_id=? AND char_id=?",
        (user_id, char_id),
    ).fetchone()
    seq_no = int((r["c"] or 0) + 1)
    cur = _exec(
        "INSERT INTO chats(user_id,char_id,mode,resp_size,seq_no) VALUES (?,?,?,?,?,?)",
        (user_id, char_id, mode, resp_size, seq_no),
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
) -> int:
    cur = _exec(
        "INSERT INTO messages(chat_id,is_user,content,usage_in,usage_out, usage_cost_rub) VALUES (?,?,?,?,?,?)",
        (chat_id, 1 if is_user else 0, content, usage_in, usage_out, usage_cost_rub),
    )
    _exec("UPDATE chats SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (chat_id,))
    return int(cur.lastrowid)


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
    _exec("DELETE FROM chats WHERE id=?", (chat_id,))
    return True


# ------------- Stats -------------
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


def usage_by_day(days: int = 7, *, use_cache: bool = True) -> List[Dict[str, Any]]:
    key = f"usage_day:{days}"
    if use_cache:
        cached = _cache_get(key, 60)
        if cached is not None:
            return cached
    rows = _q(
        """
        SELECT
          date(created_at) AS day,
          COUNT(*) AS messages,
          SUM(CASE WHEN is_user=1 THEN 1 ELSE 0 END) AS user_msgs,
          SUM(CASE WHEN is_user=0 THEN 1 ELSE 0 END) AS ai_msgs,
          SUM(COALESCE(usage_in,0)) AS in_tokens,
          SUM(COALESCE(usage_out,0)) AS out_tokens
        FROM messages
        WHERE created_at >= date('now', ?)
        GROUP BY day
        ORDER BY day DESC
        """,
        (f"-{days - 1} day",),
    ).fetchall()
    result = [dict(r) for r in rows]
    if use_cache:
        _cache_set(key, result)
    return result


def usage_by_week(weeks: int = 4, *, use_cache: bool = True) -> List[Dict[str, Any]]:
    key = f"usage_week:{weeks}"
    if use_cache:
        cached = _cache_get(key, 60)
        if cached is not None:
            return cached
    rows = _q(
        """
        SELECT
          strftime('%Y-%W', created_at) AS week,
          COUNT(*) AS messages,
          SUM(CASE WHEN is_user=1 THEN 1 ELSE 0 END) AS user_msgs,
          SUM(CASE WHEN is_user=0 THEN 1 ELSE 0 END) AS ai_msgs,
          SUM(COALESCE(usage_in,0)) AS in_tokens,
          SUM(COALESCE(usage_out,0)) AS out_tokens
        FROM messages
        WHERE created_at >= date('now', ?)
        GROUP BY week
        ORDER BY week DESC
        """,
        (f"-{weeks * 7 - 1} day",),
    ).fetchall()
    result = [dict(r) for r in rows]
    if use_cache:
        _cache_set(key, result)
    return result


def top_characters(limit: int = 5, days: int | None = None, *, use_cache: bool = True) -> List[Dict[str, Any]]:
    key = f"top_chars:{limit}:{days}"
    if use_cache:
        cached = _cache_get(key, 60)
        if cached is not None:
            return cached
    where = "WHERE m.is_user=0"
    params: List[Any] = []
    if days:
        where += " AND m.created_at >= date('now', ?)"
        params.append(f"-{days - 1} day")
    params.append(limit)
    rows = _q(
        f"""
        SELECT ch.id AS id, ch.name AS name, COUNT(*) AS cnt
          FROM messages m
          JOIN chats c ON c.id=m.chat_id
          JOIN characters ch ON ch.id=c.char_id
          {where}
         GROUP BY ch.id
         ORDER BY cnt DESC
         LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    result = [dict(r) for r in rows]
    if use_cache:
        _cache_set(key, result)
    return result


def active_users(limit: int = 5, days: int | None = None, *, use_cache: bool = True) -> List[Dict[str, Any]]:
    key = f"active_users:{limit}:{days}"
    if use_cache:
        cached = _cache_get(key, 60)
        if cached is not None:
            return cached
    where = ""
    params: List[Any] = []
    if days:
        where = "WHERE m.created_at >= date('now', ?)"
        params.append(f"-{days - 1} day")
    params.append(limit)
    rows = _q(
        f"""
        SELECT u.tg_id AS user_id, u.username AS username, COUNT(*) AS cnt
          FROM messages m
          JOIN chats c ON c.id=m.chat_id
          JOIN users u ON u.tg_id=c.user_id
          {where}
         GROUP BY u.tg_id
         ORDER BY cnt DESC
         LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    result = [dict(r) for r in rows]
    if use_cache:
        _cache_set(key, result)
    return result


def total_usage_cost_rub(user_id: int) -> float:
    r = _q(
        """
        SELECT COALESCE(SUM(m.usage_cost_rub),0) AS rub
          FROM messages m
          JOIN chats c ON c.id=m.chat_id
         WHERE c.user_id=? AND m.is_user=0
        """,
        (user_id,),
    ).fetchone()
    return float(r["rub"] or 0.0)

# ------------- Billing (toki/tokens) -------------
def add_toki(user_id: int, amount: int, meta: str = "bonus") -> None:
    _exec(
        "UPDATE users SET free_toki = free_toki + ? WHERE tg_id=?",
        (int(amount), user_id),
    )
    _exec(
        "INSERT INTO toki_log(user_id, amount, meta) VALUES (?,?,?)",
        (user_id, int(amount), meta),
    )


def add_paid_tokens(user_id: int, amount: int, meta: str = "topup") -> None:
    _exec(
        "UPDATE users SET paid_tokens = paid_tokens + ? WHERE tg_id=?",
        (int(amount), user_id),
    )
    _exec(
        "INSERT INTO toki_log(user_id, amount, meta) VALUES (?,?,?)",
        (user_id, int(amount), meta),
    )


def add_cache_tokens(user_id: int, amount: int) -> None:
    _exec(
        "UPDATE users SET cache_tokens = cache_tokens + ? WHERE tg_id=?",
        (int(amount), user_id),
    )


def spend_tokens(user_id: int, amount: int) -> Tuple[int, int, int]:
    """
    Списать amount биллинговых токенов: сначала free_toki, затем paid_tokens.
    Возвращает (spent_free, spent_paid, deficit). Если не хватило — deficit > 0 (ответ всё равно отправляется).
    """
    u = get_user(user_id) or {}
    ft = int(u.get("free_toki") or 0)
    pt = int(u.get("paid_tokens") or 0)
    need = int(max(0, amount))
    use_free = min(ft, need)
    need -= use_free
    use_paid = min(pt, need)
    need -= use_paid
    if use_free:
        _exec(
            "UPDATE users SET free_toki = free_toki - ? WHERE tg_id=?",
            (use_free, user_id),
        )
    if use_paid:
        _exec(
            "UPDATE users SET paid_tokens = paid_tokens - ? WHERE tg_id=?",
            (use_paid, user_id),
        )
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


def daily_bonus_free_users() -> int:
    amount = int(settings.subs.nightly_toki_bonus.get("free", 0))
    if amount <= 0:
        return 0
    rows = _q(
        """
        SELECT tg_id FROM users
         WHERE subscription='free'
           AND (last_daily_bonus_at IS NULL OR date(last_daily_bonus_at) < date('now','utc'))
        """
    ).fetchall()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    count = 0
    for r in rows:
        uid = int(r["tg_id"])
        add_toki(uid, amount, meta=f"daily:{today}")
        _exec(
            "UPDATE users SET last_daily_bonus_at=CURRENT_TIMESTAMP WHERE tg_id=?",
            (uid,),
        )
        count += 1
    return count


# ------------- Proactive helpers -------------
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
    cur = _exec(
        "INSERT INTO topups(user_id, amount, provider, status) VALUES (?,?,?, 'pending')",
        (user_id, float(amount), provider),
    )
    return int(cur.lastrowid)


def approve_topup(topup_id: int, admin_id: int) -> bool:
    r = _q(
        "SELECT user_id, amount, status FROM topups WHERE id=?", (topup_id,)
    ).fetchone()
    if not r or r["status"] != "pending":
        return False
    _exec(
        "UPDATE topups SET status='approved', approved_by=?, approved_at=CURRENT_TIMESTAMP WHERE id=?",
        (admin_id, topup_id),
    )
    add_paid_tokens(
        int(r["user_id"]), int(float(r["amount"]) * 1000)
    )  # пример: 1 у.е. = 1000 токенов
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
    row = _q(
        "SELECT user_id, chat_id FROM proactive_plan WHERE id=?", (int(plan_id),)
    ).fetchone()
    if row:
        insert_plan(int(row["user_id"]), int(row["chat_id"]), int(new_fire_at))
