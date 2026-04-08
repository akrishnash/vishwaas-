import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { LogOut } from 'lucide-react';
import { useToast } from '../context/ToastContext';
import { useAuth } from '../context/AuthContext';
import { api } from '../api/client';

export function TopBar({ unreadCount = 0, onRefresh }) {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const { addToast } = useToast();

  const loadNotifications = async () => {
    try {
      const list = await api.getNotifications();
      setNotifications(list);
    } catch (e) {
      addToast(e.message || 'Failed to load notifications', 'error');
    }
  };

  const openPanel = () => {
    setOpen(true);
    loadNotifications();
  };

  const markRead = async (id) => {
    try {
      await api.markNotificationRead(id);
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
      if (onRefresh) onRefresh();
    } catch (e) {
      addToast(e.message || 'Failed to mark read', 'error');
    }
  };

  return (
    <header className="topbar">
      <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
        Control Plane
      </span>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        {onRefresh && (
          <button type="button" className="btn btn--ghost" onClick={onRefresh}>
            Refresh
          </button>
        )}
        <button
          type="button"
          className="btn btn--ghost"
          onClick={() => { logout(); navigate('/login', { replace: true }); }}
          title="Sign out"
          style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}
        >
          <LogOut size={14} />
          Logout
        </button>
        <div style={{ position: 'relative' }}>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={openPanel}
            aria-label="Notifications"
          >
            🔔
            {unreadCount > 0 && (
              <span
                style={{
                  position: 'absolute',
                  top: 2,
                  right: 2,
                  background: 'var(--danger)',
                  color: '#fff',
                  fontSize: '0.7rem',
                  minWidth: '18px',
                  height: '18px',
                  borderRadius: '999px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </button>
          {open && (
            <>
              <div
                style={{
                  position: 'fixed',
                  inset: 0,
                  zIndex: 999,
                }}
                onClick={() => setOpen(false)}
                aria-hidden
              />
              <div
                style={{
                  position: 'absolute',
                  top: '100%',
                  right: 0,
                  marginTop: '0.25rem',
                  width: '320px',
                  maxHeight: '400px',
                  overflow: 'auto',
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  boxShadow: 'var(--shadow-lg)',
                  zIndex: 1000,
                }}
              >
                <div style={{ padding: '0.75rem 1rem', borderBottom: '1px solid var(--border)', fontWeight: 600 }}>
                  Notifications
                </div>
                {notifications.length === 0 ? (
                  <div style={{ padding: '1rem', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
                    No notifications
                  </div>
                ) : (
                  notifications.map((n) => (
                    <div
                      key={n.id}
                      style={{
                        padding: '0.75rem 1rem',
                        borderBottom: '1px solid var(--border)',
                        background: n.is_read ? 'transparent' : 'rgba(63, 185, 80, 0.06)',
                        cursor: n.is_read ? 'default' : 'pointer',
                      }}
                      onClick={() => !n.is_read && markRead(n.id)}
                    >
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
                        {n.type}
                      </div>
                      <div style={{ fontSize: '0.875rem' }}>{n.message}</div>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
