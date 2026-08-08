"""
Tests for Step 6 — Date Filter on the Profile page.

Source of truth: .claude/specs/06-date-filter.md

`GET /profile` accepts optional `date_from` / `date_to` query params
(ISO `YYYY-MM-DD`, inclusive bounds). Per the spec:
  - Both params must be present and well-formed to apply a filter;
    otherwise the view falls back to "All Time" (unfiltered).
  - `date_from > date_to` is invalid: flash "Start date must be before
    end date." and fall back to unfiltered.
  - A malformed date string is *not* supposed to raise an error and
    (per the spec's Definition of Done) should "silently" fall back —
    i.e. no flash message for a bad format, only for bad ordering.
    NOTE: at the time these tests were written, app.py flashes an
    "Invalid ... date format" message for malformed input, which
    contradicts the spec's "silently falls back" wording. The tests
    below follow the spec (no flash expected for a malformed format)
    since the spec is the correctness contract — if this fails against
    the current implementation, that is a real spec/implementation gap
    worth fixing, not a bug in the test.

Because `database/db.py.get_db()` connects to a hardcoded on-disk
"spendly.db" path (ignoring any Flask config), the fixtures below
monkeypatch `database.db.get_db` to point at a fresh, isolated,
file-based SQLite database per test (an in-memory DB will not work
here because each helper function opens and closes its own connection,
and a `:memory:` database does not persist across separate
`sqlite3.connect(":memory:")` calls).

Rather than hardcoding expected totals (which would silently drift if
the seeded demo data ever changes), most filtering assertions are
checked against an independent oracle (`expected_summary`) that
queries the same isolated database directly, applying exactly the
inclusive `BETWEEN` semantics the spec describes. This keeps the tests
correct regardless of the current system date or the exact contents
of the seeded demo dataset.
"""

import re
import sqlite3
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

import database.db as db_module
from app import app as flask_app

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"


# --------------------------------------------------------------------------- #
# Low-level DB helpers (test-only; parameterised SQL per project rules)      #
# --------------------------------------------------------------------------- #

def _connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def insert_expense(db_path, user_id, amount, category, expense_date, description=""):
    """Insert a single, deterministic expense row for a test scenario."""
    conn = _connect(db_path)
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, expense_date, description),
    )
    conn.commit()
    conn.close()


def expected_summary(db_path, user_id, date_from=None, date_to=None):
    """
    Independent oracle mirroring the spec's stated filtering rule:
    "when both [date_from and date_to] are provided, add
    `AND date BETWEEN ? AND ?`" (inclusive bounds); otherwise unfiltered.
    """
    conn = _connect(db_path)
    query = "SELECT amount, category FROM expenses WHERE user_id = ?"
    params = [user_id]
    if date_from and date_to:
        query += " AND date BETWEEN ? AND ?"
        params.extend([date_from, date_to])
    rows = conn.execute(query, tuple(params)).fetchall()
    conn.close()

    total = sum(r["amount"] for r in rows)
    count = len(rows)
    by_category = {}
    for r in rows:
        by_category[r["category"]] = by_category.get(r["category"], 0) + r["amount"]
    top_category = max(by_category, key=by_category.get) if by_category else None
    return {
        "total": total,
        "count": count,
        "top_category": top_category,
        "categories": set(by_category.keys()),
    }


# --------------------------------------------------------------------------- #
# HTML scraping helpers (structural landmarks matching templates/profile.html)#
# --------------------------------------------------------------------------- #

def extract_stat(html_text, label):
    pattern = (
        r'<div class="stat-label">\s*' + re.escape(label) + r'\s*</div>\s*'
        r'<div class="stat-value">\s*(.*?)\s*</div>'
    )
    match = re.search(pattern, html_text, re.DOTALL)
    return match.group(1).strip() if match else None


def extract_transaction_dates(html_text):
    return re.findall(r'<td class="date-cell">\s*(.*?)\s*</td>', html_text, re.DOTALL)


def extract_category_names(html_text):
    return re.findall(r'<span class="breakdown-name">\s*(.*?)\s*</span>', html_text, re.DOTALL)


def extract_preset_href(html_text, label):
    pattern = r'<a\s+href="([^"]*)"\s+class="preset-btn[^"]*">\s*' + re.escape(label) + r'\s*</a>'
    match = re.search(pattern, html_text, re.DOTALL)
    return match.group(1).replace("&amp;", "&") if match else None


def extract_preset_active_class(html_text, label):
    pattern = r'<a\s+href="[^"]*"\s+class="(preset-btn[^"]*)">\s*' + re.escape(label) + r'\s*</a>'
    match = re.search(pattern, html_text, re.DOTALL)
    return match.group(1) if match else None


def query_params(href):
    if not href:
        return {}
    parsed = urlparse(href)
    return {k: v[0] for k, v in parse_qs(parsed.query).items()}


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #

@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """
    Point database.db.get_db() at an isolated, file-based SQLite DB for the
    duration of a single test.
    """
    path = str(tmp_path / "test_spendly.db")
    monkeypatch.setattr(db_module, "get_db", lambda: _connect(path))
    return path


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
def demo_user_id(app, db_path):
    conn = _connect(db_path)
    row = conn.execute("SELECT id FROM users WHERE email = ?", (DEMO_EMAIL,)).fetchone()
    conn.close()
    assert row is not None, "Seeded demo user must exist"
    return row["id"]


@pytest.fixture
def auth_client(client):
    """A test client already logged in as the seeded demo user."""
    response = client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        follow_redirects=True,
    )
    assert response.status_code == 200, "Demo user login must succeed"
    return client


# --------------------------------------------------------------------------- #
# 1. Query parameter validation                                               #
# --------------------------------------------------------------------------- #

class TestQueryParamValidation:
    def test_profile_requires_login_even_with_filter_params(self, client):
        resp = client.get("/profile", query_string={"date_from": "2026-01-01", "date_to": "2026-01-31"})
        assert resp.status_code == 302, "Unauthenticated access must redirect, not filter"
        assert "/login" in resp.headers.get("Location", "")

    def test_no_params_returns_unfiltered_view(self, auth_client, db_path, demo_user_id):
        expected = expected_summary(db_path, demo_user_id)
        resp = auth_client.get("/profile")
        html = resp.data.decode("utf-8")
        assert resp.status_code == 200
        assert extract_stat(html, "Total Spent") == f"₹{expected['total']:.2f}"
        assert extract_stat(html, "Transactions") == str(expected["count"])

    def test_valid_custom_range_filters_data(self, auth_client, db_path, demo_user_id):
        insert_expense(db_path, demo_user_id, 100.0, "Food", "2000-01-15", "old food")
        insert_expense(db_path, demo_user_id, 50.0, "Bills", "2000-02-15", "old bill")
        insert_expense(db_path, demo_user_id, 999.0, "Shopping", "1999-12-31", "before range")

        expected = expected_summary(db_path, demo_user_id, "2000-01-01", "2000-02-28")
        resp = auth_client.get("/profile", query_string={"date_from": "2000-01-01", "date_to": "2000-02-28"})
        html = resp.data.decode("utf-8")

        assert resp.status_code == 200
        assert extract_stat(html, "Total Spent") == f"₹{expected['total']:.2f}"
        assert extract_stat(html, "Transactions") == str(expected["count"])
        assert "1999-12-31" not in extract_transaction_dates(html)

    def test_malformed_date_from_falls_back_to_unfiltered(self, auth_client, db_path, demo_user_id):
        expected = expected_summary(db_path, demo_user_id)
        resp = auth_client.get("/profile", query_string={"date_from": "not-a-date", "date_to": "2026-08-08"})
        html = resp.data.decode("utf-8")

        assert resp.status_code == 200, "Malformed date must not crash the app"
        assert extract_stat(html, "Total Spent") == f"₹{expected['total']:.2f}"
        assert extract_stat(html, "Transactions") == str(expected["count"])
        assert "flash-error" not in html, (
            "Spec states a malformed date format should silently fall back with no "
            "error message (only date_from > date_to shows a flash error)"
        )

    def test_malformed_date_to_falls_back_to_unfiltered(self, auth_client, db_path, demo_user_id):
        expected = expected_summary(db_path, demo_user_id)
        resp = auth_client.get("/profile", query_string={"date_from": "2026-08-01", "date_to": "31/08/2026"})
        html = resp.data.decode("utf-8")

        assert resp.status_code == 200
        assert extract_stat(html, "Total Spent") == f"₹{expected['total']:.2f}"

    def test_sql_injection_style_date_value_is_safely_rejected(self, auth_client, db_path, demo_user_id):
        expected = expected_summary(db_path, demo_user_id)
        malicious = "2026-01-01'; DROP TABLE users;--"
        resp = auth_client.get("/profile", query_string={"date_from": malicious, "date_to": "2026-12-31"})
        html = resp.data.decode("utf-8")

        assert resp.status_code == 200, "A malicious/malformed date value must not crash the app"
        assert extract_stat(html, "Total Spent") == f"₹{expected['total']:.2f}", (
            "A malformed date_from should be treated as absent, falling back to unfiltered"
        )

        # Confirm the app and its data are still intact afterward.
        followup = auth_client.get("/profile")
        assert followup.status_code == 200
        assert extract_stat(followup.data.decode("utf-8"), "Total Spent") is not None

    def test_only_date_from_present_is_treated_as_unfiltered(self, auth_client, db_path, demo_user_id):
        expected = expected_summary(db_path, demo_user_id)
        resp = auth_client.get("/profile", query_string={"date_from": "2026-08-01"})
        html = resp.data.decode("utf-8")
        assert resp.status_code == 200
        assert extract_stat(html, "Total Spent") == f"₹{expected['total']:.2f}"

    def test_only_date_to_present_is_treated_as_unfiltered(self, auth_client, db_path, demo_user_id):
        expected = expected_summary(db_path, demo_user_id)
        resp = auth_client.get("/profile", query_string={"date_to": "2026-08-08"})
        html = resp.data.decode("utf-8")
        assert resp.status_code == 200
        assert extract_stat(html, "Total Spent") == f"₹{expected['total']:.2f}"

    def test_date_from_after_date_to_flashes_error_and_falls_back(self, auth_client, db_path, demo_user_id):
        expected = expected_summary(db_path, demo_user_id)
        resp = auth_client.get("/profile", query_string={"date_from": "2026-08-08", "date_to": "2026-08-01"})
        html = resp.data.decode("utf-8")

        assert resp.status_code == 200
        assert "Start date must be before end date." in html
        assert extract_stat(html, "Total Spent") == f"₹{expected['total']:.2f}"


# --------------------------------------------------------------------------- #
# 2. Date filtering behavior                                                  #
# --------------------------------------------------------------------------- #

class TestDateFilteringBehavior:
    def test_all_time_shows_every_expense(self, auth_client, db_path, demo_user_id):
        insert_expense(db_path, demo_user_id, 42.0, "Food", "1500-01-01", "ancient")
        expected = expected_summary(db_path, demo_user_id)

        resp = auth_client.get("/profile")
        html = resp.data.decode("utf-8")

        assert extract_stat(html, "Transactions") == str(expected["count"])
        assert "1500-01-01" in extract_transaction_dates(html)

    def test_this_month_preset_filters_to_current_calendar_month(self, auth_client, db_path, demo_user_id):
        today = date.today()
        month_start = today.replace(day=1)
        previous_month_last_day = month_start - timedelta(days=1)

        insert_expense(db_path, demo_user_id, 30.0, "Food", today.isoformat(), "in this month")
        insert_expense(db_path, demo_user_id, 999.0, "Shopping", previous_month_last_day.isoformat(), "last month")

        expected = expected_summary(db_path, demo_user_id, month_start.isoformat(), today.isoformat())
        resp = auth_client.get(
            "/profile",
            query_string={"date_from": month_start.isoformat(), "date_to": today.isoformat()},
        )
        html = resp.data.decode("utf-8")
        dates_shown = extract_transaction_dates(html)

        assert today.isoformat() in dates_shown
        assert previous_month_last_day.isoformat() not in dates_shown
        assert extract_stat(html, "Total Spent") == f"₹{expected['total']:.2f}"
        assert extract_stat(html, "Transactions") == str(expected["count"])

    def test_last_3_months_preset_link_is_internally_consistent(self, auth_client, db_path, demo_user_id):
        resp = auth_client.get("/profile")
        html = resp.data.decode("utf-8")
        href = extract_preset_href(html, "Last 3 Months")
        assert href is not None, "Expected a 'Last 3 Months' preset link on the filter bar"

        params = query_params(href)
        date_from, date_to = params.get("date_from"), params.get("date_to")
        assert date_from and date_to, "Last 3 Months preset must supply both date_from and date_to"

        expected = expected_summary(db_path, demo_user_id, date_from, date_to)
        follow = auth_client.get(href)
        follow_html = follow.data.decode("utf-8")

        assert follow.status_code == 200
        assert extract_stat(follow_html, "Total Spent") == f"₹{expected['total']:.2f}"
        assert extract_stat(follow_html, "Transactions") == str(expected["count"])

    def test_last_6_months_preset_link_is_internally_consistent(self, auth_client, db_path, demo_user_id):
        resp = auth_client.get("/profile")
        html = resp.data.decode("utf-8")
        href = extract_preset_href(html, "Last 6 Months")
        assert href is not None, "Expected a 'Last 6 Months' preset link on the filter bar"

        params = query_params(href)
        date_from, date_to = params.get("date_from"), params.get("date_to")
        assert date_from and date_to, "Last 6 Months preset must supply both date_from and date_to"

        expected = expected_summary(db_path, demo_user_id, date_from, date_to)
        follow = auth_client.get(href)
        follow_html = follow.data.decode("utf-8")

        assert follow.status_code == 200
        assert extract_stat(follow_html, "Total Spent") == f"₹{expected['total']:.2f}"
        assert extract_stat(follow_html, "Transactions") == str(expected["count"])

    def test_last_6_months_window_is_not_narrower_than_last_3_months(self, auth_client):
        resp = auth_client.get("/profile")
        html = resp.data.decode("utf-8")
        href_3 = extract_preset_href(html, "Last 3 Months")
        href_6 = extract_preset_href(html, "Last 6 Months")

        from_3 = query_params(href_3).get("date_from")
        from_6 = query_params(href_6).get("date_from")

        assert from_3 and from_6
        assert from_6 <= from_3, "Last 6 Months should start on or before Last 3 Months' start date"

    def test_custom_range_filters_correctly(self, auth_client, db_path, demo_user_id):
        insert_expense(db_path, demo_user_id, 10.0, "Food", "2050-05-10", "future food")
        insert_expense(db_path, demo_user_id, 20.0, "Bills", "2050-05-20", "future bill")
        insert_expense(db_path, demo_user_id, 999.0, "Shopping", "2050-06-01", "outside range")

        expected = expected_summary(db_path, demo_user_id, "2050-05-01", "2050-05-31")
        resp = auth_client.get("/profile", query_string={"date_from": "2050-05-01", "date_to": "2050-05-31"})
        html = resp.data.decode("utf-8")
        dates_shown = extract_transaction_dates(html)

        assert "2050-05-10" in dates_shown
        assert "2050-05-20" in dates_shown
        assert "2050-06-01" not in dates_shown
        assert extract_stat(html, "Total Spent") == f"₹{expected['total']:.2f}"
        assert extract_stat(html, "Transactions") == str(expected["count"])

    def test_empty_result_set_for_range_with_no_expenses(self, auth_client):
        resp = auth_client.get("/profile", query_string={"date_from": "2999-01-01", "date_to": "2999-12-31"})
        html = resp.data.decode("utf-8")

        assert extract_stat(html, "Total Spent") == "₹0.00"
        assert extract_stat(html, "Transactions") == "0"
        assert 'class="breakdown-item"' not in html


# --------------------------------------------------------------------------- #
# 3. Summary stats recalculation                                             #
# --------------------------------------------------------------------------- #

class TestSummaryStatsRecalculation:
    def test_total_spent_updates_with_filtered_data(self, auth_client, db_path, demo_user_id):
        insert_expense(db_path, demo_user_id, 500.0, "Food", "2010-06-15", "isolated")
        expected = expected_summary(db_path, demo_user_id, "2010-06-01", "2010-06-30")

        resp = auth_client.get("/profile", query_string={"date_from": "2010-06-01", "date_to": "2010-06-30"})
        html = resp.data.decode("utf-8")

        assert extract_stat(html, "Total Spent") == f"₹{expected['total']:.2f}" == "₹500.00"

    def test_transaction_count_updates_with_filtered_data(self, auth_client, db_path, demo_user_id):
        insert_expense(db_path, demo_user_id, 12.0, "Food", "2011-03-01", "a")
        insert_expense(db_path, demo_user_id, 13.0, "Food", "2011-03-02", "b")

        resp = auth_client.get("/profile", query_string={"date_from": "2011-03-01", "date_to": "2011-03-02"})
        html = resp.data.decode("utf-8")

        assert extract_stat(html, "Transactions") == "2"

    def test_top_category_updates_with_filtered_data(self, auth_client, db_path, demo_user_id):
        insert_expense(db_path, demo_user_id, 5.0, "Food", "2012-01-01", "small")
        insert_expense(db_path, demo_user_id, 500.0, "Health", "2012-01-02", "big")

        resp = auth_client.get("/profile", query_string={"date_from": "2012-01-01", "date_to": "2012-01-02"})
        html = resp.data.decode("utf-8")

        assert extract_stat(html, "Top Category") == "Health"

    def test_categories_list_includes_only_filtered_categories(self, auth_client, db_path, demo_user_id):
        insert_expense(db_path, demo_user_id, 5.0, "Entertainment", "2013-07-01", "movie")

        resp = auth_client.get("/profile", query_string={"date_from": "2013-07-01", "date_to": "2013-07-01"})
        html = resp.data.decode("utf-8")

        assert extract_category_names(html) == ["Entertainment"], (
            "Filtered view must only show categories present in the filtered range"
        )


# --------------------------------------------------------------------------- #
# 4. UI state                                                                 #
# --------------------------------------------------------------------------- #

class TestUIState:
    def test_all_time_preset_is_active_by_default(self, auth_client):
        resp = auth_client.get("/profile")
        html = resp.data.decode("utf-8")

        active_class = extract_preset_active_class(html, "All Time")
        assert active_class and "preset-btn--active" in active_class

    def test_this_month_preset_is_highlighted_when_active(self, auth_client):
        today = date.today()
        month_start = today.replace(day=1)

        resp = auth_client.get(
            "/profile",
            query_string={"date_from": month_start.isoformat(), "date_to": today.isoformat()},
        )
        html = resp.data.decode("utf-8")

        this_month_class = extract_preset_active_class(html, "This Month")
        all_time_class = extract_preset_active_class(html, "All Time")

        assert this_month_class and "preset-btn--active" in this_month_class
        assert all_time_class and "preset-btn--active" not in all_time_class

    def test_custom_date_fields_retain_submitted_values(self, auth_client):
        resp = auth_client.get("/profile", query_string={"date_from": "2020-02-01", "date_to": "2020-02-29"})
        html = resp.data.decode("utf-8")

        assert 'name="date_from" value="2020-02-01"' in html
        assert 'name="date_to" value="2020-02-29"' in html

    def test_custom_date_fields_are_empty_for_all_time(self, auth_client):
        resp = auth_client.get("/profile")
        html = resp.data.decode("utf-8")

        assert 'name="date_from" value=""' in html
        assert 'name="date_to" value=""' in html

    def test_flash_error_appears_for_invalid_ordering(self, auth_client):
        resp = auth_client.get("/profile", query_string={"date_from": "2026-08-08", "date_to": "2026-08-01"})
        html = resp.data.decode("utf-8")

        assert "flash-error" in html
        assert "Start date must be before end date." in html

    def test_filter_bar_and_presets_render(self, auth_client):
        resp = auth_client.get("/profile")
        html = resp.data.decode("utf-8")

        assert 'class="filter-bar"' in html
        assert 'class="filter-apply"' in html
        for label in ("All Time", "This Month", "Last 3 Months", "Last 6 Months"):
            assert label in html


# --------------------------------------------------------------------------- #
# 5. Edge cases                                                              #
# --------------------------------------------------------------------------- #

class TestEdgeCases:
    def test_no_expenses_in_selected_range_shows_zero_state(self, auth_client):
        resp = auth_client.get("/profile", query_string={"date_from": "1600-01-01", "date_to": "1600-12-31"})
        html = resp.data.decode("utf-8")

        assert resp.status_code == 200
        assert extract_stat(html, "Total Spent") == "₹0.00"
        assert extract_stat(html, "Transactions") == "0"
        assert 'class="breakdown-item"' not in html

    def test_single_day_range_includes_only_that_day(self, auth_client, db_path, demo_user_id):
        insert_expense(db_path, demo_user_id, 77.0, "Food", "1975-05-05", "target day")
        insert_expense(db_path, demo_user_id, 88.0, "Food", "1975-05-04", "day before")
        insert_expense(db_path, demo_user_id, 99.0, "Food", "1975-05-06", "day after")

        resp = auth_client.get("/profile", query_string={"date_from": "1975-05-05", "date_to": "1975-05-05"})
        html = resp.data.decode("utf-8")

        assert extract_transaction_dates(html) == ["1975-05-05"]
        assert extract_stat(html, "Total Spent") == "₹77.00"

    def test_very_old_date_range_returns_empty_result(self, auth_client):
        resp = auth_client.get("/profile", query_string={"date_from": "0100-01-01", "date_to": "0200-01-01"})
        html = resp.data.decode("utf-8")

        assert resp.status_code == 200
        assert extract_stat(html, "Transactions") == "0"

    def test_very_far_future_date_range_returns_empty_result(self, auth_client):
        resp = auth_client.get("/profile", query_string={"date_from": "9000-01-01", "date_to": "9000-12-31"})
        html = resp.data.decode("utf-8")

        assert resp.status_code == 200
        assert extract_stat(html, "Transactions") == "0"

    def test_newly_registered_user_with_no_expenses_sees_zero_state(self, client):
        client.post(
            "/register",
            data={"name": "New User", "email": "newuser@example.com", "password": "password123"},
        )
        login_resp = client.post(
            "/login",
            data={"email": "newuser@example.com", "password": "password123"},
            follow_redirects=True,
        )
        assert login_resp.status_code == 200

        resp = client.get("/profile")
        html = resp.data.decode("utf-8")

        assert extract_stat(html, "Total Spent") == "₹0.00"
        assert extract_stat(html, "Transactions") == "0"
        assert 'class="breakdown-item"' not in html
