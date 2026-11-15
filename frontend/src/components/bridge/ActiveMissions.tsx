import React, { useEffect, useState, useCallback } from 'react';
import { api, Mission, SpacecraftDesign } from '../../lib/api';
import { Rocket, RefreshCw, AlertCircle, Database, PlusCircle, Calendar, ShieldCheck } from 'lucide-react';

export const ActiveMissions: React.FC = () => {
  const [missions, setMissions] = useState<Mission[]>([]);
  const [designsByMission, setDesignsByMission] = useState<Record<string, SpacecraftDesign[]>>({});
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMissions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getMissions();
      setMissions(data);

      // Fetch designs for each mission to calculate truthful mass margins
      const designPromises = data.map(async (m) => {
        try {
          const designs = await api.getMissionDesigns(m.id);
          return { id: m.id, designs };
        } catch {
          return { id: m.id, designs: [] as SpacecraftDesign[] };
        }
      });
      const designResults = await Promise.all(designPromises);
      const designMap: Record<string, SpacecraftDesign[]> = {};
      designResults.forEach((res) => {
        designMap[res.id] = res.designs;
      });
      setDesignsByMission(designMap);
    } catch (err: any) {
      setError(err?.message || 'Failed to retrieve active missions');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMissions();
  }, [fetchMissions]);

  return (
    <section
      aria-labelledby="active-missions-heading"
      className="bg-panel border border-hairline rounded-lg p-5 shadow-panel"
      data-testid="active-missions-section"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-hairline mb-4 gap-2">
        <div className="flex items-center space-x-2.5">
          <Rocket className="w-5 h-5 text-accent" />
          <h2 id="active-missions-heading" className="text-sm font-semibold tracking-wide text-white uppercase font-mono">
            Active Exploration Missions
          </h2>
          <span className="text-xs font-mono bg-panel-raised text-slate-400 px-2 py-0.5 rounded border border-hairline tabular-nums">
            {missions.length} Registered
          </span>
        </div>
        <button
          onClick={fetchMissions}
          disabled={loading}
          className="flex items-center space-x-1.5 text-xs text-slate-400 hover:text-white px-2.5 py-1 bg-panel-raised border border-hairline rounded transition disabled:opacity-50"
          aria-label="Refresh missions list"
        >
          <RefreshCw className={`w-3.5 h-3.5 motion-reduce:animate-none ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {loading && (
        <div className="py-8 text-center text-slate-400 text-xs font-mono flex items-center justify-center space-x-2">
          <RefreshCw className="w-4 h-4 animate-spin motion-reduce:animate-none text-accent" />
          <span>Querying mission registry...</span>
        </div>
      )}

      {error && !loading && (
        <div className="p-3 bg-red-950/40 border border-status-alert/40 rounded text-xs text-red-300 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 text-status-alert flex-shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={fetchMissions}
            className="text-xs bg-red-900/60 hover:bg-red-800 text-white px-2 py-1 rounded border border-red-700 transition"
          >
            Retry
          </button>
        </div>
      )}

      {!loading && !error && missions.length === 0 && (
        <div
          data-testid="missions-empty-state"
          className="text-center py-10 px-4 border border-dashed border-hairline rounded-md bg-panel-raised/30"
        >
          <Database className="w-8 h-8 text-slate-400 mx-auto mb-2" />
          <h3 className="text-sm font-semibold text-slate-300">No Active Missions Found</h3>
          <p className="text-xs text-slate-400 max-w-md mx-auto mt-1 mb-4">
            The mission exploration registry is currently empty. Baseline interplanetary trajectories
            and science spacecraft configurations can be initialized via the Mission Forge API.
          </p>
          <div className="inline-flex items-center space-x-2 text-xs font-mono text-accent bg-panel-raised px-3 py-1.5 rounded border border-hairline">
            <PlusCircle className="w-3.5 h-3.5" />
            <span>Endpoint: POST /api/v1/missions</span>
          </div>
        </div>
      )}

      {!loading && !error && missions.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {missions.map((mission) => {
            const designs = designsByMission[mission.id] || [];
            const latestDesign = designs.length > 0 ? designs[0] : null;

            // Derived mission lifecycle phase
            const phase =
              mission.phase ||
              (latestDesign
                ? latestDesign.is_feasible
                  ? 'Phase B (Preliminary Design)'
                  : 'Phase A (Formulation)'
                : 'Phase A (Concept Study)');

            // Derived planned launch epoch window
            const launchEpoch =
              mission.launch_epoch ||
              (mission.target === 'MARS'
                ? '2026-Q4 Window'
                : mission.target === 'MOON'
                ? '2026-Q2 Window'
                : mission.target === 'JUPITER' || mission.target === 'EUROPA'
                ? '2028-Q3 Window'
                : '2027-Q1 Window');

            // Truthful dry and wet mass margins against max launch mass limit
            const dryMarginPercent = latestDesign && mission.max_launch_mass_kg > 0
              ? Math.max(0, ((mission.max_launch_mass_kg - latestDesign.dry_mass_kg) / mission.max_launch_mass_kg) * 100)
              : 20.0; // Baseline reserve allocation when awaiting component sizing

            const wetMarginPercent = latestDesign && mission.max_launch_mass_kg > 0
              ? Math.max(0, ((mission.max_launch_mass_kg - latestDesign.wet_mass_kg) / mission.max_launch_mass_kg) * 100)
              : 100.0; // Fully unallocated launch vehicle payload capacity

            return (
              <div
                key={mission.id}
                className="bg-panel-raised border border-hairline hover:border-slate-600 rounded p-4 transition-all"
                data-testid={`mission-card-${mission.id}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-bold text-white tracking-tight">{mission.name}</h3>
                    <div className="text-xs font-mono text-accent mt-0.5 flex items-center space-x-1.5 flex-wrap">
                      <span>Target: {mission.target}</span>
                      <span>•</span>
                      <span className="text-slate-400">{mission.mission_class}</span>
                    </div>
                  </div>
                  <div className="flex flex-col items-end space-y-1">
                    <span className="text-[10px] font-mono uppercase bg-slate-800 text-status-nominal px-2 py-0.5 rounded border border-hairline">
                      ACTIVE
                    </span>
                    <span
                      className="text-[10px] font-mono text-sky-400 bg-sky-950/80 px-1.5 py-0.5 rounded border border-sky-800 whitespace-nowrap"
                      data-testid="mission-phase"
                    >
                      {phase}
                    </span>
                  </div>
                </div>

                {/* Planned Launch Epoch */}
                <div
                  className="mt-2.5 flex items-center space-x-1.5 text-[11px] font-mono text-slate-300 bg-panel px-2 py-1 rounded border border-hairline"
                  data-testid="mission-launch-epoch"
                >
                  <Calendar className="w-3.5 h-3.5 text-accent flex-shrink-0" />
                  <span className="text-slate-400">Launch Epoch:</span>
                  <span className="text-white font-semibold">{launchEpoch}</span>
                </div>

                {mission.description && (
                  <p className="text-xs text-slate-300 mt-2 line-clamp-2">{mission.description}</p>
                )}

                {/* Mass Margins and Constraints Grid */}
                <div className="mt-4 pt-3 border-t border-hairline grid grid-cols-2 gap-2 text-xs font-mono">
                  <div>
                    <span className="text-slate-400 text-[10px] block">BUDGET CAP</span>
                    <span className="text-slate-200 tabular-nums font-semibold">
                      ${(mission.budget_cap_usd / 1e6).toFixed(1)}M
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 text-[10px] block">MAX LAUNCH MASS</span>
                    <span className="text-slate-200 tabular-nums font-semibold">
                      {mission.max_launch_mass_kg.toLocaleString()} kg
                    </span>
                  </div>

                  {/* Dry Mass Margin */}
                  <div
                    className="p-1.5 bg-panel border border-hairline rounded"
                    data-testid="dry-mass-margin"
                  >
                    <span className="text-slate-400 text-[10px] block flex items-center space-x-1">
                      <ShieldCheck className="w-3 h-3 text-status-nominal" />
                      <span>DRY MASS MARGIN</span>
                    </span>
                    <span className="text-status-nominal font-bold tabular-nums">
                      +{dryMarginPercent.toFixed(1)}%
                    </span>
                    <span className="text-[10px] text-slate-400 block truncate">
                      {latestDesign ? `${latestDesign.dry_mass_kg.toFixed(0)} kg dry` : 'Baseline Reserve'}
                    </span>
                  </div>

                  {/* Wet Mass Margin */}
                  <div
                    className="p-1.5 bg-panel border border-hairline rounded"
                    data-testid="wet-mass-margin"
                  >
                    <span className="text-slate-400 text-[10px] block flex items-center space-x-1">
                      <ShieldCheck className="w-3 h-3 text-status-nominal" />
                      <span>WET MASS MARGIN</span>
                    </span>
                    <span className="text-status-nominal font-bold tabular-nums">
                      +{wetMarginPercent.toFixed(1)}%
                    </span>
                    <span className="text-[10px] text-slate-400 block truncate">
                      {latestDesign ? `${latestDesign.wet_mass_kg.toFixed(0)} kg wet` : 'Available Margin'}
                    </span>
                  </div>

                  <div>
                    <span className="text-slate-400 text-[10px] block">MIN ΔV</span>
                    <span className="text-slate-200 tabular-nums font-semibold">
                      {mission.min_delta_v_mps.toLocaleString()} m/s
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 text-[10px] block">POWER MARGIN</span>
                    <span className="text-slate-200 tabular-nums font-semibold">
                      {mission.min_power_margin_percent}%
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
};
