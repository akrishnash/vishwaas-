# VISHWAAS Master – Example API Requests/Responses

Base URL: `http://127.0.0.1:8000` (or use `/api` when called from frontend proxy).

**Node agents (plug-and-play):** When using the VISHWAAS node agent, set `VISHWAAS_AGENT_TOKEN` (same value as each agent’s `master_token` in `agent_config.json`) so the Master can call `POST /peer` and `DELETE /peer` on agents with header `X-VISHWAAS-TOKEN`.

---

## Join flow

### POST /request-join

Request:

```json
{
  "node_name": "edge-node-1",
  "public_key": "base64wireguardpublickey...",
  "agent_url": "http://192.168.1.10:9000"
}
```

Response (201):

```json
{
  "id": 1,
  "node_name": "edge-node-1",
  "public_key": "base64wireguardpublickey...",
  "agent_url": "http://192.168.1.10:9000",
  "status": "PENDING",
  "requested_at": "2025-02-18T12:00:00.000Z"
}
```

### GET /join-requests

Response (200): array of join requests (same shape as above).

### POST /join-requests/1/approve

Response (200):

```json
{
  "ok": true,
  "node_id": 1,
  "vpn_ip": "10.10.10.2"
}
```

### POST /join-requests/1/reject

Response (200): `{ "ok": true }`

---

## Connection flow

### POST /request-connection

Request:

```json
{
  "requester_id": 1,
  "target_id": 2
}
```

Response (200): connection request object with `id`, `requester_id`, `target_id`, `status`, `requested_at`.

### GET /connection-requests

Response (200): array of connection requests with optional `requester_name`, `target_name` when available.

### POST /connection-requests/1/approve

Response (200): `{ "ok": true, "connection_id": 1 }`

### POST /connection-requests/1/reject

Response (200): `{ "ok": true }`

---

## Nodes

### GET /nodes

Response (200): array of nodes with `id`, `name`, `public_key`, `agent_url`, `vpn_ip`, `status`, `last_seen`, `created_at`.

### GET /nodes/1

Response (200): single node object.

### DELETE /nodes/1

Response (200): `{ "ok": true }`

---

## Connections

### GET /connections

Response (200): array of connections with `node_a_id`, `node_b_id`, `node_a_name`, `node_b_name`, `status`, `created_at`.

### DELETE /connections/1

Response (200): `{ "ok": true }`

---

## Monitoring

### GET /stats

Response (200):

```json
{
  "total_nodes": 4,
  "active_nodes": 3,
  "pending_join_requests": 0,
  "pending_connection_requests": 1,
  "active_connections": 2,
  "unread_notifications": 3
}
```

### GET /notifications

Response (200): array of `{ "id", "type", "message", "is_read", "created_at" }`.

### POST /notifications/1/mark-read

Response (200): `{ "ok": true }`

### GET /logs

Response (200): array of `{ "id", "event_type", "description", "created_at" }`.

### GET /logs?event_type=JOIN_APPROVED

Response (200): same shape, filtered by event type.
