# VISHWAAS — Security Review

**Date:** 2026-05-06  
**Scope:** Full codebase — controller (FastAPI backend + React frontend), agent, nginx, deployment  
**Verdict:** Two bugs were found and fixed in this session. Remaining issues are known trade-offs, not oversights.

---

## Bugs Fixed in This Session

### BUG-01 — CRITICAL: Agents blocked from joining in production
**File:** `controller/backend/app/main.py`  
**Status:** Fixed

`/request-join` was wrapped by the global `_auth` router dependency alongside all other routes.
In dev mode (`ADMIN_PASSWORD_HASH` empty) this was invisible — `require_auth` returns `{"sub": "dev"}` for all requests.
In production (password hash set), `require_auth` demands a JWT. Agents have no JWT, so every join request was silently rejected with 401 — the entire join flow would be broken the moment the app was hardened.

The approve/reject endpoints inside the same router already carry their own `Depends(require_auth)`.
`list_join_requests` was given its own `Depends(require_auth)` too.
The router-level `_auth` wrapper was removed from `join.router` only — all other routers are unchanged.

**Result:** `/request-join` is now public (rate-limited to 10/minute); all admin-facing join endpoints remain JWT-protected.

---

### BUG-02 — HIGH: Timing attack on agent token comparison
**File:** `agent/app/security.py:27`  
**Status:** Fixed

Token validation used `x_vishwaas_token != expected` — a standard string inequality that short-circuits on the first differing byte. An attacker sending many requests and measuring sub-millisecond response time differences could recover the token one byte at a time.

Replaced with `hmac.compare_digest(x_vishwaas_token, expected)` which runs in constant time regardless of where strings diverge.

---

## Findings Not Fixed — Accepted Trade-offs

| # | Severity | Finding | Reason Accepted |
|---|----------|---------|-----------------|
| 1 | HIGH | WireGuard private keys sent over plain HTTP to agents | Acceptable on a trusted LAN; documented in `ARCHITECT_REVIEW.md`. Fix: TLS on agent channel |
| 2 | HIGH | Admin JWT stored in browser `localStorage` | Acceptable for internal admin dashboard. Real fix requires `HttpOnly` cookie session (backend refactor) |
| 3 | MEDIUM | `style-src 'unsafe-inline'` in nginx CSP | Component libraries use inline styles; removing it breaks the dashboard. Tracked in `ARCHITECT_REVIEW.md` |
| 4 | MEDIUM | Agent process runs as root | Required for `ip link` / `wg` commands. Documented. Mitigation: only controller IP reaches agent port |
| 5 | LOW | Username enumeration via login timing | Username is fixed to `"admin"` — it is not a secret. Practical impact is zero |
| 6 | LOW | SQLite has no WAL mode | Performance concern, not a security issue. Fine for <50 nodes |

---

## Security Controls Verified ✓

| Control | Implementation | Verdict |
|---------|---------------|---------|
| **JWT signing** | HS256, secret from env, startup aborts on default | ✓ Correct |
| **JWT expiry** | 8-hour expiry, `exp` claim validated by python-jose | ✓ Correct |
| **JWT revocation** | JTI blacklist in DB, checked per request, pruned on startup | ✓ Correct |
| **Brute force protection** | bcrypt for password, rate limit on `/auth/login` (20/min nginx + slowapi) | ✓ Correct |
| **CORS** | Whitelist from env, `*` blocked in prod, localhost blocked in prod | ✓ Correct |
| **Agent authentication** | `X-VISHWAAS-TOKEN` required on all endpoints except `/health`; now constant-time | ✓ Fixed |
| **Join request auth** | `/request-join` public + rate-limited; list/approve/reject JWT-gated | ✓ Fixed |
| **Input validation** | WireGuard key (44-char base64), node name regex, agent URL scheme all validated | ✓ Correct |
| **SQL injection** | SQLAlchemy ORM with bound parameters throughout; no raw SQL | ✓ Correct |
| **Shell injection** | WireGuard commands use list form (`subprocess.run([...])`) not shell=True | ✓ Correct |
| **Secrets in git** | `.env` and `agent_config.json` gitignored; confirmed not in history | ✓ Correct |
| **Production guards** | Startup aborts if JWT secret/admin hash/CORS origins are insecure defaults | ✓ Correct |
| **TLS (controller)** | nginx enforces TLS 1.2+, HSTS, strong ciphers | ✓ Correct |
| **Security headers** | X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy | ✓ Correct |
| **Metrics endpoint** | Restricted to localhost + VPN subnet via nginx allow/deny | ✓ Correct |
| **Audit trail** | All approve/reject/connect/terminate events logged with `performed_by` and timestamp | ✓ Correct |
| **Systemd hardening** | Controller: non-root, NoNewPrivileges, ProtectSystem, PrivateTmp | ✓ Correct |
| **File permissions** | Agent install creates `/etc/vishwaas` with mode 700 | ✓ Correct |

---

## What Must Be Done on the Production Machine

None of these can be automated in code — they are server configuration steps:

```bash
# 1. Generate production .env (JWT secret, bcrypt hash, domain)
export VISHWAAS_AGENT_TOKEN=<your-token>
bash controller/backend/setup_prod_env.sh

# 2. Apply DB migration
cd controller/backend && .venv/bin/alembic upgrade head

# 3. Obtain TLS certificate
sudo certbot --nginx -d your-domain.com

# 4. Start in production mode
cd controller && ./start_controller.sh --prod
```

---

*Security review completed: 2026-05-06*  
*Based on full static analysis of controller, agent, frontend, nginx, and deployment scripts.*
