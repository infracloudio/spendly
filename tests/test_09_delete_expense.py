"""
Tests for Step 9 -- Delete Expense.

Source of truth: .claude/specs/09-delete-expense.md

Spec summary:
  - POST /expenses/<id>/delete verifies ownership via `get_expense_by_id`
    (from Step 8), deletes the row via a new `delete_expense` mutation
    helper, and redirects to /profile. Logged-in only.
  - There is no confirmation page: a browser-side `confirm()` dialog
    attached to the delete form's `onsubmit` handler is the only guard
    against accidental submission.
  - `delete_expense(expense_id, user_id)` issues a parameterised
    `DELETE FROM expenses WHERE id = ? AND user_id = ?` -- ownership is
    enforced at the SQL layer, not just in the route.
  - The route only accepts POST -- a bare GET must return 405.
  - Unauthenticated access redirects to /login (302).
  - If the expense does not exist, or belongs to another user, the route
    returns 404 and the row is left untouched.
  - On success: redirect to url_for("profile"), no template rendered.
  - `profile.html` gains a delete <form> per transaction row, inside the
    existing "Actions" <td>, alongside the Step 8 "Edit" link.

Because `database/db.py.get_db()` connects to a hardcoded on-disk
"spendly.db" path (ignoring Flask config) and `database/queries.py` imports
`get_db` by name (`from database.db import get_db`), a plain monkeypatch of
`database.db.get_db` alone would not affect the already-bound name inside
`database.queries`. Both module-level bindings are patched below to point
at an isolated, file-based SQLite database per test, following the same
approach already established in tests/test_07_add_expense.py and
tests/test_08_edit_expense.py.
"""

import re
import sqlite3

import pytest

import database.db as db_module
import database.queries as queries_module
from database.queries import delete_expense
from app import app as flask_app

TEST_EMAIL = "deleteexpense@example.com"
TEST_PASSWORD = "password123"
OTHER_EMAIL = "otheruser-delete@example.com"


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


def count_expenses(db_path):
    conn = _connect(db_path)
    row = conn.execute("SELECT COUNT(*) AS n FROM expenses").fetchone()
    conn.close()
    return row["n"]


# --------------------------------------------------------------------------- #
# HTML scraping helpers (attribute-order independent)                       #
# --------------------------------------------------------------------------- #

def find_forms_with_action_containing(html, needle):
    """Return the full opening <form ...> tag markup for every form whose
    action contains `needle` (order-agnostic on attributes)."""
    pattern = r'<form\b[^>]*action=["\'][^"\']*' + re.escape(needle) + r'[^"\']*["\'][^>]*>'
    return re.findall(pattern, html, re.IGNORECASE | re.DOTALL)


def extract_attr(tag_html, attr):
    if not tag_html:
        return None
    match = re.search(rf'{attr}=["\']([^"\']*)["\']', tag_html, re.IGNORECASE)
    return match.group(1) if match else None


def find_anchor_href_containing(html, needle):
    """Return the href of the first <a> tag whose href contains `needle`."""
    pattern = rf'<a\b[^>]*href=["\']([^"\']*{re.escape(needle)}[^"\']*)["\'][^>]*>'
    match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else None


def extract_button_for_form(html, form_tag):
    """Return the <button ...>...</button> markup that immediately follows
    the given opening <form> tag (best-effort, non-greedy)."""
    start = html.find(form_tag)
    if start == -1:
        return None
    segment = html[start:start + 500]
    match = re.search(r'<button\b[^>]*>.*?</button>', segment, re.IGNORECASE | re.DOTALL)
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
        data={"name": "Delete Expense Tester", "email": TEST_EMAIL, "password": TEST_PASSWORD},
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
    owner_id = insert_test_user(db_path, "unauth-owner-delete@example.com")
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
# 1. Unit tests -- delete_expense()                                          #
# --------------------------------------------------------------------------- #

class TestDeleteExpenseUnit:
    def test_valid_id_and_correct_user_removes_row(self, initialized_db):
        user_id = insert_test_user(initialized_db, "unit-delete-1@example.com")
        expense_id = insert_test_expense(
            initialized_db, user_id, 50.0, "Food", "2026-03-20", "Lunch"
        )

        delete_expense(expense_id, user_id)

        row = fetch_expense_row(initialized_db, expense_id)
        assert row is None, "Expected the owned expense row to be removed from the DB"

    def test_wrong_user_id_leaves_row_in_place_and_raises_no_error(self, initialized_db):
        owner_id = insert_test_user(initialized_db, "unit-delete-owner@example.com")
        other_id = insert_test_user(initialized_db, "unit-delete-other@example.com")
        expense_id = insert_test_expense(
            initialized_db, owner_id, 20.0, "Transport", "2026-03-21", "Bus"
        )

        # Should not raise, even though the id belongs to a different user.
        delete_expense(expense_id, other_id)

        row = fetch_expense_row(initialized_db, expense_id)
        assert row is not None, (
            "An expense must not be deleted when the requesting user does not own it"
        )
        assert row["amount"] == 20.0
        assert row["category"] == "Transport"

    def test_nonexistent_expense_id_raises_no_error_and_leaves_db_unchanged(self, initialized_db):
        user_id = insert_test_user(initialized_db, "unit-delete-nonexistent@example.com")
        insert_test_expense(initialized_db, user_id, 10.0, "Food", "2026-03-22", "Kept")
        before = count_expenses(initialized_db)

        # Should not raise for a non-existent id.
        delete_expense(999999, user_id)

        after = count_expenses(initialized_db)
        assert after == before, "Deleting a non-existent expense id must not change row count"


# --------------------------------------------------------------------------- #
# 2. POST /expenses/<id>/delete                                              #
# --------------------------------------------------------------------------- #

class TestPostDeleteExpense:
    def test_unauthenticated_redirects_to_login(self, client, unauth_test_expense_id):
        response = client.post(f"/expenses/{unauth_test_expense_id}/delete")
        assert response.status_code == 302
        assert "/login" in response.headers.get("Location", "")

    def test_unauthenticated_does_not_delete_row(self, client, db_path, unauth_test_expense_id):
        client.post(f"/expenses/{unauth_test_expense_id}/delete")
        row = fetch_expense_row(db_path, unauth_test_expense_id)
        assert row is not None, "Unauthenticated requests must not delete the expense"

    def test_own_expense_redirects_to_profile(self, auth_client, own_expense_id):
        response = auth_client.post(f"/expenses/{own_expense_id}/delete")
        assert response.status_code == 302
        assert "/profile" in response.headers.get("Location", "")

    def test_own_expense_is_removed_from_database(self, auth_client, db_path, own_expense_id):
        auth_client.post(f"/expenses/{own_expense_id}/delete")
        row = fetch_expense_row(db_path, own_expense_id)
        assert row is None, "The deleted expense must no longer exist in the DB"

    def test_own_expense_no_longer_appears_on_profile_after_redirect(
        self, auth_client, own_expense_id
    ):
        response = auth_client.post(
            f"/expenses/{own_expense_id}/delete", follow_redirects=True
        )
        html = response.data.decode("utf-8")
        assert response.status_code == 200
        assert f"/expenses/{own_expense_id}/delete" not in html, (
            "The deleted expense's row must not appear on the profile page after redirect"
        )

    def test_other_users_expense_returns_404(self, auth_client, other_users_expense_id):
        response = auth_client.post(f"/expenses/{other_users_expense_id}/delete")
        assert response.status_code == 404, "Deleting another user's expense must 404"

    def test_other_users_expense_is_not_deleted(self, auth_client, db_path, other_users_expense_id):
        auth_client.post(f"/expenses/{other_users_expense_id}/delete")
        row = fetch_expense_row(db_path, other_users_expense_id)
        assert row is not None, "A non-owned expense must not be deleted"
        assert row["amount"] == 88.00
        assert row["category"] == "Bills"

    def test_nonexistent_expense_returns_404(self, auth_client):
        response = auth_client.post("/expenses/999999/delete")
        assert response.status_code == 404

    def test_nonexistent_expense_does_not_change_row_count(self, auth_client, db_path):
        before = count_expenses(db_path)
        auth_client.post("/expenses/999999/delete")
        after = count_expenses(db_path)
        assert after == before, "A 404 delete attempt must not change the number of rows"

    def test_get_request_returns_405(self, auth_client, own_expense_id):
        response = auth_client.get(f"/expenses/{own_expense_id}/delete")
        assert response.status_code == 405, "GET must not be allowed on the delete route"

    def test_get_request_does_not_delete_row(self, auth_client, db_path, own_expense_id):
        auth_client.get(f"/expenses/{own_expense_id}/delete")
        row = fetch_expense_row(db_path, own_expense_id)
        assert row is not None, "A GET request must never delete the expense"

    def test_get_request_unauthenticated_also_rejected(self, client, unauth_test_expense_id):
        """
        Method verification takes precedence regardless of auth state --
        the spec calls for a bare GET to return 405 for 'any user'.
        """
        response = client.get(f"/expenses/{unauth_test_expense_id}/delete")
        assert response.status_code in (302, 405), (
            "A GET to the delete route must either redirect to login or return 405, "
            "never delete the expense or render a page"
        )


# --------------------------------------------------------------------------- #
# 3. Profile page -- Delete form/button                                      #
# --------------------------------------------------------------------------- #

class TestProfileDeleteForm:
    def test_transaction_row_has_delete_form_pointing_to_correct_url(
        self, auth_client, own_expense_id
    ):
        html = auth_client.get("/profile").data.decode("utf-8")
        forms = find_forms_with_action_containing(html, f"/expenses/{own_expense_id}/delete")

        assert len(forms) >= 1, (
            "Expected a delete <form> on the profile page pointing to "
            f"/expenses/{own_expense_id}/delete"
        )

    def test_delete_form_uses_post_method(self, auth_client, own_expense_id):
        html = auth_client.get("/profile").data.decode("utf-8")
        forms = find_forms_with_action_containing(html, f"/expenses/{own_expense_id}/delete")

        assert forms, "Expected to find the delete form"
        method = extract_attr(forms[0], "method")
        assert method is not None and method.upper() == "POST", (
            "The delete form must submit via POST"
        )

    def test_delete_form_has_confirm_onsubmit_guard(self, auth_client, own_expense_id):
        html = auth_client.get("/profile").data.decode("utf-8")
        forms = find_forms_with_action_containing(html, f"/expenses/{own_expense_id}/delete")

        assert forms, "Expected to find the delete form"
        onsubmit = extract_attr(forms[0], "onsubmit")
        assert onsubmit is not None, (
            "The delete form must have an onsubmit handler to guard against "
            "accidental submission"
        )
        assert "confirm(" in onsubmit, (
            "The onsubmit handler must invoke the browser confirm() dialog "
            "before allowing the form to submit"
        )

    def test_delete_form_contains_a_delete_button(self, auth_client, own_expense_id):
        html = auth_client.get("/profile").data.decode("utf-8")
        forms = find_forms_with_action_containing(html, f"/expenses/{own_expense_id}/delete")

        assert forms, "Expected to find the delete form"
        button = extract_button_for_form(html, forms[0])
        assert button is not None, "Expected a submit button inside the delete form"
        assert 'type="submit"' in button.lower() or "type='submit'" in button.lower(), (
            "The delete button must be a submit button"
        )
        assert "delete" in button.lower(), "The button text should read 'Delete'"

    def test_transaction_row_has_both_edit_and_delete_actions(self, auth_client, own_expense_id):
        html = auth_client.get("/profile").data.decode("utf-8")

        edit_href = find_anchor_href_containing(html, f"/expenses/{own_expense_id}/edit")
        delete_forms = find_forms_with_action_containing(html, f"/expenses/{own_expense_id}/delete")

        assert edit_href is not None, "Expected an Edit action on the transaction row"
        assert delete_forms, "Expected a Delete action on the transaction row"

    def test_deleted_expense_row_disappears_from_profile_table(
        self, auth_client, own_expense_id
    ):
        before_html = auth_client.get("/profile").data.decode("utf-8")
        assert f"/expenses/{own_expense_id}/delete" in before_html, (
            "Sanity check: the row must be present before deletion"
        )

        auth_client.post(f"/expenses/{own_expense_id}/delete")

        after_html = auth_client.get("/profile").data.decode("utf-8")
        assert f"/expenses/{own_expense_id}/delete" not in after_html, (
            "After deletion the expense's row must no longer render on the profile page"
        )
