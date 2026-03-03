import { useEffect, useRef, useCallback } from 'react';

/**
 * Call a fetch function every intervalMs.
 * Used for dashboard auto-refresh (e.g. every 5 seconds).
 */
export function usePolling(fetchFn, intervalMs = 5000, enabled = true) {
  const savedFn = useRef(fetchFn);
  const intervalRef = useRef(null);

  useEffect(() => {
    savedFn.current = fetchFn;
  }, [fetchFn]);

  const tick = useCallback(() => {
    savedFn.current?.();
  }, []);

  useEffect(() => {
    if (!enabled || intervalMs <= 0) return;
    tick();
    intervalRef.current = setInterval(tick, intervalMs);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [enabled, intervalMs, tick]);

  return tick;
}
