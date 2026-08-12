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


def get_expense_by_id(expense_id, user_id):
    """
    Fetch an expense by ID, scoped to the given user.
    Returns sqlite3.Row object (dict-like) if found and owned by user, None otherwise.
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT id, user_id, amount, category, date, description FROM expenses WHERE id = ? AND user_id = ?",
        (expense_id, user_id)
    )
    expense = cursor.fetchone()
    db.close()
    return expense


def update_expense(expense_id, user_id, amount, category, date, description=None):
    """
    Update an expense, scoped to both id and user_id for ownership safety.
    Returns True if updated, False if not found or not owned.
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE expenses SET amount = ?, category = ?, date = ?, description = ? WHERE id = ? AND user_id = ?",
        (amount, category, date, description, expense_id, user_id)
    )
    db.commit()
    rows_affected = cursor.rowcount
    db.close()
    return rows_affected > 0
