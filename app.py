from flask import Flask, render_template, request, redirect, url_for, session, g
from database.db import get_db, init_db, seed_db, get_user_by_email, get_user_by_id, aggregate_expenses, get_user_expenses, get_expense_summary
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

app = Flask(__name__)
app.secret_key = "dev-secret-key-spendly-step3"

with app.app_context():
    init_db()
    seed_db()


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

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE email = ?", (email,))
        result = cursor.fetchone()

        if result["count"] > 0:
            db.close()
            return render_template("register.html", error="Email is already registered. Please log in or use a different email.")

        try:
            hashed_password = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, hashed_password)
            )
            db.commit()
            db.close()
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            db.close()
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

    # Fetch real user data from database
    user = get_user_by_id(user_id)
    if not user:
        return redirect(url_for("login"))

    user_name = user["name"]
    user_email = user["email"]
    user_initials = "".join(word[0].upper() for word in user_name.split())
    member_since = user["created_at"]

    # Fetch user expenses and calculate summary stats
    expenses = get_user_expenses(user_id)

    # Transform expenses into format for transactions display
    transactions_data = [
        {
            "date": expense["date"],
            "description": expense["description"] or "",
            "category": expense["category"],
            "category_slug": expense["category"].lower(),
            "amount": f"{expense['amount']:.2f}"
        }
        for expense in expenses
    ]

    # Get summary stats
    summary = get_expense_summary(user_id)
    total_spent = summary["total"]
    transaction_count = summary["count"]
    top_category = summary["top_category"]
    categories = summary["categories"]

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
    }

    return render_template("profile.html", **context)


@app.route("/expenses/add")
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
