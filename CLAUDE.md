# CE Tracker - Multi-Agent Development Guide

## STARTUP REMINDER
**Before you begin work, open 4 terminal windows in this project folder and run `claude` in each one.**
Assign each terminal a role by pasting the role prompt from the Agent Roles section below.
The Manager agent (this one) coordinates all work. Do NOT start coding until agents are set up.

---

## Project Overview
- **App**: CE Tracker - free web app for tracking Continuing Education credentials
- **Stack**: Python Flask, SQLAlchemy, SQLite (dev) / PostgreSQL (prod), Jinja2 templates, vanilla CSS/JS
- **Deployment**: Railway with PostgreSQL (migrated from Render, Feb 2026). Auto-deploys on push to `main`.
- **Architecture**: Blueprint-based (refactored from monolithic app.py)
  - `app.py` — slim entry point (~105 lines), creates app, registers blueprints, schema migration
  - `models.py` — all SQLAlchemy models (User, CERecord, UserDesignation, Feedback)
  - `designation_helpers.py` — all 16 designation CE requirement calculators + NAPFA calculator
  - `blueprints/auth.py` — register, login, logout, forgot/reset password
  - `blueprints/ce_records.py` — dashboard, add/edit/delete CE, CSV import/export, PDF export, analytics
  - `blueprints/admin.py` — admin feedback routes with admin_required decorator
  - `blueprints/designations.py` — manage designations (add/remove)
  - `blueprints/profile.py` — profile/settings + feedback submission
  - `tests/` — pytest suite (81 tests covering auth, routes, CSV import, backup)

## Agent Roles

### Terminal 1: Manager (this terminal)
**Prompt to paste:** "You are the Manager agent for the CE Tracker project. Read CLAUDE.md for context. Your job is to coordinate work, review changes from other agents, update the Task Board below, and ensure no conflicts between agents. Do NOT write code directly - delegate to specialists."

### Terminal 2: Backend Agent
**Prompt to paste:** "You are the Backend specialist for CE Tracker. Read CLAUDE.md for full context and rules. You ONLY work on: app.py, models.py, designation_helpers.py, blueprints/*.py, and requirements.txt. IMPORTANT RULES: (1) Only do exactly what your assigned task says — nothing more. (2) If the task says 'investigate' or 'report', do NOT make any code changes — only read files and report findings. (3) Never remove features, delete columns, or make architectural decisions without explicit Manager approval. (4) After completing a task, report back with: what files you changed (if any), what you found (if investigating), and what you recommend next."

### Terminal 3: Frontend Agent
**Prompt to paste:** "You are the Frontend specialist for CE Tracker. Read CLAUDE.md for full context and rules. You ONLY work on: templates/*.html, static/style.css, and static/js/*.js. IMPORTANT RULES: (1) Only do exactly what your assigned task says — nothing more. (2) Do not remove features or UI elements unless the Manager explicitly tells you to. (3) After completing a task, report back with: what files you changed, what you added/removed, and any issues you found."

### Terminal 4: QA/Testing Agent
**Prompt to paste:** "You are the QA/Testing specialist for CE Tracker. Read CLAUDE.md for full context and rules. Your job is to: review code for bugs and security issues, write tests, run the app locally and verify features work, and report issues. IMPORTANT RULES: (1) Only do exactly what your assigned task says — nothing more. (2) Only edit files in tests/. Never edit app code — report bugs to the Manager instead. (3) After completing a task, report back with: what tests you added, how many pass/fail, and any bugs found."

## Agent Coordination Protocol

### Task Types
Each task assigned to an agent will be one of these types. Follow the rules for your task type:

- **IMPLEMENT** — Write code to add/change functionality. Edit only your owned files. Report what you changed.
- **INVESTIGATE** — Read files, analyze, and report findings. Do NOT edit any files. Only report what you found and recommend next steps.
- **REMOVE** — Delete specific code/features as listed. Only remove exactly what's specified. Report what you removed.
- **FIX** — Fix a specific bug. Only change what's needed for the fix. Report what you changed and how to verify.

### Communication Format
When reporting back to the Manager (via Shane copying your message), use this format:
```
TASK: #[number] — [task name]
TYPE: [IMPLEMENT/INVESTIGATE/REMOVE/FIX]
STATUS: [DONE/BLOCKED/PARTIAL]
FILES CHANGED: [list files, or "None" for investigate tasks]
SUMMARY: [1-3 sentences on what you did or found]
NEEDS NEXT: [what should happen next, or "Nothing — ready for review"]
```

### Rules for ALL Agents
1. **Read CLAUDE.md before every task** — it's the source of truth
2. **Stay in your lane** — only edit files you own (see File Ownership Rules)
3. **Do exactly what's assigned** — no more, no less. Don't "improve" adjacent code.
4. **Never make architectural decisions** — if you think something should be added/removed/restructured, recommend it in your report. The Manager decides.
5. **Don't chain tasks** — complete your assigned task, report back, and wait for the next assignment
6. **If blocked, say so** — don't try workarounds. Report what's blocking you.

## File Ownership Rules
| File(s) | Owner | Others may read but NOT edit |
|---------|-------|------------------------------|
| `app.py` | Backend Agent | - |
| `models.py` | Backend Agent | - |
| `designation_helpers.py` | Backend Agent | - |
| `blueprints/*.py` | Backend Agent | - |
| `requirements.txt` | Backend Agent | - |
| `templates/*.html` | Frontend Agent | - |
| `static/style.css` | Frontend Agent | - |
| `static/js/*.js` | Frontend Agent | - |
| `tests/` | QA Agent | - |
| `CLAUDE.md` | Manager Agent | All agents should READ this |
| `Procfile`, `render.yaml` (legacy) | Manager Agent | - |

## Current State Assessment
### What's Built (Working) — as of 2026-02-23
- User registration with 17 designation options (CFP, CPA, CFA, EA, CEP, ECA, CLU, ChFC, CIMA, CIMC, CPWA, CRPS, RICP, CDFA, AIF, IAR, CLE)
- Login/logout with session auth + forgot/reset password
- User profile page (change email, password)
- Dashboard with CE records table, category filtering, stats
- Add/Edit/Delete CE records
- CSV import (bulk upload historical CE records)
- CSV + PDF export (with category filter)
- NAPFA CE tracking with progress bars
- Designation-specific CE requirement tracking with calculators for all 16 designations
- Analytics page with Chart.js (category, monthly, yearly, provider charts)
- Manage designations page (add/remove)
- Feedback system (submit + admin view with is_admin role)
- Dark mode toggle with localStorage persistence
- Blueprint-based architecture (5 blueprints)
- 81 passing pytest tests
- Mobile-responsive design
- JSON backup export/import
- Deployed on Railway with PostgreSQL (persistent DB)

### Known Issues
1. **No email notifications** — Password reset generates a token but doesn't email it (user must use the direct link)
2. **Certificate upload removed** — Removed due to Render's ephemeral filesystem. Now on Railway with persistent storage — could re-add if needed (BYTEA or S3).

### Recently Removed
- **Certificate PDF upload/download** — Fully removed from backend and frontend (models.py, ce_records.py, app.py, dashboard.html, add_ce.html).

## Task Board
Update this section as tasks are assigned and completed. Use status: TODO, IN PROGRESS, DONE.

### Completed
| # | Task | Status |
|---|------|--------|
| 1-6 | Core functionality (edit CE, password reset, profile, NAPFA fix, cleanup, footer) | DONE |
| 7-8 | Test framework + auth tests | DONE |
| 9 | PDF export with reportlab | DONE |
| 10 | Analytics page with Chart.js | DONE |
| 11 | Refactor app.py into blueprints | DONE |
| 12 | 16 designation calculators | DONE |
| 13 | Admin auth (is_admin + decorator) | DONE |
| 14 | Dark mode toggle | DONE |
| 15 | Full QA pass | DONE |
| 16 | Deploy and verify on Render (later migrated to Railway) | DONE |
| 17 | Fix CPA state dropdown bug on registration | DONE |
| 18 | CSV importer for historical CE records | DONE |
| 19 | INVESTIGATE: DB reset on Render — Render free-tier PostgreSQL recycles DBs | DONE |
| 20 | Add CSV import test coverage (14 new tests, 53 total) | DONE |
| 21 | Improve mobile responsiveness of dashboard | DONE |
| 22 | INVESTIGATE + REMOVE: Certificate upload — removed backend, frontend cleanup needed | DONE |
| 23 | Remove certificate upload UI from templates | DONE |
| 24 | Add "Export All Data" JSON backup endpoint | DONE |
| 25 | Verify certificate removal doesn't break tests (81 passing) | DONE |
| 26 | Migrate from Render to Railway with persistent PostgreSQL | DONE |
| 27 | Update CLAUDE.md to reflect Railway deployment + current state | DONE |

### Current Sprint — ACTIVE TASKS
| # | Task | Type | Agent | Status | Notes |
|---|------|------|-------|--------|-------|
| — | No active tasks | — | — | — | Ready for next sprint |

## Conventions
- **Python**: Follow PEP 8, use type hints for new functions
- **HTML**: Extend `base.html`, use Jinja2 template inheritance
- **CSS**: Use CSS custom properties (already defined in `:root`), BEM-like naming
- **Git**: Commit after each completed task with descriptive messages
- **Branches**: Work on `main` for now (solo project)
- **Flash messages**: Use categories `success`, `error`, `info`
- **Auth check pattern**: `if 'user_id' not in session:` at top of protected routes
