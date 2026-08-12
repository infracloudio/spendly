"""
Tests for Step 8 -- Edit Expense.

Source of truth: .claude/specs/08-edit-expense.md

Spec summary:
  - GET /expenses/<id>/edit renders an edit form pre-populated with the
    expense's current values. Logged-in only.
  - POST /expenses/<id>/edit validates the submission (same rules as add
    expense) and calls `update_expense`, redirecting to /profile on success.
    Logged-in only.
  - Ownership is enforced on both GET and POST: `get_expense_by_id` and
    `update_expense` are scoped to `id = ? AND user_id = ?`. If the expense
    does not exist, or belongs to another user, the route returns a 404.
  - Validation rules (identical to add expense):
      * amount: required, must parse as a positive number > 0
      * category: required, must be one of the 7 fixed categories
      * date: required, must be a valid YYYY-MM-DD date
      * description: optional; blank/whitespace-only is stored as NULL
      * On any validation error: re-render the form (200) with an error
        message and the *submitted* (not original) values pre-filled
  - `database/queries.py` exposes:
      * `get_expense_by_id(expense_id, user_id)` -> row or None
      * `update_expense(expense_id, user_id, amount, category, date, description)`
  - `profile.html` gains an "Edit" link per transaction row pointing to
    `/expenses/{{ tx.id }}/edit`.

Because `database/db.py.get_db()` connects to a hardcoded on-disk
"spendly.db" path (ignoring Flask config) and `database/queries.py` imports
`get_db` by name (`from database.db import get_db`), a plain monkeypatch of
`database.db.get_db` alone would not affect the already-bound name inside
`database.queries`. Both module-level bindings are patched below to point
at an isolated, file-based SQLite database per test, following the same
approach already established in tests/test_07_add_expense.py.
"""

import math
import re
import sqlite3

import pytest

import database.db as db_module
import database.queries as queries_module
from database.queries import get_expense_by_id, update_expense
from app import app as flask_app

VALID_CATEGORIES = {
    "Food", "Transport", "Bills", "Health",
    "Entertainment", "Shopping", "Other",
}

TEST_EMAIL = "editexpense@example.com"
TEST_PASSWORD = "password123"
OTHER_EMAIL = "otheruser@example.com"


# --------------------------------------------------------------------------- #
# Low-level DB helpers (test-only; parameterised SQL per project rules)      #
# --------------------------------------------------------------------------- #

def _connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def insert_test_user(db_path, email):
    """Create a bare user row directly (FK target for expense rows)."""
    conn = _connect(db_path)
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Unit Test User", email, "not-a-real-hash"),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return row["id"]


def insert_test_expense(db_path, user_id, amount, category, expense_date, description=None):
    """Insert a single expense row directly and return its id."""
    conn = _connect(db_path)
    cursor = conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, expense_date, description),
    )
    conn.commit()
    expense_id = cursor.lastrowid
    conn.close()
    return expense_id


def fetch_expense_row(db_path, expense_id):
    """Look up an expense row by id alone, independent of ownership rules."""
    conn = _connect(db_path)
    row = conn.execute(
        "SELECT id, user_id, amount, category, date, description "
        "FROM expenses WHERE id = ?",
        (expense_id,),
    ).fetchone()
    conn.close()
    return row


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


def extract_option_tags(select_block):
    return re.findall(r'<option\b[^>]*>', select_block or "", re.IGNORECASE | re.DOTALL)


def find_selected_option_value(select_block):
    """Return the value= of the first <option> flagged with a `selected` attribute."""
    for tag in extract_option_tags(select_block):
        if re.search(r'\bselected\b', tag, re.IGNORECASE):
            return extract_attr(tag, "value")
    return None


def extract_attr(tag_html, attr):
    if not tag_html:
        return None
    match = re.search(rf'{attr}=["\']([^"\']*)["\']', tag_html, re.IGNORECASE)
    return match.group(1) if match else None


def extract_form_tag(html):
    match = re.search(r'<form\b[^>]*>', html, re.IGNORECASE | re.DOTALL)
    return match.group(0) if match else None


def find_anchor_href_containing(html, needle):
    """Return the href of the first <a> tag whose href contains `needle`."""
    pattern = rf'<a\b[^>]*href=["\']([^"\']*{re.escape(needle)}[^"\']*)["\'][^>]*>'
    match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else None


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
        data={"name": "Edit Expense Tester", "email": TEST_EMAIL, "password": TEST_PASSWORD},
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


@pytest.fixture
def other_user_id(db_path, app):
    """A second user, unrelated to the logged-in test client, used for ownership checks."""
    return insert_test_user(db_path, OTHER_EMAIL)


@pytest.fixture
def own_expense_id(db_path, auth_user_id):
    """An expense owned by the logged-in test user, with known starting values."""
    return insert_test_expense(
        db_path, auth_user_id, 42.75, "Food", "2026-04-15", "Lunch with client"
    )


@pytest.fixture
def unauth_test_expense_id(db_path, app):
    """
    An expense that exists in the DB, owned by some user, for use in
    "unauthenticated request" tests.

    Deliberately does NOT depend on `auth_client` / `auth_user_id`: those
    fixtures log the shared `client` fixture in as a side effect, which
    would defeat the purpose of an "unauthenticated" test if the same
    `client` instance were reused. `app` here only initializes the schema
    and demo data -- it never touches the test client's session.
    """
    owner_id = insert_test_user(db_path, "unauth-owner@example.com")
    return insert_test_expense(
        db_path, owner_id, 42.75, "Food", "2026-04-15", "Lunch with client"
    )


@pytest.fixture
def other_users_expense_id(db_path, other_user_id):
    """An expense owned by a different user than the logged-in test client."""
    return insert_test_expense(
        db_path, other_user_id, 88.00, "Bills", "2026-04-16", "Not yours"
    )


# --------------------------------------------------------------------------- #
# 1. Unit tests -- get_expense_by_id()                                       #
# --------------------------------------------------------------------------- #

class TestGetExpenseByIdUnit:
    def test_valid_id_and_correct_user_returns_matching_row(self, initialized_db):
        user_id = insert_test_user(initialized_db, "unit-get-1@example.com")
        expense_id = insert_test_expense(
            initialized_db, user_id, 50.0, "Food", "2026-03-20", "Lunch"
        )

        row = get_expense_by_id(expense_id, user_id)

        assert row is not None, "Expected the owned expense to be returned"
        assert row["id"] == expense_id
        assert row["user_id"] == user_id
        assert row["amount"] == 50.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"

    def test_valid_id_wrong_user_returns_none(self, initialized_db):
        owner_id = insert_test_user(initialized_db, "unit-get-owner@example.com")
        other_id = insert_test_user(initialized_db, "unit-get-other@example.com")
        expense_id = insert_test_expense(
            initialized_db, owner_id, 20.0, "Transport", "2026-03-21", "Bus"
        )

        row = get_expense_by_id(expense_id, other_id)

        assert row is None, "An expense must not be returned to a non-owning user"

    def test_nonexistent_id_returns_none(self, initialized_db):
        user_id = insert_test_user(initialized_db, "unit-get-nonexistent@example.com")

        row = get_expense_by_id(999999, user_id)

        assert row is None, "A non-existent expense id must return None"


# --------------------------------------------------------------------------- #
# 2. Unit tests -- update_expense()                                          #
# --------------------------------------------------------------------------- #

class TestUpdateExpenseUnit:
    def test_valid_id_and_correct_user_updates_the_row(self, initialized_db):
        user_id = insert_test_user(initialized_db, "unit-update-1@example.com")
        expense_id = insert_test_expense(
            initialized_db, user_id, 10.0, "Food", "2026-03-20", "Original"
        )

        update_expense(expense_id, user_id, 99.0, "Health", "2026-03-25", "Updated")

        row = fetch_expense_row(initialized_db, expense_id)
        assert row is not None
        assert row["amount"] == 99.0, "Amount should reflect the update"
        assert row["category"] == "Health"
        assert row["date"] == "2026-03-25"
        assert row["description"] == "Updated"

    def test_wrong_user_id_leaves_row_unchanged_and_raises_no_error(self, initialized_db):
        owner_id = insert_test_user(initialized_db, "unit-update-owner@example.com")
        other_id = insert_test_user(initialized_db, "unit-update-other@example.com")
        expense_id = insert_test_expense(
            initialized_db, owner_id, 10.0, "Food", "2026-03-20", "Original"
        )

        # Should not raise, even though the update targets someone else's expense.
        update_expense(expense_id, other_id, 500.0, "Shopping", "2026-04-01", "Hacked")

        row = fetch_expense_row(initialized_db, expense_id)
        assert row is not None
        assert row["amount"] == 10.0, "Amount must be unchanged when user_id does not match"
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Original"

    def test_update_with_none_description_stores_null(self, initialized_db):
        user_id = insert_test_user(initialized_db, "unit-update-null@example.com")
        expense_id = insert_test_expense(
            initialized_db, user_id, 10.0, "Food", "2026-03-20", "Has a description"
        )

        update_expense(expense_id, user_id, 15.0, "Food", "2026-03-20", None)

        row = fetch_expense_row(initialized_db, expense_id)
        assert row["description"] is None, "Passing None should store NULL"


# --------------------------------------------------------------------------- #
# 3. GET /expenses/<id>/edit                                                 #
# --------------------------------------------------------------------------- #

class TestGetEditExpense:
    def test_unauthenticated_redirects_to_login(self, client, unauth_test_expense_id):
        response = client.get(f"/expenses/{unauth_test_expense_id}/edit")
        assert response.status_code == 302
        assert "/login" in response.headers.get("Location", "")

    def test_authenticated_own_expense_returns_200(self, auth_client, own_expense_id):
        response = auth_client.get(f"/expenses/{own_expense_id}/edit")
        assert response.status_code == 200

    def test_authenticated_own_expense_prefills_amount(self, auth_client, own_expense_id):
        html = auth_client.get(f"/expenses/{own_expense_id}/edit").data.decode("utf-8")
        amount_tag = extract_tag(html, "input", "amount")

        assert amount_tag is not None, "Expected an amount input field"
        value = extract_attr(amount_tag, "value")
        assert value is not None, "Amount field should be pre-filled"
        assert math.isclose(float(value), 42.75), (
            "Amount field should be pre-filled with the expense's current amount"
        )

    def test_authenticated_own_expense_prefills_date(self, auth_client, own_expense_id):
        html = auth_client.get(f"/expenses/{own_expense_id}/edit").data.decode("utf-8")
        date_tag = extract_tag(html, "input", "date")

        assert date_tag is not None, "Expected a date input field"
        assert extract_attr(date_tag, "value") == "2026-04-15", (
            "Date field should be pre-filled with the expense's current date"
        )

    def test_authenticated_own_expense_prefills_description(self, auth_client, own_expense_id):
        html = auth_client.get(f"/expenses/{own_expense_id}/edit").data.decode("utf-8")
        description_tag = extract_tag(html, "input", "description")

        assert description_tag is not None, "Expected a description input field"
        assert extract_attr(description_tag, "value") == "Lunch with client", (
            "Description field should be pre-filled with the expense's current description"
        )

    def test_authenticated_own_expense_category_preselected(self, auth_client, own_expense_id):
        html = auth_client.get(f"/expenses/{own_expense_id}/edit").data.decode("utf-8")
        category_block = extract_select_block(html, "category")

        assert category_block is not None, "Expected a category select field"
        assert find_selected_option_value(category_block) == "Food", (
            "The category select should have the expense's current category pre-selected"
        )

    def test_authenticated_own_expense_category_offers_all_seven_options(self, auth_client, own_expense_id):
        html = auth_client.get(f"/expenses/{own_expense_id}/edit").data.decode("utf-8")
        category_block = extract_select_block(html, "category")
        values = {v for v in extract_option_values(category_block) if v}

        assert values == VALID_CATEGORIES, f"Expected exactly the 7 fixed categories, got {values}"

    def test_authenticated_other_users_expense_returns_404(self, auth_client, other_users_expense_id):
        response = auth_client.get(f"/expenses/{other_users_expense_id}/edit")
        assert response.status_code == 404, "Editing another user's expense must 404"

    def test_authenticated_nonexistent_expense_returns_404(self, auth_client):
        response = auth_client.get("/expenses/999999/edit")
        assert response.status_code == 404, "Editing a non-existent expense must 404"


# --------------------------------------------------------------------------- #
# 4. POST /expenses/<id>/edit                                               #
# --------------------------------------------------------------------------- #

class TestPostEditExpense:
    def test_unauthenticated_redirects_to_login(self, client, unauth_test_expense_id):
        response = client.post(
            f"/expenses/{unauth_test_expense_id}/edit",
            data={"amount": "99.0", "category": "Health", "date": "2026-05-01", "description": "Changed"},
        )
        assert response.status_code == 302
        assert "/login" in response.headers.get("Location", "")

    def test_unauthenticated_does_not_update_row(self, client, db_path, unauth_test_expense_id):
        client.post(
            f"/expenses/{unauth_test_expense_id}/edit",
            data={"amount": "99.0", "category": "Health", "date": "2026-05-01", "description": "Changed"},
        )
        row = fetch_expense_row(db_path, unauth_test_expense_id)
        assert row["amount"] == 42.75, "Unauthenticated requests must not modify the expense"
        assert row["category"] == "Food"

    def test_valid_data_redirects_to_profile(self, auth_client, own_expense_id):
        response = auth_client.post(
            f"/expenses/{own_expense_id}/edit",
            data={"amount": "99.0", "category": "Health", "date": "2026-05-01", "description": "Changed"},
        )
        assert response.status_code == 302
        assert "/profile" in response.headers.get("Location", "")

    def test_valid_data_updates_the_database(self, auth_client, db_path, own_expense_id):
        auth_client.post(
            f"/expenses/{own_expense_id}/edit",
            data={"amount": "99.0", "category": "Health", "date": "2026-05-01", "description": "Changed"},
        )

        row = fetch_expense_row(db_path, own_expense_id)
        assert row is not None
        assert row["amount"] == 99.0
        assert row["category"] == "Health"
        assert row["date"] == "2026-05-01"
        assert row["description"] == "Changed"

    def test_other_users_expense_returns_404(self, auth_client, other_users_expense_id):
        response = auth_client.post(
            f"/expenses/{other_users_expense_id}/edit",
            data={"amount": "1.0", "category": "Food", "date": "2026-05-02", "description": "Hijacked"},
        )
        assert response.status_code == 404, "Editing another user's expense must 404"

    def test_other_users_expense_does_not_update_row(self, auth_client, db_path, other_users_expense_id):
        auth_client.post(
            f"/expenses/{other_users_expense_id}/edit",
            data={"amount": "1.0", "category": "Food", "date": "2026-05-02", "description": "Hijacked"},
        )

        row = fetch_expense_row(db_path, other_users_expense_id)
        assert row["amount"] == 88.00, "A non-owned expense must not be modified"
        assert row["category"] == "Bills"

    def test_nonexistent_expense_returns_404(self, auth_client):
        response = auth_client.post(
            "/expenses/999999/edit",
            data={"amount": "1.0", "category": "Food", "date": "2026-05-02", "description": ""},
        )
        assert response.status_code == 404

    def test_missing_amount_rerenders_form_with_error(self, auth_client, db_path, own_expense_id):
        response = auth_client.post(
            f"/expenses/{own_expense_id}/edit",
            data={"amount": "", "category": "Food", "date": "2026-05-01", "description": "No amount"},
        )
        html = response.data.decode("utf-8")

        assert response.status_code == 200, "Validation failure must re-render the form, not redirect"
        assert "error" in html.lower(), "Expected an error message in the response body"

    def test_missing_amount_does_not_update_row(self, auth_client, db_path, own_expense_id):
        auth_client.post(
            f"/expenses/{own_expense_id}/edit",
            data={"amount": "", "category": "Food", "date": "2026-05-01", "description": "No amount"},
        )
        row = fetch_expense_row(db_path, own_expense_id)
        assert row["amount"] == 42.75, "No update should occur when amount is missing"

    def test_missing_amount_retains_submitted_values(self, auth_client, own_expense_id):
        response = auth_client.post(
            f"/expenses/{own_expense_id}/edit",
            data={"amount": "", "category": "Bills", "date": "2026-05-09", "description": "Keep me"},
        )
        html = response.data.decode("utf-8")

        category_block = extract_select_block(html, "category")
        date_tag = extract_tag(html, "input", "date")
        description_tag = extract_tag(html, "input", "description")

        assert find_selected_option_value(category_block) == "Bills", (
            "Submitted category (not the original) should be pre-selected after a validation error"
        )
        assert extract_attr(date_tag, "value") == "2026-05-09", "Submitted date should be retained"
        assert extract_attr(description_tag, "value") == "Keep me", "Submitted description should be retained"

    def test_zero_amount_rerenders_form_with_error(self, auth_client, db_path, own_expense_id):
        response = auth_client.post(
            f"/expenses/{own_expense_id}/edit",
            data={"amount": "0", "category": "Bills", "date": "2026-05-02", "description": ""},
        )
        html = response.data.decode("utf-8")

        assert response.status_code == 200
        assert "error" in html.lower(), "An amount of 0 must be rejected as not > 0"

        row = fetch_expense_row(db_path, own_expense_id)
        assert row["amount"] == 42.75, "No update should occur when amount is 0"

    def test_negative_amount_rerenders_form_with_error(self, auth_client, db_path, own_expense_id):
        response = auth_client.post(
            f"/expenses/{own_expense_id}/edit",
            data={"amount": "-10", "category": "Bills", "date": "2026-05-03", "description": ""},
        )
        html = response.data.decode("utf-8")

        assert response.status_code == 200
        assert "error" in html.lower(), "A negative amount must be rejected"

    def test_non_numeric_amount_rerenders_form_with_error(self, auth_client, db_path, own_expense_id):
        response = auth_client.post(
            f"/expenses/{own_expense_id}/edit",
            data={"amount": "not-a-number", "category": "Health", "date": "2026-05-04", "description": ""},
        )
        html = response.data.decode("utf-8")

        assert response.status_code == 200
        assert "error" in html.lower(), "A non-numeric amount must be rejected"

        row = fetch_expense_row(db_path, own_expense_id)
        assert row["amount"] == 42.75, "No update should occur for a non-numeric amount"

    def test_invalid_category_rerenders_form_with_error(self, auth_client, db_path, own_expense_id):
        response = auth_client.post(
            f"/expenses/{own_expense_id}/edit",
            data={"amount": "20.0", "category": "NotARealCategory", "date": "2026-05-05", "description": ""},
        )
        html = response.data.decode("utf-8")

        assert response.status_code == 200
        assert "error" in html.lower(), "An invalid category must be rejected"

        row = fetch_expense_row(db_path, own_expense_id)
        assert row["category"] == "Food", "No update should occur for an invalid category"

    def test_sql_injection_style_category_is_rejected_safely(self, auth_client, db_path, own_expense_id):
        malicious = "Food'; DROP TABLE expenses;--"
        response = auth_client.post(
            f"/expenses/{own_expense_id}/edit",
            data={"amount": "20.0", "category": malicious, "date": "2026-05-06", "description": ""},
        )
        html = response.data.decode("utf-8")

        assert response.status_code == 200, "Malicious category input must not crash the app"
        assert "error" in html.lower(), "A category outside the fixed list must be rejected, even if malicious"

        # Confirm the table and app are still intact afterward.
        follow_up = auth_client.get(f"/expenses/{own_expense_id}/edit")
        assert follow_up.status_code == 200

    def test_invalid_date_rerenders_form_with_error(self, auth_client, db_path, own_expense_id):
        response = auth_client.post(
            f"/expenses/{own_expense_id}/edit",
            data={"amount": "20.0", "category": "Shopping", "date": "not-a-date", "description": ""},
        )
        html = response.data.decode("utf-8")

        assert response.status_code == 200
        assert "error" in html.lower(), "An invalid date string must be rejected"

        row = fetch_expense_row(db_path, own_expense_id)
        assert row["date"] == "2026-04-15", "No update should occur for an invalid date"

    def test_invalid_date_format_rerenders_form_with_error(self, auth_client, own_expense_id):
        response = auth_client.post(
            f"/expenses/{own_expense_id}/edit",
            data={"amount": "20.0", "category": "Shopping", "date": "15/04/2026", "description": ""},
        )
        html = response.data.decode("utf-8")

        assert response.status_code == 200
        assert "error" in html.lower(), "A non-ISO date format must be rejected"

    def test_no_description_redirects_and_saves_null(self, auth_client, db_path, own_expense_id):
        response = auth_client.post(
            f"/expenses/{own_expense_id}/edit",
            data={"amount": "30.0", "category": "Entertainment", "date": "2026-06-01"},
        )
        assert response.status_code == 302
        assert "/profile" in response.headers.get("Location", "")

        row = fetch_expense_row(db_path, own_expense_id)
        assert row is not None
        assert row["description"] is None, "Omitted description should be stored as NULL"

    def test_blank_description_saves_null(self, auth_client, db_path, own_expense_id):
        response = auth_client.post(
            f"/expenses/{own_expense_id}/edit",
            data={"amount": "15.0", "category": "Other", "date": "2026-06-02", "description": "   "},
        )
        assert response.status_code == 302

        row = fetch_expense_row(db_path, own_expense_id)
        assert row is not None
        assert row["description"] is None, "Whitespace-only description should be stripped and stored as NULL"


# --------------------------------------------------------------------------- #
# 5. Profile page — Edit link                                               #
# --------------------------------------------------------------------------- #

class TestProfileEditLink:
    def test_transaction_row_has_edit_link_to_correct_url(self, auth_client, own_expense_id):
        html = auth_client.get("/profile").data.decode("utf-8")
        href = find_anchor_href_containing(html, f"/expenses/{own_expense_id}/edit")

        assert href is not None, (
            "Expected an Edit link on the profile page pointing to "
            f"/expenses/{own_expense_id}/edit"
        )
