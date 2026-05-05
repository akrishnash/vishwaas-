# VISHWAAS — Architect's Production Readiness Review

**Date:** 2026-05-05  
**Reviewer:** Senior Architect (AI-assisted audit)  
**Scope:** Full codebase review — controller, agent, frontend, deployment, database  
**Verdict:** Not production-ready yet. Architecture is sound; blockers are configuration gaps, not design flaws.

---

## Executive Summary

The application logic, security model, and state machine are well-designed and production-grade in intent. The two-phase node approval, atomic connection rollback, heartbeat lifecycle, JWT blacklisting, and Prometheus observability are all implemented correctly. What prevents a production deployment today is a set of configuration and hardening gaps — all fixable within a few hours.

---

## Blockers — Must Fix Before Going to Production

These must all be resolved before the service handles real traffic.

### 1. `VISHWAAS_JWT_SECRET` Not Set

- **File:** `controller/backend/.env`
- **Current state:** Variable missing; falls back to default `"change-me-in-production"`
- **Risk:** Anyone who knows the default can forge valid admin JWTs and take full control of the controller
- **Fix:**
  ```bash
  echo "VISHWAAS_JWT_SECRET=$(openssl rand -hex 32)" >> controller/backend/.env
  ```

### 2. `VISHWAAS_ADMIN_PASSWORD_HASH` Not Set (Dev Bypass Active)

- **File:** `controller/backend/.env`
- **Current state:** Variable missing; auth route (`routes/auth.py`) accepts any username/password in this mode
- **Risk:** Dashboard is publicly accessible with no authentication
- **Fix:**
  ```bash
  python3 -c "from passlib.hash import bcrypt; print(bcrypt.hash('YOURPASSWORD'))"
  # Add the output to .env as VISHWAAS_ADMIN_PASSWORD_HASH=<hash>
  ```

### 3. `VISHWAAS_ENVIRONMENT` Not Set to `production`

- **File:** `controller/backend/.env`
- **Current state:** Defaults to `development`; production startup guards in `main.py:40–53` never fire
- **Risk:** Misconfigured secrets go undetected at startup — no safety net
- **Fix:**
  ```bash
  echo "VISHWAAS_ENVIRONMENT=production" >> controller/backend/.env
  ```

### 4. `VISHWAAS_ALLOWED_ORIGINS` Not Set

- **File:** `controller/backend/.env`
- **Current state:** Defaults to `http://localhost:3000,http://localhost:5173`
- **Risk:** CORS policy will block requests from the real domain; dashboard won't load
- **Fix:**
  ```bash
  echo "VISHWAAS_ALLOWED_ORIGINS=https://your-domain.com" >> controller/backend/.env
  ```

### 5. Pending Database Migration Not Applied

- **File:** `controller/backend/alembic/versions/0002_add_performed_by_to_logs.py`
- **What it does:** Adds `performed_by` column to `logs` table; adds indexes on `event_type` and `created_at`
- **Risk:** Audit log missing attribution field; queries on logs table will be slow without indexes; app may crash on log writes if column is expected
- **Fix:**
  ```bash
  cd controller/backend
  .venv/bin/alembic upgrade head
  ```

### 6. No TLS on Agent ↔ Controller Channel

- **Files:** `agent/agent_config.json.example`, `controller/backend/app/api/schemas.py`
- **Current state:** Agent advertises and accepts `http://` URLs; all controller→agent calls are plain HTTP
- **Risk:** On any non-isolated network, agent tokens and WireGuard key material can be intercepted in transit (MITM)
- **Acceptable workaround:** If all machines are on a trusted private LAN (e.g., `192.168.10.0/24`) with no external access to management ports, the risk is low but must be documented explicitly
- **Proper fix:** Put each agent behind nginx with TLS and use `https://` agent URLs, or run the management plane itself through the VPN tunnel

---

## Warnings — Should Fix, Non-Blocking

These do not block deployment but introduce operational or security debt.

### 7. No Automated Tests

- **Finding:** No test files exist in the project (only node_modules and venv contain third-party tests)
- **Risk:** Regressions in critical flows (join approval, connection rollback, heartbeat) are undetectable without manual testing
- **Recommendation:** Add pytest integration tests covering at minimum:
  - `/request-join` → approve → ACTIVE state transition
  - Connection create → terminate → peer removal
  - Heartbeat OFFLINE and auto-delete behavior
  - Auth login/logout/token revocation

### 8. Agent Process Runs as Root

- **File:** `agent/vishwaas-agent.service:14`
- **Why it exists:** WireGuard interface creation (`ip link add`, `wg setconf`) requires root privileges
- **Risk:** A compromised agent process has full system access
- **Recommendation:** Document explicitly in deployment notes. Consider a capability-limited wrapper (e.g., `CAP_NET_ADMIN` only) in a future iteration

### 9. Admin JWT Stored in Browser `localStorage`

- **File:** `controller/frontend/src/context/AuthContext.jsx:9,11`
- **Risk:** XSS vulnerability (however unlikely on an internal dashboard) could leak the admin token
- **Assessment:** Acceptable for an internal admin-only tool; would not be acceptable on a user-facing public app
- **Recommendation:** Harden CSP (see item 11) to reduce XSS risk; consider `HttpOnly` cookie-based sessions in a future iteration

### 10. Dependencies Not Version-Pinned (No Lockfile)

- **Files:** `controller/backend/requirements.txt`, `agent/requirements.txt`
- **Current state:** Ranges like `fastapi>=0.115.0` allow any compatible version; builds are not reproducible
- **Risk:** A dependency update between deploys could introduce a regression or CVE unintentionally
- **Fix:**
  ```bash
  # Generate lockfiles
  cd controller/backend && .venv/bin/pip freeze > requirements.lock
  cd agent && venv/bin/pip freeze > requirements.lock
  ```

### 11. nginx CSP Contains `unsafe-inline`

- **File:** `controller/nginx.conf:48`
- **Current state:** `Content-Security-Policy` allows `'unsafe-inline'` for both `script-src` and `style-src`
- **Risk:** Weakens XSS protection on the dashboard — inline scripts/styles are not blocked by the browser
- **Recommendation:** Replace with nonce-based CSP. Requires Vite build tooling support (`vite-plugin-csp` or equivalent)

### 12. SQLite in Production

- **File:** `controller/backend/app/persistence/database.py`
- **Assessment:** SQLite is acceptable for small networks (<50 nodes, low-concurrency writes)
- **Risk:** Under concurrent load (heartbeat + user actions + agent callbacks all writing simultaneously), SQLite write locks may cause `OperationalError: database is locked`
- **Recommendation:** For networks >20 nodes or any HA setup, migrate to PostgreSQL. The existing SQLAlchemy code is database-agnostic — only `VISHWAAS_DATABASE_URL` needs to change

---

## What Is Already Production-Grade

These components were reviewed and found to be well-implemented:

| Component | Details |
|-----------|---------|
| **JWT auth with blacklist** | Logout revokes token via JTI; blacklist persisted in DB; expired entries pruned on startup |
| **Startup production guards** | `main.py` aborts if JWT secret or CORS are at defaults when `environment=production` |
| **Two-phase node approval** | Nodes enter as `PENDING` → admin approves → `APPROVED` → agent confirms → `ACTIVE`; never active without admin action |
| **Atomic connection rollback** | If peer B `add_peer` fails, peer A is rolled back with `remove_peer`; no half-broken connections created |
| **Heartbeat lifecycle** | 90s → OFFLINE; 5min → auto-delete; immediate startup sweep; stale join request expiry |
| **Agent restart handling** | On re-join with same key, all stale connections are torn down; admin must re-approve |
| **Correlation ID tracing** | `X-Request-ID` generated at ingress and forwarded to all agent calls |
| **Prometheus metrics** | HTTP request counts/latency, agent call outcomes, node state gauges |
| **Secrets management** | `.env` and `agent_config.json` correctly gitignored; not in version control |
| **Systemd hardening** | Controller: non-root user, `NoNewPrivileges`, `ProtectSystem=full`, `PrivateTmp` |
| **nginx security** | TLS 1.2+, HSTS, security headers, rate limiting on auth and join endpoints, metrics restricted to VPN subnet |
| **Input validation** | WireGuard public key (44-char base64), agent URL scheme, node name pattern all validated on join |
| **DB migrations** | Alembic runs `upgrade head` on startup; fresh and existing DBs both handled correctly |
| **Alembic migration 0002** | Well-formed; adds audit attribution and performance indexes to logs table |

---

## Production Deployment Checklist

Work through this in order before starting the service.

```
SECRETS & CONFIG
[ ] Set VISHWAAS_JWT_SECRET    (openssl rand -hex 32)
[ ] Set VISHWAAS_ADMIN_PASSWORD_HASH  (bcrypt hash of your admin password)
[ ] Set VISHWAAS_ENVIRONMENT=production
[ ] Set VISHWAAS_ALLOWED_ORIGINS=https://your-domain.com
[ ] Verify VISHWAAS_AGENT_TOKEN is set and matches all agent configs

DATABASE
[ ] Run:  cd controller/backend && .venv/bin/alembic upgrade head
[ ] Verify:  .venv/bin/alembic current  (should show  0002 (head))

TLS
[ ] Obtain TLS certificate for controller domain  (certbot --nginx -d your-domain.com)
[ ] Update nginx.conf: ssl_certificate / ssl_certificate_key paths
[ ] Decision: accept plain HTTP for agent channel (LAN-only) OR set up agent TLS

FIREWALL
[ ] Controller: allow 443 (nginx), block 8000 from public
[ ] Agents: allow agent port ONLY from controller IP; block all others

SYSTEMD
[ ] sudo systemctl enable vishwaas-controller
[ ] sudo systemctl start vishwaas-controller
[ ] sudo systemctl status vishwaas-controller  (confirm active)

SMOKE TEST
[ ] Dashboard loads at https://your-domain.com
[ ] Login works with the configured admin password
[ ] Start an agent on a node; join request appears in dashboard
[ ] Approve the join request; node goes ACTIVE
[ ] Create a connection between two nodes; WireGuard peering works
[ ] Terminate the connection; both nodes retain VPN IP

POST-DEPLOY
[ ] Confirm Prometheus metrics at /metrics (from VPN subnet only)
[ ] Confirm /ready returns 200 (DB connectivity check)
[ ] Set up log rotation for uvicorn logs
```

---

## Quick Fix Commands (Run in Order)

```bash
cd /path/to/vishwaas/controller/backend

# 1. Generate secrets
JWT_SECRET=$(openssl rand -hex 32)
ADMIN_HASH=$(python3 -c "from passlib.hash import bcrypt; print(bcrypt.hash('YOURPASSWORD'))")

# 2. Append to .env
cat >> .env <<EOF
VISHWAAS_ENVIRONMENT=production
VISHWAAS_JWT_SECRET=${JWT_SECRET}
VISHWAAS_ADMIN_PASSWORD_HASH=${ADMIN_HASH}
VISHWAAS_ALLOWED_ORIGINS=https://your-domain.com
EOF

# 3. Apply pending migration
.venv/bin/alembic upgrade head

# 4. Verify migration
.venv/bin/alembic current
# Expected output: 0002 (head)

# 5. Restart service
sudo systemctl restart vishwaas-controller
sudo systemctl status vishwaas-controller
```

---

## Architecture Assessment

The overall design follows sound principles:

- **Separation of concerns:** Controller, agent, and frontend are independently deployable
- **Fail-safe defaults:** Nothing is active without explicit admin approval at every stage
- **Audit trail:** All events logged with `performed_by`, timestamps, and correlation IDs
- **Graceful degradation:** Heartbeat handles unreachable agents without crashing; retries with backoff on agent calls
- **Idempotency:** Re-join and re-connection flows handle duplicate state without corruption

The system is appropriate for small-to-medium private networks. For enterprise scale (>50 nodes, multi-admin, HA), the recommended evolution path is: PostgreSQL → Redis for token blacklist cache → multi-region controller with shared DB.

---

*This document was generated from a full automated + manual audit of the VISHWAAS codebase on 2026-05-05.*
