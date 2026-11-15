import React, { useState, useEffect, useCallback } from 'react';
import {
  api,
  ComponentItem,
  ComponentProvenanceResponse,
  ComponentSpecInput,
} from '../../lib/api';
import {
  Search,
  Layers,
  ShieldCheck,
  ExternalLink,
  Plus,
  Trash2,
  RefreshCw,
  AlertTriangle,
  FileCheck,
  X,
} from 'lucide-react';

export interface ComponentLedgerProps {
  configuredComponents: ComponentSpecInput[];
  onAddComponent: (comp: ComponentItem) => void;
  onRemoveComponent: (index: number) => void;
  selectedComponentId?: string | null;
  onSelectComponent?: (id: string | null) => void;
}

const SUBSYSTEM_OPTIONS = [
  'ALL',
  'STRUCTURE',
  'POWER',
  'PROPULSION',
  'TELECOM',
  'THERMAL',
  'SCIENCE',
  'ADCS',
  'PAYLOAD_SUPPORT',
];

const VERIFICATION_OPTIONS = [
  'ALL',
  'VERIFIED_AUTHORITATIVE',
  'DERIVED_FROM_FLIGHT_DATA',
  'ESTIMATED',
  'UNVERIFIED',
];

export const ComponentLedger: React.FC<ComponentLedgerProps> = ({
  configuredComponents,
  onAddComponent,
  onRemoveComponent,
  selectedComponentId,
  onSelectComponent,
}) => {
  const [catalogItems, setCatalogItems] = useState<ComponentItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Filter states
  const [subsystemFilter, setSubsystemFilter] = useState<string>('ALL');
  const [verificationFilter, setVerificationFilter] = useState<string>('ALL');
  const [minTrlFilter, setMinTrlFilter] = useState<number>(1);
  const [searchTerm, setSearchTerm] = useState<string>('');

  // Selected component provenance state
  const [provenanceData, setProvenanceData] = useState<ComponentProvenanceResponse | null>(null);
  const [provenanceLoading, setProvenanceLoading] = useState<boolean>(false);
  const [provenanceError, setProvenanceError] = useState<string | null>(null);

  const fetchCatalog = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getComponents({
        subsystem: subsystemFilter !== 'ALL' ? subsystemFilter : undefined,
        verification_status: verificationFilter !== 'ALL' ? verificationFilter : undefined,
        min_trl: minTrlFilter > 1 ? minTrlFilter : undefined,
        search: searchTerm.trim() ? searchTerm.trim() : undefined,
        limit: 50,
      });
      setCatalogItems(res.items || []);
      setTotalCount(res.total || 0);
    } catch (err: any) {
      setError(err?.message || 'Failed to load catalog components from API.');
    } finally {
      setLoading(false);
    }
  }, [subsystemFilter, verificationFilter, minTrlFilter, searchTerm]);

  useEffect(() => {
    fetchCatalog();
  }, [fetchCatalog]);

  // Fetch provenance when selected component changes
  useEffect(() => {
    if (!selectedComponentId) {
      setProvenanceData(null);
      return;
    }
    let isCancelled = false;
    const fetchProvenance = async () => {
      setProvenanceLoading(true);
      setProvenanceError(null);
      try {
        const prov = await api.getComponentProvenance(selectedComponentId);
        if (!isCancelled) {
          setProvenanceData(prov);
        }
      } catch (err: any) {
        if (!isCancelled) {
          setProvenanceError(err?.message || 'Provenance record unavailable.');
        }
      } finally {
        if (!isCancelled) setProvenanceLoading(false);
      }
    };
    fetchProvenance();
    return () => {
      isCancelled = true;
    };
  }, [selectedComponentId]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Column 1 & 2: Component Catalog & Search */}
      <div className="lg:col-span-2 bg-panel border border-hairline rounded-lg p-5 shadow-panel flex flex-col space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-hairline pb-3">
          <div className="flex items-center space-x-2">
            <Layers className="w-4 h-4 text-accent" />
            <h3 className="font-mono font-semibold text-sm uppercase text-white tracking-wider">
              Aerospace Component Catalog
            </h3>
            <span className="text-[11px] font-mono text-slate-400 bg-slate-800 px-2 py-0.5 rounded border border-hairline">
              {totalCount} Total
            </span>
          </div>

          <button
            onClick={() => fetchCatalog()}
            className="flex items-center space-x-1.5 text-xs font-mono text-slate-400 hover:text-white px-2 py-1 rounded bg-panel-raised border border-hairline"
            aria-label="Refresh Catalog"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>SYNC</span>
          </button>
        </div>

        {/* Filter controls */}
        <div className="grid grid-cols-1 sm:grid-cols-5 gap-3 text-xs font-mono">
          {/* Search box */}
          <div className="sm:col-span-2 relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search components..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 bg-slate-900 border border-hairline rounded text-white placeholder-slate-500 focus:outline-none focus:border-accent"
              aria-label="Search catalog components"
            />
          </div>

          {/* Subsystem filter */}
          <div>
            <select
              value={subsystemFilter}
              onChange={(e) => setSubsystemFilter(e.target.value)}
              className="w-full py-1.5 px-2 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent"
              aria-label="Filter by Subsystem"
            >
              {SUBSYSTEM_OPTIONS.map((sub) => (
                <option key={sub} value={sub}>
                  {sub === 'ALL' ? 'All Subsystems' : sub}
                </option>
              ))}
            </select>
          </div>

          {/* Verification status filter */}
          <div>
            <select
              value={verificationFilter}
              onChange={(e) => setVerificationFilter(e.target.value)}
              className="w-full py-1.5 px-2 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent"
              aria-label="Filter by Verification Status"
            >
              {VERIFICATION_OPTIONS.map((ver) => (
                <option key={ver} value={ver}>
                  {ver === 'ALL' ? 'All Verification' : ver.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </div>

          {/* Min TRL filter */}
          <div>
            <select
              value={minTrlFilter}
              onChange={(e) => setMinTrlFilter(Number(e.target.value))}
              className="w-full py-1.5 px-2 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent"
              aria-label="Filter by Minimum TRL"
            >
              <option value={1}>TRL 1-9</option>
              <option value={6}>TRL 6+ Flight Proto</option>
              <option value={8}>TRL 8+ Flight Qualified</option>
              <option value={9}>TRL 9 Flight Proven</option>
            </select>
          </div>
        </div>

        {/* Catalog Table */}
        {error && (
          <div
            role="alert"
            className="p-3 bg-red-950/60 border border-red-800 text-red-200 text-xs rounded flex items-center space-x-2"
          >
            <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="overflow-x-auto border border-hairline rounded bg-canvas max-h-[460px]">
          {loading && catalogItems.length === 0 ? (
            <div className="py-16 text-center text-slate-400 font-mono text-xs flex items-center justify-center space-x-2">
              <RefreshCw className="w-4 h-4 animate-spin text-accent" />
              <span>QUERYING PERSISTENT CATALOG...</span>
            </div>
          ) : catalogItems.length === 0 ? (
            <div className="py-16 text-center text-slate-500 font-mono text-xs">
              NO COMPONENTS MATCH ACTIVE SEARCH CRITERIA.
            </div>
          ) : (
            <table className="w-full text-left text-xs font-mono border-collapse" aria-label="Component Catalog List">
              <thead className="sticky top-0 bg-panel-raised border-b border-hairline text-slate-400 text-[10px] uppercase">
                <tr>
                  <th className="py-2.5 px-3">Subsystem</th>
                  <th className="py-2.5 px-3">Component Name</th>
                  <th className="py-2.5 px-3 text-center">TRL</th>
                  <th className="py-2.5 px-3 text-right">Mass (kg)</th>
                  <th className="py-2.5 px-3 text-right">Power Draw</th>
                  <th className="py-2.5 px-3">Provenance / Source</th>
                  <th className="py-2.5 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline/30">
                {catalogItems.map((comp) => {
                  const isSelected = selectedComponentId === comp.id;
                  return (
                    <tr
                      key={comp.id}
                      onClick={() => onSelectComponent && onSelectComponent(comp.id)}
                      className={`cursor-pointer transition-colors ${
                        isSelected ? 'bg-accent/15 text-white' : 'hover:bg-panel-raised/50 text-slate-300'
                      }`}
                      data-testid={`catalog-row-${comp.id}`}
                    >
                      <td className="py-2.5 px-3">
                        <span className="px-1.5 py-0.5 rounded bg-slate-800 border border-hairline text-[10px] text-slate-300">
                          {comp.subsystem}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-semibold text-white">
                        <div className="flex items-center space-x-1.5">
                          <span>{comp.name}</span>
                          {comp.techport_id && (
                            <span className="text-[9px] bg-sky-950 text-sky-400 border border-sky-800 px-1 rounded">
                              NASA
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        {comp.trl !== null && comp.trl !== undefined ? (
                          <span className="px-1.5 py-0.5 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800/60 font-semibold text-[10px]">
                            TRL {comp.trl}
                          </span>
                        ) : (
                          <span className="text-slate-500 italic text-[10px]">Not assessed</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums">
                        {comp.mass_kg !== null && comp.mass_kg !== undefined
                          ? comp.mass_kg.toFixed(2)
                          : <span className="text-slate-500 italic">Unavailable</span>}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums">
                        {comp.power_draw_w !== null && comp.power_draw_w !== undefined
                          ? `${comp.power_draw_w.toFixed(1)} W`
                          : <span className="text-slate-500 italic">Unavailable</span>}
                      </td>
                      <td className="py-2.5 px-3">
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded border ${
                            comp.verification_status === 'VERIFIED_AUTHORITATIVE'
                              ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800'
                              : comp.verification_status === 'DERIVED_FROM_FLIGHT_DATA'
                              ? 'bg-sky-950/60 text-sky-400 border-sky-800'
                              : 'bg-amber-950/60 text-amber-400 border-amber-800'
                          }`}
                        >
                          {comp.source_system || comp.verification_status}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onAddComponent(comp);
                          }}
                          className="px-2 py-1 rounded bg-accent/20 border border-accent/60 hover:bg-accent/40 text-accent font-semibold flex items-center space-x-1 ml-auto"
                          aria-label={`Add ${comp.name} to spacecraft`}
                        >
                          <Plus className="w-3 h-3" />
                          <span>ADD</span>
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Column 3: Field-Level Provenance & Configured Active Subsystems */}
      <div className="flex flex-col space-y-6">
        {/* Active Spacecraft Configuration Roster */}
        <div className="bg-panel border border-hairline rounded-lg p-5 shadow-panel flex flex-col space-y-3">
          <div className="flex items-center justify-between border-b border-hairline pb-2.5">
            <div className="flex items-center space-x-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <h3 className="font-mono font-semibold text-xs uppercase text-white tracking-wider">
                Configured Spacecraft Payload
              </h3>
            </div>
            <span className="font-mono text-xs text-slate-400">
              {configuredComponents.length} Selected
            </span>
          </div>

          {configuredComponents.length === 0 ? (
            <div className="py-8 text-center text-slate-500 font-mono text-xs">
              NO HARDWARE COMPONENTS ADDED YET. ADD COMPONENTS FROM THE CATALOG ON THE LEFT.
            </div>
          ) : (
            <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1">
              {configuredComponents.map((c, idx) => (
                <div
                  key={c.id || idx}
                  className="p-2.5 bg-slate-900 border border-hairline rounded flex items-center justify-between text-xs font-mono"
                >
                  <div>
                    <div className="text-white font-medium">{c.name}</div>
                    <div className="text-[10px] text-slate-400 flex items-center space-x-2 mt-0.5">
                      <span className="text-accent">{c.subsystem}</span>
                      <span>•</span>
                      <span>{c.mass_kg.toFixed(1)} kg</span>
                      <span>•</span>
                      <span>{c.power_draw_w.toFixed(1)} W</span>
                    </div>
                  </div>
                  <button
                    onClick={() => onRemoveComponent(idx)}
                    className="p-1 rounded text-red-400 hover:text-red-300 hover:bg-red-950/40 transition-colors"
                    title="Remove from spacecraft"
                    aria-label={`Remove ${c.name}`}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Selected Component Provenance Audit Panel */}
        <div className="bg-panel border border-hairline rounded-lg p-5 shadow-panel flex flex-col space-y-3">
          <div className="flex items-center justify-between border-b border-hairline pb-2.5">
            <div className="flex items-center space-x-2">
              <FileCheck className="w-4 h-4 text-accent" />
              <h3 className="font-mono font-semibold text-xs uppercase text-white tracking-wider">
                Field-Level Provenance Audit
              </h3>
            </div>
            {selectedComponentId && (
              <button
                onClick={() => onSelectComponent && onSelectComponent(null)}
                className="text-slate-400 hover:text-white"
                aria-label="Clear selection"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {!selectedComponentId ? (
            <div className="py-8 text-center text-slate-500 font-mono text-xs">
              SELECT ANY COMPONENT TO AUDIT ITS NASA SOURCE REPOSITORY & FLIGHT HERITAGE PROVENANCE.
            </div>
          ) : provenanceLoading ? (
            <div className="py-8 text-center text-slate-400 font-mono text-xs flex items-center justify-center space-x-2">
              <RefreshCw className="w-4 h-4 animate-spin text-accent" />
              <span>RETRIEVING PROVENANCE RECORDS...</span>
            </div>
          ) : provenanceError ? (
            <div className="p-3 bg-red-950/40 border border-red-800 text-red-300 text-xs rounded">
              {provenanceError}
            </div>
          ) : provenanceData ? (
            <div className="space-y-3 text-xs font-mono" data-testid="provenance-detail">
              <div>
                <div className="text-white font-semibold text-sm">{provenanceData.component_name}</div>
                <div className="text-slate-400 text-[11px] mt-0.5">ID: {provenanceData.component_id}</div>
              </div>

              <div className="grid grid-cols-2 gap-2 p-2 bg-slate-900 border border-hairline rounded text-[11px]">
                <div>
                  <span className="text-slate-500">Subsystem:</span>{' '}
                  <span className="text-slate-300">{provenanceData.subsystem}</span>
                </div>
                <div>
                  <span className="text-slate-500">Verification:</span>{' '}
                  <span className="text-emerald-400 font-semibold">
                    {provenanceData.verification_status}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Source:</span>{' '}
                  <span className="text-slate-300">{provenanceData.source_system || 'NASA Internal'}</span>
                </div>
                <div>
                  <span className="text-slate-500">TechPort ID:</span>{' '}
                  <span className="text-sky-400">{provenanceData.techport_id || 'Not linked'}</span>
                </div>
              </div>

              {provenanceData.source_url && (
                <div>
                  <a
                    href={provenanceData.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center space-x-1.5 text-accent hover:underline text-[11px]"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    <span>View Authoritative NASA Citation</span>
                  </a>
                </div>
              )}

              {/* Field Provenance Citations */}
              <div>
                <div className="text-slate-400 font-semibold mb-1 text-[11px]">Field Citations:</div>
                {Object.keys(provenanceData.field_provenance || {}).length === 0 ? (
                  <div className="text-slate-500 italic text-[11px]">
                    No granular field-level citations attached.
                  </div>
                ) : (
                  <div className="space-y-1.5 max-h-[160px] overflow-y-auto pr-1">
                    {Object.entries(provenanceData.field_provenance).map(([field, prov]: [string, any]) => (
                      <div
                        key={field}
                        className="p-1.5 bg-slate-900/80 border border-hairline rounded text-[10px]"
                      >
                        <span className="text-amber-400 font-semibold">{field}:</span>{' '}
                        {typeof prov === 'object' ? (
                          <span className="text-slate-300">
                            {prov.citation && <span>{prov.citation}</span>}
                            {prov.citation && prov.source && <span className="mx-1 text-slate-500">•</span>}
                            {prov.source && <span>{prov.source}</span>}
                            {!prov.citation && !prov.source && JSON.stringify(prov)}
                          </span>
                        ) : (
                          <span className="text-slate-300">{String(prov)}</span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};
