import React, { useState, useCallback } from 'react';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { useToast } from '../context/ToastContext';
import { useStats } from '../context/StatsContext';

function formatDate(d) {
  return d ? new Date(d).toLocaleString() : '—';
}

export function JoinRequests() {
  const [list, setList] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(null);
  const { addToast } = useToast();
  const { refreshStats } = useStats();

  const fetch = useCallback(async () => {
    try {
      const [requests, statsData] = await Promise.all([
        api.getJoinRequests(),
        api.getStats(),
      ]);
      setList(requests);
      setStats(statsData);
    } catch (e) {
      addToast(e.message || 'Failed to load join requests', 'error');
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  usePolling(fetch, 5000);

  const approve = async (id) => {
    setActing(id);
    try {
      await api.approveJoin(id);
      addToast('Join request approved');
      fetch();
      refreshStats?.();
    } catch (e) {
      addToast(e.message || 'Failed to approve', 'error');
    } finally {
      setActing(null);
    }
  };

  const reject = async (id) => {
    setActing(id);
    try {
      await api.rejectJoin(id);
      addToast('Join request rejected');
      fetch();
      refreshStats?.();
    } catch (e) {
      addToast(e.message || 'Failed to reject', 'error');
    } finally {
      setActing(null);
    }
  };

  return (
    <>
      <div className="content">
        <h1 style={{ margin: '0 0 1.5rem 0', fontSize: '1.5rem' }}>Join Requests</h1>
        {loading && !list.length ? (
          <div className="spinner" style={{ margin: '2rem auto', display: 'block' }} />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Node Name</th>
                  <th>Requested At</th>
                  <th>Agent URL</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {list.map((r) => (
                  <tr key={r.id}>
                    <td>{r.node_name}</td>
                    <td>{formatDate(r.requested_at)}</td>
                    <td style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {r.agent_url}
                    </td>
                    <td><StatusBadge status={r.status} /></td>
                    <td>
                      {r.status === 'PENDING' ? (
                        <>
                          <button
                            type="button"
                            className="btn btn--approve"
                            disabled={acting !== null}
                            onClick={() => approve(r.id)}
                          >
                            Approve
                          </button>
                          <button
                            type="button"
                            className="btn btn--reject"
                            disabled={acting !== null}
                            onClick={() => reject(r.id)}
                          >
                            Reject
                          </button>
                        </>
                      ) : (
                        '—'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
