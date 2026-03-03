import React, { useState, useCallback } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie,
  Legend,
} from 'recharts';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';

function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KiB', 'MiB', 'GiB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / k ** i).toFixed(1)} ${sizes[i]}`;
}

export function Overview() {
  const [stats, setStats] = useState(null);
  const [detailed, setDetailed] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [statsData, detailedData] = await Promise.all([
        api.getStats(),
        api.getStatsDetailed().catch(() => null),
      ]);
      setStats(statsData);
      setDetailed(detailedData);
    } catch (e) {
      setError(e.message || 'Failed to load stats');
    } finally {
      setLoading(false);
    }
  }, []);

  usePolling(fetchData, 5000);

  if (loading && !stats) {
    return (
      <div className="content">
        <div className="spinner" style={{ margin: '2rem auto', display: 'block' }} />
      </div>
    );
  }

  const total = stats?.total_nodes ?? 0;
  const active = stats?.active_nodes ?? 0;
  const healthPct = total ? Math.round((active / total) * 100) : 0;

  const cards = [
    { label: 'Total Nodes', value: stats?.total_nodes ?? 0 },
    { label: 'Active Nodes', value: stats?.active_nodes ?? 0 },
    { label: 'Pending Join Requests', value: stats?.pending_join_requests ?? 0 },
    { label: 'Pending Connection Requests', value: stats?.pending_connection_requests ?? 0 },
    { label: 'Active Connections', value: stats?.active_connections ?? 0 },
  ];

  const nodes = detailed?.nodes ?? [];
  const totalRx = detailed?.total_rx ?? 0;
  const totalTx = detailed?.total_tx ?? 0;

  const barData = nodes.map((n) => ({
    name: n.node_name,
    rx: n.total_rx,
    tx: n.total_tx,
    rxLabel: formatBytes(n.total_rx),
    txLabel: formatBytes(n.total_tx),
  }));

  const pieData = [
    { name: 'Received', value: totalRx, fill: 'var(--info)' },
    { name: 'Sent', value: totalTx, fill: 'var(--accent)' },
  ].filter((d) => d.value > 0);

  const chartColors = ['var(--info)', 'var(--accent)'];
  const tooltipFormatter = (value) => formatBytes(value);

  return (
    <div className="content">
      <h1 style={{ margin: '0 0 1.5rem 0', fontSize: '1.5rem' }}>Overview</h1>
      {error && (
        <div className="card" style={{ marginBottom: '1rem', borderColor: 'var(--danger)' }}>
          {error}
        </div>
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
          gap: '1rem',
          marginBottom: '1.5rem',
        }}
      >
        {cards.map((c) => (
          <div key={c.label} className="card">
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
              {c.label}
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{c.value}</div>
          </div>
        ))}
      </div>

      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
          <span>System health (node availability)</span>
          <span>{healthPct}%</span>
        </div>
        <div
          style={{
            height: '8px',
            background: 'var(--bg-secondary)',
            borderRadius: '999px',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${healthPct}%`,
              background:
                healthPct >= 70 ? 'var(--accent)' : healthPct >= 40 ? 'var(--warning)' : 'var(--danger)',
              borderRadius: '999px',
              transition: 'width 0.3s',
            }}
          />
        </div>
      </div>

      {nodes.length > 0 && (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
              gap: '1.5rem',
              marginBottom: '1.5rem',
            }}
          >
            <div className="card">
              <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem', fontWeight: 600 }}>
                Bandwidth by node
              </h3>
              <div style={{ height: 260 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={barData} margin={{ top: 12, right: 12, left: 0, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.5} />
                    <XAxis
                      dataKey="name"
                      stroke="var(--text-muted)"
                      fontSize={12}
                      tick={{ fill: 'var(--text-secondary)' }}
                    />
                    <YAxis
                      stroke="var(--text-muted)"
                      fontSize={11}
                      tick={{ fill: 'var(--text-secondary)' }}
                      tickFormatter={(v) => formatBytes(v)}
                    />
                    <Tooltip
                      contentStyle={{
                        background: 'var(--bg-card)',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-sm)',
                        color: 'var(--text-primary)',
                      }}
                      labelStyle={{ color: 'var(--text-secondary)' }}
                      formatter={tooltipFormatter}
                      labelFormatter={(label) => `Node: ${label}`}
                    />
                    <Bar dataKey="rx" name="Received" fill="var(--info)" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="tx" name="Sent" fill="var(--accent)" radius={[0, 0, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {pieData.length > 0 && (
              <div className="card">
                <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem', fontWeight: 600 }}>
                  Total traffic
                </h3>
                <div style={{ height: 260, display: 'flex', alignItems: 'center' }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={90}
                        paddingAngle={2}
                        dataKey="value"
                        nameKey="name"
                        label={({ name, value }) =>
                          `${name}: ${formatBytes(value)}`
                        }
                        labelLine={{ stroke: 'var(--border)' }}
                      >
                        {pieData.map((_, i) => (
                          <Cell key={i} fill={chartColors[i % chartColors.length]} />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{
                          background: 'var(--bg-card)',
                          border: '1px solid var(--border)',
                          borderRadius: 'var(--radius-sm)',
                          color: 'var(--text-primary)',
                        }}
                        formatter={tooltipFormatter}
                      />
                      <Legend
                        formatter={(value) => (
                          <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                            {value}
                          </span>
                        )}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
          </div>

          <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem', fontWeight: 600 }}>
            Node connectivity
          </h3>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
              gap: '1rem',
            }}
          >
            {nodes.map((n) => (
              <div
                key={n.node_id}
                className="card"
                style={{
                  borderLeft: `4px solid ${n.reachable ? 'var(--accent)' : 'var(--danger)'}`,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <div
                    className={`indicator ${n.reachable ? 'indicator--online' : 'indicator--offline'}`}
                    title={n.reachable ? 'Reachable' : 'Unreachable'}
                  />
                  <span style={{ fontWeight: 600 }}>{n.node_name}</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                    {n.vpn_ip}
                  </span>
                </div>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: '0.5rem',
                    fontSize: '0.85rem',
                    color: 'var(--text-secondary)',
                  }}
                >
                  <span>↓ {formatBytes(n.total_rx)}</span>
                  <span>↑ {formatBytes(n.total_tx)}</span>
                </div>
                {n.peers.length > 0 && (
                  <div
                    style={{
                      marginTop: '0.5rem',
                      fontSize: '0.75rem',
                      color: 'var(--text-muted)',
                    }}
                  >
                    {n.peers.length} peer{n.peers.length !== 1 ? 's' : ''}
                    {(() => {
                      const hs = n.peers
                        .filter((p) => p.latest_handshake_ago != null)
                        .map((p) => p.latest_handshake_ago);
                      if (hs.length > 0) {
                        const minSec = Math.min(...hs);
                        return (
                          <span style={{ marginLeft: '0.5rem' }}>
                            • latest handshake {minSec}s ago
                          </span>
                        );
                      }
                      return null;
                    })()}
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
