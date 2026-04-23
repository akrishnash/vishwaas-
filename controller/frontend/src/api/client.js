/**
 * API client for VISHWAAS Master backend.
 * Base URL: /api when proxied by Vite to backend.
 */
const BASE = '/api';

async function request(path, options = {}) {
  const url = path.startsWith('http') ? path : `${BASE}${path}`;
  const token = localStorage.getItem('vw_token');
  const authHeader = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...authHeader, ...options.headers },
    ...options,
  });
  if (!res.ok) {
    if (res.status === 401) {
      window.dispatchEvent(new CustomEvent('vw:unauthorized'));
    }
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
  // Auth
  login: (body) => request('/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  me: () => request('/auth/me'),

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
  updateNode: (id, body) => request(`/nodes/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  setGateway: (id, isGateway) => request(`/nodes/${id}/set-gateway`, { method: 'POST', body: JSON.stringify({ is_gateway: isGateway }) }),
  deleteNode: (id) => request(`/nodes/${id}`, { method: 'DELETE' }),
  clearAllNodes: () => request('/nodes', { method: 'DELETE' }),

  // Connections
  getConnections: () => request('/connections'),
  deleteConnection: (id) => request(`/connections/${id}`, { method: 'DELETE' }),

  // Monitoring
  getStats: () => request('/stats'),
  getStatsDetailed: () => request('/stats/detailed'),
  getTopology: () => request('/topology'),
  getNotifications: () => request('/notifications'),
  markNotificationRead: (id) => request(`/notifications/${id}/mark-read`, { method: 'POST' }),
  getLogs: (params = {}) => {
    const q = new URLSearchParams();
    if (params.event_type) q.set('event_type', params.event_type);
    if (params.search) q.set('search', params.search);
    if (params.date_from) q.set('date_from', params.date_from);
    if (params.date_to) q.set('date_to', params.date_to);
    if (params.performed_by) q.set('performed_by', params.performed_by);
    if (params.skip != null) q.set('skip', params.skip);
    if (params.limit != null) q.set('limit', params.limit);
    const qs = q.toString();
    return request(qs ? `/logs?${qs}` : '/logs');
  },
  downloadLogs: async (params = {}) => {
    const q = new URLSearchParams(params);
    const url = `${BASE}/logs/export?${q.toString()}`;
    const token = localStorage.getItem('vw_token');
    const res = await fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(res.statusText);
    const blob = await res.blob();
    const disposition = res.headers.get('content-disposition') || '';
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : `vishwaas-logs.${params.format || 'csv'}`;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  },
  getSystemLogs: (n = 200) => request(`/system-logs?n=${n}`),
  getNodeLogs: (id, n = 200) => request(`/nodes/${id}/logs?n=${n}`),
};
