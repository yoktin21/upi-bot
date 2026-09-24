"""
SQLite storage: pending payment requests (FIFO queue for matching) and
final paid/access state.
"""
import sqlite3
import time
from contextlib import contextmanager

DB_PATH = "bot.db"


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id   INTEGER PRIMARY KEY,
                username      TEXT,
                note_code     TEXT,               -- unique code put in UPI 'tn' field
                status        TEXT DEFAULT 'none', -- none|pending|paid
                requested_at  INTEGER,
                paid_at       INTEGER,
                matched_by    TEXT,               -- 'email' | 'sms' | 'manual'
                match_detail  TEXT                -- raw snippet that matched, for audit
            )
        """)
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def upsert_user(telegram_id: int, username: str | None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (telegram_id, username) VALUES (?, ?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username",
            (telegram_id, username),
        )
        conn.commit()


def create_pending(telegram_id: int, note_code: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET note_code=?, status='pending', requested_at=? "
            "WHERE telegram_id=?",
            (note_code, int(time.time()), telegram_id),
        )
        conn.commit()


def get_user(telegram_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_id=?", (telegram_id,)
        ).fetchone()
        return dict(row) if row else None


def get_pending_oldest_first():
    """FIFO queue used for amount-only matching (email/SMS alerts that
    don't echo back the note/reference)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM users WHERE status='pending' ORDER BY requested_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_pending_by_note(note_code: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE status='pending' AND note_code=?", (note_code,)
        ).fetchone()
        return dict(row) if row else None


def mark_paid(telegram_id: int, matched_by: str, match_detail: str = ""):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET status='paid', paid_at=?, matched_by=?, match_detail=? "
            "WHERE telegram_id=?",
            (int(time.time()), matched_by, match_detail[:500], telegram_id),
        )
        conn.commit()


def get_paid_telegram_ids():
    with get_conn() as conn:
        rows = conn.execute("SELECT telegram_id FROM users WHERE status='paid'").fetchall()
        return [r["telegram_id"] for r in rows]
