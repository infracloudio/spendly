from flask import Flask, render_template, request, redirect, url_for
from database.db import get_db, init_db, seed_db
from werkzeug.security import generate_password_hash
import sqlite3

app = Flask(__name__)

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


@app.route("/login")
def login():
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
    return "Logout — coming in Step 3"


@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
