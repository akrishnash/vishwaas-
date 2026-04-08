import React, { useState, useCallback } from 'react';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { ConfirmModal } from '../components/ConfirmModal';
import { useToast } from '../context/ToastContext';
import { useStats } from '../context/StatsContext';

function formatDate(d) {
  return d ? new Date(d).toLocaleString() : '—';
}

export function Connections() {
  const [list, setList] = useState([]);
  const [nodes, setNodes] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState({ open: false, conn: null });
  const [requestForm, setRequestForm] = useState({ fromId: '', toId: '' });
  const [requesting, setRequesting] = useState(false);
  const { addToast } = useToast();
  const { refreshStats } = useStats();

  const fetch = useCallback(async () => {
    try {
      const [conns, statsData, nodesList] = await Promise.all([
        api.getConnections(),
        api.getStats(),
        api.getNodes(),
      ]);
      setList(conns);
      setStats(statsData);
      setNodes(nodesList);
    } catch (e) {
      addToast(e.message || 'Failed to load connections', 'error');
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  usePolling(fetch, 5000);

  const submitRequestConnection = async () => {
    const fromId = Number(requestForm.fromId);
    const toId = Number(requestForm.toId);
    if (!fromId || !toId || fromId === toId) {
      addToast('Select two different nodes', 'error');
      return;
    }
    setRequesting(true);
    try {
      await api.requestConnection({ requester_id: fromId, target_id: toId });
      addToast('Connection requested');
      setRequestForm({ fromId: '', toId: '' });
      fetch();
      refreshStats?.();
    } catch (e) {
      addToast(e.message || 'Failed to request connection', 'error');
    } finally {
      setRequesting(false);
    }
  };

  const handleTerminate = (conn) => setModal({ open: true, conn });
  const confirmTerminate = async () => {
    if (!modal.conn) return;
    try {
      await api.deleteConnection(modal.conn.id);
      addToast('Connection terminated');
      setModal({ open: false, conn: null });
      fetch();
      refreshStats?.();
    } catch (e) {
      addToast(e.message || 'Failed to terminate', 'error');
    }
  };

  return (
    <>
      <div className="content">
        <h1 style={{ margin: '0 0 1.5rem 0', fontSize: '1.5rem' }}>Connections</h1>

        {nodes.length >= 2 && (
          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <h3 style={{ margin: '0 0 0.75rem 0', fontSize: '1rem' }}>Request new connection</h3>
            <p style={{ margin: '0 0 1rem 0', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
              Connect two nodes so they can reach each other over the VPN.
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'center' }}>
              <select
                value={requestForm.fromId}
                onChange={(e) => setRequestForm((f) => ({ ...f, fromId: e.target.value }))}
                style={{
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                  padding: '0.5rem 0.75rem',
                  borderRadius: 'var(--radius-sm)',
                  fontFamily: 'var(--font)',
                  minWidth: '160px',
                }}
              >
                <option value="">From node</option>
                {nodes.map((n) => (
                  <option key={n.id} value={n.id}>{n.name} ({n.vpn_ip})</option>
                ))}
              </select>
              <span style={{ color: 'var(--text-muted)' }}>→</span>
              <select
                value={requestForm.toId}
                onChange={(e) => setRequestForm((f) => ({ ...f, toId: e.target.value }))}
                style={{
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                  padding: '0.5rem 0.75rem',
                  borderRadius: 'var(--radius-sm)',
                  fontFamily: 'var(--font)',
                  minWidth: '160px',
                }}
              >
                <option value="">To node</option>
                {nodes.map((n) => (
                  <option key={n.id} value={n.id}>{n.name} ({n.vpn_ip})</option>
                ))}
              </select>
              <button
                type="button"
                className="btn btn--primary"
                disabled={requesting || !requestForm.fromId || !requestForm.toId}
                onClick={submitRequestConnection}
              >
                {requesting ? 'Requesting…' : 'Request connection'}
              </button>
            </div>
          </div>
        )}

        {loading && !list.length ? (
          <div className="spinner" style={{ margin: '2rem auto', display: 'block' }} />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Node A</th>
                  <th>Node B</th>
                  <th>Status</th>
                  <th>Created At</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {list.map((c) => (
                  <tr key={c.id}>
                    <td>{c.node_a_name ?? c.node_a_id}</td>
                    <td>{c.node_b_name ?? c.node_b_id}</td>
                    <td><StatusBadge status={c.status} /></td>
                    <td>{formatDate(c.created_at)}</td>
                    <td>
                      {c.status === 'ACTIVE' ? (
                        <button
                          type="button"
                          className="btn btn--danger"
                          onClick={() => handleTerminate(c)}
                        >
                          Terminate
                        </button>
                      ) : (
                        '—'
                      )}
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
        title="Terminate connection"
        message={`Terminate connection between ${modal.conn?.node_a_name ?? 'A'} and ${modal.conn?.node_b_name ?? 'B'}?`}
        confirmLabel="Terminate"
        onConfirm={confirmTerminate}
        onCancel={() => setModal({ open: false, conn: null })}
      />
    </>
  );
}
