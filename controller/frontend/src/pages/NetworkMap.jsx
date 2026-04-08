import { useState, useCallback, useMemo } from 'react';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';
import { ArrowDownLeft, ArrowUpRight, Clock, Globe, RefreshCw } from 'lucide-react';

const STATUS_COLOR = {
  ACTIVE: '#3fb950',
  PENDING: '#d29922',
  OFFLINE: '#6e7681',
  APPROVED: '#58a6ff',
};

function fmt(b) {
  if (!b) return '0 B';
  const k = 1024, u = ['B', 'KiB', 'MiB', 'GiB'];
  const i = Math.floor(Math.log(b) / Math.log(k));
  return `${(b / k ** i).toFixed(1)} ${u[i]}`;
}
function fmtHs(s) {
  if (s == null) return 'never';
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

function circlePositions(n, cx, cy, r) {
  if (n === 0) return [];
  if (n === 1) return [{ x: cx, y: cy }];
  return Array.from({ length: n }, (_, i) => ({
    x: cx + r * Math.cos((i / n) * 2 * Math.PI - Math.PI / 2),
    y: cy + r * Math.sin((i / n) * 2 * Math.PI - Math.PI / 2),
  }));
}

function NetworkSVG({ topoNodes, topoEdges, detailedNodes, selected, onSelect }) {
  const W = 640, H = 400;
  const CX = W / 2, CY = H / 2;

  // Hub-and-spoke layout: gateway hub goes to center, spokes circle around
  const hubNodes = topoNodes.filter(n => n.is_gateway);
  const spokeNodes = topoNodes.filter(n => !n.is_gateway);
  const hasHub = hubNodes.length > 0;

  const R = !hasHub
    ? (topoNodes.length <= 1 ? 0 : Math.min(CX, CY) * (topoNodes.length <= 4 ? 0.52 : 0.58))
    : Math.min(CX, CY) * (spokeNodes.length <= 4 ? 0.55 : 0.62);

  let positioned;
  if (hasHub) {
    const spokePositions = circlePositions(spokeNodes.length, CX, CY, R);
    const hubPositioned = hubNodes.map((n, i) => ({ ...n, x: CX + (i - (hubNodes.length - 1) / 2) * 0, y: CY }));
    positioned = [
      ...hubPositioned,
      ...spokeNodes.map((n, i) => ({ ...n, ...spokePositions[i] })),
    ];
  } else {
    const positions = circlePositions(topoNodes.length, CX, CY, R);
    positioned = topoNodes.map((n, i) => ({ ...n, ...positions[i] }));
  }
  const nodeMap = Object.fromEntries(positioned.map(n => [n.id, n]));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: '100%' }}>
      <defs>
        <style>{`
          @keyframes dash-flow { to { stroke-dashoffset: -24; } }
          .active-line { animation: dash-flow 1.1s linear infinite; }
        `}</style>
        {/* Radial gradient for nodes */}
        {positioned.map(n => {
          const c = STATUS_COLOR[n.status] || '#6e7681';
          return (
            <radialGradient key={`g-${n.id}`} id={`ng-${n.id}`} cx="40%" cy="35%" r="70%">
              <stop offset="0%" stopColor={c} stopOpacity={0.35} />
              <stop offset="100%" stopColor={c} stopOpacity={0.08} />
            </radialGradient>
          );
        })}
        <filter id="node-glow">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      {/* Background dots */}
      {Array.from({ length: 7 }, (_, row) =>
        Array.from({ length: 11 }, (_, col) => (
          <circle key={`d-${row}-${col}`}
            cx={col * 64 + 8} cy={row * 64 + 8} r={1.2}
            fill="rgba(255,255,255,0.035)" />
        ))
      )}

      {/* Edges */}
      {topoEdges.map(e => {
        const src = nodeMap[e.source_id], tgt = nodeMap[e.target_id];
        if (!src || !tgt) return null;
        const active = e.status === 'ACTIVE';
        const mx = (src.x + tgt.x) / 2, my = (src.y + tgt.y) / 2;
        const det = detailedNodes?.find(n => n.node_id === src.id);
        const peer = det?.peers?.find(p => {
          const tgtNode = positioned.find(n => n.id === tgt.id);
          return tgtNode && p.allowed_ips?.startsWith(tgtNode.vpn_ip?.split('/')[0]);
        });

        return (
          <g key={e.id}>
            {/* Glow track */}
            <line x1={src.x} y1={src.y} x2={tgt.x} y2={tgt.y}
              stroke={active ? '#3fb950' : '#373e47'} strokeWidth={active ? 12 : 6}
              strokeOpacity={0.06} />
            {/* Main line */}
            <line x1={src.x} y1={src.y} x2={tgt.x} y2={tgt.y}
              stroke={active ? '#3fb950' : '#4a5060'}
              strokeWidth={active ? 2 : 1.5}
              strokeDasharray={active ? '8 5' : '5 6'}
              className={active ? 'active-line' : ''} />
            {/* Label at midpoint */}
            {active && (
              <g>
                <rect x={mx - 26} y={my - 9} width={52} height={16} rx={4}
                  fill="var(--bg-secondary)" stroke="#3fb95040" strokeWidth={1} />
                <text x={mx} y={my + 3} textAnchor="middle" fill="#3fb950"
                  fontSize={9} fontWeight={700} fontFamily="system-ui">
                  ACTIVE
                </text>
              </g>
            )}
            {/* Bandwidth on line */}
            {peer && (peer.transfer_rx > 0 || peer.transfer_tx > 0) && (
              <g>
                <text x={mx + 30} y={my - 4} fill="rgba(88,166,255,0.7)" fontSize={8} fontFamily="monospace">
                  ↓{fmt(peer.transfer_rx)}
                </text>
                <text x={mx + 30} y={my + 10} fill="rgba(63,185,80,0.7)" fontSize={8} fontFamily="monospace">
                  ↑{fmt(peer.transfer_tx)}
                </text>
              </g>
            )}
          </g>
        );
      })}

      {/* Nodes */}
      {positioned.map(n => {
        const color = STATUS_COLOR[n.status] || '#6e7681';
        const sel = selected?.id === n.id;
        const detail = detailedNodes?.find(d => d.node_id === n.id);
        const isHub = n.is_gateway;
        const NR = isHub ? 38 : 30;
        const hubColor = '#f59e0b';

        return (
          <g key={n.id} style={{ cursor: 'pointer' }} onClick={() => onSelect(n)}>
            {/* Hub glow ring */}
            {isHub && (
              <circle cx={n.x} cy={n.y} r={NR + 14} fill="none"
                stroke={hubColor} strokeWidth={1.5} strokeOpacity={0.18}
                strokeDasharray="6 4" className="active-line" />
            )}
            {/* Selection ring */}
            {sel && (
              <circle cx={n.x} cy={n.y} r={NR + 10} fill="none"
                stroke="rgba(255,255,255,0.35)" strokeWidth={1.5} strokeDasharray="4 3" />
            )}
            {/* Outer pulse for active */}
            {n.status === 'ACTIVE' && (
              <circle cx={n.x} cy={n.y} r={NR + 6} fill="none"
                stroke={color} strokeWidth={1} strokeOpacity={0.2} />
            )}
            {/* Node circle */}
            <circle cx={n.x} cy={n.y} r={NR}
              fill={`url(#ng-${n.id})`}
              stroke={isHub ? hubColor : (sel ? 'rgba(255,255,255,0.6)' : color)}
              strokeWidth={isHub ? 3 : (sel ? 2.5 : 2)} />
            {/* Status dot */}
            <circle cx={n.x + NR * 0.65} cy={n.y - NR * 0.65} r={isHub ? 7 : 6}
              fill={color} stroke="var(--bg-card)" strokeWidth={1.5}
              filter={n.status === 'ACTIVE' ? 'url(#node-glow)' : undefined} />
            {/* Hub crown label */}
            {isHub && (
              <text x={n.x} y={n.y - NR - 8} textAnchor="middle"
                fill={hubColor} fontSize={9} fontWeight={800} fontFamily="system-ui" letterSpacing="0.08em">
                HUB
              </text>
            )}
            {/* Name */}
            <text x={n.x} y={n.y + 4} textAnchor="middle" fill="#e6edf3"
              fontSize={isHub ? 12 : 11} fontWeight={700} fontFamily="DM Sans, system-ui">
              {n.name.length > 10 ? n.name.slice(0, 9) + '…' : n.name}
            </text>
            {/* VPN IP */}
            <text x={n.x} y={n.y + NR + 16} textAnchor="middle"
              fill="rgba(255,255,255,0.45)" fontSize={9.5} fontFamily="monospace">
              {n.vpn_ip}
            </text>
            {/* RX/TX if detail available */}
            {detail && (detail.total_rx > 0 || detail.total_tx > 0) && (
              <>
                <text x={n.x} y={n.y + NR + 30} textAnchor="middle"
                  fill="rgba(88,166,255,0.6)" fontSize={8} fontFamily="monospace">
                  ↓{fmt(detail.total_rx)}
                </text>
                <text x={n.x} y={n.y + NR + 41} textAnchor="middle"
                  fill="rgba(63,185,80,0.6)" fontSize={8} fontFamily="monospace">
                  ↑{fmt(detail.total_tx)}
                </text>
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export function NetworkMap() {
  const [topology, setTopology] = useState({ nodes: [], edges: [] });
  const [detailed, setDetailed] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);

  const fetchAll = useCallback(async () => {
    try {
      setError(null);
      const [t, d] = await Promise.all([
        api.getTopology(),
        api.getStatsDetailed().catch(() => null),
      ]);
      setTopology(t);
      setDetailed(d);
    } catch (e) {
      setError(e.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  usePolling(fetchAll, 5000);

  const selectedDetail = useMemo(() =>
    selected && detailed ? detailed.nodes.find(n => n.node_id === selected.id) ?? null : null,
    [selected, detailed]);

  const handleSelect = useCallback(node => {
    setSelected(prev => prev?.id === node.id ? null : node);
  }, []);

  if (loading && !topology.nodes.length) {
    return <div className="content"><div className="spinner" style={{ margin: '3rem auto', display: 'block' }} /></div>;
  }

  const STATUS_COLOR_LOCAL = STATUS_COLOR;

  return (
    <div className="content" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="page-header">
        <div>
          <h1 className="page-title">Network Map</h1>
          <div className="page-sub">Static layout · animated connections · click a node for details</div>
        </div>
      </div>

      {error && <div className="card" style={{ marginBottom: '1rem', borderColor: 'var(--danger)', color: 'var(--danger)' }}>{error}</div>}

      <div className="netmap-layout">
        {/* SVG area */}
        <div className="netmap-svg-area">
          {topology.nodes.length === 0 ? (
            <div className="empty-state">
              <Globe size={36} color="var(--text-muted)" />
              <div style={{ fontWeight: 600 }}>No nodes</div>
              <div style={{ fontSize: '0.85rem' }}>Approve join requests to add nodes to the map.</div>
            </div>
          ) : (
            <NetworkSVG
              topoNodes={topology.nodes}
              topoEdges={topology.edges}
              detailedNodes={detailed?.nodes ?? []}
              selected={selected}
              onSelect={handleSelect}
            />
          )}

          {/* Stats bar bottom-left */}
          {topology.nodes.length > 0 && (
            <div style={{
              position: 'absolute', bottom: '1rem', left: '1rem',
              display: 'flex', gap: '0.5rem', fontSize: '0.75rem',
            }}>
              {[
                { label: 'Nodes', value: topology.nodes.length, color: 'var(--info)' },
                { label: 'Active', value: topology.nodes.filter(n => n.status === 'ACTIVE').length, color: 'var(--accent)' },
                { label: 'Links', value: topology.edges.filter(e => e.status === 'ACTIVE').length, color: 'var(--purple)' },
              ].map(({ label, value, color }) => (
                <div key={label} style={{
                  background: 'rgba(13,15,18,0.85)', border: '1px solid var(--border)',
                  borderRadius: 6, padding: '0.3rem 0.6rem', backdropFilter: 'blur(4px)',
                }}>
                  <span style={{ color: 'var(--text-muted)' }}>{label} </span>
                  <span style={{ color, fontWeight: 700 }}>{value}</span>
                </div>
              ))}
            </div>
          )}

          {/* Auto-refresh badge */}
          <div style={{
            position: 'absolute', top: '0.75rem', right: '0.75rem',
            background: 'rgba(13,15,18,0.8)', border: '1px solid var(--border)',
            borderRadius: 6, padding: '0.25rem 0.6rem', fontSize: '0.72rem',
            color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.35rem',
            backdropFilter: 'blur(4px)',
          }}>
            <RefreshCw size={10} style={{ animation: 'spin 3s linear infinite' }} />
            Live · 5s
          </div>
        </div>

        {/* Detail panel */}
        <div className="netmap-panel">
          <div style={{ padding: '1rem', borderBottom: '1px solid var(--border)' }}>
            <div className="topo-panel-title">Node Detail</div>
            {!selected ? (
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', paddingTop: '0.5rem' }}>
                Click a node on the map
              </div>
            ) : (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                  <svg width={10} height={10}>
                    <circle cx={5} cy={5} r={4.5} fill={STATUS_COLOR_LOCAL[selected.status] || '#6e7681'} />
                  </svg>
                  <span style={{ fontWeight: 700, fontSize: '1.05rem' }}>{selected.name}</span>
                  {selected.is_gateway && (
                    <span style={{ background: '#f59e0b', color: '#fff', padding: '1px 6px', borderRadius: 8, fontSize: '0.65rem', fontWeight: 800 }}>HUB</span>
                  )}
                </div>
                <div style={{ fontSize: '0.8rem', display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-muted)' }}>VPN IP</span>
                    <span style={{ fontFamily: 'monospace', color: 'var(--info)', fontWeight: 600 }}>{selected.vpn_ip}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Status</span>
                    <span style={{ color: STATUS_COLOR_LOCAL[selected.status] || 'var(--text-primary)', fontWeight: 700 }}>{selected.status}</span>
                  </div>
                  {selectedDetail && (
                    <>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'var(--text-muted)' }}><ArrowDownLeft size={11} style={{ verticalAlign: 'middle' }} /> Received</span>
                        <span style={{ color: 'var(--info)', fontWeight: 600 }}>{fmt(selectedDetail.total_rx)}</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'var(--text-muted)' }}><ArrowUpRight size={11} style={{ verticalAlign: 'middle' }} /> Sent</span>
                        <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{fmt(selectedDetail.total_tx)}</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'var(--text-muted)' }}>Reachable</span>
                        <span style={{ color: selectedDetail.reachable ? 'var(--accent)' : 'var(--danger)', fontWeight: 600 }}>
                          {selectedDetail.reachable ? 'Yes' : 'No'}
                        </span>
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Peers section */}
          {selectedDetail && selectedDetail.peers.length > 0 && (
            <div style={{ padding: '1rem' }}>
              <div className="topo-panel-title">Peers ({selectedDetail.peers.length})</div>
              {selectedDetail.peers.map((p, i) => (
                <div key={i} style={{
                  background: 'var(--bg-card)', border: '1px solid var(--border)',
                  borderRadius: 6, padding: '0.6rem 0.75rem', marginBottom: '0.5rem',
                  fontSize: '0.78rem',
                }}>
                  <div style={{ fontFamily: 'monospace', color: 'var(--accent)', marginBottom: '0.35rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {p.allowed_ips || '—'}
                  </div>
                  <div style={{ display: 'flex', gap: '0.75rem', color: 'var(--text-muted)' }}>
                    <span style={{ color: 'var(--info)' }}><ArrowDownLeft size={9} /> {fmt(p.transfer_rx)}</span>
                    <span style={{ color: 'var(--accent)' }}><ArrowUpRight size={9} /> {fmt(p.transfer_tx)}</span>
                  </div>
                  {p.latest_handshake_ago != null && (
                    <div style={{ color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                      <Clock size={9} style={{ verticalAlign: 'middle', marginRight: 3 }} />
                      {fmtHs(p.latest_handshake_ago)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* All nodes list */}
          <div style={{ padding: '1rem', borderTop: '1px solid var(--border)', marginTop: 'auto' }}>
            <div className="topo-panel-title">All Nodes</div>
            {topology.nodes.map(n => (
              <div key={n.id}
                style={{
                  display: 'flex', alignItems: 'center', gap: '0.5rem',
                  padding: '0.4rem 0.5rem', borderRadius: 6,
                  background: selected?.id === n.id ? 'rgba(63,185,80,0.08)' : 'transparent',
                  border: `1px solid ${selected?.id === n.id ? 'rgba(63,185,80,0.25)' : 'transparent'}`,
                  cursor: 'pointer', marginBottom: '0.25rem',
                }}
                onClick={() => handleSelect(n)}
              >
                <svg width={8} height={8}>
                  <circle cx={4} cy={4} r={3.5} fill={STATUS_COLOR_LOCAL[n.status] || '#6e7681'} />
                </svg>
                <span style={{ fontSize: '0.82rem', fontWeight: 600, flex: 1 }}>{n.name}</span>
                {n.is_gateway && (
                  <span style={{ background: '#f59e0b', color: '#fff', padding: '1px 5px', borderRadius: 6, fontSize: '0.65rem', fontWeight: 700 }}>HUB</span>
                )}
                <span style={{ fontFamily: 'monospace', fontSize: '0.72rem', color: 'var(--text-muted)' }}>{n.vpn_ip}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
