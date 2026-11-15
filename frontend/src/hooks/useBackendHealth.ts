import { useState, useEffect, useCallback } from 'react';
import { api, HealthResponse } from '../lib/api';

export type HealthStatus = 'nominal' | 'degraded' | 'offline' | 'checking';

export interface BackendHealthState {
  status: HealthStatus;
  latencyMs: number | null;
  lastChecked: Date | null;
  data: HealthResponse | null;
  error: string | null;
  checkHealth: () => Promise<void>;
}

export function useBackendHealth(pollIntervalMs: number = 30000): BackendHealthState {
  const [status, setStatus] = useState<HealthStatus>('checking');
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [data, setData] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const checkHealth = useCallback(async () => {
    const start = performance.now();
    try {
      const res = await api.getHealth();
      const elapsed = Math.round(performance.now() - start);
      setLatencyMs(elapsed);
      setData(res);

      // Probe database readiness
      try {
        await api.getReady();
        setStatus('nominal');
        setError(null);
      } catch (readyErr: any) {
        setStatus('degraded');
        setError(`Database or subsystem unready: ${readyErr?.message || 'Degraded'}`);
      }

      setLastChecked(new Date());
    } catch (err: any) {
      const elapsed = Math.round(performance.now() - start);
      setLatencyMs(elapsed);
      setStatus('offline');
      setError(err?.message || 'Backend connection failed');
      setLastChecked(new Date());
    }
  }, []);

  useEffect(() => {
    checkHealth();
    if (pollIntervalMs > 0) {
      const interval = setInterval(checkHealth, pollIntervalMs);
      return () => clearInterval(interval);
    }
  }, [checkHealth, pollIntervalMs]);

  return {
    status,
    latencyMs,
    lastChecked,
    data,
    error,
    checkHealth,
  };
}
