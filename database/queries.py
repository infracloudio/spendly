from database.db import get_db


def insert_expense(user_id, amount, category, date, description=None):
    """
    Insert a new expense record.
    Returns expense dict with id, user_id, amount, category, date, description, created_at.
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, date, description)
    )
    db.commit()

    cursor.execute("SELECT id, user_id, amount, category, date, description, created_at FROM expenses WHERE id = last_insert_rowid()")
    expense = cursor.fetchone()
    db.close()
    return expense
