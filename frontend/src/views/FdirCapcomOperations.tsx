import React, { useState, useEffect } from 'react';
import {
  api,
  FDIRRuleInfo,
  FDIRReportResponse,
  FDIRFindingLog,
  CAPCOMResponse,
  getAuthToken,
  setAuthToken,
} from '../lib/api';
import {
  AlertOctagon,
  ShieldAlert,
  Bot,
  Activity,
  CheckCircle2,
  AlertTriangle,
  Play,
  BookOpen,
  Info,
  Cpu,
  Check,
  Send,
  Clock,
  Sparkles,
  Key,
  LogOut,
} from 'lucide-react';

const SIMULATED_SCENARIOS = [
  { id: 'POWER_DEFICIT', label: 'Power Deficit (Solar Distance Drop)', subsystem: 'POWER' },
  { id: 'THERMAL_EXCEEDANCE', label: 'Thermal Exceedance (High Irradiance)', subsystem: 'THERMAL' },
  { id: 'COMM_BLACKOUT', label: 'Communications Blackout / Lock Loss', subsystem: 'TELECOM' },
  { id: 'WHEEL_SATURATION', label: 'Reaction Wheel Saturation', subsystem: 'ADCS' },
  { id: 'PROPULSION_SHORTFALL', label: 'Thruster Delta-V Shortfall', subsystem: 'PROPULSION' },
  { id: 'NOMINAL_CRUISE', label: 'Nominal Interplanetary Cruise', subsystem: 'ALL' },
];

export const FdirCapcomOperations: React.FC = () => {
  // FDIR State
  const [rules, setRules] = useState<FDIRRuleInfo[]>([]);
  const [fdirReport, setFdirReport] = useState<FDIRReportResponse | null>(null);
  const [fdirHistory, setFdirHistory] = useState<FDIRFindingLog[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<string>('POWER_DEFICIT');
  const [evaluating, setEvaluating] = useState<boolean>(false);
  const [isSimulated, setIsSimulated] = useState<boolean>(false);
  const [fdirError, setFdirError] = useState<string | null>(null);
  const [ackSuccessId, setAckSuccessId] = useState<string | null>(null);

  // Operator Auth state for CAPCOM & Acknowledgement
  const [operatorToken, setOperatorToken] = useState<string | null>(getAuthToken());
  const [showAuthDrawer, setShowAuthDrawer] = useState<boolean>(false);
  const [authEmail, setAuthEmail] = useState<string>('flight.director@missionforge.nasa.gov');
  const [authPassword, setAuthPassword] = useState<string>('FlightReady2026!');
  const [authLoggingIn, setAuthLoggingIn] = useState<boolean>(false);

  // CAPCOM State
  const [capcomQuery, setCapcomQuery] = useState<string>(
    'Assess power deficit risks and triage recommendations for battery storage.'
  );
  const [capcomResponse, setCapcomResponse] = useState<CAPCOMResponse | null>(null);
  const [capcomLoading, setCapcomLoading] = useState<boolean>(false);
  const [capcomError, setCapcomError] = useState<string | null>(null);

  // Active view tab: FDIR vs CAPCOM
  const [activeTab, setActiveTab] = useState<'FDIR' | 'CAPCOM' | 'AUDIT'>('FDIR');

  // 1. Load registered rules on mount
  useEffect(() => {
    const init = async () => {
      try {
        const rulesData = await api.listFdirRules();
        setRules(rulesData);
      } catch (err) {
        console.error('Failed to query FDIR rules', err);
      }
    };
    init();
  }, []);

  // 2. Run initial nominal evaluation or scenario
  const handleRunScenario = async (scenarioId: string) => {
    setEvaluating(true);
    setFdirError(null);
    try {
      const res = await api.runFdirScenario(scenarioId);
      setFdirReport(res);
      setIsSimulated(true);
      // Refresh history if authenticated
      if (getAuthToken()) {
        api.getFdirHistory({ limit: 20 }).then(setFdirHistory).catch(() => {});
      }
    } catch (err: any) {
      setFdirError(err?.message || 'Failed to evaluate simulation scenario.');
    } finally {
      setEvaluating(false);
    }
  };

  useEffect(() => {
    handleRunScenario('POWER_DEFICIT');
  }, []);

  // Acknowledge Finding (resolves persistent log UUID from rule_id or accepts log UUID directly)
  const handleAcknowledge = async (targetIdOrRule: string) => {
    setFdirError(null);
    try {
      if (!getAuthToken()) {
        throw new Error('Authentication required to record anomaly acknowledgement. Please log in as an operator.');
      }

      let targetLogId = targetIdOrRule;
      const directMatch = fdirHistory.find((log) => log.id === targetIdOrRule);

      if (!directMatch) {
        // Resolve latest unacknowledged log entry for this rule_id
        const ruleMatch = fdirHistory.find((log) => log.rule_id === targetIdOrRule && !log.acknowledged);
        if (ruleMatch) {
          targetLogId = ruleMatch.id;
        } else {
          // Attempt to pull latest history from backend to resolve log UUID
          const freshHistory = await api.getFdirHistory({ limit: 50 }).catch(() => []);
          setFdirHistory(freshHistory);
          const freshMatch = freshHistory.find(
            (log) => (log.rule_id === targetIdOrRule || log.id === targetIdOrRule) && !log.acknowledged
          );
          if (freshMatch) {
            targetLogId = freshMatch.id;
          } else {
            throw new Error(`No persistent anomaly record found for '${targetIdOrRule}' to acknowledge.`);
          }
        }
      }

      await api.acknowledgeFdirFinding(targetLogId);
      setAckSuccessId(targetIdOrRule);
      setTimeout(() => setAckSuccessId(null), 3000);

      // Refresh history immediately
      const updated = await api.getFdirHistory({ limit: 50 }).catch(() => []);
      setFdirHistory(updated);
    } catch (err: any) {
      setFdirError(err?.message || 'Authentication required to acknowledge FDIR anomaly.');
    }
  };

  const handleOperatorLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthLoggingIn(true);
    setFdirError(null);
    try {
      const res = await api.login(authEmail, authPassword);
      setOperatorToken(res.access_token);
      setShowAuthDrawer(false);
      api.getFdirHistory({ limit: 50 }).then(setFdirHistory).catch(() => {});
    } catch (err: any) {
      setFdirError(err?.message || 'Operator login failed. Verify credentials.');
    } finally {
      setAuthLoggingIn(false);
    }
  };

  const handleOperatorLogout = () => {
    setAuthToken(null);
    setOperatorToken(null);
    setFdirHistory([]);
  };

  // CAPCOM Query Handler
  const handleAskCapcom = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!capcomQuery.trim()) return;
    setCapcomLoading(true);
    setCapcomError(null);
    try {
      const res = await api.askCapcom({
        query: capcomQuery.trim(),
      });
      setCapcomResponse(res);
    } catch (err: any) {
      setCapcomError(err?.message || 'CAPCOM assistant query failed. Verify authentication token.');
    } finally {
      setCapcomLoading(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      {/* Header Bar */}
      <div className="bg-panel border border-hairline rounded-lg p-5 shadow-panel flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <AlertOctagon className="w-5 h-5 text-accent" />
            <h1 className="text-xl font-bold font-mono tracking-wider text-white uppercase">
              Phase 12 — FDIR Operations & Grounded CAPCOM
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Deterministic Fault Detection, Isolation & Recovery (FDIR) combined with strictly grounded advisory AI assistance.
          </p>
        </div>

        {/* View Switcher Tabs & Operator Status */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Operator Auth Badge */}
          <div className="flex items-center space-x-1.5 px-2.5 py-1 bg-slate-900 border border-hairline rounded text-xs font-mono">
            {operatorToken ? (
              <>
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                <span className="text-emerald-300 text-[11px]">OPERATOR AUTH</span>
                <button
                  onClick={handleOperatorLogout}
                  className="ml-1 text-slate-400 hover:text-white p-0.5"
                  title="Logout operator"
                >
                  <LogOut className="w-3 h-3" />
                </button>
              </>
            ) : (
              <>
                <span className="w-2 h-2 rounded-full bg-amber-400" />
                <span className="text-slate-400 text-[11px]">READ-ONLY</span>
                <button
                  onClick={() => setShowAuthDrawer(!showAuthDrawer)}
                  className="ml-1 text-accent hover:underline text-[11px] font-semibold flex items-center space-x-0.5"
                >
                  <Key className="w-2.5 h-2.5" />
                  <span>LOGIN</span>
                </button>
              </>
            )}
          </div>

          <div className="flex items-center space-x-1 bg-slate-900 p-1 rounded border border-hairline text-xs font-mono">
            <button
              onClick={() => setActiveTab('FDIR')}
              className={`px-3 py-1.5 rounded transition-all flex items-center space-x-1.5 ${
                activeTab === 'FDIR'
                  ? 'bg-panel-raised text-white font-semibold border-b-2 border-accent shadow-panel'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>FDIR ENGINE</span>
            </button>
            <button
              onClick={() => setActiveTab('CAPCOM')}
              className={`px-3 py-1.5 rounded transition-all flex items-center space-x-1.5 ${
                activeTab === 'CAPCOM'
                  ? 'bg-panel-raised text-white font-semibold border-b-2 border-accent shadow-panel'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <Bot className="w-3.5 h-3.5 text-accent" />
              <span>GROUNDED CAPCOM</span>
            </button>
            <button
              onClick={() => {
                setActiveTab('AUDIT');
                if (getAuthToken()) {
                  api.getFdirHistory({ limit: 50 }).then(setFdirHistory).catch(() => {});
                }
              }}
              className={`px-3 py-1.5 rounded transition-all flex items-center space-x-1.5 ${
                activeTab === 'AUDIT'
                  ? 'bg-panel-raised text-white font-semibold border-b-2 border-accent shadow-panel'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <Clock className="w-3.5 h-3.5" />
              <span>AUDIT TRAIL</span>
            </button>
          </div>
        </div>
      </div>

      {/* Operator Login Drawer Modal if requested */}
      {showAuthDrawer && (
        <div className="bg-panel border border-hairline rounded-lg p-4 shadow-panel max-w-md font-mono text-xs space-y-3">
          <div className="flex items-center justify-between border-b border-hairline pb-2">
            <span className="font-semibold text-white uppercase">Operator Session Authentication</span>
            <button onClick={() => setShowAuthDrawer(false)} className="text-slate-400 hover:text-white">✕</button>
          </div>
          <form onSubmit={handleOperatorLogin} className="space-y-2">
            <div>
              <label className="text-slate-400 block mb-0.5">Email:</label>
              <input
                type="email"
                value={authEmail}
                onChange={(e) => setAuthEmail(e.target.value)}
                className="w-full px-2.5 py-1 bg-slate-900 border border-hairline rounded text-white"
                required
              />
            </div>
            <div>
              <label className="text-slate-400 block mb-0.5">Password:</label>
              <input
                type="password"
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                className="w-full px-2.5 py-1 bg-slate-900 border border-hairline rounded text-white"
                required
              />
            </div>
            <button
              type="submit"
              disabled={authLoggingIn}
              className="w-full py-1.5 bg-accent text-canvas font-semibold rounded hover:bg-accent/90"
            >
              {authLoggingIn ? 'AUTHENTICATING...' : 'AUTHORIZE OPERATOR'}
            </button>
          </form>
        </div>
      )}

      {/* Mandatory Safety Notice Banner */}
      <div
        role="alert"
        className="px-4 py-2.5 bg-slate-900 border border-hairline rounded-lg text-xs font-mono text-slate-400 flex items-center justify-between"
      >
        <div className="flex items-center space-x-2">
          <Info className="w-4 h-4 text-accent flex-shrink-0" />
          <span>
            ADVISORY SIMULATION SAFETY NOTICE: CAPCOM AI & FDIR are decision-support advisory systems. They do not issue live flight computer commands or replace the designated human Flight Director.
          </span>
        </div>
        {isSimulated && (
          <span className="px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800 text-[10px] font-bold">
            [SIMULATED SCENARIO]
          </span>
        )}
      </div>

      {fdirError && (
        <div role="alert" className="p-3 bg-red-950/80 border border-red-800 text-red-200 text-xs font-mono rounded">
          {fdirError}
        </div>
      )}

      {/* TAB 1: FDIR ENGINE VIEW */}
      {activeTab === 'FDIR' && (
        <div className="space-y-6">
          {/* Simulation Controls & Registered Rules HUD */}
          <div className="bg-panel border border-hairline rounded-lg p-5 shadow-panel space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline pb-3">
              <div className="flex items-center space-x-2">
                <Activity className="w-4 h-4 text-accent" />
                <h3 className="font-mono font-semibold text-sm text-white uppercase tracking-wider">
                  Deterministic Fault Injection & Verification
                </h3>
              </div>

              {/* Scenario Selector */}
              <div className="flex items-center space-x-2 text-xs font-mono">
                <label htmlFor="scenario-select" className="text-slate-400">Scenario:</label>
                <select
                  id="scenario-select"
                  value={selectedScenario}
                  onChange={(e) => setSelectedScenario(e.target.value)}
                  className="px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent"
                >
                  {SIMULATED_SCENARIOS.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </select>

                <button
                  onClick={() => handleRunScenario(selectedScenario)}
                  disabled={evaluating}
                  className="px-3 py-1.5 rounded bg-accent text-canvas font-semibold hover:bg-accent/90 flex items-center space-x-1"
                >
                  <Play className="w-3 h-3" />
                  <span>{evaluating ? 'EVALUATING...' : 'EXECUTE SCENARIO'}</span>
                </button>
              </div>
            </div>

            {/* Registered Rules List Pill Bar */}
            <div className="text-xs font-mono">
              <div className="text-slate-400 mb-2">Registered Deterministic Rules ({rules.length}):</div>
              <div className="flex flex-wrap gap-2">
                {rules.map((r) => (
                  <div
                    key={r.rule_id}
                    className="px-2.5 py-1 rounded bg-slate-900 border border-hairline text-[11px] text-slate-300 flex items-center space-x-1.5"
                  >
                    <span className="font-semibold text-accent">{r.rule_id}</span>
                    <span className="text-slate-500">v{r.rule_version}</span>
                    <span className="px-1 rounded bg-slate-800 text-[10px] text-slate-400">{r.subsystem}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Overall Evaluation Status Card */}
          {fdirReport && (
            <div
              className={`p-4 rounded-lg border font-mono text-xs flex flex-wrap items-center justify-between gap-4 ${
                fdirReport.overall_severity === 'NOMINAL'
                  ? 'bg-emerald-950/40 border-emerald-800 text-emerald-200'
                  : fdirReport.overall_severity === 'CAUTION'
                  ? 'bg-amber-950/40 border-amber-800 text-amber-200'
                  : fdirReport.overall_severity === 'WARNING'
                  ? 'bg-orange-950/40 border-orange-800 text-orange-200'
                  : 'bg-red-950/40 border-red-800 text-red-200'
              }`}
            >
              <div className="flex items-center space-x-3">
                {fdirReport.overall_severity === 'NOMINAL' ? (
                  <CheckCircle2 className="w-6 h-6 text-emerald-400" />
                ) : (
                  <AlertTriangle className="w-6 h-6 text-red-400" />
                )}
                <div>
                  <div className="text-sm font-bold uppercase tracking-wider text-white">
                    OVERALL SEVERITY: {fdirReport.overall_severity}
                  </div>
                  <div className="text-[11px] mt-0.5 opacity-90">
                    Evaluated at: {new Date(fdirReport.eval_timestamp).toUTCString()} • Active Anomalies: {fdirReport.active_anomalies.length}
                  </div>
                </div>
              </div>

              <div className="flex items-center space-x-3 text-xs">
                <span className="px-2 py-1 rounded bg-slate-900 border border-hairline text-slate-300">
                  Total Findings: {fdirReport.findings.length}
                </span>
                <span className="px-2 py-1 rounded bg-slate-900 border border-hairline text-purple-300">
                  Insufficient Data: {fdirReport.insufficient_data_findings.length}
                </span>
              </div>
            </div>
          )}

          {/* Active Findings Cards Grid */}
          {fdirReport && (
            <div className="space-y-4">
              <h3 className="font-mono font-semibold text-sm text-white uppercase tracking-wider">
                Evaluated Findings & Anomaly Triage
              </h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {fdirReport.findings.map((f, idx) => {
                  const isInsufficient = f.status === 'INSUFFICIENT_DATA';
                  const isNominal = f.status === 'NOMINAL';
                  return (
                    <div
                      key={f.rule_id + idx}
                      className={`bg-panel border rounded-lg p-4 shadow-panel flex flex-col justify-between space-y-3 font-mono text-xs ${
                        isInsufficient
                          ? 'border-purple-800/80 bg-purple-950/20'
                          : isNominal
                          ? 'border-emerald-800/60 bg-emerald-950/10'
                          : f.severity === 'CRITICAL'
                          ? 'border-red-800 bg-red-950/20'
                          : 'border-amber-800 bg-amber-950/20'
                      }`}
                      data-testid={`finding-card-${f.rule_id}`}
                    >
                      <div>
                        {/* Finding Header */}
                        <div className="flex items-center justify-between border-b border-hairline pb-2 mb-2">
                          <div className="flex items-center space-x-2">
                            <span className="font-bold text-white text-sm">{f.rule_id}</span>
                            <span className="text-[10px] text-slate-500">v{f.rule_version}</span>
                          </div>
                          <div className="flex items-center space-x-1.5">
                            <span
                              className={`px-1.5 py-0.5 rounded text-[10px] font-bold border ${
                                isInsufficient
                                  ? 'bg-purple-900 text-purple-200 border-purple-700'
                                  : isNominal
                                  ? 'bg-emerald-950 text-emerald-400 border-emerald-800'
                                  : f.severity === 'CRITICAL'
                                  ? 'bg-red-900 text-red-100 border-red-700'
                                  : 'bg-amber-900 text-amber-200 border-amber-700'
                              }`}
                            >
                              {f.status} • {f.severity}
                            </span>
                          </div>
                        </div>

                        {/* Subsystem & Confidence status */}
                        <div className="flex items-center justify-between text-[11px] text-slate-400 mb-2">
                          <span>Subsystem: <strong className="text-white">{f.affected_subsystem}</strong></span>
                          <span>Confidence: <strong className="text-accent">{f.confidence_status}</strong></span>
                        </div>

                        {/* Explanation */}
                        <div className="text-slate-200 text-xs mb-2">
                          {f.explanation}
                        </div>

                        {/* Input Evidence & Thresholds */}
                        <div className="p-2.5 bg-slate-900 rounded border border-hairline text-[10px] space-y-1">
                          <div className="text-slate-400 font-semibold">Evidence:</div>
                          <div className="text-slate-300 font-mono">
                            {JSON.stringify(f.input_evidence)}
                          </div>
                          {Object.keys(f.thresholds || {}).length > 0 && (
                            <div className="text-slate-400 text-[10px] pt-1">
                              Threshold: {JSON.stringify(f.thresholds)}
                            </div>
                          )}
                        </div>

                        {/* Triage Guidance */}
                        <div className="mt-2 text-[11px] text-amber-300 font-medium">
                          Guidance: {f.triage_guidance}
                        </div>
                      </div>

                      {/* Acknowledge Button */}
                      {!isNominal && (
                        <div className="pt-2 border-t border-hairline flex items-center justify-between">
                          <span className="text-[10px] text-slate-500">
                            Advisory evaluation only.
                          </span>
                          <button
                            onClick={() => handleAcknowledge(f.rule_id)}
                            className="px-2.5 py-1 rounded bg-panel-raised border border-hairline hover:bg-slate-700 text-slate-300 text-xs flex items-center space-x-1"
                            aria-label={`Acknowledge anomaly for ${f.rule_id}`}
                          >
                            <Check className="w-3 h-3 text-emerald-400" />
                            <span>
                              {ackSuccessId === f.rule_id ? 'ACKNOWLEDGED' : 'ACKNOWLEDGE ANOMALY'}
                            </span>
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: GROUNDED CAPCOM VIEW */}
      {activeTab === 'CAPCOM' && (
        <div className="space-y-6 font-mono text-xs">
          {/* Query Input Box */}
          <div className="bg-panel border border-hairline rounded-lg p-5 shadow-panel space-y-4">
            <div className="flex items-center space-x-2 border-b border-hairline pb-2.5">
              <Bot className="w-5 h-5 text-accent" />
              <h3 className="font-semibold text-sm text-white uppercase tracking-wider">
                Grounded CAPCOM AI Assistant
              </h3>
            </div>

            <p className="text-slate-400 text-xs">
              Queries are mathematically grounded in authoritative CDF state, real physics formulas, and deterministic FDIR findings. CAPCOM cannot override calculations or issue hardware commands.
            </p>

            <form onSubmit={handleAskCapcom} className="space-y-3">
              <div>
                <textarea
                  value={capcomQuery}
                  onChange={(e) => setCapcomQuery(e.target.value)}
                  rows={3}
                  className="w-full p-3 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent font-mono text-xs"
                  placeholder="Enter engineering query for CAPCOM..."
                  required
                />
              </div>

              {capcomError && (
                <div className="p-3 bg-red-950/80 border border-red-800 text-red-200 rounded">
                  {capcomError}
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap gap-1.5 text-[10px] text-slate-400">
                  <span>Suggested:</span>
                  <button
                    type="button"
                    onClick={() => setCapcomQuery('Analyze power margin and battery storage deficit at 1.5 AU.')}
                    className="underline hover:text-white"
                  >
                    Power Deficit
                  </button>
                  <span>•</span>
                  <button
                    type="button"
                    onClick={() => setCapcomQuery('Triage reaction wheel saturation and momentum dumping options.')}
                    className="underline hover:text-white"
                  >
                    Wheel Saturation
                  </button>
                  <span>•</span>
                  <button
                    type="button"
                    onClick={() => setCapcomQuery('Evaluate communication link budget loss and blackout risk.')}
                    className="underline hover:text-white"
                  >
                    Telecom Blackout
                  </button>
                </div>

                <button
                  type="submit"
                  disabled={capcomLoading}
                  className="px-4 py-2 bg-accent text-canvas font-semibold rounded hover:bg-accent/90 flex items-center space-x-2 disabled:opacity-50"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>{capcomLoading ? 'GROUNDING REASONING...' : 'QUERY CAPCOM'}</span>
                </button>
              </div>
            </form>
          </div>

          {/* CAPCOM Structured Grounded Response Display */}
          {capcomResponse && (
            <div className="space-y-6" data-testid="capcom-response-container">
              {/* Response Header & Provenance */}
              <div className="bg-slate-900 border border-hairline rounded-lg p-4 flex flex-wrap items-center justify-between gap-2 text-[11px]">
                <div className="flex items-center space-x-2">
                  <Sparkles className="w-4 h-4 text-accent" />
                  <span className="text-white font-semibold">Model: {capcomResponse.model_name}</span>
                  <span
                    className={`px-1.5 py-0.5 rounded border text-[10px] ${
                      capcomResponse.is_live_generation
                        ? 'bg-emerald-950 text-emerald-400 border-emerald-800'
                        : 'bg-amber-950 text-amber-400 border-amber-800'
                    }`}
                  >
                    {capcomResponse.is_live_generation ? 'LIVE REASONING' : 'DETERMINISTIC FALLBACK'}
                  </span>
                </div>
                <div className="text-slate-500">
                  Timestamp: {new Date(capcomResponse.generation_timestamp).toLocaleTimeString()}
                </div>
              </div>

              {/* 1. Verified Source Facts Section */}
              <div className="bg-panel border border-hairline rounded-lg p-5 shadow-panel space-y-3">
                <div className="flex items-center space-x-2 border-b border-hairline pb-2">
                  <BookOpen className="w-4 h-4 text-emerald-400" />
                  <h4 className="font-semibold text-xs text-white uppercase tracking-wider">
                    1. Verified Source Facts ({capcomResponse.verified_source_facts.length})
                  </h4>
                </div>

                <div className="space-y-2">
                  {capcomResponse.verified_source_facts.map((fact, idx) => (
                    <div key={idx} className="p-2.5 bg-slate-900 border border-hairline rounded text-xs">
                      <div className="text-slate-200">{fact.statement}</div>
                      <div className="text-[10px] text-slate-500 mt-1 flex items-center space-x-2">
                        <span>Source: <strong className="text-accent">{fact.source}</strong></span>
                        <span>•</span>
                        <span>Citation: {fact.citation}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* 2. Deterministic Calculations Section */}
              <div className="bg-panel border border-hairline rounded-lg p-5 shadow-panel space-y-3">
                <div className="flex items-center space-x-2 border-b border-hairline pb-2">
                  <Cpu className="w-4 h-4 text-sky-400" />
                  <h4 className="font-semibold text-xs text-white uppercase tracking-wider">
                    2. Deterministic Calculations ({Object.keys(capcomResponse.deterministic_calculations || {}).length})
                  </h4>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {Object.entries(capcomResponse.deterministic_calculations || {}).map(([key, calc]) => (
                    <div key={key} className="p-3 bg-slate-900 border border-hairline rounded text-xs">
                      <div className="text-slate-400 font-semibold">{calc.name}</div>
                      <div className="text-lg font-bold text-white tabular-nums mt-0.5">
                        {calc.value} {calc.unit}
                      </div>
                      <div className="text-[10px] text-accent mt-1">Formula: {calc.formula_reference}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* 3. AI Advisory Recommendations Section */}
              <div className="bg-panel border border-hairline rounded-lg p-5 shadow-panel space-y-3">
                <div className="flex items-center space-x-2 border-b border-hairline pb-2">
                  <ShieldAlert className="w-4 h-4 text-amber-400" />
                  <h4 className="font-semibold text-xs text-white uppercase tracking-wider">
                    3. Advisory Recommendations ({capcomResponse.ai_recommendations.length})
                  </h4>
                </div>

                <div className="space-y-3">
                  {capcomResponse.ai_recommendations.map((rec, idx) => (
                    <div key={idx} className="p-3 bg-slate-900 border border-hairline rounded space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-white">{rec.recommendation}</span>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold border ${
                            rec.priority === 'HIGH'
                              ? 'bg-red-950 text-red-400 border-red-800'
                              : 'bg-amber-950 text-amber-400 border-amber-800'
                          }`}
                        >
                          {rec.priority} PRIORITY
                        </span>
                      </div>
                      <div className="text-[11px] text-slate-300">{rec.engineering_rationale}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* 4. Active FDIR Findings Summary */}
              {capcomResponse.fdir_active_findings.length > 0 && (
                <div className="bg-panel border border-hairline rounded-lg p-5 shadow-panel space-y-3">
                  <div className="flex items-center space-x-2 border-b border-hairline pb-2">
                    <AlertTriangle className="w-4 h-4 text-red-400" />
                    <h4 className="font-semibold text-xs text-white uppercase tracking-wider">
                      4. Associated Active FDIR Findings ({capcomResponse.fdir_active_findings.length})
                    </h4>
                  </div>

                  <div className="space-y-2">
                    {capcomResponse.fdir_active_findings.map((f, idx) => (
                      <div key={idx} className="p-2.5 bg-red-950/20 border border-red-800/40 rounded text-xs">
                        <div className="flex items-center justify-between text-red-300 font-semibold">
                          <span>{f.rule_id} ({f.affected_subsystem})</span>
                          <span className="text-[10px] px-1.5 py-0.2 bg-red-900 rounded">{f.severity}</span>
                        </div>
                        <div className="text-slate-300 text-[11px] mt-1">{f.explanation}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 5. Unknown or Insufficient Data Section */}
              {capcomResponse.unknown_or_insufficient_data.length > 0 && (
                <div className="p-3 bg-purple-950/30 border border-purple-800/60 rounded-lg text-xs space-y-1">
                  <div className="text-purple-300 font-semibold uppercase text-[11px]">
                    Unknown or Insufficient Data Warnings:
                  </div>
                  {capcomResponse.unknown_or_insufficient_data.map((item, idx) => (
                    <div key={idx} className="text-slate-400 text-[11px]">
                      • {item}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: AUDIT TRAIL VIEW */}
      {activeTab === 'AUDIT' && (
        <div className="bg-panel border border-hairline rounded-lg p-5 shadow-panel space-y-4 font-mono text-xs">
          <div className="flex items-center justify-between border-b border-hairline pb-3">
            <div className="flex items-center space-x-2">
              <Clock className="w-4 h-4 text-accent" />
              <h3 className="font-semibold text-sm text-white uppercase tracking-wider">
                FDIR Anomaly Detection Audit Trail
              </h3>
            </div>
            <span className="text-slate-400 text-[11px]">{fdirHistory.length} Log Entries</span>
          </div>

          {fdirHistory.length === 0 ? (
            <div className="py-12 text-center text-slate-500 font-mono text-xs">
              NO ANOMALY AUDIT LOG ENTRIES RECORDED OR AUTHENTICATION REQUIRED.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse" aria-label="FDIR Audit Trail">
                <thead>
                  <tr className="border-b border-hairline text-slate-400 text-[10px] uppercase">
                    <th className="py-2 px-3">Timestamp</th>
                    <th className="py-2 px-3">Rule ID</th>
                    <th className="py-2 px-3">Severity</th>
                    <th className="py-2 px-3">Subsystem</th>
                    <th className="py-2 px-3">Explanation</th>
                    <th className="py-2 px-3 text-center">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline/30 text-[11px]">
                  {fdirHistory.map((item) => (
                    <tr key={item.id} className="text-slate-300 hover:bg-slate-900/50">
                      <td className="py-2 px-3 text-slate-400">
                        {new Date(item.created_at).toLocaleTimeString()}
                      </td>
                      <td className="py-2 px-3 text-white font-semibold">{item.rule_id}</td>
                      <td className="py-2 px-3">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                            item.severity === 'CRITICAL'
                              ? 'bg-red-950 text-red-400'
                              : item.severity === 'WARNING'
                              ? 'bg-orange-950 text-orange-400'
                              : 'bg-amber-950 text-amber-400'
                          }`}
                        >
                          {item.severity}
                        </span>
                      </td>
                      <td className="py-2 px-3">{item.affected_subsystem}</td>
                      <td className="py-2 px-3 max-w-xs truncate">{item.explanation}</td>
                      <td className="py-2 px-3 text-center">
                        {item.acknowledged ? (
                          <span className="text-emerald-400 font-semibold">ACKNOWLEDGED</span>
                        ) : (
                          <button
                            onClick={() => handleAcknowledge(item.id)}
                            className="px-2 py-0.5 rounded bg-panel-raised border border-amber-800/80 hover:bg-slate-700 text-amber-300 hover:text-white text-[10px]"
                            title="Acknowledge anomaly in audit log"
                            aria-label={`Acknowledge audit finding ${item.id}`}
                          >
                            ACKNOWLEDGE
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
