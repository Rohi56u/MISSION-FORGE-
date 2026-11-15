import React, { useEffect, useState, useCallback } from 'react';
import { api, TechPortProjectSummary, TechPortProjectDetail } from '../../lib/api';
import { Cpu, Search, RefreshCw, AlertCircle, ExternalLink, ChevronRight, Layers } from 'lucide-react';

export const TechPortFeed: React.FC = () => {
  const [projects, setProjects] = useState<TechPortProjectSummary[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [projectDetail, setProjectDetail] = useState<TechPortProjectDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);

  const fetchProjects = useCallback(async (query?: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getTechPortProjects(query);
      setProjects(data.projects || []);
      setTotalCount(data.total_count || 0);

      // Auto-select first project if none selected
      if (data.projects && data.projects.length > 0 && !selectedProjectId) {
        loadDetail(data.projects[0].id);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to query NASA TechPort database');
    } finally {
      setLoading(false);
    }
  }, [selectedProjectId]);

  const loadDetail = async (id: number) => {
    setSelectedProjectId(id);
    setLoadingDetail(true);
    try {
      const detail = await api.getTechPortProject(id);
      setProjectDetail(detail);
    } catch {
      // In case detail fails, detail will remain null
      setProjectDetail(null);
    } finally {
      setLoadingDetail(false);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchProjects(searchQuery);
  };

  return (
    <section
      aria-labelledby="techport-feed-heading"
      className="bg-panel border border-hairline rounded-lg p-5 shadow-panel"
      data-testid="techport-feed-section"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-hairline mb-4 gap-2">
        <div className="flex items-center space-x-2.5">
          <Cpu className="w-5 h-5 text-accent" />
          <div>
            <h2 id="techport-feed-heading" className="text-sm font-semibold tracking-wide text-white uppercase font-mono">
              NASA TechPort R&D Feed
            </h2>
            <div className="text-[11px] text-slate-400">
              Space Technology Mission Directorate (STMD) Research Initiatives & TRL Milestones
            </div>
          </div>
        </div>

        {/* Search Bar */}
        <form onSubmit={handleSearchSubmit} className="flex items-center space-x-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search technologies..."
              className="pl-8 pr-3 py-1 bg-panel-raised border border-hairline rounded text-xs text-white placeholder-slate-400 focus:outline-none focus:border-accent w-48 sm:w-64 font-mono"
              aria-label="Search NASA TechPort projects"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="px-2.5 py-1 bg-panel-raised hover:bg-slate-800 text-xs text-slate-200 border border-hairline rounded font-mono transition"
          >
            Filter
          </button>
        </form>
      </div>

      {loading && !projects.length && (
        <div className="py-12 text-center text-slate-400 text-xs font-mono flex items-center justify-center space-x-2">
          <RefreshCw className="w-4 h-4 animate-spin motion-reduce:animate-none text-accent" />
          <span>Synchronizing NASA TechPort project portfolio...</span>
        </div>
      )}

      {error && !projects.length && (
        <div className="p-3 bg-red-950/40 border border-status-alert/40 rounded text-xs text-red-300 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 text-status-alert flex-shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={() => fetchProjects(searchQuery)}
            className="text-xs bg-red-900/60 hover:bg-red-800 text-white px-2 py-1 rounded border border-red-700 transition"
          >
            Retry
          </button>
        </div>
      )}

      {/* Main Content Layout: List on left, details on right */}
      {!loading && projects.length === 0 && (
        <div className="py-8 text-center text-slate-400 text-xs font-mono">
          No matching NASA TechPort projects found for query &ldquo;{searchQuery}&rdquo;.
        </div>
      )}

      {projects.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          {/* Projects Listing Column */}
          <div className="lg:col-span-5 space-y-2 max-h-[500px] overflow-y-auto pr-1">
            <div className="flex justify-between items-center text-[11px] font-mono text-slate-400 px-1 mb-1">
              <span>Showing {projects.length} of {totalCount} initiatives</span>
              <span>Select to inspect</span>
            </div>

            {projects.map((proj) => {
              const isSelected = selectedProjectId === proj.id;
              return (
                <button
                  key={proj.id}
                  onClick={() => loadDetail(proj.id)}
                  className={`w-full text-left p-3 rounded border transition flex items-center justify-between group ${
                    isSelected
                      ? 'bg-panel-raised border-accent text-white shadow-panel'
                      : 'bg-panel border-hairline text-slate-300 hover:bg-panel-raised/60'
                  }`}
                  aria-pressed={isSelected}
                  data-testid={`techport-item-${proj.id}`}
                >
                  <div className="pr-2">
                    <div className="flex items-center space-x-2 mb-1">
                      <span className="text-[10px] font-mono text-accent bg-sky-950/80 px-1.5 py-0.5 rounded border border-sky-800">
                        ID #{proj.id}
                      </span>
                      {proj.last_updated && (
                        <span className="text-[10px] font-mono text-slate-400">
                          {proj.last_updated}
                        </span>
                      )}
                    </div>
                    <div className="text-xs font-semibold line-clamp-2 leading-tight">
                      {proj.title}
                    </div>
                  </div>
                  <ChevronRight
                    className={`w-4 h-4 flex-shrink-0 transition-transform ${
                      isSelected ? 'text-accent translate-x-1' : 'text-slate-600 group-hover:text-slate-400'
                    }`}
                  />
                </button>
              );
            })}
          </div>

          {/* Detailed Project Inspector Column */}
          <div className="lg:col-span-7 bg-panel-raised border border-hairline rounded-lg p-4 flex flex-col justify-between">
            {loadingDetail ? (
              <div className="py-20 text-center text-slate-400 text-xs font-mono flex items-center justify-center space-x-2">
                <RefreshCw className="w-4 h-4 animate-spin motion-reduce:animate-none text-accent" />
                <span>Loading technology assessment details...</span>
              </div>
            ) : projectDetail ? (
              <div className="space-y-4" data-testid="techport-detail-panel">
                {/* Header */}
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center space-x-2">
                      <span className="text-[10px] font-mono uppercase bg-slate-800 text-slate-300 px-2 py-0.5 rounded border border-hairline">
                        {projectDetail.status || 'Active R&D'}
                      </span>
                      <span className="text-xs font-mono text-accent">ID #{projectDetail.id}</span>
                    </div>
                    {projectDetail.canonical_url && (projectDetail.canonical_url.startsWith('https://') || projectDetail.canonical_url.startsWith('http://')) && (
                      <a
                        href={projectDetail.canonical_url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="text-xs text-slate-400 hover:text-white flex items-center space-x-1 font-mono transition"
                      >
                        <span>NASA Portal</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>

                  <h3 className="text-base font-bold text-white mt-2 leading-snug">
                    {projectDetail.title}
                  </h3>
                </div>

                {/* Organization & Program */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono bg-panel border border-hairline p-3 rounded">
                  <div>
                    <span className="text-slate-400 text-[10px] block uppercase font-semibold">
                      Lead Organization
                    </span>
                    <span className="text-slate-200 font-medium">
                      {projectDetail.lead_organization || 'NASA Center / Directorate'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 text-[10px] block uppercase font-semibold">
                      Funding Program
                    </span>
                    <span className="text-slate-200 font-medium">
                      {projectDetail.program || 'Space Technology Mission Directorate'}
                    </span>
                  </div>
                </div>

                {/* TRL Progression Gauge */}
                <div className="bg-panel border border-hairline p-3 rounded">
                  <div className="flex items-center justify-between text-xs font-mono mb-2">
                    <span className="text-slate-400 flex items-center space-x-1.5 font-semibold">
                      <Layers className="w-3.5 h-3.5 text-accent" />
                      <span>TECHNOLOGY READINESS LEVEL (TRL 1–9)</span>
                    </span>
                    <span className="text-white font-bold tabular-nums">
                      Current: {projectDetail.trl_current != null ? `TRL ${projectDetail.trl_current}` : projectDetail.trl_begin != null ? `TRL ${projectDetail.trl_begin}` : 'Not Assessed'}
                    </span>
                  </div>

                  {/* 9-step discrete TRL progress bar */}
                  <div className="grid grid-cols-9 gap-1 text-center font-mono text-[10px]">
                    {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((lvl) => {
                      const assessedTrl = projectDetail.trl_current ?? projectDetail.trl_begin ?? null;
                      const target = projectDetail.trl_end ?? null;
                      const isCompleted = assessedTrl !== null && lvl <= assessedTrl;
                      const isTarget = assessedTrl !== null && target !== null && lvl <= target && lvl > assessedTrl;

                      return (
                        <div key={lvl} className="flex flex-col items-center">
                          <div
                            className={`w-full h-2 rounded-sm mb-1 ${
                              isCompleted
                                ? 'bg-status-nominal'
                                : isTarget
                                ? 'bg-accent/40 border border-accent/60'
                                : 'bg-slate-800'
                            }`}
                          />
                          <span
                            className={`tabular-nums ${
                              isCompleted ? 'text-white font-bold' : 'text-slate-400'
                            }`}
                          >
                            {lvl}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                  <div className="flex justify-between text-[10px] font-mono text-slate-400 mt-2">
                    <span>TRL Begin: {projectDetail.trl_begin ?? 'N/A'}</span>
                    <span>TRL Target: {projectDetail.trl_end ?? 'N/A'}</span>
                  </div>
                </div>

                {/* Description */}
                {projectDetail.description && (
                  <div>
                    <span className="text-[10px] font-mono uppercase text-slate-400 font-semibold tracking-wider block mb-1">
                      Technology Scope & Objectives
                    </span>
                    <p className="text-xs text-slate-300 leading-relaxed max-h-36 overflow-y-auto pr-1">
                      {projectDetail.description}
                    </p>
                  </div>
                )}

                {/* Benefits */}
                {projectDetail.benefits && (
                  <div className="pt-2 border-t border-hairline">
                    <span className="text-[10px] font-mono uppercase text-slate-400 font-semibold tracking-wider block mb-1">
                      Aerospace Exploration Benefits
                    </span>
                    <p className="text-xs text-slate-300 leading-relaxed line-clamp-3">
                      {projectDetail.benefits}
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <div className="py-20 text-center text-slate-400 text-xs font-mono">
                Select an initiative to inspect NASA Space Technology Mission Directorate details.
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
};
