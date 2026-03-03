/**
 * API client for VISHWAAS Master backend.
 * Base URL: /api when proxied by Vite to backend.
 */
const BASE = '/api';

async function request(path, options = {}) {
  const url = path.startsWith('http') ? path : `${BASE}${path}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = new Error(res.statusText);
    err.status = res.status;
    try {
      err.body = await res.json();
    } catch {
      err.body = await res.text();
    }
    throw err;
  }
  const contentType = res.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return res.json();
  }
  return res.text();
}

export const api = {
  // Join
  requestJoin: (body) => request('/request-join', { method: 'POST', body: JSON.stringify(body) }),
  getJoinRequests: () => request('/join-requests'),
  approveJoin: (id) => request(`/join-requests/${id}/approve`, { method: 'POST' }),
  rejectJoin: (id) => request(`/join-requests/${id}/reject`, { method: 'POST' }),

  // Connection
  requestConnection: (body) => request('/request-connection', { method: 'POST', body: JSON.stringify(body) }),
  getConnectionRequests: () => request('/connection-requests'),
  approveConnection: (id) => request(`/connection-requests/${id}/approve`, { method: 'POST' }),
  rejectConnection: (id) => request(`/connection-requests/${id}/reject`, { method: 'POST' }),

  // Nodes
  getNodes: () => request('/nodes'),
  getNode: (id) => request(`/nodes/${id}`),
  pushVpnAddress: (id) => request(`/nodes/${id}/push-vpn-address`, { method: 'POST' }),
  deleteNode: (id) => request(`/nodes/${id}`, { method: 'DELETE' }),

  // Connections
  getConnections: () => request('/connections'),
  deleteConnection: (id) => request(`/connections/${id}`, { method: 'DELETE' }),

  // Monitoring
  getStats: () => request('/stats'),
  getStatsDetailed: () => request('/stats/detailed'),
  getTopology: () => request('/topology'),
  getNotifications: () => request('/notifications'),
  markNotificationRead: (id) => request(`/notifications/${id}/mark-read`, { method: 'POST' }),
  getLogs: (eventType) => request(eventType ? `/logs?event_type=${encodeURIComponent(eventType)}` : '/logs'),
};
