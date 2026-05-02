import sqlite3
import os
from config import DATABASE_PATH


def get_connection():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS girls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact TEXT,
            photo_file_id TEXT NOT NULL,
            submitted_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            girl_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            score REAL NOT NULL,
            weight REAL DEFAULT 1.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (girl_id) REFERENCES girls(id),
            UNIQUE(girl_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS active_polls (
            girl_id INTEGER PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            message_id INTEGER,
            FOREIGN KEY (girl_id) REFERENCES girls(id)
        );

        CREATE TABLE IF NOT EXISTS whitelist (
            user_id INTEGER PRIMARY KEY
        );
    """)
    conn.commit()
    conn.close()


# ========== Whitelist (персистентный) ==========

def load_whitelist() -> set[int]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM whitelist")
    rows = cursor.fetchall()
    conn.close()
    return {row["user_id"] for row in rows}


def add_to_whitelist(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO whitelist (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()


def remove_from_whitelist(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM whitelist WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def is_in_whitelist(user_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM whitelist WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None


def get_all_whitelist() -> list[int]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM whitelist ORDER BY user_id")
    rows = cursor.fetchall()
    conn.close()
    return [row["user_id"] for row in rows]


# ========== Girls ==========

def add_girl(name: str, contact: str, photo_file_id: str, submitted_by: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO girls (name, contact, photo_file_id, submitted_by) VALUES (?, ?, ?, ?)",
        (name, contact, photo_file_id, submitted_by)
    )
    conn.commit()
    girl_id = cursor.lastrowid
    conn.close()
    return girl_id


def get_girl(girl_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM girls WHERE id = ?", (girl_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def get_all_girls_ranked():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            g.id, g.name, g.contact, g.photo_file_id,
            COALESCE(SUM(v.score * v.weight) / NULLIF(SUM(v.weight), 0), 0) as avg_score,
            COUNT(v.id) as vote_count
        FROM girls g
        LEFT JOIN votes v ON g.id = v.girl_id
        GROUP BY g.id
        ORDER BY avg_score DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def delete_girl(girl_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM votes WHERE girl_id = ?", (girl_id,))
    cursor.execute("DELETE FROM active_polls WHERE girl_id = ?", (girl_id,))
    cursor.execute("DELETE FROM girls WHERE id = ?", (girl_id,))
    conn.commit()
    conn.close()


# ========== Votes ==========

def add_vote(girl_id: int, user_id: int, score: float, weight: float = 1.0) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO votes (girl_id, user_id, score, weight) VALUES (?, ?, ?, ?)",
            (girl_id, user_id, score, weight)
        )
        is_new = True
    except sqlite3.IntegrityError:
        cursor.execute(
            "UPDATE votes SET score = ?, weight = ? WHERE girl_id = ? AND user_id = ?",
            (score, weight, girl_id, user_id)
        )
        is_new = False
    conn.commit()
    conn.close()
    return is_new


def get_weighted_average(girl_id: int) -> tuple:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT SUM(score * weight) / SUM(weight) as avg_score, COUNT(*) as count FROM votes WHERE girl_id = ?",
        (girl_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if row and row["count"] > 0:
        return (round(row["avg_score"], 2), row["count"])
    return (0.0, 0)


def has_user_voted(girl_id: int, user_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM votes WHERE girl_id = ? AND user_id = ?",
        (girl_id, user_id)
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


# ========== Active Polls ==========

def save_active_poll(girl_id: int, chat_id: int, message_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO active_polls (girl_id, chat_id, message_id) VALUES (?, ?, ?)",
        (girl_id, chat_id, message_id)
    )
    conn.commit()
    conn.close()


def remove_active_poll(girl_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM active_polls WHERE girl_id = ?", (girl_id,))
    conn.commit()
    conn.close()


def get_active_poll(girl_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM active_polls WHERE girl_id = ?", (girl_id,))
    row = cursor.fetchone()
    conn.close()
    return row