import React, { createContext, useContext, useState, useCallback } from 'react';
import { usePolling } from '../hooks/usePolling';
import { api } from '../api/client';

const StatsContext = createContext(null);

export function StatsProvider({ children }) {
  const [stats, setStats] = useState(null);

  const fetchStats = useCallback(async () => {
    try {
      const data = await api.getStats();
      setStats(data);
    } catch (_) {
      // Silent fail for global poll
    }
  }, []);

  usePolling(fetchStats, 5000);

  return (
    <StatsContext.Provider value={{ stats, refreshStats: fetchStats }}>
      {children}
    </StatsContext.Provider>
  );
}

export function useStats() {
  const ctx = useContext(StatsContext);
  return ctx;
}
