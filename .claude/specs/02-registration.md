# Spec: Registration

## Overview
Step 2 implements the user registration flow by adding a POST /register route that validates form input, checks for duplicate emails, hashes passwords, and creates new user accounts. The GET /register route already renders the registration form; this step completes the backend logic to handle account creation.

## Depends on
Step 1 — Database setup (users table exists with id, name, email, password_hash columns).

## Routes
- `POST /register` — handle form submission, validate input, create user account — public

## Database changes
No database changes. The users table created in Step 1 is sufficient.

## Templates
- **Modify:** `templates/register.html` — template already has POST form; may need styling for error display if not already present

## Files to change
- `app.py` — add POST /register route handler

## Files to create
None.

## New dependencies
No new dependencies. werkzeug.security is already imported in database/db.py.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterized queries only (`?` placeholders)
- Passwords hashed with `werkzeug.security.generate_password_hash`
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Validate email format (basic check: contains @)
- Check for duplicate email before insertion
- Validate password minimum length of 8 characters
- On success, redirect to login page
- On error, re-render register.html with error message displayed
- Handle database errors gracefully (e.g., constraint violations)

## Definition of done
- [ ] POST /register route accepts name, email, password form fields
- [ ] Email validation: rejects invalid email format
- [ ] Email uniqueness: rejects duplicate email with error message
- [ ] Password validation: rejects passwords shorter than 8 characters
- [ ] Password hashing: passwords are hashed before storage (verify via database inspection)
- [ ] On success: user record created and user redirected to login page
- [ ] On validation error: error message displayed on registration form and form fields retained
- [ ] SQL uses parameterized queries (no f-strings in SQL)
- [ ] PRAGMA foreign_keys is enforced in get_db()
