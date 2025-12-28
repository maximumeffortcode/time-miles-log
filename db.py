# db.py
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("time_miles.sqlite")

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            start_miles REAL NOT NULL,
            end_miles REAL NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            notes TEXT
        )
    """)
    conn.commit()
    conn.close()

def insert_log(date, start_miles, end_miles, start_time, end_time, notes=""):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO logs 
        (date, start_miles, end_miles, start_time, end_time, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (date, start_miles, end_miles, start_time, end_time, notes))
    conn.commit()
    conn.close()

def fetch_logs():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, date, start_miles, end_miles, start_time, end_time, notes
        FROM logs
        ORDER BY date DESC, id DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

def delete_log(log_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM logs WHERE id = ?", (log_id,))
    conn.commit()
    conn.close()
