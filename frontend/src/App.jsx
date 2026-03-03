import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ToastProvider, useToast } from './context/ToastContext';
import { StatsProvider } from './context/StatsContext';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Layout } from './components/Layout';
import { Overview } from './pages/Overview';
import { Topology } from './pages/Topology';
import { Nodes } from './pages/Nodes';
import { NodeDetail } from './pages/NodeDetail';
import { JoinRequests } from './pages/JoinRequests';
import { ConnectionRequests } from './pages/ConnectionRequests';
import { Connections } from './pages/Connections';
import { Logs } from './pages/Logs';

function ToastList() {
  const { toasts } = useToast();
  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast--${t.type}`}>
          {t.message}
        </div>
      ))}
    </div>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="topology" element={<Topology />} />
        <Route path="nodes" element={<Nodes />} />
        <Route path="nodes/:id" element={<NodeDetail />} />
        <Route path="join-requests" element={<JoinRequests />} />
        <Route path="connection-requests" element={<ConnectionRequests />} />
        <Route path="connections" element={<Connections />} />
        <Route path="logs" element={<Logs />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <StatsProvider>
          <BrowserRouter>
            <AppRoutes />
            <ToastList />
          </BrowserRouter>
        </StatsProvider>
      </ToastProvider>
    </ErrorBoundary>
  );
}
