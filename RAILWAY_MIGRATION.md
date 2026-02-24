# Railway Migration Guide — CE Tracker

## Prerequisites

- [ ] All code changes committed (done — `58b2939`)
- [ ] Pause multi-agent development until migration is verified
- [ ] GitHub repo is up to date (`git push` before starting)

---

## Step 1: Export Data from Render

If your Render database hasn't been recycled, grab a backup first. Get the connection string from the Render dashboard under your PostgreSQL service → "Connections" → "External Connection String".

```bash
pg_dump "YOUR_RENDER_DATABASE_URL" > ce_tracker_backup.sql
```

If the DB has already been recycled (no data), skip this step — you'll start fresh on Railway.

---

## Step 2: Create Railway Account + Project

1. Go to [railway.app](https://railway.app) and sign up (GitHub login is easiest)
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Connect your GitHub account if prompted
5. Select the **CE Tracker** repository
6. Railway will auto-detect Python from your `Procfile` and `requirements.txt`

---

## Step 3: Add PostgreSQL Database

1. Inside your Railway project, click **"+ New"** in the top-right
2. Select **"Database"** → **"PostgreSQL"**
3. Railway provisions a persistent Postgres instance immediately
4. Click on the PostgreSQL service → **"Variables"** tab → copy the `DATABASE_URL` value (you'll need it if restoring data)

---

## Step 4: Link the Database to Your App

1. Click on your **web service** (the one deployed from GitHub)
2. Go to the **"Variables"** tab
3. Click **"Add a Variable Reference"** or **"New Variable"**
4. Add a reference to the PostgreSQL service's `DATABASE_URL` — Railway can auto-link this:
   - Click **"Add Reference Variable"** → select the Postgres service → select `DATABASE_URL`
5. This makes `DATABASE_URL` available to your app as an environment variable

---

## Step 5: Set SECRET_KEY

Still in your web service's **"Variables"** tab:

1. Click **"New Variable"**
2. Key: `SECRET_KEY`
3. Value: Generate one by running this locally:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

4. Paste the output as the value

**Do NOT set `PORT`** — Railway handles this automatically.

---

## Step 6: Verify Python Version (if needed)

Railway should pick up your `runtime.txt` (`python-3.11.9`). If the build fails with a Python version error, create a file called `nixpacks.toml` in the project root:

```toml
[variables]
PYTHON_VERSION = "3.11"
```

**Try without this file first** — only add it if the deploy fails.

---

## Step 7: Deploy

1. Push your latest code to GitHub:

```bash
git push origin main
```

2. Railway auto-deploys on push. Watch the build logs in the Railway dashboard.
3. If the build succeeds, Railway assigns a URL like `ce-tracker-production-xxxx.up.railway.app`
4. Find your URL: click on your web service → **"Settings"** tab → **"Networking"** → **"Generate Domain"**

---

## Step 8: Verify Everything Works

Test these flows on your new Railway URL:

- [ ] Register a new account
- [ ] Log in
- [ ] Add a CE record
- [ ] View the dashboard — record appears
- [ ] Log out and log back in — data persists
- [ ] Check analytics page
- [ ] Test CSV export
- [ ] Test CSV import (use a small test file)

---

## Step 9: Restore Data (if applicable)

If you exported a backup in Step 1, restore it to Railway. Get the Railway database connection string from the PostgreSQL service → "Variables" → `DATABASE_URL`.

```bash
psql "YOUR_RAILWAY_DATABASE_URL" < ce_tracker_backup.sql
```

After restoring, log in with an existing account to verify data came through.

---

## Step 10: Decommission Render

Wait a few days to make sure Railway is stable, then:

1. Go to the Render dashboard
2. Delete the web service
3. Delete the PostgreSQL database
4. Optionally remove `render.yaml` from your repo (harmless to keep)

---

## Troubleshooting

### Build fails with "no module named X"
Your `requirements.txt` should be auto-detected. Make sure it's in the repo root.

### App starts but crashes immediately
Check the deploy logs in Railway. Most likely cause: `DATABASE_URL` isn't linked properly. Verify it shows up in your web service's Variables tab.

### "postgres://" vs "postgresql://" error
Already handled in `app.py` (lines 13-14). Your code converts `postgres://` to `postgresql://` automatically.

### Database tables not created
Your `app.py` calls `db.create_all()` and `update_database_schema()` on startup. Tables are created automatically on first deploy.

### Custom domain (later)
Railway supports custom domains on paid plans. Go to your web service → Settings → Networking → Custom Domain.

---

## After Migration: Resume Development

Once verified:

1. Update `CLAUDE.md` deployment section to reference Railway instead of Render
2. Resume the multi-agent development workflow
3. Continue with the task board
