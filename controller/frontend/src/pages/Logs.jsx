import React, { useState, useCallback } from 'react';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';
import { useToast } from '../context/ToastContext';

const EVENT_TYPES = [
  '',
  'JOIN_REQUESTED',
  'JOIN_APPROVED',
  'JOIN_REJECTED',
  'CONNECTION_REQUESTED',
  'CONNECTION_APPROVED',
  'CONNECTION_REJECTED',
  'CONNECTION_TERMINATED',
  'NODE_REMOVED',
  'NODE_OFFLINE',
];

function formatDate(d) {
  return d ? new Date(d).toLocaleString() : '—';
}

export function Logs() {
  const [list, setList] = useState([]);
  const [stats, setStats] = useState(null);
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const { addToast } = useToast();

  const fetch = useCallback(async () => {
    try {
      const [logsData, statsData] = await Promise.all([
        api.getLogs(filter || undefined),
        api.getStats(),
      ]);
      setList(logsData);
      setStats(statsData);
    } catch (e) {
      addToast(e.message || 'Failed to load logs', 'error');
    } finally {
      setLoading(false);
    }
  }, [filter, addToast]);

  usePolling(fetch, 5000);

  return (
    <>
      <div className="content">
        <h1 style={{ margin: '0 0 1.5rem 0', fontSize: '1.5rem' }}>Logs</h1>
        <div style={{ marginBottom: '1rem', display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <label style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
            Filter by type:
          </label>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              padding: '0.4rem 0.75rem',
              borderRadius: 'var(--radius-sm)',
              fontFamily: 'var(--font)',
            }}
          >
            {EVENT_TYPES.map((t) => (
              <option key={t} value={t}>
                {t || 'All'}
              </option>
            ))}
          </select>
        </div>
        {loading && !list.length ? (
          <div className="spinner" style={{ margin: '2rem auto', display: 'block' }} />
        ) : (
          <div className="card" style={{ padding: 0 }}>
            <ul
              style={{
                listStyle: 'none',
                margin: 0,
                padding: 0,
                borderLeft: '3px solid var(--border)',
                marginLeft: '1rem',
              }}
            >
              {list.map((log) => (
                <li
                  key={log.id}
                  style={{
                    padding: '0.75rem 1rem',
                    borderBottom: '1px solid var(--border)',
                    position: 'relative',
                    paddingLeft: '1.5rem',
                  }}
                >
                  <span
                    style={{
                      position: 'absolute',
                      left: 0,
                      top: '0.75rem',
                      width: '10px',
                      height: '10px',
                      borderRadius: '50%',
                      background: 'var(--accent)',
                      marginLeft: '-6px',
                    }}
                  />
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
                    {log.event_type} · {formatDate(log.created_at)}
                  </div>
                  <div style={{ fontSize: '0.9rem' }}>{log.description}</div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </>
  );
}
