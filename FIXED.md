# VISHWAAS — Production Fixes Log

All issues identified in `ARCHITECT_REVIEW.md` that have been resolved in code.

---

## Fixes Applied

### 1. Production startup aborts if admin password hash is not set
**File:** `controller/backend/app/main.py`  
**Problem:** `VISHWAAS_ADMIN_PASSWORD_HASH` not set → auth was silently bypassed in dev mode; no guard prevented this from reaching production.  
**Fix:** Added startup check — if `environment=production` and `admin_password_hash` is empty, the controller logs a critical error and exits immediately.

---

### 2. Production startup aborts if CORS origins still point to localhost
**File:** `controller/backend/app/main.py`  
**Problem:** If `VISHWAAS_ALLOWED_ORIGINS` was left at its default (`localhost:3000`, `localhost:5173`) in production, the dashboard would fail to load from the real domain with no clear error.  
**Fix:** Added startup check — if `environment=production` and any configured origin contains `localhost` or `127.0.0.1`, the controller logs a critical error and exits immediately.

---

### 3. Removed `__import__` hack from auth dependency
**File:** `controller/backend/app/core/security.py`  
**Problem:** `require_auth` was injecting the DB session via a `lambda: next(__import__(...).get_db())` workaround to avoid a circular import. The circular import was an ordering issue, not an actual cycle.  
**Fix:** Added a clean top-level import of `get_db` from `app.persistence.database`. Confirmed no circular dependency exists (`database.py` does not import from `security.py`). Replaced the lambda with `Depends(get_db)`.

---

### 4. Removed `unsafe-inline` from nginx Content-Security-Policy (script-src)
**File:** `controller/nginx.conf`  
**Problem:** CSP allowed `'unsafe-inline'` for `script-src`, which means injected inline scripts (XSS vectors) would not be blocked by the browser.  
**Fix:** Removed `'unsafe-inline'` from `script-src`. Vite production builds output hashed static JS bundles with no inline scripts — this is safe to remove. Also tightened the policy with explicit `connect-src 'self'` and `font-src 'self' data:` directives. `'unsafe-inline'` is retained for `style-src` only, as component libraries may inject inline styles.

---

### 5. Dependency lockfiles added
**Files:** `controller/backend/requirements.lock`, `agent/requirements.lock`  
**Problem:** `requirements.txt` used version ranges (`>=`), making builds non-reproducible — a silent dependency update between deploys could introduce regressions or CVEs.  
**Fix:** Generated exact pinned lockfiles (`==`) from the currently installed virtualenvs:
- Controller: 46 packages pinned
- Agent: 19 packages pinned

To install from lockfile on a fresh deploy:
```bash
pip install -r requirements.lock
```

---

### 6. Production `.env` setup script
**File:** `controller/backend/setup_prod_env.sh`  
**Problem:** The four required production env vars (`JWT_SECRET`, `ADMIN_PASSWORD_HASH`, `ENVIRONMENT`, `ALLOWED_ORIGINS`) had to be set manually with no guidance, making it easy to miss one and ship with an insecure default.  
**Fix:** Added an interactive setup script that:
- Generates a cryptographically random JWT secret (`secrets.token_hex(32)`)
- Prompts for admin password and hashes it with bcrypt
- Prompts for the dashboard domain
- Writes a complete, correctly formatted `.env` with mode `600`
- Refuses to overwrite an existing `.env`

Usage:
```bash
export VISHWAAS_AGENT_TOKEN=<your-token>
cd controller/backend
bash setup_prod_env.sh
```

---

### 7. Pending database migration committed and documented
**File:** `controller/backend/alembic/versions/0002_add_performed_by_to_logs.py`  
**Problem:** Migration `0002` existed on disk but was not committed to version control, meaning a fresh clone of the repo would miss it.  
**Fix:** Committed the migration. It adds:
- `performed_by` column to the `logs` table (audit attribution)
- Index on `event_type` (query performance)
- Index on `created_at` (query performance)

Apply on existing deployments before starting the controller:
```bash
cd controller/backend
.venv/bin/alembic upgrade head
```

---

## What Still Requires Manual Action on the Production Machine

These cannot be automated in code — they require configuration on the server:

| Task | Command |
|------|---------|
| Generate production `.env` | `bash controller/backend/setup_prod_env.sh` |
| Apply DB migration | `cd controller/backend && .venv/bin/alembic upgrade head` |
| Obtain TLS certificate | `sudo certbot --nginx -d your-domain.com` |
| Start in production mode | `cd controller && ./start_controller.sh --prod` |

---

## Issues Accepted / Not Fixed

| Issue | Reason |
|-------|--------|
| Agent runs as root | Required for WireGuard interface management (`CAP_NET_ADMIN`); documented in `ARCHITECT_REVIEW.md` |
| JWT in browser `localStorage` | Acceptable for an internal admin-only dashboard; `HttpOnly` cookie support requires a larger backend refactor |
| SQLite in production | Acceptable for <50 nodes; migrate to PostgreSQL by changing `VISHWAAS_DATABASE_URL` if needed |
| No automated tests | Tracked as future work; no tests exist in the codebase today |
| `style-src 'unsafe-inline'` in CSP | Retained — component libraries use inline styles; removing it risks breaking the dashboard UI |

---

*Fixes applied: 2026-05-05*  
*Based on audit in `ARCHITECT_REVIEW.md`*
