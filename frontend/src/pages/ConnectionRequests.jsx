import React, { useState, useCallback } from 'react';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { useToast } from '../context/ToastContext';
import { useStats } from '../context/StatsContext';

function formatDate(d) {
  return d ? new Date(d).toLocaleString() : '—';
}

export function ConnectionRequests() {
  const [list, setList] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(null);
  const { addToast } = useToast();
  const { refreshStats } = useStats();

  const fetch = useCallback(async () => {
    try {
      const [requests, statsData] = await Promise.all([
        api.getConnectionRequests(),
        api.getStats(),
      ]);
      setList(requests);
      setStats(statsData);
    } catch (e) {
      addToast(e.message || 'Failed to load connection requests', 'error');
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  usePolling(fetch, 5000);

  const approve = async (id) => {
    setActing(id);
    try {
      await api.approveConnection(id);
      addToast('Connection approved');
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
      await api.rejectConnection(id);
      addToast('Connection rejected');
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
        <h1 style={{ margin: '0 0 1.5rem 0', fontSize: '1.5rem' }}>Connection Requests</h1>
        {loading && !list.length ? (
          <div className="spinner" style={{ margin: '2rem auto', display: 'block' }} />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>From</th>
                  <th>To</th>
                  <th>Requested At</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {list.map((r) => (
                  <tr key={r.id}>
                    <td>{r.requester_name ?? r.requester_id}</td>
                    <td>{r.target_name ?? r.target_id}</td>
                    <td>{formatDate(r.requested_at)}</td>
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
