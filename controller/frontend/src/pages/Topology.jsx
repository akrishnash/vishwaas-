import { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';
import {
  ArrowDownLeft, ArrowUpRight, Clock, Server,
  RefreshCw, Wifi, WifiOff,
} from 'lucide-react';

const STATUS_COLOR = {
  ACTIVE:   '#3fb950',
  APPROVED: '#58a6ff',
  PENDING:  '#d29922',
  OFFLINE:  '#6e7681',
};

const W = 820, H = 500;
const CX = W / 2, CY = H / 2;
const NR = 38;

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

function circlePos(n, cx, cy, r) {
  if (n === 0) return [];
  if (n === 1) return [{ x: cx, y: cy }];
  return Array.from({ length: n }, (_, i) => ({
    x: cx + r * Math.cos((i / n) * 2 * Math.PI - Math.PI / 2),
    y: cy + r * Math.sin((i / n) * 2 * Math.PI - Math.PI / 2),
  }));
}

function buildPositions(nodes) {
  const hubs = nodes.filter(n => n.is_gateway);
  const spokes = nodes.filter(n => !n.is_gateway);
  const hasHub = hubs.length > 0;
  const R = hasHub
    ? Math.min(CX, CY) * (spokes.length <= 4 ? 0.52 : 0.60)
    : Math.min(CX, CY) * (nodes.length <= 1 ? 0 : nodes.length <= 4 ? 0.50 : 0.58);

  if (hasHub) {
    const sp = circlePos(spokes.length, CX, CY, R);
    return [
      ...hubs.map((n, i) => ({ id: n.id, x: CX + (i - (hubs.length - 1) / 2) * 80, y: CY })),
      ...spokes.map((n, i) => ({ id: n.id, ...sp[i] })),
    ];
  }
  const pos = circlePos(nodes.length, CX, CY, R);
  return nodes.map((n, i) => ({ id: n.id, ...pos[i] }));
}

// Nodes that can be connected to (ACTIVE or APPROVED)
const CONNECTABLE = new Set(['ACTIVE', 'APPROVED']);

function TopoCanvas({ nodes, edges, detailed, selected, hovered, onSelect, onHover, onConnect }) {
  const svgRef = useRef(null);
  const dragRef = useRef(null);       // node body drag
  const wasDragged = useRef(false);
  const wireRef = useRef(null);       // wire-draw drag: { fromId }

  const nodeIds = nodes.map(n => n.id).sort().join(',');
  const [positions, setPositions] = useState(() => buildPositions(nodes));
  const [drawPos, setDrawPos] = useState(null);       // cursor pos while drawing wire
  const [wireTarget, setWireTarget] = useState(null); // hovered target node id during wire draw

  useEffect(() => {
    setPositions(prev => {
      const existingIds = new Set(prev.map(p => p.id));
      const incomingIds = new Set(nodes.map(n => n.id));
      const removed = prev.filter(p => !incomingIds.has(p.id));
      const added = nodes.filter(n => !existingIds.has(n.id));
      if (!removed.length && !added.length) return prev;
      return buildPositions(nodes);
    });
  }, [nodeIds]); // eslint-disable-line

  const posMap = useMemo(
    () => Object.fromEntries(positions.map(p => [p.id, p])),
    [positions],
  );

  // Already-connected pairs (to avoid showing handle to already-connected nodes)
  const connectedPairs = useMemo(() => {
    const s = new Set();
    edges.filter(e => e.status === 'ACTIVE').forEach(e => {
      s.add(`${e.source_id}-${e.target_id}`);
      s.add(`${e.target_id}-${e.source_id}`);
    });
    return s;
  }, [edges]);

  function svgPt(e) {
    const r = svgRef.current.getBoundingClientRect();
    return {
      x: ((e.clientX - r.left) / r.width) * W,
      y: ((e.clientY - r.top) / r.height) * H,
    };
  }

  // ── Node body drag ─────────────────────────────────────
  function onNodeDown(e, id) {
    e.stopPropagation();
    if (wireRef.current) return; // wire draw in progress
    wasDragged.current = false;
    const { x, y } = svgPt(e);
    const pos = posMap[id];
    dragRef.current = { id, ox: x - pos.x, oy: y - pos.y };
  }

  // ── Wire (connect) drag ────────────────────────────────
  function onHandleDown(e, id) {
    e.stopPropagation();
    e.preventDefault();
    wireRef.current = { fromId: id };
    const pos = posMap[id];
    setDrawPos({ x: pos.x, y: pos.y });
    setWireTarget(null);
  }

  function onSvgMove(e) {
    const { x, y } = svgPt(e);

    // Wire drawing
    if (wireRef.current) {
      setDrawPos({ x, y });
      // Snap to nearby connectable node
      const fromId = wireRef.current.fromId;
      let snap = null;
      for (const n of nodes) {
        if (n.id === fromId || !CONNECTABLE.has(n.status)) continue;
        if (connectedPairs.has(`${fromId}-${n.id}`)) continue;
        const pos = posMap[n.id];
        if (!pos) continue;
        const dist = Math.hypot(x - pos.x, y - pos.y);
        if (dist < NR + 24) { snap = n.id; break; }
      }
      setWireTarget(snap);
      return;
    }

    // Node drag
    if (!dragRef.current) return;
    wasDragged.current = true;
    const { id, ox, oy } = dragRef.current;
    const nx = Math.max(NR + 6, Math.min(W - NR - 6, x - ox));
    const ny = Math.max(NR + 6, Math.min(H - NR - 6, y - oy));
    setPositions(prev => prev.map(p => p.id === id ? { ...p, x: nx, y: ny } : p));
  }

  function onSvgUp() {
    if (wireRef.current) {
      if (wireTarget) onConnect(wireRef.current.fromId, wireTarget);
      wireRef.current = null;
      setDrawPos(null);
      setWireTarget(null);
    }
    dragRef.current = null;
  }

  function onNodeClick(n) {
    if (wireRef.current) return;
    if (wasDragged.current) { wasDragged.current = false; return; }
    onSelect(n);
  }

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${W} ${H}`}
      style={{ width: '100%', height: '100%', display: 'block', cursor: 'default' }}
      onMouseMove={onSvgMove}
      onMouseUp={onSvgUp}
      onMouseLeave={onSvgUp}
    >
      <defs>
        <style>{`
          @keyframes dash-flow { to { stroke-dashoffset: -24; } }
          @keyframes topo-spin { to { stroke-dashoffset: -20; } }
          @keyframes wire-flow { to { stroke-dashoffset: -18; } }
          .lk-active { animation: dash-flow 1.3s linear infinite; }
          .hub-orbit { animation: topo-spin 4s linear infinite; }
          .wire-drawing { animation: wire-flow 0.6s linear infinite; }
        `}</style>

        <pattern id="topo-grid" width="40" height="40" patternUnits="userSpaceOnUse">
          <path d="M40 0L0 0 0 40" fill="none" stroke="rgba(255,255,255,0.028)" strokeWidth="0.6"/>
        </pattern>
        <radialGradient id="topo-bg" cx="50%" cy="50%" r="55%">
          <stop offset="0%" stopColor="rgba(63,185,80,0.03)"/>
          <stop offset="100%" stopColor="rgba(0,0,0,0)"/>
        </radialGradient>

        {nodes.map(n => {
          const c = STATUS_COLOR[n.status] || '#6e7681';
          return (
            <radialGradient key={n.id} id={`ng-${n.id}`} cx="36%" cy="30%" r="70%">
              <stop offset="0%" stopColor={c} stopOpacity={0.42}/>
              <stop offset="100%" stopColor={c} stopOpacity={0.05}/>
            </radialGradient>
          );
        })}

        <filter id="glow-md" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="4" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="glow-sm" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="2.5" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>

      <rect width={W} height={H} fill="url(#topo-grid)"/>
      <rect width={W} height={H} fill="url(#topo-bg)"/>

      {/* Edges */}
      {edges.map(e => {
        const src = posMap[e.source_id], tgt = posMap[e.target_id];
        if (!src || !tgt) return null;
        const active = e.status === 'ACTIVE';
        const mx = (src.x + tgt.x) / 2, my = (src.y + tgt.y) / 2;
        const dx = tgt.x - src.x, dy = tgt.y - src.y;
        const len = Math.sqrt(dx * dx + dy * dy) || 1;
        const px = (-dy / len) * 16, py = (dx / len) * 16;

        const srcDet = detailed?.find(d => d.node_id === e.source_id);
        const tgtNode = nodes.find(n => n.id === e.target_id);
        const peer = srcDet?.peers?.find(p =>
          tgtNode?.vpn_ip && p.allowed_ips?.startsWith(tgtNode.vpn_ip.split('/')[0])
        );
        const hasBw = peer && (peer.transfer_rx > 0 || peer.transfer_tx > 0);

        return (
          <g key={e.id}>
            {active && (
              <line x1={src.x} y1={src.y} x2={tgt.x} y2={tgt.y}
                stroke="#3fb950" strokeWidth={16} strokeOpacity={0.055}/>
            )}
            <line
              x1={src.x} y1={src.y} x2={tgt.x} y2={tgt.y}
              stroke={active ? '#3fb950' : '#374151'}
              strokeWidth={active ? 2.5 : 1.5}
              strokeDasharray={active ? '10 6' : '6 7'}
              strokeOpacity={active ? 1 : 0.45}
              className={active ? 'lk-active' : ''}
            />
            {hasBw ? (
              <g transform={`translate(${mx + px},${my + py})`}>
                <rect x={-30} y={-16} width={60} height={30} rx={5}
                  fill="rgba(13,15,18,0.92)" stroke="rgba(55,62,71,0.9)" strokeWidth={1}/>
                <text x={0} y={-3} textAnchor="middle" fill="rgba(88,166,255,0.9)"
                  fontSize={8.5} fontFamily="monospace">↓ {fmt(peer.transfer_rx)}</text>
                <text x={0} y={10} textAnchor="middle" fill="rgba(63,185,80,0.9)"
                  fontSize={8.5} fontFamily="monospace">↑ {fmt(peer.transfer_tx)}</text>
              </g>
            ) : active ? (
              <g transform={`translate(${mx},${my})`}>
                <rect x={-24} y={-10} width={48} height={19} rx={5}
                  fill="rgba(13,15,18,0.9)" stroke="rgba(63,185,80,0.4)" strokeWidth={1}/>
                <text textAnchor="middle" y={4} fill="#3fb950"
                  fontSize={9} fontWeight={700} fontFamily="system-ui" letterSpacing="0.05em">
                  ACTIVE
                </text>
              </g>
            ) : null}
          </g>
        );
      })}

      {/* Wire being drawn */}
      {wireRef.current && drawPos && (() => {
        const from = posMap[wireRef.current.fromId];
        if (!from) return null;
        const tx = wireTarget ? (posMap[wireTarget]?.x ?? drawPos.x) : drawPos.x;
        const ty = wireTarget ? (posMap[wireTarget]?.y ?? drawPos.y) : drawPos.y;
        return (
          <g>
            <line x1={from.x} y1={from.y} x2={tx} y2={ty}
              stroke="#3fb950" strokeWidth={14} strokeOpacity={0.07}/>
            <line x1={from.x} y1={from.y} x2={tx} y2={ty}
              stroke="#3fb950" strokeWidth={2.5}
              strokeDasharray="8 5" className="wire-drawing" strokeOpacity={0.9}/>
            <circle cx={tx} cy={ty} r={5}
              fill="#3fb950" fillOpacity={0.85} stroke="rgba(13,15,18,0.8)" strokeWidth={1.5}/>
          </g>
        );
      })()}

      {/* Nodes */}
      {nodes.map(n => {
        const pos = posMap[n.id];
        if (!pos) return null;
        const color = STATUS_COLOR[n.status] || '#6e7681';
        const sel = selected?.id === n.id;
        const hov = hovered === n.id;
        const isActive = n.status === 'ACTIVE';
        const isHub = n.is_gateway;
        const r = isHub ? NR + 8 : NR;
        const connCount = edges.filter(e =>
          (e.source_id === n.id || e.target_id === n.id) && e.status === 'ACTIVE'
        ).length;
        const isDrawingFrom = wireRef.current?.fromId === n.id;
        const isWireTarget = wireTarget === n.id;
        const canBeTarget = wireRef.current && CONNECTABLE.has(n.status)
          && !isDrawingFrom
          && !connectedPairs.has(`${wireRef.current.fromId}-${n.id}`);
        const showHandle = hov && !wireRef.current && CONNECTABLE.has(n.status);

        return (
          <g
            key={n.id}
            style={{ cursor: wireRef.current ? (canBeTarget ? 'crosshair' : 'default') : 'grab' }}
            onMouseDown={e => onNodeDown(e, n.id)}
            onMouseEnter={() => onHover(n.id)}
            onMouseLeave={() => onHover(null)}
            onClick={() => onNodeClick(n)}
          >
            {/* Active pulse ring */}
            {isActive && (
              <circle cx={pos.x} cy={pos.y} r={r + 14}
                fill="none" stroke={color} strokeWidth={1} strokeOpacity={hov ? 0.35 : 0.18}/>
            )}
            {/* Hub orbit ring */}
            {isHub && (
              <circle cx={pos.x} cy={pos.y} r={r + 22}
                fill="none" stroke="#f59e0b" strokeWidth={1.5} strokeOpacity={0.22}
                strokeDasharray="6 5" className="hub-orbit"/>
            )}
            {/* Wire-target highlight */}
            {isWireTarget && (
              <circle cx={pos.x} cy={pos.y} r={r + 14}
                fill="none" stroke="#3fb950" strokeWidth={2.5}
                strokeDasharray="6 4" className="wire-drawing"/>
            )}
            {/* Selection ring */}
            {sel && !isWireTarget && (
              <circle cx={pos.x} cy={pos.y} r={r + 10}
                fill="none" stroke="rgba(255,255,255,0.5)" strokeWidth={2}
                strokeDasharray="5 3"/>
            )}
            {/* Hover ring */}
            {hov && !sel && !isWireTarget && (
              <circle cx={pos.x} cy={pos.y} r={r + 8}
                fill="none" stroke="rgba(255,255,255,0.18)" strokeWidth={1.5}/>
            )}
            {/* Node body */}
            <circle cx={pos.x} cy={pos.y} r={r}
              fill={`url(#ng-${n.id})`}
              stroke={isWireTarget ? '#3fb950' : sel ? 'rgba(255,255,255,0.75)' : hov ? 'rgba(255,255,255,0.45)' : color}
              strokeWidth={isWireTarget ? 3 : sel ? 3 : hov ? 2.5 : 2}
              filter={isActive ? 'url(#glow-sm)' : undefined}
            />
            {/* Status dot (top-right) */}
            <circle cx={pos.x + r * 0.7} cy={pos.y - r * 0.7} r={7}
              fill={color} stroke="rgba(13,15,18,0.9)" strokeWidth={2}
              filter={isActive ? 'url(#glow-md)' : undefined}
            />
            {/* Connection count badge (bottom-right) */}
            {connCount > 0 && (
              <g>
                <circle cx={pos.x + r * 0.68} cy={pos.y + r * 0.68} r={8}
                  fill="rgba(13,15,18,0.92)" stroke={color} strokeWidth={1.5}/>
                <text x={pos.x + r * 0.68} y={pos.y + r * 0.68 + 4}
                  textAnchor="middle" fill={color} fontSize={9} fontWeight={700}
                  fontFamily="system-ui" pointerEvents="none">
                  {connCount}
                </text>
              </g>
            )}
            {/* Hub label above */}
            {isHub && (
              <text x={pos.x} y={pos.y - r - 12} textAnchor="middle"
                fill="#f59e0b" fontSize={8.5} fontWeight={800}
                fontFamily="system-ui" letterSpacing="0.1em" pointerEvents="none">
                HUB
              </text>
            )}
            {/* Node name */}
            <text x={pos.x} y={pos.y + 4} textAnchor="middle" dominantBaseline="middle"
              fill="#e6edf3" fontSize={isHub ? 12 : 11} fontWeight={700}
              fontFamily="DM Sans, system-ui" pointerEvents="none">
              {n.name.length > 11 ? n.name.slice(0, 10) + '…' : n.name}
            </text>
            {/* VPN IP below */}
            {n.vpn_ip && (
              <text x={pos.x} y={pos.y + r + 20} textAnchor="middle"
                fill="rgba(255,255,255,0.42)" fontSize={9.5} fontFamily="monospace" pointerEvents="none">
                {n.vpn_ip}
              </text>
            )}
            {/* ⊕ Connect handle — bottom of node, visible on hover */}
            {showHandle && (
              <g style={{ cursor: 'crosshair' }}
                onMouseDown={e => onHandleDown(e, n.id)}
                onClick={e => e.stopPropagation()}>
                <circle cx={pos.x} cy={pos.y + r + 13} r={12}
                  fill="rgba(13,15,18,0.9)" stroke="#3fb950" strokeWidth={2}/>
                <line x1={pos.x - 5} y1={pos.y + r + 13} x2={pos.x + 5} y2={pos.y + r + 13}
                  stroke="#3fb950" strokeWidth={2.5} strokeLinecap="round"/>
                <line x1={pos.x} y1={pos.y + r + 8} x2={pos.x} y2={pos.y + r + 18}
                  stroke="#3fb950" strokeWidth={2.5} strokeLinecap="round"/>
              </g>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function DetailPanel({ node, detail, allNodes, allEdges, selected, onSelect }) {
  const color = node ? (STATUS_COLOR[node.status] || '#6e7681') : null;
  const connectedTo = node
    ? allEdges
        .filter(e => e.status === 'ACTIVE' && (e.source_id === node.id || e.target_id === node.id))
        .map(e => {
          const peerId = e.source_id === node.id ? e.target_id : e.source_id;
          return allNodes.find(n => n.id === peerId);
        })
        .filter(Boolean)
    : [];

  return (
    <div style={{
      width: 282, flexShrink: 0, background: 'var(--bg-secondary)',
      border: '1px solid var(--border)', borderRadius: '0 8px 8px 0',
      overflowY: 'auto', display: 'flex', flexDirection: 'column',
    }}>
      {/* Node detail */}
      <div style={{ padding: '1rem', borderBottom: '1px solid var(--border)' }}>
        <div style={{
          fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: '0.1em', color: 'var(--text-muted)', marginBottom: '0.75rem',
        }}>
          Node Detail
        </div>
        {!node ? (
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Server size={14}/> Click a node to inspect
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.9rem' }}>
              <div style={{
                width: 10, height: 10, borderRadius: '50%', background: color,
                boxShadow: node.status === 'ACTIVE' ? `0 0 8px ${color}` : 'none',
                flexShrink: 0,
              }}/>
              <span style={{ fontWeight: 700, fontSize: '1rem', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {node.name}
              </span>
              {node.is_gateway && (
                <span style={{
                  background: 'rgba(245,158,11,0.15)', color: '#f59e0b',
                  border: '1px solid rgba(245,158,11,0.35)', padding: '1px 6px',
                  borderRadius: 6, fontSize: '0.62rem', fontWeight: 800,
                }}>HUB</span>
              )}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.8rem' }}>
              {[
                ['VPN IP', <span style={{ fontFamily: 'monospace', color: 'var(--info)', fontWeight: 600 }}>{node.vpn_ip || '—'}</span>],
                ['Status', <span style={{ color, fontWeight: 700 }}>{node.status}</span>],
                ...(detail ? [
                  ['Reachable', (
                    <span style={{ color: detail.reachable ? 'var(--accent)' : 'var(--danger)', fontWeight: 600 }}>
                      {detail.reachable ? 'Yes' : 'No'}
                    </span>
                  )],
                  ['RX', <span style={{ color: 'var(--info)', fontWeight: 600 }}>{fmt(detail.total_rx)}</span>],
                  ['TX', <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{fmt(detail.total_tx)}</span>],
                ] : []),
              ].map(([lbl, val]) => (
                <div key={lbl} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: 'var(--text-muted)' }}>{lbl}</span>
                  {val}
                </div>
              ))}
            </div>

            {/* Connected to */}
            {connectedTo.length > 0 && (
              <div style={{ marginTop: '0.9rem' }}>
                <div style={{ fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                  Connected to
                </div>
                {connectedTo.map(peer => (
                  <div key={peer.id} onClick={() => onSelect(peer)} style={{
                    display: 'flex', alignItems: 'center', gap: '0.4rem',
                    padding: '0.35rem 0.5rem', borderRadius: 5, cursor: 'pointer',
                    background: 'rgba(63,185,80,0.06)', border: '1px solid rgba(63,185,80,0.2)',
                    marginBottom: '0.3rem', fontSize: '0.8rem',
                    transition: 'background 0.15s',
                  }}>
                    <Wifi size={11} color={STATUS_COLOR[peer.status] || '#6e7681'}/>
                    <span style={{ fontWeight: 600, flex: 1 }}>{peer.name}</span>
                    <span style={{ fontFamily: 'monospace', fontSize: '0.72rem', color: 'var(--text-muted)' }}>{peer.vpn_ip}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* WireGuard peers */}
      {detail?.peers?.length > 0 && (
        <div style={{ padding: '1rem', borderBottom: '1px solid var(--border)' }}>
          <div style={{ fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-muted)', marginBottom: '0.65rem' }}>
            WireGuard Peers ({detail.peers.length})
          </div>
          {detail.peers.map((p, i) => (
            <div key={i} style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 6, padding: '0.55rem 0.7rem', marginBottom: '0.4rem', fontSize: '0.78rem',
            }}>
              <div style={{ fontFamily: 'monospace', color: 'var(--accent)', marginBottom: '0.3rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {p.allowed_ips || '—'}
              </div>
              <div style={{ display: 'flex', gap: '0.6rem', color: 'var(--text-muted)', flexWrap: 'wrap' }}>
                <span style={{ color: 'var(--info)' }}><ArrowDownLeft size={9}/> {fmt(p.transfer_rx)}</span>
                <span style={{ color: 'var(--accent)' }}><ArrowUpRight size={9}/> {fmt(p.transfer_tx)}</span>
                {p.latest_handshake_ago != null && (
                  <span><Clock size={9}/> {fmtHs(p.latest_handshake_ago)}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* All nodes list */}
      <div style={{ padding: '1rem' }}>
        <div style={{ fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-muted)', marginBottom: '0.6rem' }}>
          All Nodes
        </div>
        {allNodes.map(n => {
          const c = STATUS_COLOR[n.status] || '#6e7681';
          const isSel = selected?.id === n.id;
          const isOnline = n.status === 'ACTIVE' || n.status === 'APPROVED';
          return (
            <div key={n.id} onClick={() => onSelect(n)} style={{
              display: 'flex', alignItems: 'center', gap: '0.5rem',
              padding: '0.45rem 0.55rem', borderRadius: 6, cursor: 'pointer',
              background: isSel ? 'rgba(63,185,80,0.08)' : 'transparent',
              border: `1px solid ${isSel ? 'rgba(63,185,80,0.25)' : 'transparent'}`,
              marginBottom: '0.2rem', transition: 'background 0.12s',
            }}>
              {isOnline
                ? <Wifi size={12} color={c} style={{ flexShrink: 0 }}/>
                : <WifiOff size={12} color={c} style={{ flexShrink: 0 }}/>
              }
              <span style={{ fontSize: '0.83rem', fontWeight: 600, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {n.name}
              </span>
              {n.is_gateway && (
                <span style={{ background: 'rgba(245,158,11,0.15)', color: '#f59e0b', padding: '1px 5px', borderRadius: 5, fontSize: '0.62rem', fontWeight: 700 }}>
                  HUB
                </span>
              )}
              <span style={{ fontFamily: 'monospace', fontSize: '0.7rem', color: 'var(--text-muted)', flexShrink: 0 }}>
                {n.vpn_ip}
              </span>
            </div>
          );
        })}
      </div>

      {/* Summary stats */}
      <div style={{ padding: '1rem', borderTop: '1px solid var(--border)', marginTop: 'auto' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.4rem' }}>
          {[
            ['Total', allNodes.length, 'var(--info)'],
            ['Active', allNodes.filter(n => n.status === 'ACTIVE').length, 'var(--accent)'],
            ['Offline', allNodes.filter(n => n.status === 'OFFLINE').length, 'var(--danger)'],
            ['Links', allEdges.filter(e => e.status === 'ACTIVE').length, 'var(--purple)'],
          ].map(([lbl, val, clr]) => (
            <div key={lbl} style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 6, padding: '0.45rem 0.65rem',
            }}>
              <div style={{ fontSize: '0.62rem', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted)', fontWeight: 600 }}>{lbl}</div>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: clr, marginTop: '0.1rem' }}>{val}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function Topology() {
  const [topology, setTopology] = useState({ nodes: [], edges: [] });
  const [detailed, setDetailed] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [hovered, setHovered] = useState(null);
  const [connectMsg, setConnectMsg] = useState(null); // { text, ok }

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

  const selectedDetail = useMemo(() =>
    selected && detailed?.nodes
      ? detailed.nodes.find(n => n.node_id === selected.id) ?? null
      : null,
    [selected, detailed]);

  const handleSelect = useCallback(node => {
    setSelected(prev => prev?.id === node.id ? null : node);
  }, []);

  const handleConnect = useCallback(async (fromId, toId) => {
    try {
      const cr = await api.requestConnection({ requester_id: fromId, target_id: toId });
      await api.approveConnection(cr.id);
      setConnectMsg({ text: 'Connection established!', ok: true });
      fetchData();
    } catch (e) {
      const detail = e.body?.detail || e.message || 'Failed';
      setConnectMsg({ text: `Connect failed: ${detail}`, ok: false });
    }
    setTimeout(() => setConnectMsg(null), 3500);
  }, [fetchData]);

  if (loading && !topology.nodes.length) {
    return <div className="content"><div className="spinner" style={{ margin: '3rem auto', display: 'block' }}/></div>;
  }

  const activeNodes = topology.nodes.filter(n => n.status === 'ACTIVE').length;
  const activeLinks = topology.edges.filter(e => e.status === 'ACTIVE').length;

  return (
    <div className="content" style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: '1.25rem' }}>
      {/* Header */}
      <div style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
        <div>
          <h1 className="page-title">Network Topology</h1>
          <div className="page-sub">
            {topology.nodes.length} node{topology.nodes.length !== 1 ? 's' : ''} · {activeNodes} active · {activeLinks} link{activeLinks !== 1 ? 's' : ''}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.7rem', alignItems: 'center', fontSize: '0.75rem', color: 'var(--text-muted)', flexWrap: 'wrap' }}>
          {[['ACTIVE', '#3fb950'], ['APPROVED', '#58a6ff'], ['OFFLINE', '#6e7681']].map(([s, c]) => (
            <div key={s} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              <svg width={9} height={9}><circle cx={4.5} cy={4.5} r={4} fill={c + '28'} stroke={c} strokeWidth={1.5}/></svg>
              <span style={{ fontWeight: 500 }}>{s.charAt(0) + s.slice(1).toLowerCase()}</span>
            </div>
          ))}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', marginLeft: '0.25rem', paddingLeft: '0.7rem', borderLeft: '1px solid var(--border)' }}>
            <RefreshCw size={10} style={{ animation: 'spin 3s linear infinite' }}/>
            <span>Live · 5s</span>
          </div>
        </div>
      </div>

      {error && (
        <div className="card" style={{ marginBottom: '0.75rem', borderColor: 'var(--danger)', color: 'var(--danger)', padding: '0.75rem 1rem', fontSize: '0.85rem' }}>
          {error}
        </div>
      )}

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        {/* Canvas */}
        <div style={{
          flex: 1, minWidth: 0, background: 'var(--bg-card)',
          border: '1px solid var(--border)', borderRadius: '8px 0 0 8px',
          borderRight: 'none', overflow: 'hidden', position: 'relative',
        }}>
          {topology.nodes.length === 0 ? (
            <div className="empty-state">
              <Server size={36} color="var(--text-muted)"/>
              <div style={{ fontWeight: 600, marginTop: '0.5rem', fontSize: '1rem' }}>No nodes yet</div>
              <div style={{ fontSize: '0.82rem' }}>Approve join requests to see the network.</div>
            </div>
          ) : (
            <TopoCanvas
              nodes={topology.nodes}
              edges={topology.edges}
              detailed={detailed?.nodes ?? []}
              selected={selected}
              hovered={hovered}
              onSelect={handleSelect}
              onHover={setHovered}
            />
          )}

          {topology.nodes.length > 0 && (
            <div style={{
              position: 'absolute', bottom: '0.8rem', left: '0.8rem',
              fontSize: '0.7rem', color: 'var(--text-muted)',
              background: 'rgba(13,15,18,0.78)', borderRadius: 5,
              padding: '0.3rem 0.6rem', backdropFilter: 'blur(6px)',
              border: '1px solid rgba(255,255,255,0.06)',
              display: 'flex', alignItems: 'center', gap: '0.5rem',
            }}>
              <span>Drag nodes · click to inspect</span>
            </div>
          )}

          {/* Connection count badge for no-connection state */}
          {topology.nodes.length > 0 && activeLinks === 0 && (
            <div style={{
              position: 'absolute', top: '0.8rem', left: '50%', transform: 'translateX(-50%)',
              fontSize: '0.75rem', color: 'var(--warning)',
              background: 'rgba(210,153,34,0.1)', border: '1px solid rgba(210,153,34,0.3)',
              borderRadius: 6, padding: '0.3rem 0.75rem', backdropFilter: 'blur(4px)',
            }}>
              No active connections — go to Nodes to connect
            </div>
          )}
        </div>

        <DetailPanel
          node={selected}
          detail={selectedDetail}
          allNodes={topology.nodes}
          allEdges={topology.edges}
          selected={selected}
          onSelect={handleSelect}
        />
      </div>
    </div>
  );
}
