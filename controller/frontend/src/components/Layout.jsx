import { NavLink, Outlet } from 'react-router-dom';
import { TopBar } from './TopBar';
import { useStats } from '../context/StatsContext';
import {
  LayoutDashboard, Globe, Share2, Server, LogIn,
  GitMerge, Link, FileText, ShieldCheck,
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
        <div className="sidebar-footer">v1.0 · WireGuard VPN</div>
      </aside>
      <main className="main">
        <TopBar unreadCount={stats?.unread_notifications ?? 0} onRefresh={refreshStats} />
        <Outlet />
      </main>
    </div>
  );
}
