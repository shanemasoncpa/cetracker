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
- **URL structure**: Monolithic `app.py` (1288 lines), single `style.css` (1559 lines)

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
| `requirements.txt` | Backend Agent | - |
| `templates/*.html` | Frontend Agent | - |
| `static/style.css` | Frontend Agent | - |
| `static/js/*.js` | Frontend Agent | - |
| `tests/` | QA Agent | - |
| `CLAUDE.md` | Manager Agent | All agents should READ this |
| `render.yaml`, `Procfile` | Manager Agent | - |

## Current State Assessment
### What's Built (Working)
- User registration with designation selection (CFP, CPA, EA, CEP, ECA, + 12 more)
- Login/logout with session auth
- Dashboard with CE records table, category filtering, stats
- Add CE modal with PDF certificate upload
- Delete CE records
- CSV export (with category filter)
- NAPFA CE tracking with progress bars
- Designation-specific CE requirement tracking (CFP, CPA, EA, CEP, ECA)
- Manage designations page (add/remove)
- Feedback system (submit + admin view)
- Responsive design
- Render deployment config

### What Needs Work
1. **No Edit CE** - Users can add/delete but NOT edit existing CE records
2. **No Password Reset** - No forgot password flow
3. **No User Profile/Settings** - Can't change email, password, or profile info
4. **Monolithic app.py** - 1288 lines, should be refactored into blueprints
5. **No Tests** - Zero test coverage
6. **Hardcoded NAPFA cycle** - Locked to 2024-2025, needs dynamic calculation
7. **No PDF Export** - Only CSV export exists
8. **No Email Reminders** - Listed as future feature
9. **No Reporting/Analytics** - Only basic stats (total hours, record count)
10. **Missing designations** - CFA, CLE, CLU, ChFC, CIMA, CIMC, CPWA, CRPS, RICP, CDFA, AIF, IAR have no requirement calculators
11. **Admin auth is weak** - Uses URL query param key, no real admin system
12. **Footer says 2025** - Should say 2026
13. **Junk files** - `_ul`, `tmpclaude-*` files, backup `app-BKV00092LALO.py` should be cleaned up
14. **No dark mode** - Would improve UX
15. **Security** - Admin key has a hardcoded default (`cetracker2025admin`)

## Task Board
Update this section as tasks are assigned and completed. Use status: TODO, IN PROGRESS, DONE.

### Week 1 (Priority - Core Functionality)
| # | Task | Agent | Status | Notes |
|---|------|-------|--------|-------|
| 1 | Add Edit CE Record feature | Backend + Frontend | DONE | Edit route + modal with data attributes |
| 2 | Add Password Reset flow | Backend + Frontend | DONE | Profile page with change password (email reset later) |
| 3 | Add User Profile/Settings page | Backend + Frontend | DONE | Email update, password change, account info |
| 4 | Fix hardcoded NAPFA cycle dates | Backend | DONE | Dynamic 2-year cycle calculation |
| 5 | Clean up junk files | Manager | DONE | Removed _ul, tmpclaude-*, backup .py/.db |
| 6 | Update footer year to 2026 | Frontend | DONE | Quick fix |
| 7 | Set up test framework | QA | TODO | pytest + basic route tests |
| 8 | Write tests for auth flows | QA | TODO | Register, login, logout |

### Week 2 (Polish & Features)
| # | Task | Agent | Status | Notes |
|---|------|-------|--------|-------|
| 9 | Add PDF export | Backend + Frontend | TODO | Using reportlab or weasyprint |
| 10 | Add reporting/analytics page | Backend + Frontend | TODO | Charts, category breakdown |
| 11 | Refactor app.py into blueprints | Backend | TODO | auth, ce_records, admin, designations |
| 12 | Add more designation calculators | Backend | TODO | CFA, CPWA, CLU at minimum |
| 13 | Improve admin auth | Backend | TODO | Proper admin role on User model |
| 14 | Add dark mode toggle | Frontend | TODO | CSS variables approach |
| 15 | Full QA pass | QA | TODO | Test all features end-to-end |
| 16 | Deploy and verify on Render | Manager | TODO | Final production check |

## Conventions
- **Python**: Follow PEP 8, use type hints for new functions
- **HTML**: Extend `base.html`, use Jinja2 template inheritance
- **CSS**: Use CSS custom properties (already defined in `:root`), BEM-like naming
- **Git**: Commit after each completed task with descriptive messages
- **Branches**: Work on `main` for now (solo project)
- **Flash messages**: Use categories `success`, `error`, `info`
- **Auth check pattern**: `if 'user_id' not in session:` at top of protected routes
