import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash


def get_db():
    db_path = os.path.join(os.path.dirname(__file__), "..", "spendly.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
    """)
    db.commit()
    db.close()


def seed_db():
    db = get_db()
    cursor = db.cursor()

    # Check if users table already has data
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]

    if user_count > 0:
        db.close()
        return

    # Insert demo user
    demo_user_password = generate_password_hash("demo123")
    cursor.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", demo_user_password),
    )
    db.commit()

    # Get demo user id
    cursor.execute("SELECT id FROM users WHERE email = ?", ("demo@spendly.com",))
    user_id = cursor.fetchone()[0]

    # Insert 8 sample expenses across categories
    sample_expenses = [
        (user_id, 12.50, "Food", "2026-08-01", "Coffee and breakfast"),
        (user_id, 45.00, "Transport", "2026-08-02", "Uber to office"),
        (user_id, 120.00, "Bills", "2026-08-03", "Internet bill"),
        (user_id, 25.00, "Health", "2026-08-04", "Gym membership"),
        (user_id, 60.00, "Entertainment", "2026-08-05", "Movie tickets"),
        (user_id, 85.50, "Shopping", "2026-08-06", "New shoes"),
        (user_id, 15.00, "Food", "2026-08-07", "Lunch"),
        (user_id, 30.00, "Other", "2026-08-08", "Miscellaneous"),
    ]

    cursor.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        sample_expenses,
    )
    db.commit()
    db.close()


def get_user_by_email(email):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, name, email, password_hash FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    db.close()
    return user
