import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';
import { ZoomIn, ZoomOut, Maximize2, ArrowDownLeft, ArrowUpRight, Clock } from 'lucide-react';

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

function paintNode(node, ctx) {
  const r = 20;
  const color = STATUS_COLOR[node.status] || '#6e7681';
  const selected = node.__selected;

  // Glow ring for selected
  if (selected) {
    ctx.beginPath();
    ctx.arc(node.x, node.y, r + 7, 0, 2 * Math.PI);
    ctx.strokeStyle = 'rgba(255,255,255,0.4)';
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }

  // Outer glow for active
  if (node.status === 'ACTIVE') {
    ctx.beginPath();
    ctx.arc(node.x, node.y, r + 4, 0, 2 * Math.PI);
    ctx.fillStyle = color + '20';
    ctx.fill();
  }

  // Fill
  ctx.beginPath();
  ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
  ctx.fillStyle = color + '22';
  ctx.fill();

  // Border
  ctx.beginPath();
  ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
  ctx.strokeStyle = color;
  ctx.lineWidth = selected ? 2.5 : 2;
  ctx.stroke();

  // Name
  ctx.font = `700 11px system-ui, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = '#e6edf3';
  const name = node.name.length > 9 ? node.name.slice(0, 8) + '…' : node.name;
  ctx.fillText(name, node.x, node.y);

  // IP below
  ctx.font = '9px system-ui, sans-serif';
  ctx.textBaseline = 'top';
  ctx.fillStyle = 'rgba(255,255,255,0.4)';
  ctx.fillText(node.vpn_ip || '', node.x, node.y + r + 5);
}

export function Topology() {
  const [topology, setTopology] = useState({ nodes: [], edges: [] });
  const [detailed, setDetailed] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const containerRef = useRef(null);
  const graphRef = useRef(null);
  const [size, setSize] = useState({ width: 600, height: 500 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver(() => setSize({ width: el.offsetWidth, height: el.offsetHeight }));
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const fetch = useCallback(async () => {
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

  usePolling(fetch, 5000);

  const graphData = useMemo(() => ({
    nodes: topology.nodes.map(n => ({
      id: n.id, name: n.name, vpn_ip: n.vpn_ip, status: n.status,
      __selected: selected?.id === n.id,
    })),
    links: topology.edges.map(e => ({
      id: e.id, source: e.source_id, target: e.target_id, status: e.status,
    })),
  }), [topology, selected]);

  const selectedDetail = useMemo(() => {
    if (!selected || !detailed) return null;
    return detailed.nodes.find(n => n.node_id === selected.id) ?? null;
  }, [selected, detailed]);

  const handleNodeClick = useCallback(node => {
    setSelected(prev => prev?.id === node.id ? null : node);
  }, []);

  if (loading && !topology.nodes.length) {
    return <div className="content"><div className="spinner" style={{ margin: '3rem auto', display: 'block' }} /></div>;
  }

  return (
    <div className="content" style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: '1.5rem' }}>
      <div className="page-header">
        <div>
          <h1 className="page-title">Network Topology</h1>
          <div className="page-sub">Force-directed graph · click a node to inspect</div>
        </div>
      </div>

      {error && <div className="card" style={{ marginBottom: '1rem', borderColor: 'var(--danger)', color: 'var(--danger)' }}>{error}</div>}

      <div className="topo-layout">
        {/* Graph */}
        <div className="topo-graph" ref={containerRef}>
          {topology.nodes.length === 0 ? (
            <div className="empty-state">
              <div style={{ fontWeight: 600 }}>No nodes yet</div>
              <div style={{ fontSize: '0.85rem' }}>Approve join requests to add nodes to the graph.</div>
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
                ctx.arc(node.x, node.y, 24, 0, 2 * Math.PI);
                ctx.fill();
              }}
              nodeLabel={node => `${node.name} · ${node.vpn_ip}`}
              onNodeClick={handleNodeClick}
              onBackgroundClick={() => setSelected(null)}
              linkColor={link => link.status === 'ACTIVE' ? '#3fb950' : '#373e47'}
              linkWidth={link => link.status === 'ACTIVE' ? 2 : 1}
              linkDirectionalParticles={link => link.status === 'ACTIVE' ? 4 : 0}
              linkDirectionalParticleSpeed={0.004}
              linkDirectionalParticleColor={() => '#3fb950'}
              linkDirectionalParticleWidth={2}
              cooldownTicks={120}
              enableNodeDrag
              enableZoomInteraction
              enablePanInteraction
            />
          )}

          {/* Zoom controls */}
          <div className="zoom-controls">
            <button className="btn btn--ghost btn--sm" onClick={() => graphRef.current?.zoom(1.4, 400)} title="Zoom in">
              <ZoomIn size={14} />
            </button>
            <button className="btn btn--ghost btn--sm" onClick={() => graphRef.current?.zoom(0.7, 400)} title="Zoom out">
              <ZoomOut size={14} />
            </button>
            <button className="btn btn--ghost btn--sm" onClick={() => graphRef.current?.zoomToFit(400)} title="Fit all">
              <Maximize2 size={14} />
            </button>
          </div>
        </div>

        {/* Side panel */}
        <div className="topo-panel">
          {/* Legend */}
          <div className="topo-panel-section">
            <div className="topo-panel-title">Legend</div>
            {Object.entries(STATUS_COLOR).map(([status, color]) => (
              <div key={status} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem', fontSize: '0.82rem' }}>
                <svg width={14} height={14}>
                  <circle cx={7} cy={7} r={6} fill={color + '22'} stroke={color} strokeWidth={1.5} />
                </svg>
                <span style={{ color: 'var(--text-secondary)' }}>{status}</span>
              </div>
            ))}
            <div style={{ marginTop: '0.75rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
                <svg width={28} height={6}><line x1={0} y1={3} x2={28} y2={3} stroke="#3fb950" strokeWidth={2} /></svg>
                Active connection
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <svg width={28} height={6}><line x1={0} y1={3} x2={28} y2={3} stroke="#373e47" strokeWidth={1} strokeDasharray="4 2" /></svg>
                Inactive
              </div>
            </div>
          </div>

          {/* Network stats */}
          <div className="topo-panel-section">
            <div className="topo-panel-title">Network</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', fontSize: '0.8rem' }}>
              {[
                ['Nodes', topology.nodes.length],
                ['Active', topology.nodes.filter(n => n.status === 'ACTIVE').length],
                ['Links', topology.edges.length],
                ['Active links', topology.edges.filter(e => e.status === 'ACTIVE').length],
              ].map(([label, val]) => (
                <div key={label} style={{ background: 'var(--bg-primary)', borderRadius: 6, padding: '0.5rem 0.6rem', border: '1px solid var(--border)' }}>
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.68rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
                  <div style={{ fontWeight: 700, fontSize: '1.1rem', marginTop: '0.15rem' }}>{val}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Selected node detail */}
          <div className="topo-panel-section" style={{ flex: 1 }}>
            <div className="topo-panel-title">Selected Node</div>
            {!selected ? (
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textAlign: 'center', paddingTop: '1rem' }}>
                Click a node to inspect
              </div>
            ) : (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                  <svg width={12} height={12}>
                    <circle cx={6} cy={6} r={5} fill={(STATUS_COLOR[selected.status] || '#6e7681') + '30'} stroke={STATUS_COLOR[selected.status] || '#6e7681'} strokeWidth={1.5} />
                  </svg>
                  <span style={{ fontWeight: 700, fontSize: '1rem' }}>{selected.name}</span>
                </div>
                <div style={{ fontSize: '0.8rem', display: 'flex', flexDirection: 'column', gap: '0.4rem', marginBottom: '1rem' }}>
                  {[
                    ['VPN IP', selected.vpn_ip],
                    ['Status', selected.status],
                  ].map(([k, v]) => (
                    <div key={k} style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'var(--text-muted)' }}>{k}</span>
                      <span style={{ fontWeight: 600, fontFamily: k === 'VPN IP' ? 'monospace' : undefined, color: k === 'Status' ? (STATUS_COLOR[v] || 'var(--text-primary)') : 'var(--text-primary)' }}>{v}</span>
                    </div>
                  ))}
                </div>

                {selectedDetail && (
                  <>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '0.75rem' }}>
                      <span style={{ color: 'var(--text-muted)' }}><ArrowDownLeft size={11} style={{ verticalAlign: 'middle' }} /> RX</span>
                      <span style={{ color: 'var(--info)', fontWeight: 600 }}>{fmt(selectedDetail.total_rx)}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '0.75rem' }}>
                      <span style={{ color: 'var(--text-muted)' }}><ArrowUpRight size={11} style={{ verticalAlign: 'middle' }} /> TX</span>
                      <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{fmt(selectedDetail.total_tx)}</span>
                    </div>

                    {selectedDetail.peers.length > 0 && (
                      <>
                        <div style={{ fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                          Peers ({selectedDetail.peers.length})
                        </div>
                        {selectedDetail.peers.map((p, i) => (
                          <div key={i} style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 6, padding: '0.5rem', marginBottom: '0.4rem', fontSize: '0.78rem' }}>
                            <div style={{ fontFamily: 'monospace', color: 'var(--text-secondary)', marginBottom: '0.25rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {p.allowed_ips || p.public_key?.slice(0, 20) + '…'}
                            </div>
                            <div style={{ display: 'flex', gap: '0.75rem', color: 'var(--text-muted)' }}>
                              <span><ArrowDownLeft size={9} /> {fmt(p.transfer_rx)}</span>
                              <span><ArrowUpRight size={9} /> {fmt(p.transfer_tx)}</span>
                              {p.latest_handshake_ago != null && <span><Clock size={9} /> {fmtHs(p.latest_handshake_ago)}</span>}
                            </div>
                          </div>
                        ))}
                      </>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
