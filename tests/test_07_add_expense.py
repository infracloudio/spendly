"""
Tests for Step 7 -- Add Expense.

Source of truth: .claude/specs/07-add-expense.md

Spec summary:
  - GET /expenses/add renders the add-expense form and requires login.
  - POST /expenses/add validates form input, inserts via `insert_expense`,
    and redirects to /profile on success. It also requires login.
  - Validation rules (Rules for implementation section):
      * amount: required, must parse as a positive number > 0
      * category: required, must be one of the 7 fixed categories
      * date: required, must be a valid YYYY-MM-DD date
      * description: optional; blank/whitespace-only is stored as NULL
      * On any validation error: re-render the form (200) with an error
        message and the previously submitted values pre-filled
  - `database/queries.py` exposes `insert_expense(user_id, amount, category,
    date, description)`.

Because `database/db.py.get_db()` connects to a hardcoded on-disk
"spendly.db" path (ignoring Flask config) and `database/queries.py` imports
`get_db` by name (`from database.db import get_db`), a plain monkeypatch of
`database.db.get_db` alone would not affect the already-bound name inside
`database.queries`. Both module-level bindings are patched below to point
at an isolated, file-based SQLite database per test, following the same
approach already established in tests/test_06-date-filter.py.
"""

import re
import sqlite3
from datetime import date

import pytest

import database.db as db_module
import database.queries as queries_module
from database.queries import insert_expense
from app import app as flask_app

VALID_CATEGORIES = {
    "Food", "Transport", "Bills", "Health",
    "Entertainment", "Shopping", "Other",
}

TEST_EMAIL = "addexpense@example.com"
TEST_PASSWORD = "password123"


# --------------------------------------------------------------------------- #
# Low-level DB helpers (test-only; parameterised SQL per project rules)      #
# --------------------------------------------------------------------------- #

def _connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def fetch_expense_by(db_path, user_id, category, expense_date):
    """Look up an expense row directly, independent of the app/route layer."""
    conn = _connect(db_path)
    row = conn.execute(
        "SELECT id, user_id, amount, category, date, description "
        "FROM expenses WHERE user_id = ? AND category = ? AND date = ?",
        (user_id, category, expense_date),
    ).fetchone()
    conn.close()
    return row


def count_expenses_for(db_path, user_id, category, expense_date):
    conn = _connect(db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM expenses WHERE user_id = ? AND category = ? AND date = ?",
        (user_id, category, expense_date),
    ).fetchone()[0]
    conn.close()
    return count


def insert_test_user(db_path, email):
    """Create a bare user row directly (FK target for insert_expense unit tests)."""
    conn = _connect(db_path)
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Unit Test User", email, "not-a-real-hash"),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return row["id"]


# --------------------------------------------------------------------------- #
# HTML scraping helpers (attribute-order independent)                       #
# --------------------------------------------------------------------------- #

def extract_tag(html, tag, name):
    """Return the opening tag markup for <tag ... name="name" ...> (order-agnostic)."""
    pattern = rf'<{tag}\b[^>]*name=["\']{name}["\'][^>]*>'
    match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    return match.group(0) if match else None


def extract_select_block(html, name):
    """Return the inner HTML of a <select name="name">...</select> element."""
    pattern = rf'<select\b[^>]*name=["\']{name}["\'][^>]*>(.*?)</select>'
    match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else None


def extract_option_values(select_block):
    return re.findall(r'<option[^>]*value=["\']([^"\']*)["\']', select_block or "")


def extract_attr(tag_html, attr):
    if not tag_html:
        return None
    match = re.search(rf'{attr}=["\']([^"\']*)["\']', tag_html, re.IGNORECASE)
    return match.group(1) if match else None


def extract_form_tag(html):
    match = re.search(r'<form\b[^>]*>', html, re.IGNORECASE | re.DOTALL)
    return match.group(0) if match else None


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #

@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """
    Point both database.db.get_db() and database.queries.get_db() at an
    isolated, file-based SQLite DB for the duration of a single test.
    """
    path = str(tmp_path / "test_spendly.db")
    monkeypatch.setattr(db_module, "get_db", lambda: _connect(path))
    monkeypatch.setattr(queries_module, "get_db", lambda: _connect(path))
    return path


@pytest.fixture
def initialized_db(db_path):
    """Create the schema (no Flask app context required)."""
    db_module.init_db()
    return db_path


@pytest.fixture
def app(db_path):
    flask_app.config.update({"TESTING": True})
    with flask_app.app_context():
        db_module.init_db()
        db_module.seed_db()
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """A test client logged in as a freshly registered, expense-free user."""
    client.post(
        "/register",
        data={"name": "Add Expense Tester", "email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    response = client.post(
        "/login",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        follow_redirects=True,
    )
    assert response.status_code == 200, "Test user login must succeed"
    return client


@pytest.fixture
def auth_user_id(auth_client, db_path):
    conn = _connect(db_path)
    row = conn.execute("SELECT id FROM users WHERE email = ?", (TEST_EMAIL,)).fetchone()
    conn.close()
    assert row is not None, "Registered test user must exist"
    return row["id"]


# --------------------------------------------------------------------------- #
# 1. Unit tests -- insert_expense()                                          #
# --------------------------------------------------------------------------- #

class TestInsertExpenseUnit:
    def test_valid_data_is_inserted_and_queryable(self, initialized_db):
        user_id = insert_test_user(initialized_db, "unit1@example.com")

        insert_expense(user_id, 50.0, "Food", "2026-03-20", "Lunch")

        row = fetch_expense_by(initialized_db, user_id, "Food", "2026-03-20")
        assert row is not None, "Expected the inserted expense row to be queryable"
        assert row["user_id"] == user_id
        assert row["amount"] == 50.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"

    def test_null_description_is_stored_as_null(self, initialized_db):
        user_id = insert_test_user(initialized_db, "unit2@example.com")

        insert_expense(user_id, 12.34, "Transport", "2026-04-01", None)

        row = fetch_expense_by(initialized_db, user_id, "Transport", "2026-04-01")
        assert row is not None
        assert row["description"] is None, "description should be stored as NULL, not empty string"


# --------------------------------------------------------------------------- #
# 2. GET /expenses/add                                                        #
# --------------------------------------------------------------------------- #

class TestGetAddExpense:
    def test_unauthenticated_redirects_to_login(self, client):
        response = client.get("/expenses/add")
        assert response.status_code == 302
        assert "/login" in response.headers.get("Location", "")

    def test_authenticated_returns_200_with_form(self, auth_client):
        response = auth_client.get("/expenses/add")
        assert response.status_code == 200

    def test_authenticated_form_contains_all_required_fields(self, auth_client):
        html = auth_client.get("/expenses/add").data.decode("utf-8")

        amount_tag = extract_tag(html, "input", "amount")
        date_tag = extract_tag(html, "input", "date")
        description_tag = extract_tag(html, "input", "description")
        category_block = extract_select_block(html, "category")

        assert amount_tag is not None, "Expected an amount input field"
        assert date_tag is not None, "Expected a date input field"
        assert description_tag is not None, "Expected a description input field"
        assert category_block is not None, "Expected a category select field"

    def test_form_uses_post_method(self, auth_client):
        html = auth_client.get("/expenses/add").data.decode("utf-8")
        form_tag = extract_form_tag(html)

        assert form_tag is not None, "Expected a <form> element on the page"
        method = extract_attr(form_tag, "method")
        assert method is not None and method.lower() == "post", (
            "Add-expense form must submit via POST"
        )

    def test_category_select_offers_exactly_the_seven_fixed_categories(self, auth_client):
        html = auth_client.get("/expenses/add").data.decode("utf-8")
        block = extract_select_block(html, "category")
        assert block is not None, "Expected a category select field"

        values = {v for v in extract_option_values(block) if v}
        assert values == VALID_CATEGORIES, (
            f"Expected exactly the 7 fixed categories, got {values}"
        )

    def test_date_field_defaults_to_today(self, auth_client):
        html = auth_client.get("/expenses/add").data.decode("utf-8")
        date_tag = extract_tag(html, "input", "date")
        assert date_tag is not None

        value = extract_attr(date_tag, "value")
        assert value == date.today().isoformat(), (
            "Date field should default to today's date when the form has not been submitted"
        )


# --------------------------------------------------------------------------- #
# 3. POST /expenses/add                                                       #
# --------------------------------------------------------------------------- #

class TestPostAddExpense:
    def test_unauthenticated_redirects_to_login(self, client):
        response = client.post(
            "/expenses/add",
            data={"amount": "50.0", "category": "Food", "date": "2026-03-20", "description": "Lunch"},
        )
        assert response.status_code == 302
        assert "/login" in response.headers.get("Location", "")

    def test_unauthenticated_does_not_insert_a_row(self, client, db_path):
        client.post(
            "/expenses/add",
            data={"amount": "50.0", "category": "Food", "date": "2099-01-01", "description": "Should not save"},
        )
        db_module.init_db()  # ensure schema exists even though nothing was inserted
        conn = _connect(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE date = ?", ("2099-01-01",)
        ).fetchone()[0]
        conn.close()
        assert count == 0, "No expense should be persisted for an unauthenticated request"

    def test_valid_data_redirects_to_profile(self, auth_client):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "50.0", "category": "Food", "date": "2026-03-20", "description": "Lunch"},
        )
        assert response.status_code == 302
        assert "/profile" in response.headers.get("Location", "")

    def test_valid_data_is_saved_to_the_database(self, auth_client, db_path, auth_user_id):
        auth_client.post(
            "/expenses/add",
            data={"amount": "50.0", "category": "Food", "date": "2026-03-20", "description": "Lunch"},
        )

        row = fetch_expense_by(db_path, auth_user_id, "Food", "2026-03-20")
        assert row is not None, "Expected the new expense to exist in the database"
        assert row["amount"] == 50.0
        assert row["description"] == "Lunch"

    def test_missing_amount_rerenders_form_with_error(self, auth_client, db_path, auth_user_id):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "", "category": "Food", "date": "2026-05-01", "description": "No amount"},
        )
        html = response.data.decode("utf-8")

        assert response.status_code == 200, "Validation failure must re-render the form, not redirect"
        assert "error" in html.lower(), "Expected an error message in the response body"
        assert count_expenses_for(db_path, auth_user_id, "Food", "2026-05-01") == 0, (
            "No row should be inserted when amount is missing"
        )

    def test_missing_amount_retains_previously_submitted_values(self, auth_client):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "", "category": "Food", "date": "2026-05-01", "description": "Keep me"},
        )
        html = response.data.decode("utf-8")

        category_block = extract_select_block(html, "category")
        date_tag = extract_tag(html, "input", "date")
        description_tag = extract_tag(html, "input", "description")

        assert "Food" in extract_option_values(category_block), (
            "Submitted category should remain among rendered options"
        )
        assert extract_attr(date_tag, "value") == "2026-05-01", "Submitted date should be retained"
        assert extract_attr(description_tag, "value") == "Keep me", "Submitted description should be retained"

    def test_zero_amount_rerenders_form_with_error(self, auth_client, db_path, auth_user_id):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "0", "category": "Bills", "date": "2026-05-02", "description": ""},
        )
        html = response.data.decode("utf-8")

        assert response.status_code == 200
        assert "error" in html.lower(), "An amount of 0 must be rejected as not > 0"
        assert count_expenses_for(db_path, auth_user_id, "Bills", "2026-05-02") == 0

    def test_negative_amount_rerenders_form_with_error(self, auth_client, db_path, auth_user_id):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "-10", "category": "Bills", "date": "2026-05-03", "description": ""},
        )
        html = response.data.decode("utf-8")

        assert response.status_code == 200
        assert "error" in html.lower(), "A negative amount must be rejected"
        assert count_expenses_for(db_path, auth_user_id, "Bills", "2026-05-03") == 0

    def test_non_numeric_amount_rerenders_form_with_error(self, auth_client, db_path, auth_user_id):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "not-a-number", "category": "Health", "date": "2026-05-04", "description": ""},
        )
        html = response.data.decode("utf-8")

        assert response.status_code == 200
        assert "error" in html.lower(), "A non-numeric amount must be rejected"
        assert count_expenses_for(db_path, auth_user_id, "Health", "2026-05-04") == 0

    def test_invalid_category_rerenders_form_with_error(self, auth_client, db_path, auth_user_id):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "20.0", "category": "NotARealCategory", "date": "2026-05-05", "description": ""},
        )
        html = response.data.decode("utf-8")

        assert response.status_code == 200
        assert "error" in html.lower(), "An invalid category must be rejected"
        assert count_expenses_for(db_path, auth_user_id, "NotARealCategory", "2026-05-05") == 0

    def test_sql_injection_style_category_is_rejected_safely(self, auth_client, db_path, auth_user_id):
        malicious = "Food'; DROP TABLE expenses;--"
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "20.0", "category": malicious, "date": "2026-05-06", "description": ""},
        )
        html = response.data.decode("utf-8")

        assert response.status_code == 200, "Malicious category input must not crash the app"
        assert "error" in html.lower(), "A category outside the fixed list must be rejected, even if malicious"

        # Confirm the table and app are still intact afterward.
        follow_up = auth_client.get("/expenses/add")
        assert follow_up.status_code == 200

    def test_invalid_date_rerenders_form_with_error(self, auth_client, db_path, auth_user_id):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "20.0", "category": "Shopping", "date": "not-a-date", "description": ""},
        )
        html = response.data.decode("utf-8")

        assert response.status_code == 200
        assert "error" in html.lower(), "An invalid date string must be rejected"

    def test_invalid_date_format_rerenders_form_with_error(self, auth_client, db_path, auth_user_id):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "20.0", "category": "Shopping", "date": "20/05/2026", "description": ""},
        )
        html = response.data.decode("utf-8")

        assert response.status_code == 200
        assert "error" in html.lower(), "A non-ISO date format must be rejected"

    def test_missing_description_saves_with_null(self, auth_client, db_path, auth_user_id):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "30.0", "category": "Entertainment", "date": "2026-06-01"},
        )
        assert response.status_code == 302
        assert "/profile" in response.headers.get("Location", "")

        row = fetch_expense_by(db_path, auth_user_id, "Entertainment", "2026-06-01")
        assert row is not None
        assert row["description"] is None, "Omitted description should be stored as NULL"

    def test_blank_description_saves_with_null(self, auth_client, db_path, auth_user_id):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "15.0", "category": "Other", "date": "2026-06-02", "description": "   "},
        )
        assert response.status_code == 302

        row = fetch_expense_by(db_path, auth_user_id, "Other", "2026-06-02")
        assert row is not None
        assert row["description"] is None, "Whitespace-only description should be stripped and stored as NULL"
