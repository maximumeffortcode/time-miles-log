# db.py
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "time_miles.sqlite"


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                start_miles REAL NOT NULL,
                end_miles REAL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                notes TEXT
            )
            """
        )
        conn.commit()


def insert_start_log(date_str: str, start_miles: float, start_time: str, notes: str = ""):
    """Create an OPEN log (no end miles/time yet)."""
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO logs (date, start_miles, end_miles, start_time, end_time, notes)
            VALUES (?, ?, NULL, ?, NULL, ?)
            """,
            (date_str, start_miles, start_time, notes),
        )
        conn.commit()


def complete_log(log_id: int, end_miles: float, end_time: str):
    """Complete an existing log by filling in end miles/time."""
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE logs
            SET end_miles = ?, end_time = ?
            WHERE id = ?
            """,
            (end_miles, end_time, log_id),
        )
        conn.commit()


def fetch_open_logs():
    """Logs missing end_miles or end_time are considered OPEN."""
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT id, date, start_miles, end_miles, start_time, end_time, notes
            FROM logs
            WHERE end_miles IS NULL OR end_time IS NULL
            ORDER BY date DESC, id DESC
            """
        )
        return cur.fetchall()


def fetch_completed_logs():
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT id, date, start_miles, end_miles, start_time, end_time, notes
            FROM logs
            WHERE end_miles IS NOT NULL AND end_time IS NOT NULL
            ORDER BY date DESC, id DESC
            """
        )
        return cur.fetchall()


def delete_log(log_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM logs WHERE id = ?", (log_id,))
        conn.commit()
