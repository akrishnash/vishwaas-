import React, { useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';

export function Topology() {
  const [topology, setTopology] = React.useState({ nodes: [], edges: [] });
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);

  const fetchTopology = React.useCallback(async () => {
    try {
      setError(null);
      const data = await api.getTopology();
      setTopology(data);
    } catch (e) {
      setError(e.message || 'Failed to load topology');
    } finally {
      setLoading(false);
    }
  }, []);

  usePolling(fetchTopology, 5000);

  const graphData = useMemo(
    () => ({
      nodes: topology.nodes.map((n) => ({
        id: n.id,
        name: n.name,
        label: `${n.name}\n${n.vpn_ip}`,
        status: n.status,
      })),
      links: topology.edges.map((e) => ({
        id: e.id,
        source: e.source_id,
        target: e.target_id,
        status: e.status,
      })),
    }),
    [topology],
  );

  if (loading && !topology.nodes.length) {
    return (
      <div className="content">
        <div className="spinner" style={{ margin: '2rem auto', display: 'block' }} />
      </div>
    );
  }

  return (
    <div className="content">
      <h1 style={{ margin: '0 0 1.5rem 0', fontSize: '1.5rem' }}>Network Topology</h1>
      {error && (
        <div className="card" style={{ marginBottom: '1rem', borderColor: 'var(--danger)' }}>
          {error}
        </div>
      )}
      <div className="card" style={{ height: '480px', position: 'relative' }}>
        {graphData.nodes.length === 0 ? (
          <div style={{ padding: '1rem', color: 'var(--text-muted)' }}>No nodes yet. Approve some joins and connections.</div>
        ) : (
          <ForceGraph2D
            graphData={graphData}
            nodeLabel="label"
            nodeAutoColorBy="status"
            linkColor={() => '#373e47'}
            linkWidth={1.5}
            linkDirectionalParticles={2}
            linkDirectionalParticleSpeed={0.01}
            backgroundColor="transparent"
          />
        )}
      </div>
    </div>
  );
}

