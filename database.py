import sqlite3
import random
import string
from datetime import datetime
from contextlib import contextmanager
import os

DB_PATH = os.getenv("DB_PATH", "confession_bot.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id   INTEGER PRIMARY KEY,
                anonymous_id  TEXT    UNIQUE NOT NULL,
                username      TEXT,
                first_name    TEXT,
                banned        INTEGER DEFAULT 0,
                allow_confess INTEGER DEFAULT 1,
                allow_dm      INTEGER DEFAULT 1,
                created_at    TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS confessions (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id           INTEGER NOT NULL,
                receiver_id         INTEGER,
                target_description  TEXT,
                message             TEXT,
                media_type          TEXT,
                media_file_id       TEXT,
                status              TEXT    DEFAULT 'pending',
                group_msg_id        INTEGER,
                created_at          TEXT    DEFAULT (datetime('now')),
                FOREIGN KEY(sender_id) REFERENCES users(telegram_id)
            );

            CREATE TABLE IF NOT EXISTS replies (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                confession_id  INTEGER NOT NULL,
                sender_id      INTEGER NOT NULL,
                receiver_id    INTEGER NOT NULL,
                message        TEXT    NOT NULL,
                created_at     TEXT    DEFAULT (datetime('now')),
                FOREIGN KEY(confession_id) REFERENCES confessions(id)
            );

            CREATE TABLE IF NOT EXISTS matches (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_a     INTEGER NOT NULL,
                user_b     INTEGER NOT NULL,
                matched_at TEXT    DEFAULT (datetime('now')),
                UNIQUE(user_a, user_b)
            );

            CREATE TABLE IF NOT EXISTS reports (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                reporter_id    INTEGER NOT NULL,
                confession_id  INTEGER,
                reason         TEXT,
                created_at     TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS rate_limits (
                telegram_id  INTEGER NOT NULL,
                action       TEXT    NOT NULL,
                window_start TEXT    NOT NULL,
                count        INTEGER DEFAULT 1,
                PRIMARY KEY (telegram_id, action)
            );

            CREATE INDEX IF NOT EXISTS idx_confessions_receiver ON confessions(receiver_id);
            CREATE INDEX IF NOT EXISTS idx_confessions_sender   ON confessions(sender_id);
            CREATE INDEX IF NOT EXISTS idx_confessions_status   ON confessions(status);
        """)

        # ── Migration: add new columns if they don't exist yet ──
        for col_sql in [
            "ALTER TABLE confessions ADD COLUMN target_description TEXT",
        ]:
            try:
                conn.execute(col_sql)
            except Exception:
                pass  # column already exists


# ── Users ────────────────────────────────────────────────────

def _gen_anon_id():
    prefix = random.choice(list("ABCDEFGHJKLMNPQRSTUVWXYZ"))
    suffix = "".join(random.choices(string.digits, k=4))
    return f"{prefix}{suffix}"


def get_or_create_user(telegram_id: int, username: str = None, first_name: str = None) -> sqlite3.Row:
    with get_conn() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        if user:
            return user
        # Generate unique anon ID
        while True:
            anon_id = _gen_anon_id()
            exists = conn.execute(
                "SELECT 1 FROM users WHERE anonymous_id = ?", (anon_id,)
            ).fetchone()
            if not exists:
                break
        conn.execute(
            "INSERT INTO users (telegram_id, anonymous_id, username, first_name) VALUES (?,?,?,?)",
            (telegram_id, anon_id, username, first_name),
        )
    return get_user_by_telegram_id(telegram_id)


def get_user_by_telegram_id(telegram_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()


def get_user_by_anon_id(anon_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE anonymous_id = ? COLLATE NOCASE", (anon_id,)
        ).fetchone()


def get_user_by_username(username: str) -> sqlite3.Row | None:
    """Lookup a user by their Telegram @username (case-insensitive, strip leading @)."""
    username = username.lstrip("@").lower()
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE LOWER(username) = ?", (username,)
        ).fetchone()


def ban_user(telegram_id: int, banned: bool = True):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET banned = ? WHERE telegram_id = ?",
            (1 if banned else 0, telegram_id),
        )


def update_setting(telegram_id: int, field: str, value: int):
    allowed = {"allow_confess", "allow_dm"}
    if field not in allowed:
        raise ValueError("Invalid setting field")
    with get_conn() as conn:
        conn.execute(f"UPDATE users SET {field} = ? WHERE telegram_id = ?", (value, telegram_id))


# ── Confessions ──────────────────────────────────────────────

def create_confession(
    sender_id: int,
    receiver_id: int = None,        # None = no specific user (public/nameless confession)
    message: str = None,
    media_type: str = None,
    media_file_id: str = None,
    target_description: str = None, # e.g. "sarah from class 5"
    status: str = "pending",
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO confessions
               (sender_id, receiver_id, message, media_type, media_file_id, target_description, status)
               VALUES (?,?,?,?,?,?,?)""",
            (sender_id, receiver_id, message, media_type, media_file_id, target_description, status),
        )
        return cur.lastrowid


def get_confession(confession_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM confessions WHERE id = ?", (confession_id,)
        ).fetchone()


def get_admin_review_confessions():
    """Return all confessions waiting for admin approval before posting to channel."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM confessions WHERE status = 'admin_review' ORDER BY created_at ASC LIMIT 20"
        ).fetchall()



def update_confession_status(confession_id: int, status: str, group_msg_id: int = None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE confessions SET status = ?, group_msg_id = ? WHERE id = ?",
            (status, group_msg_id, confession_id),
        )


def count_approved_confessions() -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM confessions WHERE status = 'approved'"
        ).fetchone()
        return row["c"]


# ── Replies ──────────────────────────────────────────────────

def create_reply(confession_id: int, sender_id: int, receiver_id: int, message: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO replies (confession_id, sender_id, receiver_id, message) VALUES (?,?,?,?)",
            (confession_id, sender_id, receiver_id, message),
        )
        return cur.lastrowid


# ── Crush Match ──────────────────────────────────────────────

def check_mutual_confession(user_a: int, user_b: int) -> bool:
    """Return True ONLY if BOTH users have valid (non-failed, non-rejected) confessions to each other."""
    # Only these statuses count as a real confession
    valid = ("pending", "approved", "private", "admin_review")
    placeholders = ",".join("?" * len(valid))
    with get_conn() as conn:
        a_to_b = conn.execute(
            f"SELECT 1 FROM confessions WHERE sender_id=? AND receiver_id=? AND status IN ({placeholders})",
            (user_a, user_b, *valid)
        ).fetchone()
        if not a_to_b:
            return False  # short-circuit — no need to check the other direction
        b_to_a = conn.execute(
            f"SELECT 1 FROM confessions WHERE sender_id=? AND receiver_id=? AND status IN ({placeholders})",
            (user_b, user_a, *valid)
        ).fetchone()
        return bool(b_to_a)


def record_match(user_a: int, user_b: int) -> bool:
    """Record match. Returns True if this is a new match."""
    lo, hi = min(user_a, user_b), max(user_a, user_b)
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT 1 FROM matches WHERE user_a=? AND user_b=?", (lo, hi)
        ).fetchone()
        if existing:
            return False
        conn.execute(
            "INSERT OR IGNORE INTO matches (user_a, user_b) VALUES (?,?)", (lo, hi)
        )
        return True


# ── Reports ──────────────────────────────────────────────────

def create_report(reporter_id: int, confession_id: int = None, reason: str = None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO reports (reporter_id, confession_id, reason) VALUES (?,?,?)",
            (reporter_id, confession_id, reason),
        )


def get_all_reports():
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM reports ORDER BY created_at DESC LIMIT 50"
        ).fetchall()


# ── Rate Limiting ────────────────────────────────────────────

def check_rate_limit(telegram_id: int, action: str, max_count: int, window_minutes: int) -> bool:
    """Returns True if allowed, False if rate limit exceeded."""
    now = datetime.utcnow()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM rate_limits WHERE telegram_id=? AND action=?",
            (telegram_id, action),
        ).fetchone()

        if row:
            window_start = datetime.fromisoformat(row["window_start"])
            elapsed = (now - window_start).total_seconds() / 60
            if elapsed > window_minutes:
                conn.execute(
                    "UPDATE rate_limits SET window_start=?, count=1 WHERE telegram_id=? AND action=?",
                    (now.isoformat(), telegram_id, action),
                )
                return True
            if row["count"] >= max_count:
                return False
            conn.execute(
                "UPDATE rate_limits SET count=count+1 WHERE telegram_id=? AND action=?",
                (telegram_id, action),
            )
        else:
            conn.execute(
                "INSERT INTO rate_limits (telegram_id, action, window_start) VALUES (?,?,?)",
                (telegram_id, action, now.isoformat()),
            )
        return True


# ── Stats ────────────────────────────────────────────────────

def get_stats() -> dict:
    with get_conn() as conn:
        users     = conn.execute("SELECT COUNT(*) as c FROM users WHERE banned=0").fetchone()["c"]
        total     = conn.execute("SELECT COUNT(*) as c FROM confessions").fetchone()["c"]
        approved  = conn.execute("SELECT COUNT(*) as c FROM confessions WHERE status='approved'").fetchone()["c"]
        pending   = conn.execute("SELECT COUNT(*) as c FROM confessions WHERE status='pending'").fetchone()["c"]
        matches   = conn.execute("SELECT COUNT(*) as c FROM matches").fetchone()["c"]
        reports   = conn.execute("SELECT COUNT(*) as c FROM reports").fetchone()["c"]
        return {
            "users": users,
            "total_confessions": total,
            "approved": approved,
            "pending": pending,
            "matches": matches,
            "reports": reports,
        }
