import React, { useState, useCallback, useEffect, useRef } from 'react';
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

const EVENT_BADGE_COLOR = {
  JOIN_APPROVED: '#22c55e',
  CONNECTION_APPROVED: '#22c55e',
  JOIN_REJECTED: '#ef4444',
  CONNECTION_REJECTED: '#ef4444',
  NODE_REMOVED: '#ef4444',
  JOIN_REQUESTED: '#f97316',
  CONNECTION_REQUESTED: '#f97316',
  CONNECTION_TERMINATED: '#a78bfa',
  NODE_OFFLINE: '#94a3b8',
};

function formatDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleString();
}

function EventBadge({ type }) {
  const color = EVENT_BADGE_COLOR[type] || '#64748b';
  return (
    <span style={{
      display: 'inline-block',
      padding: '0.15rem 0.5rem',
      borderRadius: '999px',
      fontSize: '0.72rem',
      fontWeight: 600,
      background: color + '22',
      color,
      border: `1px solid ${color}55`,
      whiteSpace: 'nowrap',
    }}>
      {type.replace(/_/g, ' ')}
    </span>
  );
}

function logLineColor(line) {
  const u = line.toUpperCase();
  if (u.includes(' ERROR') || u.includes('CRITICAL')) return '#f87171';
  if (u.includes('WARNING') || u.includes('WARN')) return '#fbbf24';
  if (u.includes(' INFO')) return '#86efac';
  return '#94a3b8';
}

// ---- Audit Log Tab ----

function AuditLogTab() {
  const { addToast } = useToast();
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [skip, setSkip] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const LIMIT = 100;

  const [filters, setFilters] = useState({
    event_type: '',
    search: '',
    date_from: '',
    date_to: '',
    performed_by: '',
  });
  const [liveFilters, setLiveFilters] = useState(filters);
  const searchTimer = useRef(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [exporting, setExporting] = useState(false);

  const fetchLogs = useCallback(async (currentSkip, currentFilters, append = false) => {
    try {
      const params = { ...currentFilters, skip: currentSkip, limit: LIMIT };
      const data = await api.getLogs(params);
      setList(prev => append ? [...prev, ...data] : data);
      setHasMore(data.length === LIMIT);
    } catch (e) {
      addToast(e.message || 'Failed to load logs', 'error');
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  // Initial + refresh
  useEffect(() => {
    setLoading(true);
    setSkip(0);
    fetchLogs(0, liveFilters, false);
  }, [liveFilters, fetchLogs]);

  // Auto-refresh every 10s when no filters are active
  useEffect(() => {
    if (!autoRefresh) return;
    const hasActiveFilters = Object.values(liveFilters).some(v => v !== '');
    if (hasActiveFilters) return;
    const id = setInterval(() => fetchLogs(0, liveFilters, false), 10000);
    return () => clearInterval(id);
  }, [autoRefresh, liveFilters, fetchLogs]);

  const handleFilterChange = (key, value) => {
    const next = { ...filters, [key]: value };
    setFilters(next);
    if (key === 'search') {
      clearTimeout(searchTimer.current);
      searchTimer.current = setTimeout(() => setLiveFilters(next), 300);
    } else {
      setLiveFilters(next);
    }
    setSkip(0);
  };

  const handleLoadMore = async () => {
    const newSkip = skip + LIMIT;
    setSkip(newSkip);
    await fetchLogs(newSkip, liveFilters, true);
  };

  const handleExport = async (format) => {
    setExporting(true);
    try {
      const params = { ...liveFilters, format };
      Object.keys(params).forEach(k => { if (!params[k]) delete params[k]; });
      await api.downloadLogs(params);
    } catch (e) {
      addToast(e.message || 'Export failed', 'error');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div>
      {/* Filters */}
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1rem', alignItems: 'flex-end' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label style={labelStyle}>Event type</label>
          <select value={filters.event_type} onChange={e => handleFilterChange('event_type', e.target.value)} style={selectStyle}>
            {EVENT_TYPES.map(t => <option key={t} value={t}>{t || 'All'}</option>)}
          </select>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label style={labelStyle}>Search</label>
          <input
            type="text"
            placeholder="Filter description…"
            value={filters.search}
            onChange={e => handleFilterChange('search', e.target.value)}
            style={{ ...inputStyle, width: '160px' }}
          />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label style={labelStyle}>Performed by</label>
          <input
            type="text"
            placeholder="Username…"
            value={filters.performed_by}
            onChange={e => handleFilterChange('performed_by', e.target.value)}
            style={{ ...inputStyle, width: '120px' }}
          />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label style={labelStyle}>From</label>
          <input type="datetime-local" value={filters.date_from} onChange={e => handleFilterChange('date_from', e.target.value)} style={inputStyle} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <label style={labelStyle}>To</label>
          <input type="datetime-local" value={filters.date_to} onChange={e => handleFilterChange('date_to', e.target.value)} style={inputStyle} />
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-end' }}>
          <button className="btn btn--ghost" disabled={exporting} onClick={() => handleExport('csv')}>
            {exporting ? '…' : 'CSV'}
          </button>
          <button className="btn btn--ghost" disabled={exporting} onClick={() => handleExport('json')}>
            {exporting ? '…' : 'JSON'}
          </button>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.8rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
            <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} />
            Auto-refresh
          </label>
        </div>
      </div>

      {/* Table */}
      {loading && !list.length ? (
        <div className="spinner" style={{ margin: '2rem auto', display: 'block' }} />
      ) : list.length === 0 ? (
        <div style={{ color: 'var(--text-muted)', padding: '2rem 0', textAlign: 'center' }}>No log entries match the current filters.</div>
      ) : (
        <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="table" style={{ width: '100%', fontSize: '0.85rem' }}>
            <thead>
              <tr>
                <th style={thStyle}>Timestamp</th>
                <th style={thStyle}>Event</th>
                <th style={thStyle}>Performed By</th>
                <th style={thStyle}>Description</th>
              </tr>
            </thead>
            <tbody>
              {list.map(log => (
                <tr key={log.id}>
                  <td style={{ ...tdStyle, whiteSpace: 'nowrap', color: 'var(--text-muted)', fontSize: '0.78rem' }}>{formatDate(log.created_at)}</td>
                  <td style={tdStyle}><EventBadge type={log.event_type} /></td>
                  <td style={{ ...tdStyle, color: 'var(--text-secondary)', fontSize: '0.8rem' }}>{log.performed_by || <span style={{ color: 'var(--text-muted)' }}>—</span>}</td>
                  <td style={tdStyle}>{log.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {hasMore && (
            <div style={{ padding: '0.75rem 1rem', borderTop: '1px solid var(--border)' }}>
              <button className="btn btn--ghost" onClick={handleLoadMore}>Load more</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---- System Logs Tab ----

function SystemLogsTab() {
  const { addToast } = useToast();
  const [lines, setLines] = useState([]);
  const [total, setTotal] = useState(0);
  const [file, setFile] = useState('');
  const [loading, setLoading] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const bottomRef = useRef(null);

  const fetchLogs = useCallback(async () => {
    try {
      const data = await api.getSystemLogs(500);
      setLines(data.lines || []);
      setTotal(data.total || 0);
      setFile(data.file || '');
    } catch (e) {
      addToast(e.message || 'Failed to load system logs', 'error');
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [lines, autoScroll]);

  return (
    <div>
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
        <button className="btn btn--ghost" onClick={fetchLogs}>Refresh</button>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.8rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
          <input type="checkbox" checked={autoScroll} onChange={e => setAutoScroll(e.target.checked)} />
          Auto-scroll
        </label>
        {file && <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{file} ({total} lines total)</span>}
      </div>
      {loading ? (
        <div className="spinner" style={{ margin: '2rem auto', display: 'block' }} />
      ) : (
        <div style={{
          background: '#0d1117',
          borderRadius: 'var(--radius)',
          padding: '1rem',
          height: '520px',
          overflowY: 'auto',
          fontFamily: 'monospace',
          fontSize: '0.78rem',
          lineHeight: '1.6',
          border: '1px solid var(--border)',
        }}>
          {lines.length === 0 ? (
            <span style={{ color: '#64748b' }}>No log file yet — logs will appear here after first activity.</span>
          ) : (
            lines.map((line, i) => (
              <div key={i} style={{ color: logLineColor(line), whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{line}</div>
            ))
          )}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}

// ---- Shared styles ----

const labelStyle = { fontSize: '0.75rem', color: 'var(--text-secondary)' };
const inputStyle = {
  background: 'var(--bg-secondary)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  padding: '0.35rem 0.6rem',
  borderRadius: 'var(--radius-sm)',
  fontFamily: 'var(--font)',
  fontSize: '0.85rem',
};
const selectStyle = { ...inputStyle, cursor: 'pointer' };
const thStyle = {
  textAlign: 'left',
  padding: '0.6rem 1rem',
  fontSize: '0.78rem',
  color: 'var(--text-muted)',
  fontWeight: 600,
  borderBottom: '1px solid var(--border)',
  background: 'var(--bg-secondary)',
};
const tdStyle = {
  padding: '0.6rem 1rem',
  borderBottom: '1px solid var(--border)',
  verticalAlign: 'top',
};

// ---- Main export ----

export function Logs() {
  const [tab, setTab] = useState('audit');

  return (
    <>
      <div className="content">
        <h1 style={{ margin: '0 0 1.25rem 0', fontSize: '1.5rem' }}>Logs</h1>

        {/* Tab bar */}
        <div style={{ display: 'flex', gap: '0', marginBottom: '1.5rem', borderBottom: '1px solid var(--border)' }}>
          {[['audit', 'Audit Log'], ['system', 'System Logs']].map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              style={{
                background: 'none',
                border: 'none',
                borderBottom: tab === key ? '2px solid var(--accent)' : '2px solid transparent',
                color: tab === key ? 'var(--text-primary)' : 'var(--text-muted)',
                padding: '0.5rem 1.25rem',
                cursor: 'pointer',
                fontFamily: 'var(--font)',
                fontSize: '0.9rem',
                fontWeight: tab === key ? 600 : 400,
                marginBottom: '-1px',
                transition: 'color 0.15s',
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === 'audit' ? <AuditLogTab /> : <SystemLogsTab />}
      </div>
    </>
  );
}
