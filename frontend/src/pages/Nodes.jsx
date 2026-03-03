import React, { useState, useCallback } from 'react';
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
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState({ open: false, node: null });
  const [pushingId, setPushingId] = useState(null);
  const navigate = useNavigate();
  const { addToast } = useToast();
  const { refreshStats } = useStats();

  const fetch = useCallback(async () => {
    try {
      const [nodesList, statsData] = await Promise.all([api.getNodes(), api.getStats()]);
      setNodes(nodesList);
      setStats(statsData);
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

  return (
    <>
      <div className="content">
        <h1 style={{ margin: '0 0 1.5rem 0', fontSize: '1.5rem' }}>Nodes</h1>
        {loading && !nodes.length ? (
          <div className="spinner" style={{ margin: '2rem auto', display: 'block' }} />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>VPN IP</th>
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
                        className="btn btn--danger"
                        onClick={() => handleRemove(n)}
                        disabled={n.status === 'PENDING' || n.status === 'REJECTED'}
                        title={n.status === 'PENDING' || n.status === 'REJECTED' ? 'Remove only for ACTIVE, OFFLINE, or APPROVED nodes' : undefined}
                      >
                        Remove
                      </button>
                      <button
                        type="button"
                        className="btn btn--ghost"
                        title="Restart (no-op in this version)"
                        disabled
                      >
                        Restart
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
    </>
  );
}
