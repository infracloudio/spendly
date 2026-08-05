# Spec: Login and Logout

## Overview
Step 3 implements user authentication by adding a POST /login route that verifies email and password credentials, creates a secure session for authenticated users, and implements a /logout route to clear the session. This enables the login flow to work end-to-end from registration → login → authenticated session.

## Depends on
Step 2 — Registration (users table has email and password_hash; users can register accounts).

## Routes
- `POST /login` — handle form submission, verify credentials, create session — public
- `GET /logout` — destroy session and redirect to login page — logged-in users only

## Database changes
No database changes. The users table created in Step 1 is sufficient.

## Templates
- **Modify:** `templates/login.html` — template already exists with POST form and error display; no changes needed unless styling is required

## Files to change
- `app.py` — add POST /login route handler and GET /logout route; configure Flask session; import werkzeug.security.check_password_hash and session

## Files to create
None.

## New dependencies
No new dependencies. werkzeug.security.check_password_hash is available via werkzeug (already imported).

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterized queries only (`?` placeholders)
- Passwords verified with `werkzeug.security.check_password_hash`
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Flask session support must be configured with app.secret_key
- Email lookup is case-sensitive (use exact match)
- On successful login: set session['user_id'] and redirect to profile page (or home if profile not yet implemented)
- On failed login: re-render login.html with error message "Invalid email or password"
- Logout: clear session and redirect to login page
- POST /login should check for empty fields and display appropriate error messages
- Session data must persist across requests (test by navigating between pages while logged in)

## Definition of done
- [ ] POST /login route accepts email and password form fields
- [ ] Email lookup: query database for user with matching email
- [ ] Password verification: uses check_password_hash to verify password
- [ ] Successful login: session['user_id'] is set and user redirected to next page
- [ ] Failed login: error message displayed on login form ("Invalid email or password")
- [ ] Empty fields: error message displayed on login form
- [ ] GET /logout route exists and destroys session
- [ ] After logout: session is cleared and user redirected to login page
- [ ] SQL uses parameterized queries (no f-strings in SQL)
- [ ] Flask app.secret_key is configured (use a reasonable default or environment variable)
- [ ] Session data persists across multiple page navigations while logged in
- [ ] PRAGMA foreign_keys is enforced in get_db()
