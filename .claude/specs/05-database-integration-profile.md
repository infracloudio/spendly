# Spec: Database Integration for Profile Page

## Overview
This step replaces the hardcoded demo data on the `/profile` page with real queries to the `users` and `expenses` tables. The profile page UI layout from Step 4 remains unchanged, but all data — user info, summary stats, transaction history, and category breakdown — now comes from the logged-in user's actual database records. This is the first feature to show how the application loads and displays real user data.

## Depends on
- Step 1: Database setup (schema must exist)
- Step 2: Registration (user accounts must be creatable)
- Step 3: Login + Logout (session must be set; `/profile` must be a protected route)
- Step 4: Profile Page (UI layout and template structure must be complete)

## Routes
No new routes. The existing `GET /profile` route will be modified to fetch real data instead of passing hardcoded values.

## Database changes
No database changes. The existing `users` and `expenses` tables are sufficient.

## Templates
- **Modify:** `templates/profile.html` — no layout changes; the template remains identical, but the context variables it receives are now real data from queries

## Files to change
- `app.py` — modify the `/profile` route handler to:
  1. Query the `users` table to get the logged-in user's name and email
  2. Query the `expenses` table for all expenses belonging to `user_id` from session
  3. Calculate total spent (SUM of amount column)
  4. Calculate transaction count (COUNT of expense rows)
  5. Determine top category (category with highest total amount spent)
  6. Build a transaction list with all user's expenses
  7. Build category breakdown with totals and percentages
  8. Pass all calculated data to `profile.html`

- `database/db.py` — add helper functions:
  - `get_user_by_id(user_id)` — fetch user record by id; returns dict with id, name, email, created_at
  - `get_user_expenses(user_id)` — fetch all expenses for a user; returns list of dicts with id, amount, category, date, description
  - `get_expense_summary(user_id)` — calculate and return dict with: total_spent, transaction_count, top_category, category_breakdown (list of dicts with category, total, percentage)

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw sqlite3 via `get_db()` only
- Parameterised queries only — use `?` placeholders, never f-strings in SQL
- Enable `PRAGMA foreign_keys = ON` in `get_db()`
- All queries must be in `database/db.py`, never in route handlers
- Route handlers call helper functions and pass results to templates
- No hardcoded data in `/profile` handler (except error messages)
- All data passed to template must come from database queries
- Formatting (e.g., currency symbols, date formatting) happens in the template, not in Python
- Category colors use CSS variables, not hardcoded hex values
- Transaction dates must be in YYYY-MM-DD format from database

## Definition of done
- [ ] Visiting `/profile` while logged in shows the logged-in user's real name
- [ ] Visiting `/profile` shows the logged-in user's real email address
- [ ] Total spent stat reflects the SUM of all expenses for the logged-in user
- [ ] Transaction count stat reflects the actual number of expenses in the database
- [ ] Top category stat shows the category with highest total amount (ties: alphabetical order)
- [ ] Transaction history table displays all user's expenses sorted by date descending (newest first)
- [ ] Each transaction row shows: date (YYYY-MM-DD), description, category badge, amount
- [ ] Category breakdown shows all categories that have at least one expense, with totals and percentages
- [ ] Category percentages sum to 100% (rounded)
- [ ] Testing with demo user (demo@spendly.com) shows 8 transactions and correct stats
- [ ] Testing with a fresh user (0 expenses) shows "No transactions yet" or similar empty state message
- [ ] No hardcoded color hex values in `profile.html`
- [ ] All database queries are parameterised (no f-strings in SQL)
