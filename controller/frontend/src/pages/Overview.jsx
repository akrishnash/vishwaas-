import { useState, useCallback, useMemo, useRef } from 'react';
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend,
} from 'recharts';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';
import {
  Server, Activity, LogIn, Link, Wifi,
  ArrowDownLeft, ArrowUpRight, Clock, Users,
} from 'lucide-react';

function fmt(b, p = 1) {
  if (!b || b === 0) return '0 B';
  const k = 1024;
  const u = ['B', 'KiB', 'MiB', 'GiB'];
  const i = Math.floor(Math.log(b) / Math.log(k));
  return `${(b / k ** i).toFixed(p)} ${u[i]}`;
}

function fmtHandshake(s) {
  if (s == null) return 'never';
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

function MetricCard({ icon: Icon, label, value, color, sub }) {
  return (
    <div className="metric-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.4rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{label}</div>
          <div style={{ fontSize: '2rem', fontWeight: 800, lineHeight: 1, color: 'var(--text-primary)' }}>{value}</div>
          {sub && <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.35rem' }}>{sub}</div>}
        </div>
        <div className="metric-icon" style={{ background: `${color}18`, border: `1px solid ${color}40` }}>
          <Icon size={18} color={color} />
        </div>
      </div>
    </div>
  );
}

function MiniNetworkMap({ topoNodes, topoEdges }) {
  const W = 480, H = 220;
  const positioned = useMemo(() => {
    if (!topoNodes.length) return [];
    const cx = W / 2, cy = H / 2;
    const r = topoNodes.length === 1 ? 0 : Math.min(cx, cy) * 0.6;
    return topoNodes.map((n, i) => {
      const angle = (i / topoNodes.length) * 2 * Math.PI - Math.PI / 2;
      return { ...n, x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
    });
  }, [topoNodes]);

  const nodeMap = useMemo(() => Object.fromEntries(positioned.map(n => [n.id, n])), [positioned]);
  if (!positioned.length) return null;

  const STATUS_COLOR = { ACTIVE: '#3fb950', PENDING: '#d29922', OFFLINE: '#6e7681', APPROVED: '#58a6ff' };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: '100%' }}>
      <defs>
        <style>{`@keyframes dash-flow { to { stroke-dashoffset: -24; } }`}</style>
      </defs>
      {/* Grid dots */}
      {Array.from({ length: 8 }, (_, y) => Array.from({ length: 12 }, (_, x) => (
        <circle key={`${x}-${y}`} cx={x * 44 + 10} cy={y * 30 + 10} r={1} fill="rgba(255,255,255,0.04)" />
      )))}
      {/* Edges */}
      {topoEdges.map(e => {
        const src = nodeMap[e.source_id], tgt = nodeMap[e.target_id];
        if (!src || !tgt) return null;
        const active = e.status === 'ACTIVE';
        return (
          <g key={e.id}>
            <line x1={src.x} y1={src.y} x2={tgt.x} y2={tgt.y}
              stroke={active ? '#3fb95030' : '#37394730'} strokeWidth={active ? 20 : 10} />
            <line x1={src.x} y1={src.y} x2={tgt.x} y2={tgt.y}
              stroke={active ? '#3fb950' : '#373e47'} strokeWidth={active ? 2 : 1}
              strokeDasharray={active ? '8 4' : '4 6'}
              style={active ? { animation: 'dash-flow 1.2s linear infinite' } : {}} />
            {active && (() => {
              const mx = (src.x + tgt.x) / 2, my = (src.y + tgt.y) / 2;
              return (
                <text x={mx} y={my - 6} textAnchor="middle" fill="rgba(63,185,80,0.7)" fontSize={9} fontWeight={600}>
                  ACTIVE
                </text>
              );
            })()}
          </g>
        );
      })}
      {/* Nodes */}
      {positioned.map(n => {
        const color = STATUS_COLOR[n.status] || '#6e7681';
        return (
          <g key={n.id}>
            {n.status === 'ACTIVE' && (
              <circle cx={n.x} cy={n.y} r={32} fill="none" stroke={color} strokeWidth={1} opacity={0.15} />
            )}
            <circle cx={n.x} cy={n.y} r={24} fill={color} fillOpacity={0.12} stroke={color} strokeWidth={2} />
            <circle cx={n.x + 16} cy={n.y - 16} r={5} fill={color} />
            <text x={n.x} y={n.y + 5} textAnchor="middle" fill="#e6edf3" fontSize={11} fontWeight={700}
              style={{ fontFamily: 'DM Sans, system-ui, sans-serif' }}>
              {n.name.length > 10 ? n.name.slice(0, 9) + '…' : n.name}
            </text>
            <text x={n.x} y={n.y + 40} textAnchor="middle" fill="rgba(255,255,255,0.4)" fontSize={9.5}
              style={{ fontFamily: 'DM Sans, monospace' }}>
              {n.vpn_ip}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function ConnMatrix({ nodes, edges }) {
  if (nodes.length < 2) return null;
  const connected = new Set();
  edges.forEach(e => {
    connected.add(`${e.source_id}-${e.target_id}`);
    connected.add(`${e.target_id}-${e.source_id}`);
  });
  return (
    <div className="table-wrap" style={{ marginBottom: '1.5rem' }}>
      <table className="table">
        <thead>
          <tr>
            <th style={{ minWidth: 100 }}>Node</th>
            {nodes.map(n => <th key={n.id}>{n.name}</th>)}
          </tr>
        </thead>
        <tbody>
          {nodes.map(row => (
            <tr key={row.id}>
              <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span className={`indicator indicator--${row.status === 'ACTIVE' ? 'online' : 'offline'}`} />
                  {row.name}
                </div>
              </td>
              {nodes.map(col => (
                <td key={col.id} style={{ textAlign: 'center' }}>
                  {row.id === col.id
                    ? <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>—</span>
                    : connected.has(`${row.id}-${col.id}`)
                      ? <span style={{ color: 'var(--accent)', fontWeight: 700, fontSize: '0.85rem' }}>✓ Connected</span>
                      : <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Not linked</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const tooltipStyle = {
  contentStyle: { background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '6px', color: 'var(--text-primary)', fontSize: '0.8rem' },
  labelStyle: { color: 'var(--text-secondary)' },
};

const MAX_HISTORY = 40; // ~3.3 minutes at 5s interval

function fmtRate(bps) {
  if (bps == null || bps <= 0) return '0 B/s';
  const k = 1024;
  const u = ['B/s', 'KiB/s', 'MiB/s', 'GiB/s'];
  const i = Math.floor(Math.log(bps) / Math.log(k));
  return `${(bps / k ** i).toFixed(1)} ${u[i]}`;
}

function LiveThroughputGraph({ history, nodeNames }) {
  if (!history || history.length < 2) {
    return (
      <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: '0.5rem' }}>
        <Activity size={24} color="var(--text-muted)" />
        <span style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>Collecting data… (needs 2 polls)</span>
      </div>
    );
  }

  // Color palette for per-node lines
  const NODE_COLORS = ['#58a6ff', '#3fb950', '#f78166', '#d2a8ff', '#ffa657', '#79c0ff'];

  const linesRx = nodeNames.map((name, i) => (
    <Line key={`rx-${name}`} type="monotone" dataKey={`${name}_rx`}
      name={`${name} ↓`} stroke={NODE_COLORS[i % NODE_COLORS.length]}
      strokeWidth={2} dot={false} activeDot={{ r: 4 }}
      strokeDasharray={undefined} />
  ));
  const linesTx = nodeNames.map((name, i) => (
    <Line key={`tx-${name}`} type="monotone" dataKey={`${name}_tx`}
      name={`${name} ↑`} stroke={NODE_COLORS[i % NODE_COLORS.length]}
      strokeWidth={1.5} dot={false} activeDot={{ r: 3 }}
      strokeDasharray="4 3" strokeOpacity={0.7} />
  ));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={history} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
        <defs>
          {nodeNames.map((name, i) => (
            <linearGradient key={name} id={`lg-${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={NODE_COLORS[i % NODE_COLORS.length]} stopOpacity={0.3} />
              <stop offset="95%" stopColor={NODE_COLORS[i % NODE_COLORS.length]} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
        <XAxis dataKey="time" stroke="var(--text-muted)" fontSize={10}
          tick={{ fill: 'var(--text-muted)' }} tickLine={false} axisLine={false}
          interval="preserveStartEnd" />
        <YAxis stroke="var(--text-muted)" fontSize={10} tickFormatter={fmtRate}
          tick={{ fill: 'var(--text-muted)' }} tickLine={false} axisLine={false} width={62} />
        <Tooltip
          contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '8px', fontSize: '0.78rem' }}
          labelStyle={{ color: 'var(--text-secondary)', marginBottom: '0.35rem', fontWeight: 600 }}
          formatter={(v, name) => [fmtRate(v), name]}
        />
        <Legend iconType="circle" iconSize={8}
          formatter={v => <span style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>{v}</span>} />
        {linesRx}
        {linesTx}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function Overview() {
  const [stats, setStats] = useState(null);
  const [detailed, setDetailed] = useState(null);
  const [topology, setTopology] = useState({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [throughputHistory, setThroughputHistory] = useState([]);

  // Track previous cumulative bytes to compute per-interval deltas (bytes/s)
  const prevBytes = useRef({});

  const fetchAll = useCallback(async () => {
    try {
      setError(null);
      const [s, d, t] = await Promise.all([
        api.getStats(),
        api.getStatsDetailed().catch(() => null),
        api.getTopology().catch(() => ({ nodes: [], edges: [] })),
      ]);
      setStats(s); setDetailed(d); setTopology(t);

      // Build throughput history point
      if (d && d.nodes && d.nodes.length) {
        const now = new Date();
        const timeLabel = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        const point = { time: timeLabel };
        const prev = prevBytes.current;
        const INTERVAL = 5; // seconds

        d.nodes.forEach(n => {
          const key = `node_${n.node_id}`;
          const prevRx = prev[`${key}_rx`] ?? n.total_rx;
          const prevTx = prev[`${key}_tx`] ?? n.total_tx;
          const deltaRx = Math.max(0, n.total_rx - prevRx);
          const deltaTx = Math.max(0, n.total_tx - prevTx);
          point[`${n.node_name}_rx`] = Math.round(deltaRx / INTERVAL);
          point[`${n.node_name}_tx`] = Math.round(deltaTx / INTERVAL);
          prev[`${key}_rx`] = n.total_rx;
          prev[`${key}_tx`] = n.total_tx;
        });

        setThroughputHistory(h => [...h.slice(-MAX_HISTORY + 1), point]);
      }
    } catch (e) {
      setError(e.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  usePolling(fetchAll, 5000);

  if (loading && !stats) {
    return <div className="content"><div className="spinner" style={{ margin: '3rem auto', display: 'block' }} /></div>;
  }

  const total = stats?.total_nodes ?? 0;
  const active = stats?.active_nodes ?? 0;
  const healthPct = total ? Math.round((active / total) * 100) : 0;
  const nodes = detailed?.nodes ?? [];
  const maxBw = Math.max(...nodes.map(n => Math.max(n.total_rx, n.total_tx, 1)), 1);

  const barData = nodes.map(n => ({ name: n.node_name, rx: n.total_rx, tx: n.total_tx }));
  const pieData = [
    { name: 'Received', value: detailed?.total_rx ?? 0, fill: 'var(--info)' },
    { name: 'Sent', value: detailed?.total_tx ?? 0, fill: 'var(--accent)' },
  ].filter(d => d.value > 0);

  return (
    <div className="content">
      <div className="page-header">
        <div>
          <h1 className="page-title">Overview</h1>
          <div className="page-sub">Live · refreshes every 5s</div>
        </div>
      </div>

      {error && <div className="card" style={{ marginBottom: '1rem', borderColor: 'var(--danger)', color: 'var(--danger)' }}>{error}</div>}

      {/* Metric cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(175px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        <MetricCard icon={Server} label="Total Nodes" value={total} color="var(--info)" sub={`${active} active`} />
        <MetricCard icon={Activity} label="Active Nodes" value={active} color="var(--accent)"
          sub={healthPct + '% healthy'} />
        <MetricCard icon={LogIn} label="Join Requests" value={stats?.pending_join_requests ?? 0} color="var(--warning)"
          sub="pending approval" />
        <MetricCard icon={Link} label="Active Connections" value={stats?.active_connections ?? 0} color="var(--purple)"
          sub="VPN tunnels" />
        <MetricCard icon={Wifi} label="Total Traffic" value={fmt(( detailed?.total_rx ?? 0) + (detailed?.total_tx ?? 0))}
          color="var(--info)" sub="rx + tx combined" />
      </div>

      {/* Health bar */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem' }}>
          <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>Network Health</span>
          <span style={{ fontWeight: 700, color: healthPct >= 70 ? 'var(--accent)' : healthPct >= 40 ? 'var(--warning)' : 'var(--danger)' }}>
            {healthPct}%
          </span>
        </div>
        <div style={{ height: 6, background: 'var(--bg-secondary)', borderRadius: 999, overflow: 'hidden' }}>
          <div style={{
            height: '100%',
            width: `${healthPct}%`,
            background: healthPct >= 70 ? 'linear-gradient(90deg, var(--accent-dim), var(--accent))' : healthPct >= 40 ? 'var(--warning)' : 'var(--danger)',
            borderRadius: 999,
            transition: 'width 0.4s',
          }} />
        </div>
        <div style={{ display: 'flex', gap: '1.5rem', marginTop: '0.75rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
          <span><span style={{ color: 'var(--accent)', fontWeight: 700 }}>{active}</span> online</span>
          <span><span style={{ color: 'var(--danger)', fontWeight: 700 }}>{total - active}</span> offline</span>
          <span><span style={{ color: 'var(--warning)', fontWeight: 700 }}>{stats?.pending_join_requests ?? 0}</span> pending joins</span>
          <span><span style={{ color: 'var(--purple)', fontWeight: 700 }}>{stats?.active_connections ?? 0}</span> active connections</span>
        </div>
      </div>

      {/* Network map + Charts row */}
      {(topology.nodes.length > 0 || nodes.length > 0) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
          {/* Mini network map */}
          <div className="card" style={{ gridColumn: topology.nodes.length > 0 ? '1' : undefined }}>
            <p className="section-label" style={{ marginBottom: '0.5rem' }}>Network Diagram</p>
            <div style={{ height: 200 }}>
              {topology.nodes.length === 0
                ? <div className="empty-state" style={{ padding: '1rem' }}>No nodes yet</div>
                : <MiniNetworkMap topoNodes={topology.nodes} topoEdges={topology.edges} />}
            </div>
          </div>

          {/* Bandwidth chart */}
          {nodes.length > 0 && (
            <div className="card">
              <p className="section-label" style={{ marginBottom: '0.5rem' }}>Bandwidth by Node</p>
              <div style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={barData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.4} />
                    <XAxis dataKey="name" stroke="var(--text-muted)" fontSize={11} tick={{ fill: 'var(--text-secondary)' }} />
                    <YAxis stroke="var(--text-muted)" fontSize={10} tickFormatter={v => fmt(v, 0)} tick={{ fill: 'var(--text-secondary)' }} />
                    <Tooltip {...tooltipStyle} formatter={v => fmt(v)} labelFormatter={l => `Node: ${l}`} />
                    <Bar dataKey="rx" name="Received" fill="var(--info)" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="tx" name="Sent" fill="var(--accent)" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Traffic pie */}
          {pieData.length > 0 && (
            <div className="card">
              <p className="section-label" style={{ marginBottom: '0.5rem' }}>Traffic Distribution</p>
              <div style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={pieData} cx="50%" cy="48%" innerRadius={48} outerRadius={72}
                      paddingAngle={3} dataKey="value">
                      {pieData.map((d, i) => <Cell key={i} fill={d.fill} />)}
                    </Pie>
                    <Tooltip {...tooltipStyle} formatter={v => fmt(v)} />
                    <Legend formatter={v => <span style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>{v}</span>} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Live throughput line graph */}
      {nodes.length > 0 && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <div>
              <p className="section-label" style={{ margin: 0 }}>Live Throughput</p>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                Bytes/second · solid = RX · dashed = TX · updates every 5s
              </div>
            </div>
            <div style={{ display: 'flex', gap: '1rem', fontSize: '0.78rem' }}>
              {nodes.map(n => {
                const last = throughputHistory[throughputHistory.length - 1];
                const rxRate = last?.[`${n.node_name}_rx`] ?? 0;
                const txRate = last?.[`${n.node_name}_tx`] ?? 0;
                return (
                  <div key={n.node_id} style={{ textAlign: 'right' }}>
                    <div style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '0.8rem' }}>{n.node_name}</div>
                    <div style={{ color: 'var(--info)' }}>↓ {fmtRate(rxRate)}</div>
                    <div style={{ color: 'var(--accent)' }}>↑ {fmtRate(txRate)}</div>
                  </div>
                );
              })}
            </div>
          </div>
          <LiveThroughputGraph
            history={throughputHistory}
            nodeNames={nodes.map(n => n.node_name)}
          />
        </div>
      )}

      {/* Connectivity matrix */}
      {topology.nodes.length >= 2 && (
        <>
          <p className="section-label">Connectivity Matrix</p>
          <ConnMatrix nodes={topology.nodes} edges={topology.edges} />
        </>
      )}

      {/* Node cards */}
      {nodes.length > 0 && (
        <>
          <p className="section-label">Node Details</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1rem' }}>
            {nodes.map(n => (
              <div key={n.node_id} className={`node-conn-card node-conn-card--${n.reachable ? 'online' : 'offline'}`}>
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span className={`indicator indicator--${n.reachable ? 'online' : 'offline'}`} />
                    <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>{n.node_name}</span>
                  </div>
                  <span style={{ fontFamily: 'monospace', fontSize: '0.8rem', color: 'var(--info)', background: 'rgba(88,166,255,0.1)', padding: '0.15rem 0.5rem', borderRadius: 4 }}>
                    {n.vpn_ip}
                  </span>
                </div>

                {/* Reachability + peers summary */}
                <div style={{ display: 'flex', gap: '1rem', marginBottom: '0.75rem', fontSize: '0.78rem' }}>
                  <span style={{ color: n.reachable ? 'var(--accent)' : 'var(--danger)' }}>
                    {n.reachable ? '● Reachable' : '○ Unreachable'}
                  </span>
                  <span style={{ color: 'var(--text-muted)' }}>
                    <Users size={11} style={{ verticalAlign: 'middle', marginRight: 3 }} />
                    {n.peers.length} peer{n.peers.length !== 1 ? 's' : ''}
                  </span>
                  {(() => {
                    const hs = n.peers.filter(p => p.latest_handshake_ago != null).map(p => p.latest_handshake_ago);
                    if (!hs.length) return null;
                    return (
                      <span style={{ color: 'var(--text-muted)' }}>
                        <Clock size={11} style={{ verticalAlign: 'middle', marginRight: 3 }} />
                        {fmtHandshake(Math.min(...hs))}
                      </span>
                    );
                  })()}
                </div>

                {/* Bandwidth */}
                <div style={{ marginBottom: '0.75rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.3rem', fontSize: '0.78rem' }}>
                    <span style={{ color: 'var(--text-muted)' }}><ArrowDownLeft size={11} style={{ verticalAlign: 'middle' }} /> Received</span>
                    <span style={{ color: 'var(--info)', fontWeight: 600 }}>{fmt(n.total_rx)}</span>
                  </div>
                  <div className="bw-bar-wrap">
                    <div className="bw-bar-fill" style={{ width: `${Math.round((n.total_rx / maxBw) * 100)}%`, background: 'var(--info)' }} />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '0.4rem', marginBottom: '0.3rem', fontSize: '0.78rem' }}>
                    <span style={{ color: 'var(--text-muted)' }}><ArrowUpRight size={11} style={{ verticalAlign: 'middle' }} /> Sent</span>
                    <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{fmt(n.total_tx)}</span>
                  </div>
                  <div className="bw-bar-wrap">
                    <div className="bw-bar-fill" style={{ width: `${Math.round((n.total_tx / maxBw) * 100)}%`, background: 'var(--accent)' }} />
                  </div>
                </div>

                {/* Peers */}
                {n.peers.length > 0 && (
                  <div>
                    <div style={{ fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: '0.4rem' }}>
                      Peers
                    </div>
                    {n.peers.slice(0, 3).map((p, pi) => (
                      <div key={pi} className="peer-row">
                        <span style={{ color: 'var(--accent)', fontWeight: 700, fontSize: '0.85rem' }}>→</span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontFamily: 'monospace', fontSize: '0.78rem', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {p.allowed_ips || p.public_key?.slice(0, 16) + '…'}
                          </div>
                          <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.25rem', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                            <span><ArrowDownLeft size={9} style={{ verticalAlign: 'middle' }} /> {fmt(p.transfer_rx)}</span>
                            <span><ArrowUpRight size={9} style={{ verticalAlign: 'middle' }} /> {fmt(p.transfer_tx)}</span>
                            {p.latest_handshake_ago != null && (
                              <span><Clock size={9} style={{ verticalAlign: 'middle' }} /> {fmtHandshake(p.latest_handshake_ago)}</span>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                    {n.peers.length > 3 && (
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem', textAlign: 'center' }}>
                        +{n.peers.length - 3} more
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {!loading && nodes.length === 0 && total === 0 && (
        <div className="card">
          <div className="empty-state">
            <Server size={32} color="var(--text-muted)" />
            <div style={{ fontWeight: 600 }}>No nodes yet</div>
            <div style={{ fontSize: '0.85rem' }}>Start an agent and approve its join request to add nodes.</div>
          </div>
        </div>
      )}
    </div>
  );
}
