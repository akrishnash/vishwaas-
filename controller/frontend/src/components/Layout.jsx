import { NavLink, Outlet } from 'react-router-dom';
import { TopBar } from './TopBar';
import { useStats } from '../context/StatsContext';
import { useToast } from '../context/ToastContext';
import {
  LayoutDashboard, Globe, Share2, Server, LogIn,
  GitMerge, Link, FileText, ShieldCheck, Download,
} from 'lucide-react';

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/network', label: 'Network Map', icon: Globe },
  { to: '/topology', label: 'Topology', icon: Share2 },
  null, // divider
  { to: '/nodes', label: 'Nodes', icon: Server },
  { to: '/connections', label: 'Connections', icon: Link },
  null,
  { to: '/join-requests', label: 'Join Requests', icon: LogIn },
  { to: '/connection-requests', label: 'Conn. Requests', icon: GitMerge },
  null,
  { to: '/logs', label: 'Audit Logs', icon: FileText },
];

export function Layout() {
  const { stats, refreshStats } = useStats();
  const { addToast } = useToast();

  const handleBackup = async () => {
    try {
      const BASE = '/api';
      const token = localStorage.getItem('vw_token');
      const res = await fetch(`${BASE}/backup`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(res.statusText);
      const blob = await res.blob();
      const disposition = res.headers.get('content-disposition') || '';
      const match = disposition.match(/filename="?([^"]+)"?/);
      const filename = match ? match[1] : 'vishwaas-backup.db';
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      addToast(e.message || 'Backup download failed', 'error');
    }
  };

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-icon">
            <ShieldCheck size={16} color="var(--accent)" />
          </div>
          <div>
            <div className="sidebar-brand-name">VISHWAAS</div>
            <div className="sidebar-brand-sub">Control Plane</div>
          </div>
        </div>
        <nav>
          {NAV.map((item, i) => {
            if (!item) return <div key={i} style={{ height: 1, background: 'var(--border)', margin: '0.4rem 1.25rem' }} />;
            const Icon = item.icon;
            return (
              <NavLink key={item.to} to={item.to} end={item.end}>
                <Icon size={15} />
                {item.label}
              </NavLink>
            );
          })}
        </nav>
        <div className="sidebar-footer" style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
          <button
            type="button"
            onClick={handleBackup}
            style={{
              display: 'flex', alignItems: 'center', gap: '0.4rem',
              background: 'none', border: '1px solid var(--border)',
              color: 'var(--text-muted)', borderRadius: 'var(--radius-sm)',
              padding: '0.3rem 0.6rem', cursor: 'pointer', fontSize: '0.75rem',
              fontFamily: 'var(--font)', width: '100%', justifyContent: 'center',
            }}
          >
            <Download size={12} /> Download Backup
          </button>
          <span>v1.0 · WireGuard VPN</span>
        </div>
      </aside>
      <main className="main">
        <TopBar unreadCount={stats?.unread_notifications ?? 0} onRefresh={refreshStats} />
        <Outlet />
      </main>
    </div>
  );
}
