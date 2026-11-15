import React, { useState, useEffect, useRef, useCallback } from 'react';
import { api, PorkchopRequest, PorkchopResponse } from '../../lib/api';
import { Compass, RefreshCw, AlertCircle, Table as TableIcon, Layers, Info, CheckCircle2 } from 'lucide-react';

interface PorkchopPlotProps {
  onSelectOpportunity?: (opportunity: {
    departureDate: string;
    arrivalDate: string;
    tofDays: number;
    c3: number | null;
    vinfDep: number | null;
    vinfArr: number | null;
    dvTotal?: number | null;
  }) => void;
}

export const PorkchopPlot: React.FC<PorkchopPlotProps> = ({ onSelectOpportunity }) => {
  // Form State
  const [originBody, setOriginBody] = useState<string>('EARTH');
  const [targetBody, setTargetBody] = useState<string>('MARS');
  const [departureStart, setDepartureStart] = useState<string>('2026-05-01');
  const [departureEnd, setDepartureEnd] = useState<string>('2026-08-01');
  const [arrivalStart, setArrivalStart] = useState<string>('2026-11-01');
  const [arrivalEnd, setArrivalEnd] = useState<string>('2027-04-01');
  const [stepSize, setStepSize] = useState<number>(5.0);
  const [selectedMetric, setSelectedMetric] = useState<'c3' | 'vinf_dep' | 'vinf_arr' | 'tof'>('c3');

  // Computation & Display State
  const [data, setData] = useState<PorkchopResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'contour' | 'table'>('contour');

  // Selected Cell State
  const [selectedPoint, setSelectedPoint] = useState<{
    depIdx: number;
    arrIdx: number;
    depDate: string;
    arrDate: string;
    c3: number | null;
    vinfDep: number | null;
    vinfArr: number | null;
    tofDays: number | null;
    isValid: boolean;
  } | null>(null);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Execute Porkchop Analysis
  const handleCalculate = useCallback(async () => {
    setError(null);

    // Client-side validation guards
    if (originBody === targetBody) {
      setError('Origin body and target destination cannot be identical.');
      return;
    }

    const tDepStart = new Date(departureStart).getTime();
    const tDepEnd = new Date(departureEnd).getTime();
    const tArrStart = new Date(arrivalStart).getTime();
    const tArrEnd = new Date(arrivalEnd).getTime();

    if (isNaN(tDepStart) || isNaN(tDepEnd) || isNaN(tArrStart) || isNaN(tArrEnd)) {
      setError('Invalid date format. Please specify valid calendar dates (YYYY-MM-DD).');
      return;
    }

    if (tDepStart > tDepEnd) {
      setError('Departure start date must be before or equal to departure end date.');
      return;
    }

    if (tArrStart > tArrEnd) {
      setError('Arrival start date must be before or equal to arrival end date.');
      return;
    }

    if (tDepStart >= tArrEnd) {
      setError('Departure window must begin strictly before arrival window ends.');
      return;
    }

    // Grid point bounds check
    const depSteps = Math.floor((tDepEnd - tDepStart) / (stepSize * 86400000)) + 1;
    const arrSteps = Math.floor((tArrEnd - tArrStart) / (stepSize * 86400000)) + 1;
    const totalPoints = depSteps * arrSteps;
    if (totalPoints > 10000) {
      setError(`Grid size exceeds 10,000 calculation cells (${totalPoints.toLocaleString()} points). Increase resolution step size or narrow the date window.`);
      return;
    }

    setLoading(true);
    try {
      const req: PorkchopRequest = {
        origin_body: originBody,
        target_body: targetBody,
        departure_start_date: departureStart,
        departure_end_date: departureEnd,
        arrival_start_date: arrivalStart,
        arrival_end_date: arrivalEnd,
        step_size_days: stepSize,
      };

      const result = await api.calculatePorkchop(req);
      setData(result);

      // Default selection to minimum C3 opportunity if present
      if (
        result.minima?.c3 &&
        typeof result.minima.c3.dep_idx === 'number' &&
        typeof result.minima.c3.arr_idx === 'number'
      ) {
        const minC3 = result.minima.c3;
        const depIdx = minC3.dep_idx as number;
        const arrIdx = minC3.arr_idx as number;
        setSelectedPoint({
          depIdx,
          arrIdx,
          depDate: result.departure_dates[depIdx],
          arrDate: result.arrival_dates[arrIdx],
          c3: minC3.c3 ?? result.c3_grid[arrIdx]?.[depIdx] ?? null,
          vinfDep: result.vinf_dep_grid[arrIdx]?.[depIdx] ?? null,
          vinfArr: result.vinf_arr_grid[arrIdx]?.[depIdx] ?? null,
          tofDays: result.tof_days_grid[arrIdx]?.[depIdx] ?? null,
          isValid: true,
        });

        if (onSelectOpportunity) {
          onSelectOpportunity({
            departureDate: result.departure_dates[depIdx],
            arrivalDate: result.arrival_dates[arrIdx],
            tofDays: result.tof_days_grid[arrIdx]?.[depIdx] ?? 0,
            c3: minC3.c3 ?? null,
            vinfDep: result.vinf_dep_grid[arrIdx]?.[depIdx] ?? null,
            vinfArr: result.vinf_arr_grid[arrIdx]?.[depIdx] ?? null,
            dvTotal: result.dv_total_grid?.[arrIdx]?.[depIdx] ?? null,
          });
        }
      }
    } catch (err: any) {
      setData(null);
      setSelectedPoint(null);
      setError(err?.message || 'Failed to compute porkchop trajectory grid');
    } finally {
      setLoading(false);
    }
  }, [
    originBody,
    targetBody,
    departureStart,
    departureEnd,
    arrivalStart,
    arrivalEnd,
    stepSize,
    onSelectOpportunity,
  ]);

  // Initial calculation on mount
  useEffect(() => {
    handleCalculate();
  }, []);

  // Compute color for cell value (with strict null / non-converged handling)
  const getCellColor = (
    val: number | null,
    minVal: number,
    maxVal: number
  ): string => {
    if (val === null || isNaN(val)) {
      // Non-converged / unavailable cells rendered as dark void gap (NOT ZERO!)
      return '#070a11';
    }

    const clamped = Math.max(minVal, Math.min(maxVal, val));
    const ratio = (clamped - minVal) / Math.max(1e-5, maxVal - minVal);

    // Continuous aerospace gradient: Cyan (#0284C7) -> Teal (#0D9488) -> Yellow (#F59E0B) -> Red (#EF4444)
    if (ratio < 0.33) {
      const r = Math.round(2 + (13 - 2) * (ratio / 0.33));
      const g = Math.round(132 + (148 - 132) * (ratio / 0.33));
      const b = Math.round(199 + (136 - 199) * (ratio / 0.33));
      return `rgb(${r}, ${g}, ${b})`;
    } else if (ratio < 0.66) {
      const t = (ratio - 0.33) / 0.33;
      const r = Math.round(13 + (245 - 13) * t);
      const g = Math.round(148 + (158 - 148) * t);
      const b = Math.round(136 + (11 - 136) * t);
      return `rgb(${r}, ${g}, ${b})`;
    } else {
      const t = (ratio - 0.66) / 0.34;
      const r = Math.round(245 + (239 - 245) * t);
      const g = Math.round(158 + (68 - 158) * t);
      const b = Math.round(11 + (68 - 11) * t);
      return `rgb(${r}, ${g}, ${b})`;
    }
  };

  // Render Canvas when data or metric changes
  useEffect(() => {
    if (!data || !canvasRef.current || viewMode !== 'contour') return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    const padding = { top: 30, right: 30, bottom: 50, left: 70 };

    const plotW = width - padding.left - padding.right;
    const plotH = height - padding.top - padding.bottom;

    // Clear background
    ctx.fillStyle = '#05080E';
    ctx.fillRect(0, 0, width, height);

    const nDep = data.departure_dates.length;
    const nArr = data.arrival_dates.length;

    if (nDep === 0 || nArr === 0) return;

    const cellW = plotW / nDep;
    const cellH = plotH / nArr;

    // Select grid
    let targetGrid: (number | null)[][] = data.c3_grid;
    if (selectedMetric === 'vinf_dep') targetGrid = data.vinf_dep_grid;
    else if (selectedMetric === 'vinf_arr') targetGrid = data.vinf_arr_grid;
    else if (selectedMetric === 'tof') targetGrid = data.tof_days_grid;

    // Determine value range for scaling
    let minVal = Infinity;
    let maxVal = -Infinity;

    for (let r = 0; r < nArr; r++) {
      for (let c = 0; c < nDep; c++) {
        const val = targetGrid[r]?.[c];
        if (val != null && !isNaN(val)) {
          if (val < minVal) minVal = val;
          if (val > maxVal) maxVal = val;
        }
      }
    }

    if (minVal === Infinity) minVal = 0;
    if (maxVal === -Infinity) maxVal = 100;
    if (selectedMetric === 'c3') {
      maxVal = Math.min(maxVal, minVal + 80); // Clamp high C3 for visual contour definition
    }

    // Draw Grid Cells
    for (let r = 0; r < nArr; r++) {
      for (let c = 0; c < nDep; c++) {
        const val = targetGrid[r]?.[c];
        const isValid = data.valid_mask ? data.valid_mask[r]?.[c] : val != null;

        const x = padding.left + c * cellW;
        // Invert Y so later arrival dates appear towards the top
        const y = padding.top + (nArr - 1 - r) * cellH;

        if (!isValid || val == null) {
          // Render explicit non-converged gap (hatched pattern / dark void)
          ctx.fillStyle = '#090D16';
          ctx.fillRect(x, y, cellW, cellH);

          // Subtle diagonal hash to indicate unavailable
          ctx.strokeStyle = '#141D2D';
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(x, y);
          ctx.lineTo(x + cellW, y + cellH);
          ctx.stroke();
        } else {
          ctx.fillStyle = getCellColor(val, minVal, maxVal);
          ctx.fillRect(x, y, cellW, cellH);
        }
      }
    }

    // Highlight Global Minimum C3 (Pareto Anchor)
    if (data.minima?.c3 && data.minima.c3.dep_idx != null && data.minima.c3.arr_idx != null) {
      const minDepIdx = data.minima.c3.dep_idx;
      const minArrIdx = data.minima.c3.arr_idx;
      const x = padding.left + minDepIdx * cellW + cellW / 2;
      const y = padding.top + (nArr - 1 - minArrIdx) * cellH + cellH / 2;

      ctx.strokeStyle = '#FFFFFF';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(x, y, 6, 0, Math.PI * 2);
      ctx.stroke();

      ctx.fillStyle = '#0284C7';
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fill();
    }

    // Highlight Currently Selected Point Reticle
    if (selectedPoint) {
      const selX = padding.left + selectedPoint.depIdx * cellW;
      const selY = padding.top + (nArr - 1 - selectedPoint.arrIdx) * cellH;

      ctx.strokeStyle = '#38BDF8';
      ctx.lineWidth = 2;
      ctx.strokeRect(selX - 1, selY - 1, cellW + 2, cellH + 2);

      // Crosshair markers extending across plot
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.4)';
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(padding.left, selY + cellH / 2);
      ctx.lineTo(padding.left + plotW, selY + cellH / 2);
      ctx.moveTo(selX + cellW / 2, padding.top);
      ctx.lineTo(selX + cellW / 2, padding.top + plotH);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Axes & Outer Border
    ctx.strokeStyle = '#1E293B';
    ctx.lineWidth = 1;
    ctx.strokeRect(padding.left, padding.top, plotW, plotH);

    // Labels & Numerals font
    ctx.fillStyle = '#94A3B8';
    ctx.font = '10px "JetBrains Mono", monospace';

    // X-Axis Ticks (Departure Dates)
    const xStep = Math.max(1, Math.floor(nDep / 5));
    for (let c = 0; c < nDep; c += xStep) {
      const x = padding.left + c * cellW + cellW / 2;
      const dateStr = data.departure_dates[c].slice(5); // MM-DD
      ctx.fillText(dateStr, x - 12, height - padding.bottom + 16);

      ctx.beginPath();
      ctx.moveTo(x, height - padding.bottom);
      ctx.lineTo(x, height - padding.bottom + 4);
      ctx.strokeStyle = '#334155';
      ctx.stroke();
    }
    ctx.fillText('Departure Window (UTC)', padding.left + plotW / 2 - 60, height - 10);

    // Y-Axis Ticks (Arrival Dates)
    const yStep = Math.max(1, Math.floor(nArr / 5));
    for (let r = 0; r < nArr; r += yStep) {
      const y = padding.top + (nArr - 1 - r) * cellH + cellH / 2;
      const dateStr = data.arrival_dates[r].slice(5); // MM-DD
      ctx.fillText(dateStr, padding.left - 48, y + 3);

      ctx.beginPath();
      ctx.moveTo(padding.left - 4, y);
      ctx.lineTo(padding.left, y);
      ctx.strokeStyle = '#334155';
      ctx.stroke();
    }

    ctx.save();
    ctx.translate(16, padding.top + plotH / 2 + 50);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText('Arrival Window (UTC)', 0, 0);
    ctx.restore();
  }, [data, selectedMetric, selectedPoint, viewMode]);

  // Canvas Click Handler for Point Selection
  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!data || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;

    const clickX = (e.clientX - rect.left) * scaleX;
    const clickY = (e.clientY - rect.top) * scaleY;

    const padding = { top: 30, right: 30, bottom: 50, left: 70 };
    const plotW = canvas.width - padding.left - padding.right;
    const plotH = canvas.height - padding.top - padding.bottom;

    if (
      clickX < padding.left ||
      clickX > padding.left + plotW ||
      clickY < padding.top ||
      clickY > padding.top + plotH
    ) {
      return;
    }

    const nDep = data.departure_dates.length;
    const nArr = data.arrival_dates.length;
    const cellW = plotW / nDep;
    const cellH = plotH / nArr;

    const depIdx = Math.min(nDep - 1, Math.max(0, Math.floor((clickX - padding.left) / cellW)));
    const invertedY = Math.min(
      nArr - 1,
      Math.max(0, Math.floor((clickY - padding.top) / cellH))
    );
    const arrIdx = nArr - 1 - invertedY;

    const isValid = data.valid_mask ? !!data.valid_mask[arrIdx]?.[depIdx] : data.c3_grid[arrIdx]?.[depIdx] != null;
    const c3Val = data.c3_grid[arrIdx]?.[depIdx] ?? null;
    const vinfDep = data.vinf_dep_grid[arrIdx]?.[depIdx] ?? null;
    const vinfArr = data.vinf_arr_grid[arrIdx]?.[depIdx] ?? null;
    const tof = data.tof_days_grid[arrIdx]?.[depIdx] ?? null;
    const dvTotal = data.dv_total_grid?.[arrIdx]?.[depIdx] ?? null;

    const point = {
      depIdx,
      arrIdx,
      depDate: data.departure_dates[depIdx],
      arrDate: data.arrival_dates[arrIdx],
      c3: c3Val,
      vinfDep,
      vinfArr,
      tofDays: tof,
      isValid,
    };

    setSelectedPoint(point);

    if (isValid && onSelectOpportunity) {
      onSelectOpportunity({
        departureDate: point.depDate,
        arrivalDate: point.arrDate,
        tofDays: tof || 0,
        c3: c3Val,
        vinfDep,
        vinfArr,
        dvTotal,
      });
    }
  };

  // Compile Top Minimum C3 Opportunities for Table Fallback
  const minC3Opportunities = React.useMemo(() => {
    if (!data) return [];
    const list: Array<{
      depDate: string;
      arrDate: string;
      c3: number;
      vinfDep: number;
      vinfArr: number;
      tofDays: number;
      dvTotal: number | null;
      depIdx: number;
      arrIdx: number;
    }> = [];

    const nArr = data.arrival_dates.length;
    const nDep = data.departure_dates.length;

    for (let r = 0; r < nArr; r++) {
      for (let c = 0; c < nDep; c++) {
        const isValid = data.valid_mask ? !!data.valid_mask[r]?.[c] : data.c3_grid[r]?.[c] != null;
        const c3 = data.c3_grid[r]?.[c];
        if (isValid && c3 != null && !isNaN(c3)) {
          list.push({
            depDate: data.departure_dates[c],
            arrDate: data.arrival_dates[r],
            c3,
            vinfDep: data.vinf_dep_grid[r]?.[c] ?? 0,
            vinfArr: data.vinf_arr_grid[r]?.[c] ?? 0,
            tofDays: data.tof_days_grid[r]?.[c] ?? 0,
            dvTotal: data.dv_total_grid?.[r]?.[c] ?? null,
            depIdx: c,
            arrIdx: r,
          });
        }
      }
    }

    // Sort by ascending C3 (single-objective minimum injection energy)
    return list.sort((a, b) => a.c3 - b.c3).slice(0, 15);
  }, [data]);

  return (
    <section
      aria-labelledby="porkchop-section-heading"
      className="bg-panel border border-hairline rounded-lg p-5 shadow-panel"
      data-testid="porkchop-plot-section"
    >
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-hairline mb-4 gap-2">
        <div className="flex items-center space-x-2.5">
          <Compass className="w-5 h-5 text-accent" />
          <div>
            <h2 id="porkchop-section-heading" className="text-sm font-semibold tracking-wide text-white uppercase font-mono">
              Interplanetary Trajectory Analysis (Porkchop Plot)
            </h2>
            <div className="text-[11px] text-slate-400">
              Deterministic 2D Lambert contour mesh over departure and arrival epochs
            </div>
          </div>
        </div>

        {/* View Switcher & Action */}
        <div className="flex items-center space-x-2">
          <div className="flex bg-panel-raised border border-hairline rounded p-0.5 text-xs font-mono">
            <button
              onClick={() => setViewMode('contour')}
              className={`px-2.5 py-1 rounded transition ${
                viewMode === 'contour' ? 'bg-accent text-white font-semibold' : 'text-slate-400 hover:text-white'
              }`}
            >
              2D Contour Mesh
            </button>
            <button
              onClick={() => setViewMode('table')}
              className={`px-2.5 py-1 rounded flex items-center space-x-1 transition ${
                viewMode === 'table' ? 'bg-accent text-white font-semibold' : 'text-slate-400 hover:text-white'
              }`}
            >
              <TableIcon className="w-3.5 h-3.5" />
              <span>Opportunities Table</span>
            </button>
          </div>

          <button
            onClick={handleCalculate}
            disabled={loading}
            className="flex items-center space-x-1.5 px-3 py-1 bg-accent hover:bg-accent-hover text-white rounded text-xs font-mono font-medium transition disabled:opacity-50"
            aria-label="Compute trajectory porkchop grid"
          >
            <RefreshCw className={`w-3.5 h-3.5 motion-reduce:animate-none ${loading ? 'animate-spin' : ''}`} />
            <span>Compute</span>
          </button>
        </div>
      </div>

      {/* Trajectory Parameters Control Form */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3 mb-5 p-3.5 bg-panel-raised border border-hairline rounded text-xs font-mono">
        <div>
          <label htmlFor="origin-body-select" className="text-slate-400 text-[10px] block uppercase font-semibold mb-1">
            Origin Body
          </label>
          <select
            id="origin-body-select"
            aria-label="Origin Body"
            value={originBody}
            onChange={(e) => setOriginBody(e.target.value)}
            className="w-full bg-panel border border-hairline rounded px-2 py-1 text-white focus:outline-none focus:border-accent"
          >
            <option value="EARTH">Earth (399)</option>
            <option value="MARS">Mars (499)</option>
            <option value="VENUS">Venus (299)</option>
          </select>
        </div>

        <div>
          <label htmlFor="target-body-select" className="text-slate-400 text-[10px] block uppercase font-semibold mb-1">
            Target Body
          </label>
          <select
            id="target-body-select"
            aria-label="Target Body"
            value={targetBody}
            onChange={(e) => setTargetBody(e.target.value)}
            className="w-full bg-panel border border-hairline rounded px-2 py-1 text-white focus:outline-none focus:border-accent"
          >
            <option value="MARS">Mars (499)</option>
            <option value="EARTH">Earth (399)</option>
            <option value="JUPITER">Jupiter (599)</option>
            <option value="VENUS">Venus (299)</option>
          </select>
        </div>

        <div>
          <label htmlFor="dep-start-date" className="text-slate-400 text-[10px] block uppercase font-semibold mb-1">
            Departure Start
          </label>
          <input
            id="dep-start-date"
            aria-label="Departure Start"
            type="date"
            value={departureStart}
            onChange={(e) => setDepartureStart(e.target.value)}
            className="w-full bg-panel border border-hairline rounded px-2 py-1 text-white focus:outline-none focus:border-accent"
          />
        </div>

        <div>
          <label htmlFor="dep-end-date" className="text-slate-400 text-[10px] block uppercase font-semibold mb-1">
            Departure End
          </label>
          <input
            id="dep-end-date"
            aria-label="Departure End"
            type="date"
            value={departureEnd}
            onChange={(e) => setDepartureEnd(e.target.value)}
            className="w-full bg-panel border border-hairline rounded px-2 py-1 text-white focus:outline-none focus:border-accent"
          />
        </div>

        <div>
          <label htmlFor="arr-start-date" className="text-slate-400 text-[10px] block uppercase font-semibold mb-1">
            Arrival Start
          </label>
          <input
            id="arr-start-date"
            aria-label="Arrival Start"
            type="date"
            value={arrivalStart}
            onChange={(e) => setArrivalStart(e.target.value)}
            className="w-full bg-panel border border-hairline rounded px-2 py-1 text-white focus:outline-none focus:border-accent"
          />
        </div>

        <div>
          <label htmlFor="arr-end-date" className="text-slate-400 text-[10px] block uppercase font-semibold mb-1">
            Arrival End
          </label>
          <input
            id="arr-end-date"
            aria-label="Arrival End"
            type="date"
            value={arrivalEnd}
            onChange={(e) => setArrivalEnd(e.target.value)}
            className="w-full bg-panel border border-hairline rounded px-2 py-1 text-white focus:outline-none focus:border-accent"
          />
        </div>

        <div>
          <label htmlFor="step-size-select" className="text-slate-400 text-[10px] block uppercase font-semibold mb-1">
            Resolution Step
          </label>
          <select
            id="step-size-select"
            aria-label="Resolution Step"
            value={stepSize}
            onChange={(e) => setStepSize(Number(e.target.value))}
            className="w-full bg-panel border border-hairline rounded px-2 py-1 text-white focus:outline-none focus:border-accent"
          >
            <option value={2}>2.0 Days</option>
            <option value={5}>5.0 Days</option>
            <option value={10}>10.0 Days</option>
          </select>
        </div>
      </div>

      {/* Metric Selector Bar & Diagnostics */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4 text-xs font-mono">
        <div className="flex items-center space-x-2">
          <span className="text-slate-400 text-[11px] uppercase font-semibold">Contour Metric:</span>
          <div className="flex bg-panel-raised border border-hairline rounded p-0.5">
            <button
              onClick={() => setSelectedMetric('c3')}
              className={`px-2 py-0.5 rounded transition ${
                selectedMetric === 'c3' ? 'bg-sky-950 text-accent font-semibold border border-sky-800' : 'text-slate-400 hover:text-white'
              }`}
            >
              C₃ Energy (km²/s²)
            </button>
            <button
              onClick={() => setSelectedMetric('vinf_dep')}
              className={`px-2 py-0.5 rounded transition ${
                selectedMetric === 'vinf_dep' ? 'bg-sky-950 text-accent font-semibold border border-sky-800' : 'text-slate-400 hover:text-white'
              }`}
            >
              V∞ Dep (km/s)
            </button>
            <button
              onClick={() => setSelectedMetric('vinf_arr')}
              className={`px-2 py-0.5 rounded transition ${
                selectedMetric === 'vinf_arr' ? 'bg-sky-950 text-accent font-semibold border border-sky-800' : 'text-slate-400 hover:text-white'
              }`}
            >
              V∞ Arr (km/s)
            </button>
            <button
              onClick={() => setSelectedMetric('tof')}
              className={`px-2 py-0.5 rounded transition ${
                selectedMetric === 'tof' ? 'bg-sky-950 text-accent font-semibold border border-sky-800' : 'text-slate-400 hover:text-white'
              }`}
            >
              Flight Time (Days)
            </button>
          </div>
        </div>

        {data && (
          <div className="flex items-center space-x-3 text-[11px] text-slate-400">
            <span>
              Grid: <strong className="text-white tabular-nums">{data.valid_cells_count}</strong> valid / {data.total_grid_points} total
            </span>
            <span>•</span>
            <span>Step: {data.step_size_days}d</span>
          </div>
        )}
      </div>

      {error && (
        <div className="p-3 bg-red-950/40 border border-status-alert/40 rounded text-xs text-red-300 flex items-center justify-between mb-4">
          <div className="flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 text-status-alert flex-shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={handleCalculate}
            className="text-xs bg-red-900/60 hover:bg-red-800 text-white px-2 py-1 rounded border border-red-700 transition"
          >
            Retry Calculation
          </button>
        </div>
      )}

      {/* Main View Area */}
      {viewMode === 'contour' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
          {/* Canvas Viewport */}
          <div className="lg:col-span-8 bg-panel-raised border border-hairline rounded-lg p-3 flex flex-col items-center">
            <div className="w-full flex items-center justify-between text-[11px] font-mono text-slate-400 mb-2 px-1">
              <span>Click any cell to inspect transfer boundary conditions</span>
              <div className="flex items-center space-x-2">
                <span className="w-3 h-3 bg-[#0284C7] rounded-sm inline-block" />
                <span>Low (Optimal)</span>
                <span className="w-3 h-3 bg-[#EF4444] rounded-sm inline-block ml-1" />
                <span>High</span>
                <span className="w-3 h-3 bg-[#070a11] border border-slate-700 rounded-sm inline-block ml-1" />
                <span className="text-slate-400">Non-converged gap</span>
              </div>
            </div>

            <div className="relative w-full overflow-x-auto flex justify-center">
              <canvas
                ref={canvasRef}
                width={680}
                height={460}
                onClick={handleCanvasClick}
                className="cursor-crosshair border border-hairline rounded bg-canvas max-w-full"
                aria-label="2D Porkchop Plot Contour Grid"
              />
            </div>
          </div>

          {/* Transfer Opportunity Inspector Panel */}
          <div className="lg:col-span-4 bg-panel-raised border border-hairline rounded-lg p-4 space-y-4">
            <div className="flex items-center justify-between border-b border-hairline pb-2.5">
              <h3 className="text-xs font-bold text-white uppercase font-mono tracking-wider flex items-center space-x-1.5">
                <Layers className="w-4 h-4 text-accent" />
                <span>Selected Opportunity</span>
              </h3>
              {selectedPoint?.isValid ? (
                <span className="text-[10px] font-mono px-2 py-0.5 bg-emerald-950 text-status-nominal rounded border border-emerald-800">
                  CONVERGED
                </span>
              ) : selectedPoint ? (
                <span className="text-[10px] font-mono px-2 py-0.5 bg-red-950 text-status-alert rounded border border-red-800">
                  UNAVAILABLE
                </span>
              ) : null}
            </div>

            {selectedPoint ? (
              <div className="space-y-3 font-mono text-xs" data-testid="porkchop-inspector">
                <div className="p-2.5 bg-panel border border-hairline rounded space-y-1">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Departure:</span>
                    <span className="text-white font-semibold">{selectedPoint.depDate} UTC</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Arrival:</span>
                    <span className="text-white font-semibold">{selectedPoint.arrDate} UTC</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Flight Time:</span>
                    <span className="text-slate-200 tabular-nums">
                      {selectedPoint.tofDays != null ? `${selectedPoint.tofDays.toFixed(1)} days` : '—'}
                    </span>
                  </div>
                </div>

                {selectedPoint.isValid ? (
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="p-2.5 bg-panel border border-hairline rounded">
                      <span className="text-slate-400 text-[10px] block uppercase">C₃ Energy</span>
                      <span className="text-accent font-bold text-base tabular-nums">
                        {selectedPoint.c3 != null ? selectedPoint.c3.toFixed(2) : '—'}
                      </span>
                      <span className="text-[10px] text-slate-400 block">km²/s²</span>
                    </div>

                    <div className="p-2.5 bg-panel border border-hairline rounded">
                      <span className="text-slate-400 text-[10px] block uppercase">V∞ Dep</span>
                      <span className="text-slate-200 font-bold text-base tabular-nums">
                        {selectedPoint.vinfDep != null ? selectedPoint.vinfDep.toFixed(2) : '—'}
                      </span>
                      <span className="text-[10px] text-slate-400 block">km/s</span>
                    </div>

                    <div className="p-2.5 bg-panel border border-hairline rounded">
                      <span className="text-slate-400 text-[10px] block uppercase">V∞ Arr</span>
                      <span className="text-slate-200 font-bold text-base tabular-nums">
                        {selectedPoint.vinfArr != null ? selectedPoint.vinfArr.toFixed(2) : '—'}
                      </span>
                      <span className="text-[10px] text-slate-400 block">km/s</span>
                    </div>

                    <div className="p-2.5 bg-panel border border-hairline rounded">
                      <span className="text-slate-400 text-[10px] block uppercase">Status</span>
                      <span className="text-status-nominal font-bold text-base">Nominal</span>
                      <span className="text-[10px] text-slate-400 block">Patched-Conic</span>
                    </div>
                  </div>
                ) : (
                  <div className="p-3 bg-red-950/40 border border-status-alert/40 rounded text-red-300 text-xs leading-relaxed">
                    <strong>Non-converged boundary condition:</strong> This departure/arrival pair
                    either represents negative time of flight, parabolic asymptote singularity, or
                    exceeds boundary iteration limits. Rendered as unavailable gap.
                  </div>
                )}

                {/* Dispatch to 3D Trajectory button */}
                {selectedPoint.isValid && (
                  <button
                    onClick={() => {
                      if (onSelectOpportunity) {
                        onSelectOpportunity({
                          departureDate: selectedPoint.depDate,
                          arrivalDate: selectedPoint.arrDate,
                          tofDays: selectedPoint.tofDays || 0,
                          c3: selectedPoint.c3,
                          vinfDep: selectedPoint.vinfDep,
                          vinfArr: selectedPoint.vinfArr,
                        });
                      }
                    }}
                    className="w-full py-2 bg-panel hover:bg-slate-800 text-white border border-accent/60 rounded flex items-center justify-center space-x-1.5 transition text-xs font-semibold"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5 text-accent" />
                    <span>Apply to 3D Trajectory Viewer</span>
                  </button>
                )}
              </div>
            ) : (
              <div className="py-12 text-center text-slate-400 text-xs font-mono">
                Click on any cell in the 2D contour mesh to inspect exact trajectory parameters.
              </div>
            )}

            {/* Global Minima Quick Info */}
            {data?.minima?.c3 && (
              <div className="p-2.5 bg-panel/60 border border-hairline rounded text-[11px] font-mono text-slate-400">
                <div className="text-[10px] text-accent uppercase font-semibold mb-1 flex items-center space-x-1">
                  <Info className="w-3 h-3" />
                  <span>Global Minimum C₃ Opportunity</span>
                </div>
                <div>
                  C₃ = <strong className="text-white">{data.minima.c3.c3?.toFixed(2)} km²/s²</strong>
                </div>
                <div>
                  Dates: {data.minima.c3.departure_date} → {data.minima.c3.arrival_date}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Accessible Table Fallback */}
      {viewMode === 'table' && (
        <div className="overflow-x-auto border border-hairline rounded-lg" data-testid="porkchop-table-fallback">
          <table className="w-full text-left text-xs font-mono" aria-label="Optimal Minimum C3 Trajectory Windows Table">
            <thead className="bg-panel-raised text-slate-400 uppercase text-[10px] tracking-wider border-b border-hairline">
              <tr>
                <th scope="col" className="p-3">Rank</th>
                <th scope="col" className="p-3">Departure Date</th>
                <th scope="col" className="p-3">Arrival Date</th>
                <th scope="col" className="p-3">TOF (Days)</th>
                <th scope="col" className="p-3">C₃ Energy (km²/s²)</th>
                <th scope="col" className="p-3">V∞ Dep (km/s)</th>
                <th scope="col" className="p-3">V∞ Arr (km/s)</th>
                <th scope="col" className="p-3">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline bg-panel text-slate-200">
              {minC3Opportunities.map((opp, idx) => (
                <tr key={`${opp.depDate}-${opp.arrDate}`} className="hover:bg-panel-raised/50 transition">
                  <td className="p-3 font-bold text-accent">#{idx + 1}</td>
                  <td className="p-3 font-medium text-white">{opp.depDate}</td>
                  <td className="p-3 text-slate-300">{opp.arrDate}</td>
                  <td className="p-3 tabular-nums">{opp.tofDays.toFixed(1)}</td>
                  <td className="p-3 font-semibold text-white tabular-nums">{opp.c3.toFixed(2)}</td>
                  <td className="p-3 tabular-nums">{opp.vinfDep.toFixed(2)}</td>
                  <td className="p-3 tabular-nums">{opp.vinfArr.toFixed(2)}</td>
                  <td className="p-3">
                    <button
                      onClick={() => {
                        setSelectedPoint({
                          depIdx: opp.depIdx,
                          arrIdx: opp.arrIdx,
                          depDate: opp.depDate,
                          arrDate: opp.arrDate,
                          c3: opp.c3,
                          vinfDep: opp.vinfDep,
                          vinfArr: opp.vinfArr,
                          tofDays: opp.tofDays,
                          isValid: true,
                        });
                        setViewMode('contour');
                        if (onSelectOpportunity) {
                          onSelectOpportunity({
                            departureDate: opp.depDate,
                            arrivalDate: opp.arrDate,
                            tofDays: opp.tofDays,
                            c3: opp.c3,
                            vinfDep: opp.vinfDep,
                            vinfArr: opp.vinfArr,
                            dvTotal: opp.dvTotal,
                          });
                        }
                      }}
                      className="px-2 py-1 bg-panel-raised hover:bg-slate-700 text-xs rounded border border-hairline text-slate-200"
                    >
                      Select
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};
