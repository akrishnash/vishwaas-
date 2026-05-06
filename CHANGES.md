# VISHWAAS — Changes Report

All changes made to the controller (backend + nginx) and agent since the initial commit (`08ee1a1`).
Organised by component. Each section lists the file, what changed, and why.

---

## Controller — Backend (`controller/backend/`)

### `app/main.py`

| What changed | Why |
|---|---|
| Added production startup abort if `VISHWAAS_ADMIN_PASSWORD_HASH` is not set | Prevents running in production with no authentication — anyone could log in |
| Added production startup abort if `VISHWAAS_ALLOWED_ORIGINS` contains `localhost` or `127.0.0.1` | Prevents CORS misconfiguration — in production the dashboard must only accept requests from its real domain |
| Removed `join.router` from the global `_auth` dependency wrapper | **Critical bug (BUG-01)**: agents submitting join requests have no JWT; wrapping the entire join router in `require_auth` made every `POST /request-join` return 401 in production, breaking the entire join flow. This bug was invisible in dev mode because dev mode bypasses auth for everyone |
| Imported `limiter` from `app.core.rate_limiter` instead of creating a new instance | The join route was also creating its own `Limiter()`, giving two separate rate-limit counters. Production had no actual cross-route enforcement; the test suite could not reset the correct counter |
| Removed duplicate `Limiter(key_func=get_remote_address)` call | Cleaned up after moving limiter to shared module |
| Added `CorrelationMiddleware` | Attaches a `X-Request-ID` UUID to every request; forwarded to agent calls for end-to-end tracing |
| Added `PrometheusMiddleware` | Tracks `vishwaas_http_requests_total` and `vishwaas_http_request_duration_seconds` |
| Added `prune_revoked_tokens()` on startup | Clears expired JWT blacklist entries so the `revoked_tokens` table doesn't grow unbounded |
| Added heartbeat task to lifespan | Starts the 60-second sweep loop; was previously absent |
| Added shared HTTP pool init/close in lifespan | `httpx.AsyncClient` is now reused across all agent calls instead of creating a new connection per call |

---

### `app/core/rate_limiter.py` *(new file)*

Created a single shared `Limiter` instance (`from slowapi import Limiter`). Both `main.py` and `join.py` now import from here. Previously each module created its own `Limiter`, so they had independent storage: rate limit state in `join.py` was invisible to `main.py`, and test resets targeted the wrong object.

---

### `app/core/security.py`

| What changed | Why |
|---|---|
| Replaced `passlib.handlers.bcrypt.CryptContext` with direct `bcrypt.checkpw()` | `passlib 1.7.4` is incompatible with `bcrypt >= 4.0.0`: it uses `bcrypt.__about__` (removed in 4.0) and a >72-byte test password rejected by bcrypt 5.0. Production login would crash with `AttributeError` on every attempt |
| Replaced `__import__("app.persistence.database")` hack with `from app.persistence.database import get_db` | The `__import__` workaround was not needed; there is no circular dependency when the import is structured correctly |
| Added `jti` (JWT ID) claim to every token | Enables per-token revocation |
| Added `revoke_token()` — writes JTI to `revoked_tokens` table | Called by `POST /auth/logout` |
| Added `prune_revoked_tokens()` — deletes expired JTIs | Called at startup to keep the blacklist table clean |
| Added `_is_token_revoked()` check in `_decode_token()` | Every authenticated request checks the blacklist; revoked tokens are rejected with 401 |

---

### `app/core/heartbeat.py`

| What changed | Why |
|---|---|
| Added `startup=True` mode — one immediate sweep runs before the first 60s sleep | After a controller restart, stale ACTIVE nodes from the previous run were showing as healthy for up to 90s. The startup sweep marks them OFFLINE within seconds of the backend starting |
| Stage 1 (90s offline): mark node `OFFLINE` | Makes unreachable nodes visible on the dashboard without immediately deleting them |
| Stage 2 (5 min offline): auto-delete node + its connections | Cleans up nodes that are truly gone; avoids manual admin cleanup |
| Nodes with `last_seen=None` skipped in offline/delete logic | Belt-and-suspenders guard — freshly approved nodes start with `last_seen=None`; without this guard they would be auto-deleted on the very first heartbeat sweep |
| Added `_expire_stale_join_requests()` | After each sweep, pings agents with PENDING join requests. If unreachable for >120s the request is marked REJECTED so offline agents stop cluttering the dashboard |
| Prometheus gauges updated after each sweep | `vishwaas_nodes_active_total` and `vishwaas_nodes_offline_total` reflect current state |

---

### `app/core/config.py`

Added fields: `jwt_secret`, `allowed_origins`, `environment`, `admin_password_hash`, `admin_username`. Previously these were hardcoded or absent, making it impossible to configure production securely from environment variables.

---

### `app/core/logging_config.py` *(new file)*

`VISHWAAS_LOG_JSON=true` switches to `python-json-logger` with `service` and `level` fields. Defaults to plain text. Structured JSON logging is needed for log aggregation pipelines (Loki, Datadog, CloudWatch).

---

### `app/core/metrics.py` *(new file)*

Prometheus counters and gauges:
- `vishwaas_http_requests_total` — per-route request counts
- `vishwaas_http_request_duration_seconds` — latency histogram
- `vishwaas_agent_calls_total` — success/failure per agent operation
- `vishwaas_nodes_active_total`, `vishwaas_nodes_offline_total`
- `vishwaas_join_requests_pending_total`

---

### `app/core/correlation.py` *(new file)*

`ContextVar` holding the `X-Request-ID` for the current request. Set by `CorrelationMiddleware` in `main.py`, read by `agent_client.py` to forward the ID to every outbound agent call.

---

### `app/core/http_client.py` *(new file)*

Shared `httpx.AsyncClient` pool. Previously every agent call opened and closed its own TCP connection. The shared pool reuses connections and respects the pool lifecycle (init on startup, close on shutdown).

---

### `app/api/routes/join.py`

| What changed | Why |
|---|---|
| Added explicit `Depends(require_auth)` to `list_join_requests` | Without this, removing the router-level auth wrapper (BUG-01 fix) would have left `GET /join-requests` completely open |
| Stamp `node.last_seen = now` on approval before commit | Without this, the heartbeat would see `last_seen=None` on a freshly approved node and treat it as "never pinged" — exceeding the delete threshold immediately and auto-deleting the node before it could connect |
| **Restart handling**: when an agent rejoins with a known key, all active connections are torn down, old node is deleted, and a fresh PENDING is created | Ensures admin must explicitly re-approve every restart; prevents stale WireGuard peer state from persisting after a node reboots |
| Input validation on `RequestJoinBody`: `node_name` pattern (`[a-zA-Z0-9._-]+`), WireGuard key length/format, `agent_url` scheme (`http` or `https` only) | Rejects malformed requests early rather than storing invalid data |
| Rate limiting: `@limiter.limit("10/minute")` on `POST /request-join` | Prevents join-request flooding from a single IP |
| `skip` + `limit` pagination on `GET /join-requests` | Prevents unbounded responses when many join requests accumulate |
| Imported `limiter` from `app.core.rate_limiter` | Fixes the duplicate-limiter bug described in `main.py` above |

---

### `app/api/routes/auth.py` *(new file)*

- `POST /auth/login` — dev mode accepts any credentials when `ADMIN_PASSWORD_HASH` is empty; production verifies bcrypt hash
- `POST /auth/logout` — adds the token's `jti` to `revoked_tokens`; subsequent requests with that token are rejected

---

### `app/api/routes/health.py` *(new file)*

- `GET /health` — liveness probe; always returns 200
- `GET /ready` — readiness probe; runs `SELECT 1` and returns 503 if the database is down. Kubernetes and load balancers can use this to avoid routing traffic to a backend with no DB connection

---

### `app/api/routes/monitoring.py`

| What changed | Why |
|---|---|
| `GET /stats` — `total_nodes` now counts only ACTIVE + APPROVED | OFFLINE nodes are unreachable agents awaiting deletion. Counting them inflated the dashboard node count |
| `GET /topology` — returns only ACTIVE + APPROVED nodes | Previously returned all nodes including OFFLINE; the network map was showing dead nodes as if they were active peers |

---

### `app/services/join_service.py`

| What changed | Why |
|---|---|
| Node inserted as `APPROVED` (not `ACTIVE`) | Two-phase approval: the node is only upgraded to `ACTIVE` after the agent confirms it received the VPN configuration. Inserting as `ACTIVE` immediately was incorrect — the agent might be unreachable |
| `get_next_vpn_ip()` added | Scans existing node IPs and returns the lowest unused address in the pool. Prevents IP conflicts when multiple nodes are approved |

---

### `app/services/connection_service.py`

| What changed | Why |
|---|---|
| Atomic `add_peer` rollback: if `add_peer(node_a)` succeeds but `add_peer(node_b)` fails, calls `remove_peer(node_a)` before returning 502 | Without this, node A would have node B as a WireGuard peer but no connection record existed. The VPN state and database would be inconsistent |
| `terminate_connection_and_teardown` calls `remove_peer` on both agents only | Previous version called `wg_down` when a node had no remaining connections, tearing down the entire WireGuard interface. Nodes should keep their VPN interface and IP; only the peer relationship should be removed |

---

### `app/services/agent_client.py`

| What changed | Why |
|---|---|
| Switched from `httpx.AsyncClient()` per call to shared pool | One TCP handshake per agent call was wasteful and slow. The shared pool reuses connections |
| Added `_call_with_retry()` — exponential backoff, 2 retries (1s, 2s) | Transient network errors between controller and agent no longer immediately fail the operation |
| `X-Request-ID` header forwarded to every agent request | Correlates controller logs with agent logs for a single operation |
| Prometheus counter incremented on success and failure | `vishwaas_agent_calls_total` tracks reliability of each agent endpoint |

---

### `app/persistence/models.py`

| What changed | Why |
|---|---|
| Added `RevokedToken` table (`jti`, `expires_at`) | JWT blacklist for logout support |
| `Node.status` path changed from `PENDING → ACTIVE` to `PENDING → APPROVED → ACTIVE` | Reflects the two-phase approval lifecycle |
| Added `Node.last_seen` | Heartbeat uses this to detect offline nodes |
| Added `logs` table with `event_type`, `performed_by`, `details` columns + indexes on `event_type` and `created_at` | Immutable audit trail; `performed_by` added via migration `0002_add_performed_by_to_logs.py` |

---

### `alembic/` *(new)*

Replaced `Base.metadata.create_all()` with Alembic-managed migrations.

- `0001_initial_schema.py` — baseline capturing all tables including `revoked_tokens`
- `0002_add_performed_by_to_logs.py` — adds `performed_by` column + indexes to `logs`

Existing databases must run `alembic stamp head` once before the first upgrade.

---

### `setup_prod_env.sh` *(new file)*

Interactive script that:
1. Generates a cryptographically random JWT secret (`secrets.token_hex(32)`)
2. Prompts for admin password and hashes it with `bcrypt` directly (no passlib)
3. Prompts for dashboard domain
4. Writes `.env` with mode `600`

Refuses to run if `.env` already exists or if `VISHWAAS_AGENT_TOKEN` is not pre-set in the shell.

---

### `requirements.lock` *(new file)*

46 packages with exact pinned versions from the production venv. Prevents "works on my machine" version drift between deployments.

---

### `requirements-test.txt` *(new file)*

Test-only dependencies (`pytest>=8.0.0`, `pytest-asyncio>=0.24.0`) kept separate from production `requirements.txt`.

---

### `pytest.ini` *(new file)*

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
```

---

### `tests/` *(new directory — 87 tests)*

| File | What it tests |
|---|---|
| `conftest.py` | Shared fixtures: in-memory SQLite with StaticPool, TestClient with mocked lifespan, JWT auth helper, `with_auth` (enables bcrypt enforcement), `pending_join`, shared limiter reset |
| `test_auth.py` | Dev-mode login, production credential check, logout + token revocation, protected routes, BUG-01 regression (request-join must be public even when auth is enforced) |
| `test_join.py` | Public access, input validation (node_name regex, WireGuard key format, URL scheme), idempotency, restart/stale-node teardown, approve/reject flows including auth enforcement |
| `test_services.py` | Unit tests for `get_next_vpn_ip`, `approve_join`, `reject_join` — pure DB logic, no HTTP layer |
| `test_connections.py` | Atomic rollback (if add_peer(B) fails, remove_peer(A) is called), termination (both agents get remove_peer, nodes keep VPN IPs), auth enforcement |
| `test_health.py` | `/health` returns 200, `/ready` returns 200 with DB up |

**Infrastructure issues fixed during test development:**
- SQLite `StaticPool` required so `create_all()` and the test session share the same in-memory connection
- `join.py` had a duplicate `Limiter()` instance with its own storage; rate limit counts bled across tests causing spurious 429s after the 10th request-join call — fixed by moving to shared `app.core.rate_limiter`
- `limiter.enabled = False` reset moved inside the `client` fixture (not a separate autouse) so it is guaranteed to run before fixture-level HTTP calls (`pending_join`, `auth_headers`)
- `test_restart_clears_stale_node`: patch target corrected to `app.services.agent_client.remove_peer` — `remove_peer` is a local import inside the function body, not a module-level attribute
- `test_approve_requires_auth` / `test_reject_requires_auth`: added `with_auth` fixture so auth enforcement is actually active

---

## Controller — nginx (`controller/nginx.conf`)

| What changed | Why |
|---|---|
| Removed `'unsafe-inline'` from `script-src` in Content-Security-Policy | Vite production builds do not use inline scripts; `unsafe-inline` allows XSS via injected script tags |
| Added `connect-src 'self'` to CSP | Explicitly restricts which URLs the frontend JavaScript can call |
| Added `font-src 'self' data:` to CSP | Allows self-hosted fonts and base64 data URIs without opening font-src to the internet |
| `/metrics` endpoint restricted to VPN subnet (`10.10.10.0/24`) | Prometheus metrics expose internal counters; blocking public access prevents information leakage |

---

## Agent (`agent/`)

### `app/main.py`

| What changed | Why |
|---|---|
| Removed `_already_active()` check from lifespan | If WireGuard was already up on startup, the agent skipped the join loop entirely and never re-registered after a restart. The controller handles re-join logic; the agent should always submit a fresh request |
| `_join_decided = True` set whenever `provision_interface()` succeeds, not only when a private key was pushed | For normal approvals (agent generates its own keys), `_join_decided` stayed False, so the join loop kept firing every 10s. The controller treated each re-submission as a node restart, deleted the approved node, and created a new PENDING — an infinite approve → delete → re-appear loop |
| `/health` endpoint now uses `wireguard.interface_is_up()` instead of `interface_exists()` | `interface_exists()` returned True for a DOWN WireGuard interface; `is_up` parses the `UP` flag from `ip link show` |
| WireGuard teardown in lifespan shutdown (`wg_down()`) | After agent process exits, the WireGuard interface was left in DOWN state. Next restart would find it and behave inconsistently. Cleaning up on shutdown gives a known starting state |
| `/health` response enriched with `wg_interface`, `wg_up`, `peer_count`, `vpn_ip` | Richer health data lets the controller heartbeat and admins distinguish "process up but VPN down" from "fully operational" |

---

### `app/wireguard.py`

| What changed | Why |
|---|---|
| Added `_interface_is_up(iface)` — parses flags between `<` and `>` from `ip link show` | `interface_exists()` only checked the return code; a DOWN interface returned True, making the agent appear healthy when WireGuard was not actually routing |
| Added `interface_is_up()` public wrapper | Called from `main.py` health endpoint and lifespan shutdown |
| Fixed `provision_interface()` to remove stale IPs before adding the new one | On re-approval, the interface kept the previous IP (e.g. `10.10.10.4`) while the database showed the new one (e.g. `10.10.10.2`). Now reads all `inet` addresses via `ip address show dev <iface>` and removes any that don't match the newly assigned IP before adding the correct one |

---

### `app/security.py`

| What changed | Why |
|---|---|
| Replaced `x_vishwaas_token != expected` with `hmac.compare_digest(x_vishwaas_token, expected)` | **Security bug (BUG-02)**: Python string `!=` short-circuits at the first differing byte, leaking timing information. An attacker making many requests can measure response time differences to recover the token one character at a time. `hmac.compare_digest` takes constant time regardless of where strings differ |

---

### `app/state.py`

| What changed | Why |
|---|---|
| `set_state()` writes `agent_state.json` to `keys_dir`; `get_state()` reads it on first call | State was held in-memory only. After an agent process restart the state was lost, and the agent defaulted to WAITING even if it was previously APPROVED, causing unnecessary re-join cycles |

---

### `app/logger.py`

`VISHWAAS_AGENT_LOG_JSON=true` enables `pythonjsonlogger` with `service` and `level` fields, matching the controller's structured log format. Falls back to plain text gracefully if the package is not installed.

---

### `requirements.lock` *(new file)*

19 packages pinned for the agent venv — same rationale as the controller lock file.

---

## Summary of Bugs Fixed

| ID | Severity | Component | Description |
|---|---|---|---|
| BUG-01 | Critical | Controller | `POST /request-join` blocked by global JWT middleware in production — entire VPN join flow broken |
| BUG-02 | High | Agent | Timing attack on controller→agent token comparison via `!=` instead of `hmac.compare_digest` |
| — | High | Controller | `passlib 1.7.4` incompatible with `bcrypt >= 4.0.0`; login endpoint crashed in production |
| — | Medium | Agent | `_already_active()` skipped join loop if WireGuard was already down — node never re-registered after restart |
| — | Medium | Agent | `_join_decided` not set after key-less approval — infinite approve→delete→re-appear loop |
| — | Medium | Controller | Freshly approved nodes with `last_seen=None` auto-deleted by heartbeat on first sweep |
| — | Medium | Agent | `interface_exists()` returned True for DOWN interfaces — health endpoint reported UP incorrectly |
| — | Medium | Agent | `provision_interface()` left old IP on re-approval — VPN IP mismatch between agent and controller |
| — | Low | Controller | `terminate_connection` called `wg_down` on last peer removal — tore down the WireGuard interface instead of just removing the peer |
| — | Low | Controller | OFFLINE nodes counted in `total_nodes` on dashboard |
| — | Low | Controller | OFFLINE nodes shown in `/topology` network map |
| — | Low | Controller | APPROVED nodes excluded from `active_nodes` count — dashboard showed 0 after approval |
| — | Low | Controller | Duplicate `Limiter()` instances in `main.py` and `join.py` — two independent rate-limit counters |
| — | Low | nginx | `unsafe-inline` in CSP `script-src` — unnecessary XSS vector |
