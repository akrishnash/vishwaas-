import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { TopBar } from './TopBar';
import { useStats } from '../context/StatsContext';

export function Layout() {
  const { stats, refreshStats } = useStats();
  return (
    <div className="layout">
      <aside className="sidebar">
        <div style={{ padding: '1rem 1.25rem', fontWeight: 700, fontSize: '1rem' }}>
          VISHWAAS
        </div>
        <nav>
          <NavLink to="/" end>Overview</NavLink>
          <NavLink to="/topology">Topology</NavLink>
          <NavLink to="/nodes">Nodes</NavLink>
          <NavLink to="/join-requests">Join Requests</NavLink>
          <NavLink to="/connection-requests">Connection Requests</NavLink>
          <NavLink to="/connections">Connections</NavLink>
          <NavLink to="/logs">Logs</NavLink>
        </nav>
      </aside>
      <main className="main">
        <TopBar unreadCount={stats?.unread_notifications ?? 0} onRefresh={refreshStats} />
        <Outlet />
      </main>
    </div>
  );
}
