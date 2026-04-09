import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';
import {
  ZoomIn, ZoomOut, Maximize2, ArrowDownLeft, ArrowUpRight,
  Clock, ChevronDown, ChevronRight, Wifi, WifiOff, Server,
} from 'lucide-react';

const STATUS_COLOR = {
  ACTIVE:   '#3fb950',
  APPROVED: '#58a6ff',
  PENDING:  '#d29922',
  OFFLINE:  '#6e7681',
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

// Compact node painter — small circle with status ring
function paintNode(node, ctx, globalScale) {
  const r = 10;
  const color = STATUS_COLOR[node.status] || '#6e7681';
  const selected = node.__selected;

  // Selection ring
  if (selected) {
    ctx.beginPath();
    ctx.arc(node.x, node.y, r + 5, 0, 2 * Math.PI);
    ctx.strokeStyle = 'rgba(255,255,255,0.25)';
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  // Active glow
  if (node.status === 'ACTIVE') {
    ctx.beginPath();
    ctx.arc(node.x, node.y, r + 3, 0, 2 * Math.PI);
    ctx.fillStyle = color + '18';
    ctx.fill();
  }

  // Node fill
  ctx.beginPath();
  ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
  ctx.fillStyle = color + '28';
  ctx.fill();

  // Node border
  ctx.beginPath();
  ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
  ctx.strokeStyle = color;
  ctx.lineWidth = selected ? 2 : 1.5;
  ctx.stroke();

  // Name label (only draw when zoomed enough)
  if (globalScale > 0.6) {
    const label = node.name.length > 10 ? node.name.slice(0, 9) + '…' : node.name;
    ctx.font = `600 ${9 / globalScale}px system-ui, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = '#e6edf3';
    ctx.fillText(label, node.x, node.y);
  }

  // IP below node
  if (globalScale > 0.8 && node.vpn_ip) {
    ctx.font = `${7 / globalScale}px system-ui, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = 'rgba(255,255,255,0.35)';
    ctx.fillText(node.vpn_ip, node.x, node.y + r + 3 / globalScale);
  }
}

// Expandable node card for the side panel
function NodeCard({ node, detail, isExpanded, onToggle, isSelected, onSelect }) {
  const color = STATUS_COLOR[node.status] || '#6e7681';
  const isOnline = node.status === 'ACTIVE' || node.status === 'APPROVED';

  return (
    <div
      className={`topo-node-card${isSelected ? ' topo-node-card--selected' : ''}`}
      style={{ borderLeftColor: color }}
    >
      {/* Header row — always visible */}
      <div
        className="topo-node-card-header"
        onClick={() => { onSelect(node); onToggle(node.id); }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 0 }}>
          {isOnline
            ? <Wifi size={13} color={color} style={{ flexShrink: 0 }} />
            : <WifiOff size={13} color={color} style={{ flexShrink: 0 }} />
          }
          <span className="topo-node-name">{node.name}</span>
          {node.is_gateway && (
            <span className="tag" style={{ fontSize: '0.6rem', padding: '0.1rem 0.4rem', color: '#a371f7', borderColor: '#a371f740', background: '#a371f710' }}>
              GW
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexShrink: 0 }}>
          <span className="topo-node-ip">{node.vpn_ip || '—'}</span>
          {isExpanded
            ? <ChevronDown size={13} color="var(--text-muted)" />
            : <ChevronRight size={13} color="var(--text-muted)" />
          }
        </div>
      </div>

      {/* Expanded detail */}
      {isExpanded && (
        <div className="topo-node-card-body">
          <div className="topo-kv-row">
            <span>Status</span>
            <span style={{ color, fontWeight: 600 }}>{node.status}</span>
          </div>

          {detail ? (
            <>
              <div className="topo-kv-row">
                <span><ArrowDownLeft size={10} style={{ verticalAlign: 'middle' }} /> RX</span>
                <span style={{ color: 'var(--info)', fontWeight: 600 }}>{fmt(detail.total_rx)}</span>
              </div>
              <div className="topo-kv-row">
                <span><ArrowUpRight size={10} style={{ verticalAlign: 'middle' }} /> TX</span>
                <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{fmt(detail.total_tx)}</span>
              </div>
              <div className="topo-kv-row">
                <span>Reachable</span>
                <span style={{ color: detail.reachable ? 'var(--accent)' : 'var(--danger)', fontWeight: 600 }}>
                  {detail.reachable ? 'Yes' : 'No'}
                </span>
              </div>

              {detail.peers?.length > 0 && (
                <div style={{ marginTop: '0.6rem' }}>
                  <div className="topo-subsection-label">Peers ({detail.peers.length})</div>
                  {detail.peers.map((p, i) => (
                    <div key={i} className="topo-peer-row">
                      <div className="topo-peer-ip">
                        {p.allowed_ips || (p.public_key?.slice(0, 16) + '…')}
                      </div>
                      <div className="topo-peer-stats">
                        <span><ArrowDownLeft size={9} /> {fmt(p.transfer_rx)}</span>
                        <span><ArrowUpRight size={9} /> {fmt(p.transfer_tx)}</span>
                        {p.latest_handshake_ago != null && (
                          <span><Clock size={9} /> {fmtHs(p.latest_handshake_ago)}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', paddingTop: '0.25rem' }}>
              No live stats
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function Topology() {
  const [topology, setTopology] = useState({ nodes: [], edges: [] });
  const [detailed, setDetailed] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [expandedIds, setExpandedIds] = useState(new Set());
  const containerRef = useRef(null);
  const graphRef = useRef(null);
  const [size, setSize] = useState({ width: 600, height: 500 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver(() =>
      setSize({ width: el.offsetWidth, height: el.offsetHeight })
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const fetchData = useCallback(async () => {
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

  usePolling(fetchData, 5000);

  const graphData = useMemo(() => ({
    nodes: topology.nodes.map(n => ({
      id: n.id, name: n.name, vpn_ip: n.vpn_ip, status: n.status,
      is_gateway: n.is_gateway, __selected: selectedId === n.id,
    })),
    links: topology.edges.map(e => ({
      id: e.id, source: e.source_id, target: e.target_id, status: e.status,
    })),
  }), [topology, selectedId]);

  const detailByNodeId = useMemo(() => {
    if (!detailed?.nodes) return {};
    return Object.fromEntries(detailed.nodes.map(n => [n.node_id, n]));
  }, [detailed]);

  const handleNodeClick = useCallback(node => {
    const id = node.id;
    setSelectedId(prev => prev === id ? null : id);
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleCardSelect = useCallback(node => {
    setSelectedId(prev => prev === node.id ? null : node.id);
    // zoom graph to node
    if (graphRef.current) {
      const gNode = graphData.nodes.find(n => n.id === node.id);
      if (gNode?.x != null) {
        graphRef.current.centerAt(gNode.x, gNode.y, 600);
        graphRef.current.zoom(2, 600);
      }
    }
  }, [graphData]);

  const handleCardToggle = useCallback(id => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  if (loading && !topology.nodes.length) {
    return (
      <div className="content">
        <div className="spinner" style={{ margin: '3rem auto', display: 'block' }} />
      </div>
    );
  }

  const activeNodes = topology.nodes.filter(n => n.status === 'ACTIVE').length;
  const activeLinks = topology.edges.filter(e => e.status === 'ACTIVE').length;

  return (
    <div className="content" style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: '1.25rem' }}>
      <div className="page-header" style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h1 className="page-title">Network Topology</h1>
            <div className="page-sub">
              {topology.nodes.length} node{topology.nodes.length !== 1 ? 's' : ''} · {activeNodes} active · {activeLinks} connection{activeLinks !== 1 ? 's' : ''}
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            {Object.entries(STATUS_COLOR).map(([s, c]) => (
              <div key={s} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <svg width={10} height={10}>
                  <circle cx={5} cy={5} r={4} fill={c + '25'} stroke={c} strokeWidth={1.5} />
                </svg>
                <span>{s}</span>
              </div>
            ))}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginLeft: '0.25rem' }}>
              <svg width={22} height={4}>
                <line x1={0} y1={2} x2={22} y2={2} stroke="#3fb950" strokeWidth={2} />
              </svg>
              <span>Link</span>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="card" style={{ marginBottom: '0.75rem', borderColor: 'var(--danger)', color: 'var(--danger)', padding: '0.75rem 1rem', fontSize: '0.85rem' }}>
          {error}
        </div>
      )}

      <div className="topo-layout" style={{ flex: 1, minHeight: 0 }}>
        {/* Graph canvas */}
        <div className="topo-graph" ref={containerRef}>
          {topology.nodes.length === 0 ? (
            <div className="empty-state">
              <Server size={32} color="var(--text-muted)" />
              <div style={{ fontWeight: 600, marginTop: '0.5rem' }}>No nodes yet</div>
              <div style={{ fontSize: '0.82rem' }}>Approve join requests to add nodes.</div>
            </div>
          ) : (
            <ForceGraph2D
              ref={graphRef}
              graphData={graphData}
              width={size.width}
              height={size.height}
              backgroundColor="transparent"
              nodeCanvasObject={paintNode}
              nodeCanvasObjectMode={() => 'replace'}
              nodePointerAreaPaint={(node, color, ctx) => {
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(node.x, node.y, 16, 0, 2 * Math.PI);
                ctx.fill();
              }}
              nodeLabel={node => `${node.name}${node.vpn_ip ? ' · ' + node.vpn_ip : ''} · ${node.status}`}
              onNodeClick={handleNodeClick}
              onBackgroundClick={() => setSelectedId(null)}
              linkColor={link => link.status === 'ACTIVE' ? '#3fb950' : '#373e47'}
              linkWidth={link => link.status === 'ACTIVE' ? 1.5 : 1}
              linkDirectionalParticles={link => link.status === 'ACTIVE' ? 3 : 0}
              linkDirectionalParticleSpeed={0.004}
              linkDirectionalParticleColor={() => '#3fb950'}
              linkDirectionalParticleWidth={1.5}
              d3AlphaDecay={0.02}
              d3VelocityDecay={0.3}
              cooldownTicks={150}
              enableNodeDrag
              enableZoomInteraction
              enablePanInteraction
            />
          )}

          {/* Zoom controls */}
          <div className="zoom-controls">
            <button className="btn btn--ghost btn--sm" onClick={() => graphRef.current?.zoom(1.4, 350)} title="Zoom in">
              <ZoomIn size={13} />
            </button>
            <button className="btn btn--ghost btn--sm" onClick={() => graphRef.current?.zoom(0.7, 350)} title="Zoom out">
              <ZoomOut size={13} />
            </button>
            <button className="btn btn--ghost btn--sm" onClick={() => graphRef.current?.zoomToFit(350, 40)} title="Fit all">
              <Maximize2 size={13} />
            </button>
          </div>
        </div>

        {/* Side panel — node list */}
        <div className="topo-panel">
          <div className="topo-panel-section">
            <div className="topo-panel-title">Nodes</div>
            {topology.nodes.length === 0 ? (
              <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textAlign: 'center', padding: '1rem 0' }}>
                No nodes
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                {topology.nodes.map(n => (
                  <NodeCard
                    key={n.id}
                    node={n}
                    detail={detailByNodeId[n.id] ?? null}
                    isExpanded={expandedIds.has(n.id)}
                    isSelected={selectedId === n.id}
                    onSelect={handleCardSelect}
                    onToggle={handleCardToggle}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Network summary */}
          <div className="topo-panel-section">
            <div className="topo-panel-title">Summary</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.4rem' }}>
              {[
                ['Total nodes', topology.nodes.length],
                ['Active', activeNodes],
                ['Offline', topology.nodes.filter(n => n.status === 'OFFLINE').length],
                ['Links', activeLinks],
              ].map(([label, val]) => (
                <div key={label} className="topo-stat-cell">
                  <div className="topo-stat-label">{label}</div>
                  <div className="topo-stat-val">{val}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Total bandwidth */}
          {detailed && (
            <div className="topo-panel-section">
              <div className="topo-panel-title">Total Bandwidth</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                <div className="topo-kv-row">
                  <span><ArrowDownLeft size={11} style={{ verticalAlign: 'middle' }} /> RX</span>
                  <span style={{ color: 'var(--info)', fontWeight: 700 }}>{fmt(detailed.total_rx)}</span>
                </div>
                <div className="topo-kv-row">
                  <span><ArrowUpRight size={11} style={{ verticalAlign: 'middle' }} /> TX</span>
                  <span style={{ color: 'var(--accent)', fontWeight: 700 }}>{fmt(detailed.total_tx)}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
