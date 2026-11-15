import React from 'react';
import { useUtcClock } from '../../hooks/useUtcClock';
import { useBackendHealth } from '../../hooks/useBackendHealth';
import {
  Compass,
  Radio,
  Clock,
  Server,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Box,
  Users,
  ShieldAlert,
  FileText,
} from 'lucide-react';

export interface ShellProps {
  currentPath: string;
  onNavigate: (path: string) => void;
  children: React.ReactNode;
}

export const Shell: React.FC<ShellProps> = ({ currentPath, onNavigate, children }) => {
  const { isoDate, utcTime, julianDate } = useUtcClock();
  const { status, latencyMs, lastChecked, error, checkHealth } = useBackendHealth();

  return (
    <div className="min-h-screen bg-canvas text-slate-100 flex flex-col font-sans">
      {/* Primary Header */}
      <header className="bg-panel border-b border-hairline sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Brand Logo & Title */}
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-panel-raised border border-hairline rounded text-accent flex items-center justify-center">
                <Compass className="w-5 h-5 text-accent" aria-hidden="true" />
              </div>
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-bold tracking-wider text-base sm:text-lg text-white font-mono">
                    MISSION FORGE
                  </span>
                  <span className="text-[10px] font-mono uppercase bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded border border-hairline">
                    v1.0
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 hidden sm:block">
                  Aerospace Mission Design & Autonomous Simulation
                </div>
              </div>
            </div>

            {/* Live UTC Chronometer */}
            <div
              className="flex items-center space-x-2 px-3 py-1.5 bg-panel-raised border border-hairline rounded font-mono text-xs tabular-nums"
              data-testid="utc-chronometer"
              title={`Julian Date: ${julianDate}`}
            >
              <Clock className="w-4 h-4 text-slate-400" aria-hidden="true" />
              <div className="flex flex-col sm:flex-row sm:items-center sm:space-x-2 text-slate-300">
                <span className="text-slate-400">{isoDate}</span>
                <span className="text-white font-semibold">{utcTime} UTC</span>
              </div>
            </div>

            {/* Backend Health & Navigation */}
            <div className="flex items-center space-x-3">
              {/* Telemetry Freshness & Health Indicator */}
              <div
                className="flex items-center space-x-2 px-2.5 py-1 bg-panel-raised border border-hairline rounded text-xs font-mono"
                data-testid="health-indicator"
              >
                <Server className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
                {status === 'nominal' && (
                  <span className="flex items-center space-x-1.5 text-status-nominal">
                    <CheckCircle2 className="w-3 h-3" />
                    <span className="hidden md:inline">API</span>
                    <span className="tabular-nums">
                      {latencyMs !== null ? `${latencyMs}ms` : 'NOMINAL'}
                    </span>
                  </span>
                )}
                {status === 'checking' && (
                  <span className="flex items-center space-x-1.5 text-status-caution">
                    <RefreshCw className="w-3 h-3 animate-spin motion-reduce:animate-none" />
                    <span>SYNCING</span>
                  </span>
                )}
                {status === 'degraded' && (
                  <span className="flex items-center space-x-1.5 text-status-caution" title={error || 'Degraded'}>
                    <AlertTriangle className="w-3 h-3 text-status-caution" />
                    <span className="hidden md:inline">API</span>
                    <span>DEGRADED</span>
                  </span>
                )}
                {status === 'offline' && (
                  <span className="flex items-center space-x-1.5 text-status-alert">
                    <XCircle className="w-3 h-3" />
                    <span>OFFLINE</span>
                  </span>
                )}
                <button
                  onClick={() => checkHealth()}
                  title={`Refresh backend health (Last: ${
                    lastChecked ? lastChecked.toISOString().slice(11, 19) + ' UTC' : 'never'
                  })`}
                  className="ml-1 text-slate-400 hover:text-white transition-colors p-0.5"
                  aria-label="Refresh connection health"
                >
                  <RefreshCw className="w-3 h-3 motion-reduce:animate-none" />
                </button>
              </div>
            </div>
          </div>

          {/* Navigation Bar */}
          <nav className="flex space-x-1 border-t border-hairline py-1.5 overflow-x-auto" aria-label="Main Navigation">
            <button
              onClick={() => onNavigate('/')}
              className={`px-3 py-1.5 text-xs font-medium rounded flex items-center space-x-2 transition-all flex-shrink-0 ${
                currentPath === '/'
                  ? 'bg-panel-raised text-white border-b-2 border-accent font-semibold shadow-panel'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-panel-raised/50'
              }`}
              aria-current={currentPath === '/' ? 'page' : undefined}
            >
              <Radio className="w-3.5 h-3.5" />
              <span>COMMAND BRIDGE</span>
            </button>
            <button
              onClick={() => onNavigate('/trajectory')}
              className={`px-3 py-1.5 text-xs font-medium rounded flex items-center space-x-2 transition-all flex-shrink-0 ${
                currentPath === '/trajectory'
                  ? 'bg-panel-raised text-white border-b-2 border-accent font-semibold shadow-panel'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-panel-raised/50'
              }`}
              aria-current={currentPath === '/trajectory' ? 'page' : undefined}
            >
              <Compass className="w-3.5 h-3.5" />
              <span>ASTRODYNAMICS LAB</span>
            </button>
            <button
              onClick={() => onNavigate('/spacecraft')}
              className={`px-3 py-1.5 text-xs font-medium rounded flex items-center space-x-2 transition-all flex-shrink-0 ${
                currentPath === '/spacecraft'
                  ? 'bg-panel-raised text-white border-b-2 border-accent font-semibold shadow-panel'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-panel-raised/50'
              }`}
              aria-current={currentPath === '/spacecraft' ? 'page' : undefined}
            >
              <Box className="w-3.5 h-3.5" />
              <span>SPACECRAFT</span>
            </button>
            <button
              onClick={() => onNavigate('/cdf')}
              className={`px-3 py-1.5 text-xs font-medium rounded flex items-center space-x-2 transition-all flex-shrink-0 ${
                currentPath === '/cdf'
                  ? 'bg-panel-raised text-white border-b-2 border-accent font-semibold shadow-panel'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-panel-raised/50'
              }`}
              aria-current={currentPath === '/cdf' ? 'page' : undefined}
            >
              <Users className="w-3.5 h-3.5" />
              <span>CDF COLLAB</span>
            </button>
            <button
              onClick={() => onNavigate('/fdir')}
              className={`px-3 py-1.5 text-xs font-medium rounded flex items-center space-x-2 transition-all flex-shrink-0 ${
                currentPath === '/fdir'
                  ? 'bg-panel-raised text-white border-b-2 border-accent font-semibold shadow-panel'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-panel-raised/50'
              }`}
              aria-current={currentPath === '/fdir' ? 'page' : undefined}
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>FDIR & CAPCOM</span>
            </button>
            <button
              onClick={() => onNavigate('/dossier')}
              className={`px-3 py-1.5 text-xs font-medium rounded flex items-center space-x-2 transition-all flex-shrink-0 ${
                currentPath === '/dossier'
                  ? 'bg-panel-raised text-white border-b-2 border-accent font-semibold shadow-panel'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-panel-raised/50'
              }`}
              aria-current={currentPath === '/dossier' ? 'page' : undefined}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>MISSION DOSSIER</span>
            </button>
          </nav>
        </div>
      </header>

      {/* Global Connectivity Banner if Backend Offline */}
      {status === 'offline' && (
        <div
          role="alert"
          className="bg-red-950/80 border-b border-status-alert/40 text-red-200 px-4 py-2.5 text-xs flex items-center justify-between"
        >
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-status-alert flex-shrink-0" />
            <span>
              <strong>Telemetry Link Severed:</strong> Cannot reach backend server at{' '}
              <code className="bg-red-900/60 px-1 py-0.5 rounded font-mono">http://127.0.0.1:8000</code>.
              {error ? ` Reason: ${error}` : ''}
            </span>
          </div>
          <button
            onClick={() => checkHealth()}
            className="flex items-center space-x-1.5 bg-red-900/80 hover:bg-red-800 text-white px-2.5 py-1 rounded text-xs border border-red-700 transition"
          >
            <RefreshCw className="w-3 h-3" />
            <span>Retry Connection</span>
          </button>
        </div>
      )}

      {/* Primary Workspace Viewport */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {children}
      </main>

      {/* Aerospace Footer */}
      <footer className="bg-panel border-t border-hairline py-3 text-slate-400 text-xs font-mono">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-2">
          <div className="flex items-center space-x-4">
            <span>MISSION FORGE • AEROSPACE MISSION PLATFORM</span>
            <span>•</span>
            <span>NASA JPL Horizons & DSN Live Telemetry</span>
          </div>
          <div>Two-Body Patched-Conic Mechanics • Universal Variable Lambert Formulation</div>
        </div>
      </footer>
    </div>
  );
};
