import React, { useState, useEffect, useCallback } from 'react';
import {
  api,
  Mission,
  ComponentItem,
  ComponentSpecInput,
  SWaPCAnalysisResponse,
  CatalogStatusResponse,
  SpacecraftDesign,
} from '../lib/api';
import { SpacecraftVisualizer3D } from '../components/spacecraft/SpacecraftVisualizer3D';
import { ComponentLedger } from '../components/spacecraft/ComponentLedger';
import {
  Box,
  Zap,
  DollarSign,
  Fuel,
  ShieldCheck,
  AlertTriangle,
  Save,
  CheckCircle2,
  Flame,
} from 'lucide-react';

export const SpacecraftDesigner: React.FC = () => {
  const [missions, setMissions] = useState<Mission[]>([]);
  const [selectedMissionId, setSelectedMissionId] = useState<string>('');
  const [catalogStatus, setCatalogStatus] = useState<CatalogStatusResponse | null>(null);

  // Active configuration state
  const [designName, setDesignName] = useState<string>('Flight Architecture Alpha');
  const [configuredComponents, setConfiguredComponents] = useState<ComponentSpecInput[]>([]);
  const [propellantMassKg, setPropellantMassKg] = useState<number>(450);
  const [selectedComponentId, setSelectedComponentId] = useState<string | null>(null);

  // SWaP-C Calculation State
  const [swapcResult, setSwapcResult] = useState<SWaPCAnalysisResponse | null>(null);
  const [swapcLoading, setSwapcLoading] = useState<boolean>(false);
  const [swapcError, setSwapcError] = useState<string | null>(null);

  // Save design state
  const [savedDesigns, setSavedDesigns] = useState<SpacecraftDesign[]>([]);
  const [saving, setSaving] = useState<boolean>(false);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // 1. Load missions and catalog status on mount
  useEffect(() => {
    const init = async () => {
      try {
        const [missionsData, statusData] = await Promise.all([
          api.getMissions(),
          api.getCatalogStatus().catch(() => null),
        ]);
        setMissions(missionsData);
        if (missionsData.length > 0) {
          setSelectedMissionId(missionsData[0].id);
        }
        if (statusData) {
          setCatalogStatus(statusData);
        }
      } catch (err) {
        console.error('Failed to load initial mission data', err);
      }
    };
    init();
  }, []);

  // 2. Load saved designs when mission changes
  useEffect(() => {
    if (!selectedMissionId) return;
    const fetchDesigns = async () => {
      try {
        const designs = await api.getMissionDesigns(selectedMissionId);
        setSavedDesigns(designs);
      } catch (err) {
        console.error('Failed to load mission designs', err);
      }
    };
    fetchDesigns();
  }, [selectedMissionId]);

  // Current active mission
  const activeMission = React.useMemo(() => {
    return missions.find((m) => m.id === selectedMissionId) || null;
  }, [missions, selectedMissionId]);

  // 3. Trigger SWaP-C evaluation whenever components, propellant, or mission changes
  const evaluateSwapc = useCallback(async () => {
    if (!activeMission) return;
    setSwapcLoading(true);
    setSwapcError(null);
    try {
      const res = await api.analyzeSwapc({
        target: activeMission.target,
        mission_class: activeMission.mission_class,
        components: configuredComponents,
        propellant_mass_kg: propellantMassKg,
        required_delta_v_mps: activeMission.min_delta_v_mps || 3800,
        custom_budget_cap_usd: activeMission.budget_cap_usd,
        custom_max_mass_kg: activeMission.max_launch_mass_kg,
        min_power_margin_percent: activeMission.min_power_margin_percent || 15,
      });
      setSwapcResult(res);
    } catch (err: any) {
      setSwapcError(err?.message || 'SWaP-C evaluation encountered an engineering calculation error.');
    } finally {
      setSwapcLoading(false);
    }
  }, [activeMission, configuredComponents, propellantMassKg]);

  useEffect(() => {
    evaluateSwapc();
  }, [evaluateSwapc]);

  // Component management handlers
  const handleAddComponent = (comp: ComponentItem) => {
    const input: ComponentSpecInput = {
      id: comp.id,
      name: comp.name,
      subsystem: comp.subsystem,
      mass_kg: comp.mass_kg || 0,
      power_draw_w: comp.power_draw_w || 0,
      power_generation_w: comp.power_generation_w || 0,
      cost_usd: comp.cost_usd || 0,
      isp_seconds: comp.isp_seconds,
      thrust_newtons: comp.thrust_newtons,
      solar_area_m2: comp.solar_area_m2,
      solar_efficiency: comp.solar_efficiency || 0.3,
      antenna_diameter_m: comp.antenna_diameter_m,
      tx_power_w: comp.tx_power_w,
    };
    setConfiguredComponents((prev) => [...prev, input]);
    setSelectedComponentId(comp.id);
  };

  const handleRemoveComponent = (index: number) => {
    setConfiguredComponents((prev) => prev.filter((_, i) => i !== index));
  };

  // Save Design Handler
  const handleSaveDesign = async () => {
    if (!selectedMissionId) return;
    setSaving(true);
    setSaveError(null);
    setSaveSuccessMsg(null);
    try {
      const design = await api.createDesign(selectedMissionId, {
        name: designName,
        components: configuredComponents,
        propellant_mass_kg: propellantMassKg,
      });
      setSavedDesigns((prev) => [design, ...prev]);
      setSaveSuccessMsg(`Design '${design.name}' saved with version ${design.version}.`);
      setTimeout(() => setSaveSuccessMsg(null), 4000);
    } catch (err: any) {
      setSaveError(err?.message || 'Failed to save spacecraft design.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      {/* Viewport Header & Mission Selector */}
      <div className="bg-panel border border-hairline rounded-lg p-5 shadow-panel flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <Box className="w-5 h-5 text-accent" />
            <h1 className="text-xl font-bold font-mono tracking-wider text-white uppercase">
              Phase 10 — Spacecraft Visualizer & Component Ledger
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Authoritative component ledger, procedural 3D subsystem modeling, and deterministic SWaP-C margin analysis.
          </p>
        </div>

        {/* Mission Selector */}
        <div className="flex items-center space-x-3 text-xs font-mono">
          <label htmlFor="mission-select" className="text-slate-400">Target Mission:</label>
          <select
            id="mission-select"
            value={selectedMissionId}
            onChange={(e) => setSelectedMissionId(e.target.value)}
            className="px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent"
          >
            {missions.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name} ({m.target})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Catalog Freshness & Provenance Status Banner */}
      {catalogStatus && (
        <div className="bg-slate-900/80 border border-hairline rounded-lg px-4 py-2.5 text-xs font-mono flex flex-wrap items-center justify-between gap-2 text-slate-300">
          <div className="flex items-center space-x-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>
              CATALOG PROVENANCE COVERAGE:{' '}
              <span className="text-emerald-400 font-semibold">{catalogStatus.provenance_coverage_percent}%</span> ({catalogStatus.components_with_provenance}/{catalogStatus.total_components} items)
            </span>
          </div>
          <div className="text-slate-400 text-[11px]">
            Sources: {catalogStatus.source_systems?.join(', ') || 'NASA TechPort / NTRS'}
            {catalogStatus.last_synced_at && ` • Last Synced: ${new Date(catalogStatus.last_synced_at).toLocaleDateString()}`}
          </div>
        </div>
      )}

      {/* SWaP-C Error if any */}
      {swapcError && (
        <div role="alert" className="p-3 bg-red-950/60 border border-red-800 rounded text-xs font-mono text-red-200">
          {swapcError}
        </div>
      )}

      {/* SWaP-C Systems Engineering Dashboard Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs font-mono">
        {/* Mass Budget Card */}
        <div className="bg-panel border border-hairline rounded-lg p-4 shadow-panel">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="uppercase text-[11px]">Mass Budget</span>
            {swapcLoading ? <span className="text-[10px] text-accent animate-pulse">CALCULATING...</span> : <Box className="w-3.5 h-3.5 text-accent" />}
          </div>
          <div className="text-xl font-bold text-white tabular-nums">
            {swapcResult ? `${swapcResult.wet_mass_kg.toFixed(1)} kg` : '--'}
          </div>
          <div className="text-[11px] text-slate-400 mt-1 flex justify-between">
            <span>Dry: {swapcResult ? `${swapcResult.dry_mass_kg.toFixed(1)} kg` : '--'}</span>
            <span>Prop: {swapcResult ? `${swapcResult.propellant_mass_kg.toFixed(1)} kg` : '--'}</span>
          </div>
          <div className="text-[10px] text-slate-500 mt-1">
            Max Cap: {activeMission ? `${activeMission.max_launch_mass_kg} kg` : '1800 kg'}
          </div>
        </div>

        {/* Power Balance Card */}
        <div className="bg-panel border border-hairline rounded-lg p-4 shadow-panel">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="uppercase text-[11px]">Power Balance</span>
            <Zap className="w-3.5 h-3.5 text-amber-400" />
          </div>
          <div className="text-xl font-bold text-white tabular-nums">
            {swapcResult ? `${swapcResult.total_power_generated_w.toFixed(1)} W` : '--'}
          </div>
          <div className="text-[11px] text-slate-400 mt-1 flex justify-between">
            <span>Load: {swapcResult ? `${swapcResult.total_power_draw_w.toFixed(1)} W` : '--'}</span>
            <span className={swapcResult && swapcResult.power_margin_percent >= 15 ? 'text-emerald-400' : 'text-amber-400'}>
              Margin: {swapcResult ? `${swapcResult.power_margin_percent.toFixed(1)}%` : '--'}
            </span>
          </div>
          <div className="text-[10px] text-slate-500 mt-1">
            Min Margin Req: {activeMission ? `${activeMission.min_power_margin_percent}%` : '15%'}
          </div>
        </div>

        {/* Propulsion Delta-V Card */}
        <div className="bg-panel border border-hairline rounded-lg p-4 shadow-panel">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="uppercase text-[11px]">Available Delta-V</span>
            <Flame className="w-3.5 h-3.5 text-red-400" />
          </div>
          <div className="text-xl font-bold text-white tabular-nums">
            {swapcResult ? `${Math.round(swapcResult.available_delta_v_mps)} m/s` : '--'}
          </div>
          <div className="text-[11px] text-slate-400 mt-1 flex justify-between">
            <span>Req: {activeMission ? `${Math.round(activeMission.min_delta_v_mps)} m/s` : '3800 m/s'}</span>
            <span className={swapcResult && swapcResult.delta_v_margin_mps >= 0 ? 'text-emerald-400' : 'text-red-400'}>
              Margin: {swapcResult ? `${Math.round(swapcResult.delta_v_margin_mps)} m/s` : '--'}
            </span>
          </div>
          <div className="text-[10px] text-slate-500 mt-1">
            Isp Eff: {swapcResult ? `${swapcResult.effective_isp_s.toFixed(1)} s` : '--'}
          </div>
        </div>

        {/* Financial Cost Budget Card */}
        <div className="bg-panel border border-hairline rounded-lg p-4 shadow-panel">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="uppercase text-[11px]">Total Cost</span>
            <DollarSign className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="text-xl font-bold text-white tabular-nums">
            {swapcResult ? `$${(swapcResult.total_mission_cost_usd / 1e6).toFixed(1)}M` : '--'}
          </div>
          <div className="text-[11px] text-slate-400 mt-1 flex justify-between">
            <span>Hardware: {swapcResult ? `$${(swapcResult.hardware_cost_usd / 1e6).toFixed(1)}M` : '--'}</span>
            <span className={swapcResult && swapcResult.budget_margin_usd >= 0 ? 'text-emerald-400' : 'text-red-400'}>
              Margin: {swapcResult ? `$${(swapcResult.budget_margin_usd / 1e6).toFixed(1)}M` : '--'}
            </span>
          </div>
          <div className="text-[10px] text-slate-500 mt-1">
            Cap: {activeMission ? `$${(activeMission.budget_cap_usd / 1e6).toFixed(0)}M` : '$500M'}
          </div>
        </div>
      </div>

      {/* Feasibility Verdict & Constraint Violations Alert Banner */}
      {swapcResult && (
        <div
          role="region"
          aria-label="Feasibility Analysis"
          className={`p-4 rounded-lg border text-xs font-mono flex flex-col md:flex-row items-start md:items-center justify-between gap-3 ${
            swapcResult.status === 'NOMINAL'
              ? 'bg-emerald-950/40 border-emerald-800 text-emerald-200'
              : swapcResult.status === 'MARGINAL'
              ? 'bg-amber-950/40 border-amber-800 text-amber-200'
              : 'bg-red-950/40 border-red-800 text-red-200'
          }`}
        >
          <div className="flex items-center space-x-3">
            {swapcResult.status === 'NOMINAL' ? (
              <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
            ) : (
              <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0" />
            )}
            <div>
              <div className="font-semibold uppercase tracking-wider text-sm text-white">
                VERDICT: {swapcResult.status} {swapcResult.is_feasible ? '— FEASIBLE FLIGHT ARCHITECTURE' : '— CONSTRAINTS VIOLATED'}
              </div>
              <div className="text-[11px] mt-0.5 opacity-90">
                {swapcResult.violations.length === 0
                  ? 'All aerospace systems engineering constraints (mass, power margin, delta-V, budget) satisfied.'
                  : `${swapcResult.violations.length} engineering constraint violations detected.`}
              </div>
            </div>
          </div>

          {/* Sized Propellant Adjuster Slider */}
          <div className="flex items-center space-x-2 bg-slate-900/80 px-3 py-1.5 rounded border border-hairline">
            <Fuel className="w-3.5 h-3.5 text-accent" />
            <label htmlFor="prop-slider" className="text-slate-300 text-[11px]">Propellant:</label>
            <input
              id="prop-slider"
              type="range"
              min="0"
              max="2000"
              step="10"
              value={propellantMassKg}
              onChange={(e) => setPropellantMassKg(Number(e.target.value))}
              className="w-24 accent-accent"
              aria-label="Adjust propellant mass in kg"
            />
            <span className="text-white font-semibold tabular-nums w-14 text-right">
              {propellantMassKg} kg
            </span>
          </div>
        </div>
      )}

      {/* Constraint Violations Detail if any */}
      {swapcResult && swapcResult.violations.length > 0 && (
        <div className="bg-panel border border-red-900/60 rounded-lg p-4 shadow-panel space-y-2">
          <div className="text-xs font-mono font-semibold text-red-400 uppercase tracking-wider">
            Active Engineering Constraint Violations:
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {swapcResult.violations.map((v, i) => (
              <div key={i} className="p-2.5 bg-red-950/30 border border-red-800/50 rounded text-xs font-mono">
                <div className="flex items-center justify-between text-red-300 font-semibold">
                  <span>{v.constraint_type}</span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-red-900 text-red-100">{v.severity}</span>
                </div>
                <div className="text-slate-300 text-[11px] mt-1">{v.message}</div>
                <div className="text-accent text-[10px] mt-1.5 font-medium">Fix: {v.actionable_fix}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Spacecraft Visualizer 3D Viewport */}
      <SpacecraftVisualizer3D
        components={configuredComponents}
        selectedComponentId={selectedComponentId}
        onSelectComponent={setSelectedComponentId}
        dryMassKg={swapcResult?.dry_mass_kg || 0}
        wetMassKg={swapcResult?.wet_mass_kg || 0}
        powerDrawW={swapcResult?.total_power_draw_w || 0}
        powerGenW={swapcResult?.total_power_generated_w || 0}
      />

      {/* Save Configuration & Version Controls */}
      <div className="bg-panel border border-hairline rounded-lg p-4 shadow-panel flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
        <div className="flex items-center space-x-2 flex-grow max-w-md">
          <label htmlFor="design-name-input" className="text-slate-400 flex-shrink-0">Design Name:</label>
          <input
            id="design-name-input"
            type="text"
            value={designName}
            onChange={(e) => setDesignName(e.target.value)}
            className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent"
          />
        </div>

        <div className="flex items-center space-x-3">
          <span className="text-slate-400 text-[11px] hidden sm:inline">
            Saved Architectures: {savedDesigns.length}
          </span>
          {saveSuccessMsg && (
            <span className="text-emerald-400 font-semibold flex items-center space-x-1">
              <CheckCircle2 className="w-4 h-4" />
              <span>{saveSuccessMsg}</span>
            </span>
          )}
          {saveError && <span className="text-red-400">{saveError}</span>}

          <button
            onClick={handleSaveDesign}
            disabled={saving || !selectedMissionId}
            className="px-4 py-2 rounded bg-accent text-canvas font-semibold hover:bg-accent/90 transition-all flex items-center space-x-2 disabled:opacity-50"
            aria-label="Save spacecraft design configuration"
          >
            <Save className="w-4 h-4" />
            <span>{saving ? 'SAVING...' : 'SAVE ARCHITECTURE'}</span>
          </button>
        </div>
      </div>

      {/* Component Catalog & Ledger Panel */}
      <ComponentLedger
        configuredComponents={configuredComponents}
        onAddComponent={handleAddComponent}
        onRemoveComponent={handleRemoveComponent}
        selectedComponentId={selectedComponentId}
        onSelectComponent={setSelectedComponentId}
      />
    </div>
  );
};
