from flask import Flask, render_template, request, redirect, url_for, session, g, flash, abort
from database.db import get_db, init_db, seed_db, get_user_by_email, get_user_by_id, aggregate_expenses, get_user_expenses, get_expense_summary, email_exists, create_user
from database.queries import insert_expense, get_expense_by_id, update_expense, delete_expense as delete_expense_row
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import sqlite3
import math

app = Flask(__name__)
app.secret_key = "dev-secret-key-spendly-step3"

try:
    with app.app_context():
        init_db()
        seed_db()
except Exception as e:
    print(f"Warning: Failed to initialize database on startup: {e}")
    pass


# ------------------------------------------------------------------ #
# Helper functions                                                    #
# ------------------------------------------------------------------ #

def parse_iso_date(value):
    """Return normalized value if valid YYYY-MM-DD, else None."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def get_preset_dates(preset):
    """
    Return dict with 'from' and 'to' keys for a preset, or {'from': None, 'to': None} for 'all_time'.
    Dates are returned as ISO format strings (YYYY-MM-DD).
    """
    today = datetime.now().date()

    if preset == "this_month":
        return {
            "from": today.replace(day=1).isoformat(),
            "to": today.isoformat()
        }
    elif preset == "last_3_months":
        return {
            "from": (today - timedelta(days=90)).isoformat(),
            "to": today.isoformat()
        }
    elif preset == "last_6_months":
        return {
            "from": (today - timedelta(days=180)).isoformat(),
            "to": today.isoformat()
        }
    else:  # "all_time" or absent
        return {"from": None, "to": None}


def determine_active_preset(date_from, date_to):
    """
    Return preset name if current dates match a preset, else 'custom'.
    If no dates are set, return 'all_time'.
    """
    if not date_from or not date_to:
        return "all_time"

    for preset in ("this_month", "last_3_months", "last_6_months"):
        preset_dates = get_preset_dates(preset)
        if date_from == preset_dates["from"] and date_to == preset_dates["to"]:
            return preset

    return "custom"


VALID_CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]


def validate_expense_form(amount, category, date_str, description):
    if not amount:
        return "Amount is required"
    if not category:
        return "Category is required"
    if not date_str:
        return "Date is required"

    try:
        amount_float = float(amount)
    except ValueError:
        return "Amount must be a number"

    if not math.isfinite(amount_float) or amount_float <= 0:
        return "Amount must be greater than 0"

    if category not in VALID_CATEGORIES:
        return "Please select a valid category"

    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return "Date must be in YYYY-MM-DD format"

    if description and len(description) > 200:
        return "Description must be 200 characters or fewer"

    return None


def render_add_expense_form(error=None, amount="", category="", date_str="", description=""):
    return render_template(
        "add_expense.html",
        error=error,
        amount=amount,
        category=category,
        date=date_str,
        description=description,
        default_date=datetime.now().date().isoformat(),
        categories=VALID_CATEGORIES,
    )


def render_edit_expense_form(expense, error=None, amount="", category="", date_str="", description=""):
    return render_template(
        "edit_expense.html",
        expense=expense,
        error=error,
        amount=amount,
        category=category,
        date=date_str,
        description=description,
        categories=VALID_CATEGORIES,
    )


def read_expense_form(form):
    return (
        form.get("amount", "").strip(),
        form.get("category", "").strip(),
        form.get("date", "").strip(),
        form.get("description", "").strip(),
    )


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("landing"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not name or not email or not password:
            return render_template("register.html", error="Name, email, and password are required")

        if "@" not in email:
            return render_template("register.html", error="Please enter a valid email address")

        parts = email.split("@")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return render_template("register.html", error="Please enter a valid email address")

        if len(password) < 8:
            return render_template("register.html", error="Password must be at least 8 characters")

        if email_exists(email):
            return render_template("register.html", error="Email is already registered. Please log in or use a different email.")

        try:
            hashed_password = generate_password_hash(password)
            create_user(name, email, hashed_password)
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            return render_template("register.html", error="Email is already registered. Please log in or use a different email.")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            return render_template("login.html", error="Email and password are required")

        user = get_user_by_email(email)

        if user is None:
            return render_template("login.html", error="Invalid email or password")

        if not check_password_hash(user["password_hash"], password):
            return render_template("login.html", error="Invalid email or password")

        session.clear()
        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        return redirect(url_for("profile"))

    return render_template("login.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session.get("user_id")

    # Extract and validate date filter parameters
    date_from = parse_iso_date(request.args.get("date_from"))
    date_to = parse_iso_date(request.args.get("date_to"))

    if date_from and date_to and date_from > date_to:
        flash("Start date must be before end date.", "error")
        date_from = None
        date_to = None

    # Fetch real user data from database
    user = get_user_by_id(user_id)
    if not user:
        return redirect(url_for("login"))

    user_name = user["name"]
    user_email = user["email"]
    user_initials = "".join(word[0].upper() for word in user_name.split())
    member_since = user["created_at"]

    # Fetch user expenses and calculate summary stats (with optional date filtering)
    expenses = get_user_expenses(user_id, date_from, date_to)

    # Transform expenses into format for transactions display
    transactions_data = [
        {
            "id": expense["id"],
            "date": expense["date"],
            "description": expense["description"] or "",
            "category": expense["category"],
            "category_slug": expense["category"].lower(),
            "amount": f"{expense['amount']:.2f}"
        }
        for expense in expenses
    ]

    # Get summary stats (with optional date filtering)
    summary = get_expense_summary(user_id, date_from, date_to)
    total_spent = summary["total"]
    transaction_count = summary["count"]
    top_category = summary["top_category"]
    categories = summary["categories"]

    # Compute preset dates for filter bar (using dict with 'from'/'to' keys)
    preset_this_month = get_preset_dates("this_month")
    preset_last_3_months = get_preset_dates("last_3_months")
    preset_last_6_months = get_preset_dates("last_6_months")

    # Determine which preset (if any) is currently active
    active_preset = determine_active_preset(date_from, date_to)

    context = {
        "user_name": user_name,
        "user_initials": user_initials,
        "user_email": user_email,
        "member_since": member_since,
        "total_spent": total_spent,
        "transaction_count": transaction_count,
        "top_category": top_category,
        "transactions": transactions_data,
        "categories": categories,
        "date_from": date_from,
        "date_to": date_to,
        "active_preset": active_preset,
        "preset_this_month": preset_this_month,
        "preset_last_3_months": preset_last_3_months,
        "preset_last_6_months": preset_last_6_months,
    }

    return render_template("profile.html", **context)


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_add_expense_form()

    elif request.method == "POST":
        user_id = session.get("user_id")
        amount, category, date_str, description = read_expense_form(request.form)

        error = validate_expense_form(amount, category, date_str, description)

        if error:
            return render_add_expense_form(
                error=error,
                amount=amount,
                category=category,
                date_str=date_str,
                description=description,
            )

        description_db = description if description else None
        try:
            insert_expense(user_id, float(amount), category, date_str, description_db)
            return redirect(url_for("profile"))
        except sqlite3.IntegrityError:
            return render_add_expense_form(
                error="An error occurred while saving the expense. Please try again.",
                amount=amount,
                category=category,
                date_str=date_str,
                description=description,
            )


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session.get("user_id")
    expense = get_expense_by_id(id, user_id)

    if not expense:
        abort(404)

    if request.method == "GET":
        return render_edit_expense_form(expense)

    elif request.method == "POST":
        amount, category, date_str, description = read_expense_form(request.form)

        error = validate_expense_form(amount, category, date_str, description)

        if error:
            return render_edit_expense_form(
                expense,
                error=error,
                amount=amount,
                category=category,
                date_str=date_str,
                description=description,
            )

        description_db = description if description else None
        try:
            update_expense(id, user_id, float(amount), category, date_str, description_db)
            return redirect(url_for("profile"))
        except sqlite3.IntegrityError:
            return render_edit_expense_form(
                expense,
                error="An error occurred while saving the expense. Please try again.",
                amount=amount,
                category=category,
                date_str=date_str,
                description=description,
            )


@app.route("/expenses/<int:id>/delete", methods=["POST"])
def delete_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session.get("user_id")
    expense = get_expense_by_id(id, user_id)

    if not expense:
        abort(404)

    delete_expense_row(id, user_id)
    return redirect(url_for("profile"))


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5001)
