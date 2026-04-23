import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { useToast } from '../context/ToastContext';

function logLineColor(line) {
  const u = line.toUpperCase();
  if (u.includes(' ERROR') || u.includes('CRITICAL')) return '#f87171';
  if (u.includes('WARNING') || u.includes('WARN')) return '#fbbf24';
  if (u.includes(' INFO')) return '#86efac';
  return '#94a3b8';
}

function AgentLogs({ nodeId }) {
  const { addToast } = useToast();
  const [lines, setLines] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);

  const fetchLogs = useCallback(async () => {
    setError(null);
    try {
      const data = await api.getNodeLogs(nodeId, 100);
      setLines(data.lines || []);
      setTotal(data.total || 0);
    } catch (e) {
      if (e.status === 502) {
        setError('Agent unreachable — no logs available.');
      } else {
        setError(e.message || 'Failed to fetch agent logs');
      }
    } finally {
      setLoading(false);
    }
  }, [nodeId]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  useEffect(() => {
    if (bottomRef.current) bottomRef.current.scrollIntoView();
  }, [lines]);

  return (
    <div style={{ marginTop: '2rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.75rem' }}>
        <h2 style={{ margin: 0, fontSize: '1rem' }}>Agent Logs</h2>
        <button className="btn btn--ghost" style={{ fontSize: '0.8rem', padding: '0.25rem 0.6rem' }} onClick={fetchLogs}>Refresh</button>
        {total > 0 && <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>last 100 of {total} lines</span>}
      </div>
      <div style={{
        background: '#0d1117',
        borderRadius: 'var(--radius)',
        padding: '0.75rem 1rem',
        height: '300px',
        overflowY: 'auto',
        fontFamily: 'monospace',
        fontSize: '0.75rem',
        lineHeight: '1.6',
        border: '1px solid var(--border)',
      }}>
        {loading ? (
          <span style={{ color: '#64748b' }}>Loading…</span>
        ) : error ? (
          <span style={{ color: '#94a3b8' }}>{error}</span>
        ) : lines.length === 0 ? (
          <span style={{ color: '#64748b' }}>No log file yet on this agent.</span>
        ) : (
          lines.map((line, i) => (
            <div key={i} style={{ color: logLineColor(line), whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{line}</div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function formatDate(d) {
  return d ? new Date(d).toLocaleString() : '—';
}

export function NodeDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [node, setNode] = useState(null);
  const [loading, setLoading] = useState(true);
  const [pushing, setPushing] = useState(false);
  const { addToast } = useToast();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.getNode(Number(id));
        if (!cancelled) setNode(data);
      } catch (e) {
        if (!cancelled) addToast(e.message || 'Node not found', 'error');
        navigate('/nodes');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [id, navigate, addToast]);

  const handlePushVpn = async () => {
    if (!node) return;
    setPushing(true);
    try {
      await api.pushVpnAddress(node.id);
      addToast(`VPN IP ${node.vpn_ip} pushed to ${node.name}`);
      setNode((n) => n && { ...n });
    } catch (e) {
      addToast(e.body?.detail || e.message || 'Failed to push VPN IP', 'error');
    } finally {
      setPushing(false);
    }
  };

  if (loading || !node) {
    return (
      <div className="content">
        <div className="spinner" style={{ margin: '2rem auto', display: 'block' }} />
      </div>
    );
  }

  return (
    <div className="content">
      <button
        type="button"
        className="btn btn--ghost"
        style={{ marginBottom: '1rem' }}
        onClick={() => navigate('/nodes')}
      >
        ← Back to Nodes
      </button>
      <h1 style={{ margin: '0 0 1.5rem 0', fontSize: '1.5rem' }}>{node.name}</h1>
      <div style={{ marginBottom: '1rem' }}>
        <button
          type="button"
          className="btn btn--ghost"
          disabled={pushing}
          onClick={handlePushVpn}
          title="Retry sending VPN config to the agent"
        >
          {pushing ? 'Retrying…' : 'Retry config'}
        </button>
      </div>
      <div className="card">
        <table className="table">
          <tbody>
            <tr><td><strong>VPN IP</strong></td><td>{node.vpn_ip}</td></tr>
            <tr><td><strong>Status</strong></td><td><StatusBadge status={node.status} /></td></tr>
            <tr><td><strong>Agent URL</strong></td><td>{node.agent_url}</td></tr>
            <tr><td><strong>Last Seen</strong></td><td>{formatDate(node.last_seen)}</td></tr>
            <tr><td><strong>Created</strong></td><td>{formatDate(node.created_at)}</td></tr>
            <tr><td><strong>Public Key</strong></td><td style={{ wordBreak: 'break-all', fontSize: '0.8rem' }}>{node.public_key}</td></tr>
          </tbody>
        </table>
      </div>
      <AgentLogs nodeId={node.id} />
    </div>
  );
}
