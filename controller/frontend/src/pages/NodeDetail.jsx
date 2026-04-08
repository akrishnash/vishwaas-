import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { useToast } from '../context/ToastContext';

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
    </div>
  );
}
