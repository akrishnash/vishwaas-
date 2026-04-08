import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { ConfirmModal } from '../components/ConfirmModal';
import { useToast } from '../context/ToastContext';
import { useStats } from '../context/StatsContext';

function formatDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleString();
}

export function Nodes() {
  const [nodes, setNodes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState({ open: false, node: null });
  const [clearModal, setClearModal] = useState(false);
  const [connectModal, setConnectModal] = useState({ open: false, requester: null });
  const [connecting, setConnecting] = useState(false);
  const [pushingId, setPushingId] = useState(null);
  const [togglingGatewayId, setTogglingGatewayId] = useState(null);
  const navigate = useNavigate();
  const { addToast } = useToast();
  const { refreshStats } = useStats();

  const fetch = useCallback(async () => {
    try {
      const nodesList = await api.getNodes();
      setNodes(nodesList);
    } catch (e) {
      addToast(e.message || 'Failed to load nodes', 'error');
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  usePolling(fetch, 5000);

  const handlePushVpn = async (node) => {
    setPushingId(node.id);
    try {
      await api.pushVpnAddress(node.id);
      addToast(`VPN IP ${node.vpn_ip} pushed to ${node.name}`);
      fetch();
    } catch (e) {
      const msg = e.body?.detail ?? e.body ?? e.message ?? 'Failed to push VPN IP';
      addToast(typeof msg === 'string' ? msg : JSON.stringify(msg), 'error');
    } finally {
      setPushingId(null);
    }
  };

  const handleToggleGateway = async (node) => {
    setTogglingGatewayId(node.id);
    try {
      await api.setGateway(node.id, !node.is_gateway);
      addToast(`${node.name} is now ${!node.is_gateway ? 'a gateway hub' : 'a regular spoke'}`);
      fetch();
    } catch (e) {
      addToast(e.message || 'Failed to update gateway status', 'error');
    } finally {
      setTogglingGatewayId(null);
    }
  };

  const handleConnect = (node) => setConnectModal({ open: true, requester: node });
  const confirmConnect = async (targetId) => {
    if (!connectModal.requester) return;
    const requesterId = connectModal.requester.id;
    setConnectModal({ open: false, requester: null });
    setConnecting(true);
    try {
      await api.requestConnection({ requester_id: requesterId, target_id: targetId });
      addToast('Connection request created — approve it in Conn. Requests');
      refreshStats?.();
    } catch (e) {
      addToast(e.body?.detail || e.message || 'Failed to request connection', 'error');
    } finally {
      setConnecting(false);
    }
  };

  const handleRemove = (node) => setModal({ open: true, node });
  const confirmRemove = async () => {
    if (!modal.node) return;
    try {
      await api.deleteNode(modal.node.id);
      addToast('Node removed');
      setModal({ open: false, node: null });
      fetch();
      refreshStats?.();
    } catch (e) {
      addToast(e.message || 'Failed to remove node', 'error');
    }
  };

  const confirmClearAll = async () => {
    try {
      const res = await api.clearAllNodes();
      addToast(`All nodes cleared (${res.removed} removed)`);
      setClearModal(false);
      fetch();
      refreshStats?.();
    } catch (e) {
      addToast(e.message || 'Failed to clear nodes', 'error');
    }
  };

  return (
    <>
      <div className="content">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <h1 style={{ margin: 0, fontSize: '1.5rem' }}>Nodes</h1>
          {nodes.length > 0 && (
            <button type="button" className="btn btn--danger" onClick={() => setClearModal(true)}>
              Clear All
            </button>
          )}
        </div>
        {loading && !nodes.length ? (
          <div className="spinner" style={{ margin: '2rem auto', display: 'block' }} />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>VPN IP</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Last Seen</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map((n) => (
                  <tr key={n.id}>
                    <td>
                      <span
                        className={`indicator indicator--${
                          n.status === 'ACTIVE' ? 'online' : n.status === 'PENDING' ? 'pending' : 'offline'
                        }`}
                        style={{ marginRight: '0.5rem', display: 'inline-block', verticalAlign: 'middle' }}
                      />
                      {n.name}
                    </td>
                    <td>{n.vpn_ip}</td>
                    <td>
                      {n.is_gateway ? (
                        <span style={{
                          background: 'linear-gradient(135deg, #f59e0b, #d97706)',
                          color: '#fff',
                          padding: '2px 8px',
                          borderRadius: '10px',
                          fontSize: '0.7rem',
                          fontWeight: 700,
                          letterSpacing: '0.05em',
                        }}>HUB</span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Spoke</span>
                      )}
                    </td>
                    <td><StatusBadge status={n.status} /></td>
                    <td>{formatDate(n.last_seen)}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn--ghost"
                        style={{ marginRight: '0.5rem' }}
                        onClick={() => navigate(`/nodes/${n.id}`)}
                      >
                        View
                      </button>
                      <button
                        type="button"
                        className="btn btn--ghost"
                        disabled={pushingId !== null}
                        onClick={() => handlePushVpn(n)}
                        title="Retry sending VPN config to the agent (e.g. if it was offline when you approved)"
                      >
                        {pushingId === n.id ? 'Retrying…' : 'Retry config'}
                      </button>
                      <button
                        type="button"
                        className="btn btn--ghost"
                        disabled={togglingGatewayId !== null || n.status === 'PENDING'}
                        onClick={() => handleToggleGateway(n)}
                        title={n.is_gateway ? 'Unset as gateway hub (revert to spoke)' : 'Set as gateway hub — spokes will route all VPN traffic through this node'}
                        style={n.is_gateway ? { color: '#f59e0b', borderColor: '#f59e0b' } : {}}
                      >
                        {togglingGatewayId === n.id ? '…' : n.is_gateway ? 'Unset Hub' : 'Set Hub'}
                      </button>
                      <button
                        type="button"
                        className="btn btn--approve"
                        disabled={nodes.length <= 1 || connecting}
                        onClick={() => handleConnect(n)}
                        title="Request a WireGuard peer connection to another node"
                      >
                        Connect
                      </button>
                      <button
                        type="button"
                        className="btn btn--danger"
                        onClick={() => handleRemove(n)}
                        disabled={n.status === 'PENDING' || n.status === 'REJECTED'}
                        title={n.status === 'PENDING' || n.status === 'REJECTED' ? 'Remove only for ACTIVE, OFFLINE, or APPROVED nodes' : undefined}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <ConfirmModal
        open={modal.open}
        title="Remove node"
        message={`Remove node "${modal.node?.name}" from the control plane? This cannot be undone.`}
        confirmLabel="Remove"
        onConfirm={confirmRemove}
        onCancel={() => setModal({ open: false, node: null })}
      />
      <ConfirmModal
        open={clearModal}
        title="Clear all nodes"
        message="Remove all nodes, connections, and connection requests from the control plane? This cannot be undone."
        confirmLabel="Clear All"
        onConfirm={confirmClearAll}
        onCancel={() => setClearModal(false)}
      />
      {connectModal.open && (
        <div className="modal-overlay" onClick={() => setConnectModal({ open: false, requester: null })}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 0.75rem 0' }}>Connect {connectModal.requester?.name} to…</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1rem' }}>
              {nodes.filter(n => n.id !== connectModal.requester?.id).map(n => (
                <button
                  key={n.id}
                  type="button"
                  className="btn btn--ghost"
                  style={{ textAlign: 'left' }}
                  onClick={() => confirmConnect(n.id)}
                >
                  {n.name} <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>({n.vpn_ip})</span>
                </button>
              ))}
            </div>
            <button type="button" className="btn btn--ghost" onClick={() => setConnectModal({ open: false, requester: null })}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </>
  );
}
