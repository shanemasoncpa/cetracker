# CE Tracker - Multi-Agent Development Guide

## STARTUP REMINDER
**Before you begin work, open 4 terminal windows in this project folder and run `claude` in each one.**
Assign each terminal a role by pasting the role prompt from the Agent Roles section below.
The Manager agent (this one) coordinates all work. Do NOT start coding until agents are set up.

---

## Project Overview
- **App**: CE Tracker - free web app for tracking Continuing Education credentials
- **Stack**: Python Flask, SQLAlchemy, SQLite (dev) / PostgreSQL (prod), Jinja2 templates, vanilla CSS/JS
- **Deployment**: Render (see `render.yaml`, `Procfile`, `runtime.txt`)
- **Architecture**: Blueprint-based (refactored from monolithic app.py)
  - `app.py` — slim entry point (~105 lines), creates app, registers blueprints, schema migration
  - `models.py` — all SQLAlchemy models (User, CERecord, UserDesignation, Feedback)
  - `designation_helpers.py` — all 16 designation CE requirement calculators + NAPFA calculator
  - `blueprints/auth.py` — register, login, logout, forgot/reset password
  - `blueprints/ce_records.py` — dashboard, add/edit/delete CE, CSV import/export, PDF export, analytics
  - `blueprints/admin.py` — admin feedback routes with admin_required decorator
  - `blueprints/designations.py` — manage designations (add/remove)
  - `blueprints/profile.py` — profile/settings + feedback submission
  - `tests/` — pytest suite (39 tests covering auth + routes)

## Agent Roles

### Terminal 1: Manager (this terminal)
**Prompt to paste:** "You are the Manager agent for the CE Tracker project. Read CLAUDE.md for context. Your job is to coordinate work, review changes from other agents, update the Task Board below, and ensure no conflicts between agents. Do NOT write code directly - delegate to specialists."

### Terminal 2: Backend Agent
**Prompt to paste:** "You are the Backend specialist for CE Tracker. Read CLAUDE.md for context. You ONLY work on: app.py, database models, routes, and requirements.txt. Before making changes, check CLAUDE.md for your current assigned task. After completing a task, tell the manager agent what you changed."

### Terminal 3: Frontend Agent
**Prompt to paste:** "You are the Frontend specialist for CE Tracker. Read CLAUDE.md for context. You ONLY work on: templates/*.html and static/style.css. Before making changes, check CLAUDE.md for your current assigned task. After completing a task, tell the manager agent what you changed."

### Terminal 4: QA/Testing Agent
**Prompt to paste:** "You are the QA/Testing specialist for CE Tracker. Read CLAUDE.md for context. Your job is to: review code for bugs and security issues, write tests, run the app locally and verify features work, and report issues. Check CLAUDE.md for your current assigned task."

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
| `render.yaml`, `Procfile` | Manager Agent | - |

## Current State Assessment
### What's Built (Working) — as of 2026-02-23
- User registration with 17 designation options (CFP, CPA, CFA, EA, CEP, ECA, CLU, ChFC, CIMA, CIMC, CPWA, CRPS, RICP, CDFA, AIF, IAR, CLE)
- Login/logout with session auth + forgot/reset password
- User profile page (change email, password)
- Dashboard with CE records table, category filtering, stats
- Add/Edit/Delete CE records with PDF certificate upload
- CSV import (bulk upload historical CE records)
- CSV + PDF export (with category filter)
- NAPFA CE tracking with progress bars
- Designation-specific CE requirement tracking with calculators for all 16 designations
- Analytics page with Chart.js (category, monthly, yearly, provider charts)
- Manage designations page (add/remove)
- Feedback system (submit + admin view with is_admin role)
- Dark mode toggle with localStorage persistence
- Blueprint-based architecture (5 blueprints)
- 39 passing pytest tests
- Responsive design
- Deployed on Render with PostgreSQL

### Known Issues
1. **Database resets on deploy** — User data (including PDFs) appears to be lost when pushing to production. Needs investigation. Affected user: shanemasoncpa.
2. **No email notifications** — Password reset generates a token but doesn't email it (user must use the direct link)
3. **Certificate PDFs stored on ephemeral filesystem** — Render's filesystem resets on deploy, so uploaded PDFs are lost. Need cloud storage (S3/Cloudinary) or database storage.

## Task Board
Update this section as tasks are assigned and completed. Use status: TODO, IN PROGRESS, DONE.

### Completed (Previous Sessions)
| # | Task | Status |
|---|------|--------|
| 1-6 | Core functionality (edit CE, password reset, profile, NAPFA fix, cleanup, footer) | DONE |
| 7-8 | Test framework + auth tests (39 tests) | DONE |
| 9 | PDF export with reportlab | DONE |
| 10 | Analytics page with Chart.js | DONE |
| 11 | Refactor app.py into blueprints | DONE |
| 12 | 16 designation calculators | DONE |
| 13 | Admin auth (is_admin + decorator) | DONE |
| 14 | Dark mode toggle | DONE |
| 15 | Full QA pass | DONE |
| 16 | Deploy and verify on Render | DONE |
| 17 | Fix CPA state dropdown bug on registration | DONE |
| 18 | CSV importer for historical CE records | DONE |

### Current Sprint — ACTIVE TASKS
| # | Task | Agent | Status | Notes |
|---|------|-------|--------|-------|
| 19 | Investigate database reset issue on Render deploys | Backend | TODO | Why is user data being lost? Check if db.create_all() or migrations are dropping tables. Check Render PostgreSQL persistence. User affected: shanemasoncpa |
| 20 | Add CSV import test coverage | QA | TODO | Write tests for /import_ce route: valid CSV, missing columns, duplicate detection, bad dates, empty file |
| 21 | Improve mobile responsiveness of dashboard | Frontend | TODO | Test dashboard, modals, and import modal on small screens. Fix any overflow/layout issues. Check that the header-actions buttons wrap nicely on mobile. |
| 22 | Investigate certificate PDF persistence | Backend | TODO | Render's ephemeral filesystem loses uploaded files on redeploy. Research options: store PDFs as BLOBs in PostgreSQL, or use external storage. Document findings — do NOT implement yet, just report back. |

## Conventions
- **Python**: Follow PEP 8, use type hints for new functions
- **HTML**: Extend `base.html`, use Jinja2 template inheritance
- **CSS**: Use CSS custom properties (already defined in `:root`), BEM-like naming
- **Git**: Commit after each completed task with descriptive messages
- **Branches**: Work on `main` for now (solo project)
- **Flash messages**: Use categories `success`, `error`, `info`
- **Auth check pattern**: `if 'user_id' not in session:` at top of protected routes
