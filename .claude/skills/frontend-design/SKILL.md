---
name: spendly-ui-design
description: Generate production-ready UI components and pages for Spendly expense tracker. Trigger when user says "Design/Create/Build the ___ page/component" or "Redesign/Improve ___" for Spendly. Output includes Jinja2 templates, vanilla CSS, and design rationale. Ensure modern fintech aesthetic with clean cards, soft shadows, 8px spacing grid, consistent styling, and intuitive UX. Match existing Spendly design patterns and use Lucide icons.
compatibility: Flask, Jinja2, Vanilla CSS (no frameworks)
---

# Spendly Frontend Designer

A skill for designing clean, production-ready UI pages and components for the Spendly expense tracker.

## What This Skill Does

Generates modern, high-quality UI for Spendly that:
- Matches the existing fintech design language
- Follows the 8px spacing grid and soft card-based layout
- Includes complete Jinja2 templates ready to drop into Flask
- Uses vanilla CSS (no Tailwind, no frameworks)
- Incorporates Lucide icons where appropriate
- Prioritizes usability and clarity

## When to Use This Skill

Use this skill whenever the user asks to:
- Design a new page (dashboard, reports, analytics, settings, transactions, etc.)
- Create a component (cards, forms, modals, navigation, etc.)
- Redesign or improve an existing Spendly page
- Build UI for a new feature

Keywords that trigger: "design", "create", "build", "redesign", "improve", "UI", "page", "component", "layout"

## Core Design System for Spendly

### Colors
- **Primary Brand**: #2563eb (Blue - actions, highlights)
- **Success**: #10b981 (Green - positive balance, income)
- **Danger**: #ef4444 (Red - overspending, expenses)
- **Warning**: #f59e0b (Amber - approaching limit)
- **Neutral Background**: #f9fafb (Light gray)
- **Card Background**: #ffffff (White)
- **Text Primary**: #111827 (Near black)
- **Text Secondary**: #6b7280 (Medium gray)
- **Border**: #e5e7eb (Light gray)

### Typography
- **Font Family**: System fonts: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif
- **Headings**: 600 weight (semibold)
  - H1: 28px, line-height: 1.3
  - H2: 24px, line-height: 1.35
  - H3: 20px, line-height: 1.4
- **Body Text**: 400 weight, 14-16px, line-height: 1.5
- **Labels/Small**: 12px, 500 weight

### Spacing (8px Grid)
- 8px, 16px, 24px, 32px, 48px
- Padding: 16px (default card), 24px (sections)
- Margins: 16px (between elements), 24px (between sections)
- Gap (flex): 12px (compact), 16px (default)

### Components Style Guide

#### Cards
```css
background: #ffffff;
border-radius: 12px;
box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05), 0 1px 3px rgba(0, 0, 0, 0.1);
padding: 16px;
border: 1px solid #e5e7eb;
```

#### Buttons
- **Primary**: background #2563eb, text white, radius 8px, 10px padding
- **Secondary**: background #f3f4f6, text #111827, radius 8px, 10px padding
- **Hover**: Slight brightness increase, subtle shadow
- **Disabled**: opacity 0.5

#### Forms
- Input: border 1px solid #d1d5db, radius 8px, padding 10px 12px
- Focus: border #2563eb, box-shadow 0 0 0 3px rgba(37, 99, 235, 0.1)
- Label: 12px, 500 weight, margin-bottom 6px

#### Tables
- Header background: #f9fafb
- Rows: alternating white/f9fafb on hover
- Padding: 12px per cell
- Border-bottom: 1px #e5e7eb between rows

### Layout Patterns
- **Header Bar**: 56px height, sticky, light background with border-bottom
- **Sidebar/Nav**: 240px width, vertical menu items with hover states
- **Main Content**: Margin auto, max-width varies (usually full with padding)
- **Card Grid**: 2-4 columns depending on screen, gap 16px
- **Dashboard**: Hero stat cards top, charts/tables below

### Responsive Breakpoints
- Mobile: max 100% width, single column
- Tablet: 600px+, 2 columns
- Desktop: 1024px+, 3-4 columns

## Output Structure

When designing a page or component, provide:

### 1. Design Rationale (Brief)
- Layout structure and UX decisions
- Key sections and information hierarchy
- Why certain patterns were chosen

### 2. HTML Template (Jinja2)
- Clean structure with semantic HTML
- CSS classes using a consistent naming scheme
- Icons from Lucide (using `<svg>` or icon classes)
- Dynamic placeholders for Flask variables

### 3. CSS Stylesheet
- Scoped to the component/page if needed
- Variables for colors (optional)
- Responsive media queries
- Hover/active states for interactive elements
- No external dependencies

### 4. Integration Notes
- Which Flask route this template maps to
- Required context variables from the backend
- Any JavaScript dependencies (minimal)

## Example: Add Expense Form

### Design Rationale
A modal/card that slides in from the right, with a simple step-by-step flow: date, category, amount, description. Uses primary blue for the submit button. Form validation on blur, helpful hints below each field.

### Template (Jinja2)
```html
<div class="modal modal-add-expense">
  <div class="modal-header">
    <h3>Add Expense</h3>
    <button class="btn-close" onclick="closeModal()">×</button>
  </div>
  <form id="expenseForm" class="expense-form">
    <!-- Date Field -->
    <div class="form-group">
      <label for="date">Date</label>
      <input type="date" id="date" name="date" value="{{ today }}" required>
      <small class="hint">Select the date of the expense</small>
    </div>

    <!-- Category Field -->
    <div class="form-group">
      <label for="category">Category</label>
      <select id="category" name="category" required>
        <option value="">Choose a category</option>
        {% for cat in categories %}
          <option value="{{ cat.id }}">{{ cat.name }}</option>
        {% endfor %}
      </select>
    </div>

    <!-- Amount Field -->
    <div class="form-group">
      <label for="amount">Amount</label>
      <input type="number" id="amount" name="amount" placeholder="0.00" min="0.01" step="0.01" required>
      <small class="hint">Enter the expense amount</small>
    </div>

    <!-- Description Field -->
    <div class="form-group">
      <label for="description">Description (Optional)</label>
      <textarea id="description" name="description" rows="3" placeholder="Add notes..."></textarea>
    </div>

    <!-- Submit Button -->
    <button type="submit" class="btn btn-primary btn-full">Add Expense</button>
  </form>
</div>
```

### CSS
```css
.modal-add-expense {
  position: fixed;
  right: -400px;
  top: 0;
  width: 400px;
  height: 100vh;
  background: white;
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.1);
  transition: right 0.3s ease;
  padding: 24px;
  overflow-y: auto;
}

.modal-add-expense.active {
  right: 0;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  border-bottom: 1px solid #e5e7eb;
  padding-bottom: 16px;
}

.btn-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #6b7280;
}

.expense-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
}

.form-group label {
  font-size: 12px;
  font-weight: 500;
  margin-bottom: 6px;
  color: #111827;
}

.form-group input,
.form-group select,
.form-group textarea {
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 14px;
  font-family: inherit;
}

.form-group input:focus,
.form-group select:focus,
.form-group textarea:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.hint {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
}

.btn-full {
  width: 100%;
  margin-top: 16px;
}
```

## Reference: Common Spendly Pages

### Pages to Design
- **Dashboard**: Overview with spending summary, recent transactions, quick-add button
- **Transactions**: Full list with filters, search, export
- **Analytics/Reports**: Charts by category, spending trends, budget vs. actual
- **Budget Setup**: Budget creation and management by category
- **Settings**: User preferences, categories, recurring expenses
- **Profile**: User info, notification preferences

### Common Components
- **Stat Card**: Icon + label + number (with trend indicator)
- **Transaction Row**: Date, category icon, description, amount (color-coded)
- **Category Badge**: Icon + category name + small amount
- **Spending Chart**: Simple bar or pie chart (use existing library or canvas)
- **Modal/Sidebar**: Form containers for adding/editing
- **Top Navigation**: Spendly logo, user menu, notifications

## Best Practices

### Do
- Use semantic HTML (`<header>`, `<nav>`, `<main>`, `<section>`)
- Include descriptive CSS class names (e.g., `.expense-card`, `.category-icon`)
- Test responsive design (mobile first approach)
- Keep CSS organized (structure, then colors, then interactive states)
- Use Lucide icons via SVG or icon font
- Document integration points in templates

### Avoid
- Inline styles
- Overly complex CSS (keep it vanilla and readable)
- Missing focus states (accessibility)
- Hard-coded values (use data attributes or variables)
- Unnecessary DOM nesting

## Testing the Skill

Test scenarios:
1. Design the dashboard page
2. Create an expense entry modal
3. Build the transaction list with filters
4. Design a spending report chart component
5. Create the settings/preferences page

Ask the user for feedback on:
- Visual hierarchy and clarity
- Responsiveness across devices
- Consistency with existing Spendly design
- Any missing elements or adjustments needed

## Integration with Flask

Typical Flask route:
```python
@app.route('/dashboard')
def dashboard():
    stats = get_spending_stats()
    recent = get_recent_transactions()
    return render_template('dashboard.html', stats=stats, recent=recent)
```

The Jinja2 template will access these variables directly with `{{ variable_name }}`.

---

**Questions?** Clarify design requirements, provide existing design samples if available, or confirm layout preferences.
