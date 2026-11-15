import React, { useState, useEffect, useCallback } from 'react';
import {
  api,
  Mission,
  DossierJobResponse,
  DossierReportMetadata,
  getAuthToken,
} from '../lib/api';
import {
  FileText,
  Download,
  Eye,
  RefreshCw,
  ShieldCheck,
  ExternalLink,
  Copy,
  BookOpen,
  Lock,
  ZoomIn,
  ZoomOut,
  FileCode,
} from 'lucide-react';

export const MissionDossierCenter: React.FC = () => {
  // Mission state
  const [missions, setMissions] = useState<Mission[]>([]);
  const [selectedMissionId, setSelectedMissionId] = useState<string>('');

  // Generation Request Form State
  const [dossierTitle, setDossierTitle] = useState<string>('Flight Architecture Dossier');
  const [exportFormat, setExportFormat] = useState<'PDF' | 'JSON' | 'BOTH'>('BOTH');
  const [includeCdf, setIncludeCdf] = useState<boolean>(true);
  const [includeFdir, setIncludeFdir] = useState<boolean>(true);
  const [includeCapcom, setIncludeCapcom] = useState<boolean>(true);

  // Active Job Tracker
  const [activeJob, setActiveJob] = useState<DossierJobResponse | null>(null);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [generationError, setGenerationError] = useState<string | null>(null);

  // Compiled Reports List
  const [reports, setReports] = useState<DossierReportMetadata[]>([]);
  const [loadingReports, setLoadingReports] = useState<boolean>(false);

  // Previewer State
  const [selectedReport, setSelectedReport] = useState<DossierReportMetadata | null>(null);
  const [previewMode, setPreviewMode] = useState<'NONE' | 'PDF' | 'JSON'>('NONE');
  const [jsonContent, setJsonContent] = useState<string | null>(null);
  const [loadingJson, setLoadingJson] = useState<boolean>(false);
  const [copiedJson, setCopiedJson] = useState<boolean>(false);
  const [showFullJson, setShowFullJson] = useState<boolean>(false);

  // Real client-side cryptographic SHA-256 verification map
  const [verificationStatus, setVerificationStatus] = useState<
    Record<
      string,
      {
        state: 'VERIFIED' | 'MISMATCH' | 'VERIFYING';
        computedHash?: string;
        expectedHash?: string;
        formatVerified?: string;
        error?: string;
      }
    >
  >({});

  // PDF Preview Zoom
  const [pdfZoom, setPdfZoom] = useState<number>(100);

  // Signed URL State
  const [signedUrlData, setSignedUrlData] = useState<{
    url: string;
    expiresIn?: number;
    provider: string;
  } | null>(null);

  // 1. Load missions on mount
  useEffect(() => {
    const init = async () => {
      try {
        const missionsData = await api.getMissions();
        setMissions(missionsData);
        if (missionsData.length > 0) {
          setSelectedMissionId(missionsData[0].id);
        }
      } catch (err) {
        console.error('Failed to load missions', err);
      }
    };
    init();
  }, []);

  // 2. Load compiled dossiers when selected mission changes
  const fetchReports = useCallback(async () => {
    if (!selectedMissionId) return;
    setLoadingReports(true);
    try {
      const res = await api.listMissionDossiers(selectedMissionId);
      setReports(res.reports || []);
      if (res.reports && res.reports.length > 0 && !selectedReport) {
        setSelectedReport(res.reports[0]);
      }
    } catch (err) {
      console.error('Failed to load mission dossiers', err);
    } finally {
      setLoadingReports(false);
    }
  }, [selectedMissionId, selectedReport]);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  // 3. Polling active dossier job status
  useEffect(() => {
    if (!activeJob || activeJob.status === 'COMPLETED' || activeJob.status === 'FAILED') {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const updated = await api.getDossierJobStatus(activeJob.job_id);
        setActiveJob(updated);
        if (updated.status === 'COMPLETED') {
          fetchReports();
          if (updated.report_id) {
            const rep = await api.getDossierReport(updated.report_id);
            setSelectedReport(rep);
          }
        }
      } catch (e) {
        console.error('Failed to poll dossier job status', e);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [activeJob, fetchReports]);

  // Submit Dossier Generation Job
  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedMissionId) return;
    setSubmitting(true);
    setGenerationError(null);
    try {
      const job = await api.generateDossier({
        mission_id: selectedMissionId,
        title: dossierTitle,
        format: exportFormat,
        include_cdf_history: includeCdf,
        include_fdir_audit: includeFdir,
        include_capcom_summary: includeCapcom,
      });
      setActiveJob(job);
    } catch (err: any) {
      setGenerationError(err?.message || 'Failed to submit dossier generation job.');
    } finally {
      setSubmitting(false);
    }
  };

  // Client-Side Cryptographic SHA-256 Digest Helper using Web Crypto API
  const computeSha256Digest = async (data: ArrayBuffer): Promise<string> => {
    const cryptoObj =
      (typeof window !== 'undefined' && (window.crypto || (window as any).msCrypto)) || globalThis.crypto;
    const hashBuffer = await cryptoObj.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
  };

  // Explicit Client-Side SHA-256 Recomputation & Verification
  const verifyArtifactIntegrity = async (
    report: DossierReportMetadata,
    formatToVerify: 'json' | 'pdf' = 'json'
  ) => {
    const expectedHash = formatToVerify === 'pdf' ? report.pdf_sha256 : report.json_sha256;
    if (!expectedHash) {
      setVerificationStatus((prev) => ({
        ...prev,
        [report.id]: {
          state: 'MISMATCH',
          error: `No ${formatToVerify.toUpperCase()} digest recorded by server.`,
        },
      }));
      return;
    }

    setVerificationStatus((prev) => ({
      ...prev,
      [report.id]: {
        state: 'VERIFYING',
        expectedHash,
        formatVerified: formatToVerify.toUpperCase(),
      },
    }));

    try {
      const token = getAuthToken();
      const headers: Record<string, string> = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch(
        `/api/v1/dossiers/${encodeURIComponent(report.id)}/download?format=${formatToVerify}`,
        { headers }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);

      const buffer = await res.arrayBuffer();
      const computedHex = await computeSha256Digest(buffer);
      const isMatch = computedHex.toLowerCase() === expectedHash.toLowerCase();

      setVerificationStatus((prev) => ({
        ...prev,
        [report.id]: {
          state: isMatch ? 'VERIFIED' : 'MISMATCH',
          computedHash: computedHex,
          expectedHash,
          formatVerified: formatToVerify.toUpperCase(),
          error: isMatch ? undefined : 'Computed SHA-256 digest does not match server expected hash.',
        },
      }));
    } catch (err: any) {
      setVerificationStatus((prev) => ({
        ...prev,
        [report.id]: {
          state: 'MISMATCH',
          error: err?.message || 'Verification network request failed.',
        },
      }));
    }
  };

  // Inspect JSON Snapshot with real-time SHA-256 integrity verification
  const handleInspectJson = async (report: DossierReportMetadata) => {
    setSelectedReport(report);
    setPreviewMode('JSON');
    setLoadingJson(true);
    setJsonContent(null);
    setShowFullJson(false);
    try {
      const token = getAuthToken();
      const headers: Record<string, string> = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch(`/api/v1/dossiers/${encodeURIComponent(report.id)}/download?format=json`, {
        headers,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const buffer = await res.arrayBuffer();
      const decoder = new TextDecoder('utf-8');
      const text = decoder.decode(buffer);

      // Recompute and verify SHA-256 digest
      if (report.json_sha256) {
        try {
          const computedHex = await computeSha256Digest(buffer);
          const isMatch = computedHex.toLowerCase() === report.json_sha256.toLowerCase();
          setVerificationStatus((prev) => ({
            ...prev,
            [report.id]: {
              state: isMatch ? 'VERIFIED' : 'MISMATCH',
              computedHash: computedHex,
              expectedHash: report.json_sha256 || undefined,
              formatVerified: 'JSON',
              error: isMatch ? undefined : 'Computed SHA-256 digest does not match server expected hash.',
            },
          }));
        } catch {
          // non-blocking
        }
      }

      try {
        const parsed = JSON.parse(text);
        setJsonContent(JSON.stringify(parsed, null, 2));
      } catch {
        setJsonContent(text);
      }
    } catch (err: any) {
      setJsonContent(`Error loading JSON snapshot: ${err.message}`);
    } finally {
      setLoadingJson(false);
    }
  };

  // Inspect PDF
  const handleInspectPdf = (report: DossierReportMetadata) => {
    setSelectedReport(report);
    setPreviewMode('PDF');
  };

  // Request Expiring Signed URL
  const handleGetSignedUrl = async (reportId: string, format: 'pdf' | 'json') => {
    try {
      const res = await api.getDossierSignedUrl(reportId, format, 3600);
      setSignedUrlData({
        url: res.download_url,
        expiresIn: res.expires_in_seconds,
        provider: res.storage_provider,
      });
    } catch (err: any) {
      alert(`Signed URL retrieval failed: ${err.message}`);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      {/* Header Bar */}
      <div className="bg-panel border border-hairline rounded-lg p-5 shadow-panel flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <FileText className="w-5 h-5 text-accent" />
            <h1 className="text-xl font-bold font-mono tracking-wider text-white uppercase">
              Phase 13 — Mission Dossier & Artifact Export Center
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Tamper-evident mission concept dossiers, cryptographic SHA-256 digests, in-browser PDF rendering, and structured JSON snapshots.
          </p>
        </div>

        {/* Mission Selector */}
        <div className="flex items-center space-x-3 text-xs font-mono">
          <label htmlFor="dossier-mission-select" className="text-slate-400">Target Mission:</label>
          <select
            id="dossier-mission-select"
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

      {/* Generation Request Form & Active Job Tracker Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Dossier Generation Request Form */}
        <form
          onSubmit={handleGenerate}
          className="lg:col-span-2 bg-panel border border-hairline rounded-lg p-5 shadow-panel space-y-4 font-mono text-xs"
        >
          <div className="flex items-center justify-between border-b border-hairline pb-2.5">
            <div className="flex items-center space-x-2">
              <BookOpen className="w-4 h-4 text-accent" />
              <h3 className="font-semibold text-sm text-white uppercase tracking-wider">
                Generate Certified Mission Dossier
              </h3>
            </div>
            <span className="text-[10px] text-slate-400">Deterministic Engine</span>
          </div>

          {generationError && (
            <div className="p-3 bg-red-950/80 border border-red-800 text-red-200 rounded">
              {generationError}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-slate-400 block mb-1">Dossier Title:</label>
              <input
                type="text"
                value={dossierTitle}
                onChange={(e) => setDossierTitle(e.target.value)}
                required
                className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent"
              />
            </div>

            <div>
              <label className="text-slate-400 block mb-1">Export Format:</label>
              <select
                value={exportFormat}
                onChange={(e) => setExportFormat(e.target.value as 'PDF' | 'JSON' | 'BOTH')}
                className="w-full px-3 py-1.5 bg-slate-900 border border-hairline rounded text-white focus:outline-none focus:border-accent"
              >
                <option value="BOTH">Both (PDF Report & Frozen JSON Snapshot)</option>
                <option value="PDF">PDF Report Only</option>
                <option value="JSON">Frozen JSON Snapshot Only</option>
              </select>
            </div>
          </div>

          {/* Section Inclusions Checkboxes */}
          <div className="p-3 bg-slate-900 rounded border border-hairline space-y-2">
            <div className="text-slate-400 font-semibold mb-1">Include Mission Sections:</div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <label className="flex items-center space-x-2 cursor-pointer text-slate-300">
                <input
                  type="checkbox"
                  checked={includeCdf}
                  onChange={(e) => setIncludeCdf(e.target.checked)}
                  className="rounded border-hairline bg-slate-800 text-accent"
                />
                <span>CDF Revision History</span>
              </label>

              <label className="flex items-center space-x-2 cursor-pointer text-slate-300">
                <input
                  type="checkbox"
                  checked={includeFdir}
                  onChange={(e) => setIncludeFdir(e.target.checked)}
                  className="rounded border-hairline bg-slate-800 text-accent"
                />
                <span>Deterministic FDIR Audit</span>
              </label>

              <label className="flex items-center space-x-2 cursor-pointer text-slate-300">
                <input
                  type="checkbox"
                  checked={includeCapcom}
                  onChange={(e) => setIncludeCapcom(e.target.checked)}
                  className="rounded border-hairline bg-slate-800 text-accent"
                />
                <span>CAPCOM Advisory Summary</span>
              </label>
            </div>
          </div>

          <button
            type="submit"
            disabled={submitting || Boolean(activeJob && (activeJob.status === 'RUNNING' || activeJob.status === 'QUEUED'))}
            className="w-full py-2.5 bg-accent text-canvas font-semibold rounded hover:bg-accent/90 transition-all flex items-center justify-center space-x-2 disabled:opacity-50"
          >
            <Download className="w-4 h-4" />
            <span>{submitting ? 'DISPATCHING WORKER...' : 'COMPILE MISSION DOSSIER'}</span>
          </button>
        </form>

        {/* Real-Time Job Progress Tracker */}
        <div className="bg-panel border border-hairline rounded-lg p-5 shadow-panel space-y-3 font-mono text-xs flex flex-col justify-between">
          <div className="border-b border-hairline pb-2.5 flex items-center justify-between">
            <h3 className="font-semibold text-xs text-white uppercase tracking-wider">
              Asynchronous Compilation Job
            </h3>
            {activeJob && (
              <span
                className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                  activeJob.status === 'COMPLETED'
                    ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                    : activeJob.status === 'RUNNING'
                    ? 'bg-sky-950 text-sky-400 border border-sky-800 animate-pulse'
                    : activeJob.status === 'FAILED'
                    ? 'bg-red-950 text-red-400 border border-red-800'
                    : 'bg-slate-800 text-slate-300 border border-hairline'
                }`}
              >
                {activeJob.status}
              </span>
            )}
          </div>

          {!activeJob ? (
            <div className="py-8 text-center text-slate-500 text-xs">
              NO ACTIVE BACKGROUND COMPILATION JOB. CLICK 'COMPILE' TO INITIATE.
            </div>
          ) : (
            <div className="space-y-3" data-testid="active-dossier-job">
              <div>
                <div className="flex justify-between text-[11px] text-slate-400 mb-1">
                  <span>Authoritative Progress:</span>
                  <span className="text-white font-semibold tabular-nums">
                    {Math.round(activeJob.progress_percent)}%
                  </span>
                </div>
                {/* Progress bar */}
                <div className="w-full h-2 bg-slate-900 rounded-full overflow-hidden border border-hairline">
                  <div
                    className="h-full bg-accent transition-all duration-300"
                    style={{ width: `${Math.max(5, activeJob.progress_percent)}%` }}
                  />
                </div>
              </div>

              <div className="p-2.5 bg-slate-900 rounded border border-hairline text-[10px] space-y-1">
                <div>Job ID: <span className="text-slate-300 font-mono">{activeJob.job_id}</span></div>
                <div>Format: <span className="text-accent">{activeJob.format}</span></div>
                <div>Created: <span className="text-slate-300">{new Date(activeJob.created_at).toLocaleTimeString()}</span></div>
                {activeJob.completed_at && (
                  <div>Completed: <span className="text-emerald-400">{new Date(activeJob.completed_at).toLocaleTimeString()}</span></div>
                )}
                {activeJob.error_message && (
                  <div className="text-red-400 font-semibold mt-1">Error: {activeJob.error_message}</div>
                )}
              </div>
            </div>
          )}

          <div className="text-[10px] text-slate-500 border-t border-hairline pt-2">
            No synthetic percentages. Progress reflects real worker task completion.
          </div>
        </div>
      </div>

      {/* Compiled Dossier Reports Catalog Table */}
      <div className="bg-panel border border-hairline rounded-lg p-5 shadow-panel space-y-4 font-mono text-xs">
        <div className="flex items-center justify-between border-b border-hairline pb-2.5">
          <div className="flex items-center space-x-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <h3 className="font-semibold text-sm text-white uppercase tracking-wider">
              Compiled Dossiers & Cryptographic Artifacts
            </h3>
          </div>
          <button
            onClick={() => fetchReports()}
            className="flex items-center space-x-1 px-2 py-1 rounded bg-panel-raised border border-hairline text-slate-400 hover:text-white"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingReports ? 'animate-spin' : ''}`} />
            <span>REFRESH</span>
          </button>
        </div>

        {reports.length === 0 ? (
          <div className="py-12 text-center text-slate-500 font-mono text-xs">
            NO COMPILED DOSSIERS GENERATED YET FOR THIS MISSION.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse" aria-label="Compiled Mission Dossiers">
              <thead>
                <tr className="border-b border-hairline text-slate-400 text-[10px] uppercase">
                  <th className="py-2.5 px-3">Title</th>
                  <th className="py-2.5 px-3">Compiled Date</th>
                  <th className="py-2.5 px-3 text-center">Format</th>
                  <th className="py-2.5 px-3 text-center">Pages</th>
                  <th className="py-2.5 px-3 text-right">PDF Size</th>
                  <th className="py-2.5 px-3 text-right">JSON Size</th>
                  <th className="py-2.5 px-3 text-center">SHA-256 Digest</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline/30 text-[11px]">
                {reports.map((rep) => {
                  const isSelected = selectedReport?.id === rep.id;
                  return (
                    <tr
                      key={rep.id}
                      onClick={() => setSelectedReport(rep)}
                      className={`cursor-pointer transition-colors ${
                        isSelected ? 'bg-accent/15 text-white' : 'text-slate-300 hover:bg-slate-900/60'
                      }`}
                      data-testid={`report-row-${rep.id}`}
                    >
                      <td className="py-2.5 px-3 font-semibold text-white">{rep.title}</td>
                      <td className="py-2.5 px-3 text-slate-400">
                        {new Date(rep.created_at).toLocaleDateString()} {new Date(rep.created_at).toLocaleTimeString()}
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        <span className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-accent">
                          {rep.format}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-center tabular-nums">{rep.page_count}</td>
                      <td className="py-2.5 px-3 text-right tabular-nums">
                        {rep.pdf_size_bytes ? `${(rep.pdf_size_bytes / 1024).toFixed(1)} KB` : '--'}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums">
                        {rep.json_size_bytes ? `${(rep.json_size_bytes / 1024).toFixed(1)} KB` : '--'}
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        {verificationStatus[rep.id]?.state === 'VERIFIED' ? (
                          <span
                            className="px-1.5 py-0.5 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800 text-[10px] font-semibold flex items-center justify-center space-x-1"
                            title={`Recomputed match for ${verificationStatus[rep.id]?.formatVerified}\nDigest: ${verificationStatus[rep.id]?.computedHash}`}
                          >
                            <ShieldCheck className="w-3 h-3 text-emerald-400" />
                            <span>SHA-256 VERIFIED</span>
                          </span>
                        ) : verificationStatus[rep.id]?.state === 'MISMATCH' ? (
                          <span
                            className="px-1.5 py-0.5 rounded bg-red-950/80 text-red-400 border border-red-800 text-[10px] font-semibold"
                            title={verificationStatus[rep.id]?.error}
                          >
                            CHECKSUM MISMATCH
                          </span>
                        ) : verificationStatus[rep.id]?.state === 'VERIFYING' ? (
                          <span className="text-accent text-[10px] animate-pulse">VERIFYING...</span>
                        ) : rep.pdf_sha256 || rep.json_sha256 ? (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              verifyArtifactIntegrity(rep, rep.json_sha256 ? 'json' : 'pdf');
                            }}
                            className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-hairline text-[10px] transition"
                            title="Recompute SHA-256 in client and verify against recorded hash"
                            aria-label={`Verify SHA-256 for ${rep.title}`}
                          >
                            VERIFY CHECKSUM
                          </button>
                        ) : (
                          <span className="text-slate-500 italic text-[10px]">Unrecorded</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-right space-x-1">
                        {/* PDF Inspect */}
                        {rep.pdf_size_bytes && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleInspectPdf(rep);
                            }}
                            className="px-2 py-1 rounded bg-panel-raised border border-hairline hover:bg-slate-700 text-slate-300"
                            title="Inspect PDF in browser"
                            aria-label="Inspect PDF in browser"
                          >
                            <Eye className="w-3 h-3 inline mr-1" />
                            <span>PDF</span>
                          </button>
                        )}

                        {/* JSON Inspect */}
                        {rep.json_size_bytes && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleInspectJson(rep);
                            }}
                            className="px-2 py-1 rounded bg-panel-raised border border-hairline hover:bg-slate-700 text-slate-300"
                            title="Inspect JSON snapshot"
                            aria-label="Inspect JSON snapshot"
                          >
                            <FileCode className="w-3 h-3 inline mr-1" />
                            <span>JSON</span>
                          </button>
                        )}

                        {/* Direct Download */}
                        <a
                          href={`/api/v1/dossiers/${rep.id}/download?format=${rep.pdf_size_bytes ? 'pdf' : 'json'}`}
                          download
                          onClick={(e) => e.stopPropagation()}
                          className="px-2 py-1 rounded bg-accent/20 border border-accent/60 text-accent font-semibold hover:bg-accent/30 inline-block"
                          title="Direct Authenticated Download"
                        >
                          <Download className="w-3 h-3 inline" />
                        </a>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Selected Dossier Cryptographic Details Drawer */}
      {selectedReport && (
        <div className="bg-panel border border-hairline rounded-lg p-5 shadow-panel space-y-4 font-mono text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-hairline pb-2.5">
            <div>
              <h3 className="font-semibold text-sm text-white uppercase">{selectedReport.title}</h3>
              <div className="text-[11px] text-slate-400 mt-0.5">ID: {selectedReport.id}</div>
            </div>

            <div className="flex items-center space-x-2">
              <button
                onClick={() => handleGetSignedUrl(selectedReport.id, 'pdf')}
                className="px-2.5 py-1 rounded bg-slate-900 border border-hairline text-slate-300 hover:text-white flex items-center space-x-1"
              >
                <Lock className="w-3 h-3 text-accent" />
                <span>GET EXPIRING CLOUD URL</span>
              </button>
            </div>
          </div>

          {/* Cryptographic Hash Summary */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="p-3 bg-slate-900 rounded border border-hairline space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-slate-400 font-semibold text-[10px]">PDF ARTIFACT SHA-256 DIGEST:</span>
                {selectedReport.pdf_sha256 && (
                  <button
                    onClick={() => verifyArtifactIntegrity(selectedReport, 'pdf')}
                    className="text-[10px] text-accent hover:underline font-semibold"
                  >
                    VERIFY PDF
                  </button>
                )}
              </div>
              <div className="text-emerald-400 text-[11px] break-all select-all">
                {selectedReport.pdf_sha256 || 'NOT APPLICABLE (JSON ONLY EXPORT)'}
              </div>
            </div>

            <div className="p-3 bg-slate-900 rounded border border-hairline space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-slate-400 font-semibold text-[10px]">JSON SNAPSHOT SHA-256 DIGEST:</span>
                {selectedReport.json_sha256 && (
                  <button
                    onClick={() => verifyArtifactIntegrity(selectedReport, 'json')}
                    className="text-[10px] text-accent hover:underline font-semibold"
                  >
                    VERIFY JSON
                  </button>
                )}
              </div>
              <div className="text-accent text-[11px] break-all select-all">
                {selectedReport.json_sha256 || 'NOT APPLICABLE (PDF ONLY EXPORT)'}
              </div>
            </div>
          </div>

          {/* Verification Audit Details if computed */}
          {verificationStatus[selectedReport.id] && (
            <div
              className={`p-3 rounded border text-[11px] flex items-center justify-between ${
                verificationStatus[selectedReport.id].state === 'VERIFIED'
                  ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300'
                  : verificationStatus[selectedReport.id].state === 'VERIFYING'
                  ? 'bg-sky-950/40 border-sky-800 text-sky-300'
                  : 'bg-red-950/40 border-red-800 text-red-300'
              }`}
            >
              <div className="flex items-center space-x-2">
                <ShieldCheck className="w-4 h-4 flex-shrink-0" />
                <div>
                  <span className="font-semibold">
                    Client Cryptographic Verification ({verificationStatus[selectedReport.id].formatVerified}):{' '}
                  </span>
                  <span>
                    {verificationStatus[selectedReport.id].state === 'VERIFIED'
                      ? 'Recomputed SHA-256 matches server attested digest.'
                      : verificationStatus[selectedReport.id].state === 'VERIFYING'
                      ? 'Fetching bytes and hashing in client...'
                      : verificationStatus[selectedReport.id].error || 'Digest mismatch detected.'}
                  </span>
                  {verificationStatus[selectedReport.id].computedHash && (
                    <div className="text-[10px] opacity-80 break-all select-all mt-0.5 font-mono">
                      Computed: {verificationStatus[selectedReport.id].computedHash}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {signedUrlData && (
            <div className="p-3 bg-slate-900 border border-accent/40 rounded space-y-1">
              <div className="text-slate-300 font-semibold">
                Expiring Signed URL ({signedUrlData.provider}):
              </div>
              <a
                href={signedUrlData.url}
                target="_blank"
                rel="noreferrer"
                className="text-accent text-[11px] break-all hover:underline flex items-center space-x-1"
              >
                <span>{signedUrlData.url}</span>
                <ExternalLink className="w-3 h-3 flex-shrink-0" />
              </a>
              {signedUrlData.expiresIn && (
                <div className="text-[10px] text-slate-500">Expires in: {signedUrlData.expiresIn} seconds</div>
              )}
            </div>
          )}
        </div>
      )}

      {/* In-Browser PDF Previewer Modal / Section */}
      {previewMode === 'PDF' && selectedReport && (
        <div className="bg-panel border border-hairline rounded-lg overflow-hidden shadow-panel font-mono text-xs">
          <div className="px-4 py-3 bg-panel-raised border-b border-hairline flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Eye className="w-4 h-4 text-accent" />
              <span className="font-semibold text-white uppercase">In-Browser PDF Viewer: {selectedReport.title}</span>
            </div>

            <div className="flex items-center space-x-2">
              <button
                onClick={() => setPdfZoom((z) => Math.max(50, z - 15))}
                className="p-1 rounded bg-slate-900 border border-hairline text-slate-300 hover:text-white"
                title="Zoom Out"
              >
                <ZoomOut className="w-3.5 h-3.5" />
              </button>
              <span className="tabular-nums text-slate-400 w-12 text-center">{pdfZoom}%</span>
              <button
                onClick={() => setPdfZoom((z) => Math.min(200, z + 15))}
                className="p-1 rounded bg-slate-900 border border-hairline text-slate-300 hover:text-white"
                title="Zoom In"
              >
                <ZoomIn className="w-3.5 h-3.5" />
              </button>

              <button
                onClick={() => setPreviewMode('NONE')}
                className="px-2.5 py-1 rounded bg-slate-900 border border-hairline text-slate-400 hover:text-white ml-2"
              >
                CLOSE PREVIEW
              </button>
            </div>
          </div>

          <div className="p-4 bg-slate-950 flex justify-center overflow-auto min-h-[500px]">
            <iframe
              src={`/api/v1/dossiers/${selectedReport.id}/download?format=pdf`}
              title="PDF Report Preview"
              className="w-full h-[600px] border border-hairline rounded bg-white shadow-lg"
              style={{ transform: `scale(${pdfZoom / 100})`, transformOrigin: 'top center' }}
            />
          </div>
        </div>
      )}

      {/* In-Browser JSON Snapshot Viewer Modal / Section */}
      {previewMode === 'JSON' && selectedReport && (
        <div className="bg-panel border border-hairline rounded-lg overflow-hidden shadow-panel font-mono text-xs">
          <div className="px-4 py-3 bg-panel-raised border-b border-hairline flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center space-x-2">
              <FileCode className="w-4 h-4 text-accent" />
              <span className="font-semibold text-white uppercase">JSON Frozen Snapshot: {selectedReport.title}</span>
            </div>

            <div className="flex items-center space-x-2">
              <button
                onClick={() => {
                  if (jsonContent) {
                    navigator.clipboard.writeText(jsonContent);
                    setCopiedJson(true);
                    setTimeout(() => setCopiedJson(false), 2000);
                  }
                }}
                className="px-2.5 py-1 rounded bg-slate-900 border border-hairline text-slate-300 hover:text-white flex items-center space-x-1"
              >
                <Copy className="w-3 h-3" />
                <span>{copiedJson ? 'COPIED' : 'COPY JSON'}</span>
              </button>

              <button
                onClick={() => setPreviewMode('NONE')}
                className="px-2.5 py-1 rounded bg-slate-900 border border-hairline text-slate-400 hover:text-white"
              >
                CLOSE
              </button>
            </div>
          </div>

          <div className="p-4 bg-slate-950 max-h-[550px] overflow-auto">
            {loadingJson ? (
              <div className="py-16 text-center text-slate-400 flex items-center justify-center space-x-2">
                <RefreshCw className="w-4 h-4 animate-spin text-accent" />
                <span>RETRIEVING FROZEN JSON SNAPSHOT...</span>
              </div>
            ) : jsonContent && jsonContent.length > 100000 && !showFullJson ? (
              <div className="space-y-3">
                <div className="p-2.5 bg-amber-950/60 border border-amber-800 rounded text-amber-300 text-[11px] flex items-center justify-between">
                  <span>
                    Large JSON payload ({(jsonContent.length / 1024).toFixed(1)} KB) — preview truncated to first 100KB for UI responsiveness.
                  </span>
                  <button
                    onClick={() => setShowFullJson(true)}
                    className="px-2 py-0.5 rounded bg-amber-900 hover:bg-amber-800 text-white font-semibold text-[10px]"
                  >
                    RENDER FULL JSON
                  </button>
                </div>
                <pre className="text-slate-200 text-xs font-mono leading-relaxed select-all">
                  {jsonContent.slice(0, 100000)}
                  {'\n... [TRUNCATED FOR RESPONSIVENESS]'}
                </pre>
              </div>
            ) : (
              <pre className="text-slate-200 text-xs font-mono leading-relaxed select-all">
                {jsonContent}
              </pre>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
