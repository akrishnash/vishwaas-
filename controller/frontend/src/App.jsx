import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import { ToastProvider, useToast } from './context/ToastContext';
import { StatsProvider } from './context/StatsContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Layout } from './components/Layout';
import { Login } from './pages/Login';
import { Overview } from './pages/Overview';
import { Topology } from './pages/Topology';
import { NetworkMap } from './pages/NetworkMap';
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

function ProtectedRoute({ children }) {
  const { isAuth } = useAuth();
  if (!isAuth) return <Navigate to="/login" replace />;
  return children;
}

function UnauthorizedHandler() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  useEffect(() => {
    const handler = () => {
      logout();
      navigate('/login', { replace: true });
    };
    window.addEventListener('vw:unauthorized', handler);
    return () => window.removeEventListener('vw:unauthorized', handler);
  }, [logout, navigate]);
  return null;
}

function AppRoutes() {
  return (
    <>
      <UnauthorizedHandler />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Overview />} />
          <Route path="network" element={<NetworkMap />} />
          <Route path="topology" element={<Topology />} />
          <Route path="nodes" element={<Nodes />} />
          <Route path="nodes/:id" element={<NodeDetail />} />
          <Route path="join-requests" element={<JoinRequests />} />
          <Route path="connection-requests" element={<ConnectionRequests />} />
          <Route path="connections" element={<Connections />} />
          <Route path="logs" element={<Logs />} />
        </Route>
      </Routes>
    </>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <ToastProvider>
          <StatsProvider>
            <BrowserRouter>
              <AppRoutes />
              <ToastList />
            </BrowserRouter>
          </StatsProvider>
        </ToastProvider>
      </AuthProvider>
    </ErrorBoundary>
  );
}
