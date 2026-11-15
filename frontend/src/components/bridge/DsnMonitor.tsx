import React, { useEffect, useState, useCallback } from 'react';
import { api, DSNFeedResponse, DSNStation } from '../../lib/api';
import { Radio, RefreshCw, AlertCircle, Signal, Globe, Table as TableIcon, LayoutGrid } from 'lucide-react';

// Authoritative static geographic coordinates for the three Deep Space Communications Complexes
export const STATIC_STATION_COORDINATES: Record<string, { lat: string; lon: string; location: string }> = {
  gdscc: {
    lat: '35.4267°N',
    lon: '116.8900°W',
    location: 'Goldstone, California, USA',
  },
  goldstone: {
    lat: '35.4267°N',
    lon: '116.8900°W',
    location: 'Goldstone, California, USA',
  },
  mdscc: {
    lat: '40.4272°N',
    lon: '4.2500°W',
    location: 'Madrid, Spain',
  },
  madrid: {
    lat: '40.4272°N',
    lon: '4.2500°W',
    location: 'Madrid, Spain',
  },
  cdscc: {
    lat: '35.4014°S',
    lon: '148.9817°E',
    location: 'Canberra, Australia',
  },
  canberra: {
    lat: '35.4014°S',
    lon: '148.9817°E',
    location: 'Canberra, Australia',
  },
};

export const DsnMonitor: React.FC = () => {
  const [feed, setFeed] = useState<DSNFeedResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');

  const fetchDsn = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getDsnNow(true);
      setFeed(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to retrieve NASA DSN telemetry');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDsn();
    // Refresh DSN feed every 30 seconds
    const interval = setInterval(fetchDsn, 30000);
    return () => clearInterval(interval);
  }, [fetchDsn]);

  // Aggregate flattened active passes for the accessible table view
  const flattenedPasses = React.useMemo(() => {
    if (!feed?.stations) return [];
    const passes: Array<{
      stationCode: string;
      stationName: string;
      dishName: string;
      azimuth: number | null;
      elevation: number | null;
      targetName: string;
      rangeKm: number | null;
      rtltSec: number | null;
      upBand: string | null;
      upRate: number | null;
      upPower: number | null;
      downBand: string | null;
      downRate: number | null;
      downPower: number | null;
      activity: string | null;
    }> = [];

    feed.stations.forEach((station) => {
      station.dishes.forEach((dish) => {
        const targets = dish.targets.length > 0
          ? dish.targets
          : [{ name: dish.activity || 'STANDBY', target_id: null, upleg_range_km: null, downleg_range_km: null, rtlt_seconds: null }];

        targets.forEach((target) => {
          const upSig =
            dish.up_signals.find((s) => s.spacecraft === target.name && s.active) ||
            dish.up_signals.find((s) => s.active) ||
            dish.up_signals[0] ||
            null;
          const downSig =
            dish.down_signals.find((s) => s.spacecraft === target.name && s.active) ||
            dish.down_signals.find((s) => s.active) ||
            dish.down_signals[0] ||
            null;

          passes.push({
            stationCode: station.name.toLowerCase(),
            stationName: station.friendly_name,
            dishName: dish.name,
            azimuth: dish.azimuth_deg,
            elevation: dish.elevation_deg,
            targetName: target.name,
            rangeKm: target.downleg_range_km || target.upleg_range_km || null,
            rtltSec: target.rtlt_seconds || null,
            upBand: upSig?.band || null,
            upRate: upSig?.data_rate_bps || null,
            upPower: upSig?.power_dbm_or_kw || null,
            downBand: downSig?.band || null,
            downRate: downSig?.data_rate_bps || null,
            downPower: downSig?.power_dbm_or_kw || null,
            activity: dish.activity,
          });
        });
      });
    });

    return passes;
  }, [feed]);

  return (
    <section
      aria-labelledby="dsn-monitor-heading"
      className="bg-panel border border-hairline rounded-lg p-5 shadow-panel"
      data-testid="dsn-monitor-section"
    >
      {/* Header & Truthful Telemetry Indicators */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-hairline mb-4 gap-2">
        <div className="flex items-center space-x-2.5">
          <Radio className="w-5 h-5 text-accent" />
          <div>
            <h2 id="dsn-monitor-heading" className="text-sm font-semibold tracking-wide text-white uppercase font-mono">
              Deep Space Network (DSN) Ground Station Monitor
            </h2>
            <div className="text-[11px] text-slate-400">
              International ground telemetry from Goldstone, Madrid, and Canberra complexes
            </div>
          </div>
        </div>

        {/* View Toggle & Refresh */}
        <div className="flex items-center space-x-2">
          <div className="flex bg-panel-raised border border-hairline rounded p-0.5 text-xs font-mono">
            <button
              onClick={() => setViewMode('cards')}
              className={`px-2 py-1 rounded flex items-center space-x-1 transition ${
                viewMode === 'cards' ? 'bg-accent text-white font-semibold' : 'text-slate-400 hover:text-white'
              }`}
              aria-label="Cards view"
            >
              <LayoutGrid className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Complexes</span>
            </button>
            <button
              onClick={() => setViewMode('table')}
              className={`px-2 py-1 rounded flex items-center space-x-1 transition ${
                viewMode === 'table' ? 'bg-accent text-white font-semibold' : 'text-slate-400 hover:text-white'
              }`}
              aria-label="Table view"
            >
              <TableIcon className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Table Fallback</span>
            </button>
          </div>

          <button
            onClick={fetchDsn}
            disabled={loading}
            className="flex items-center space-x-1.5 text-xs text-slate-400 hover:text-white px-2.5 py-1 bg-panel-raised border border-hairline rounded transition disabled:opacity-50"
            aria-label="Refresh DSN telemetry"
          >
            <RefreshCw className={`w-3.5 h-3.5 motion-reduce:animate-none ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Distinction Bar: Static Metadata vs Live Telemetry */}
      <div className="mb-4 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
        <div className="bg-panel-raised border border-hairline rounded p-2.5 flex items-start space-x-2.5">
          <Globe className="w-4 h-4 text-slate-400 mt-0.5 flex-shrink-0" />
          <div>
            <div className="flex items-center space-x-1.5">
              <span className="text-[10px] font-bold uppercase bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded border border-hairline">
                STATIC METADATA
              </span>
              <span className="text-slate-300 font-semibold">Station Coordinates</span>
            </div>
            <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
              Goldstone (35.4267°N, 116.8900°W) • Madrid (40.4272°N, 4.2500°W) • Canberra (35.4014°S, 148.9817°E).
              Geographic coordinates and facility datum are invariant terrestrial reference points.
            </p>
          </div>
        </div>

        <div className="bg-panel-raised border border-hairline rounded p-2.5 flex items-start space-x-2.5">
          <Signal className="w-4 h-4 text-status-nominal mt-0.5 flex-shrink-0" />
          <div>
            <div className="flex items-center space-x-1.5">
              <span className="text-[10px] font-bold uppercase bg-emerald-950 text-status-nominal px-1.5 py-0.5 rounded border border-emerald-800">
                LIVE FEED DATA
              </span>
              <span className="text-slate-300 font-semibold">Active Dish Telemetry</span>
            </div>
            <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
              Tracked: <span className="text-white font-semibold tabular-nums">{feed?.active_tracking_count || 0}</span> dishes active • 
              Targets: <span className="text-white font-semibold">{feed?.tracked_spacecraft.join(', ') || 'None in contact'}</span> • 
              Feed: <span className="text-slate-300 uppercase">{feed?.cache_status || 'INITIALIZING'}</span>
            </p>
          </div>
        </div>
      </div>

      {loading && !feed && (
        <div className="py-12 text-center text-slate-400 text-xs font-mono flex items-center justify-center space-x-2">
          <RefreshCw className="w-4 h-4 animate-spin text-accent" />
          <span>Polling NASA DSN live XML feed...</span>
        </div>
      )}

      {error && !feed && (
        <div className="p-3 bg-red-950/40 border border-status-alert/40 rounded text-xs text-red-300 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 text-status-alert flex-shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={fetchDsn}
            className="text-xs bg-red-900/60 hover:bg-red-800 text-white px-2 py-1 rounded border border-red-700 transition"
          >
            Retry
          </button>
        </div>
      )}

      {/* Complexes Card View */}
      {feed && viewMode === 'cards' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4" data-testid="dsn-complexes-grid">
          {feed.stations.map((station: DSNStation) => {
            const staticCoord =
              STATIC_STATION_COORDINATES[station.name.toLowerCase()] ||
              STATIC_STATION_COORDINATES[station.friendly_name.toLowerCase()] || {
                lat: 'Unknown',
                lon: 'Unknown',
                location: station.friendly_name,
              };

            return (
              <div
                key={station.name}
                className="bg-panel-raised border border-hairline rounded-lg p-4 flex flex-col justify-between"
                data-testid={`dsn-station-${station.name.toLowerCase()}`}
              >
                <div>
                  {/* Station Header */}
                  <div className="flex items-start justify-between pb-3 border-b border-hairline">
                    <div>
                      <h3 className="text-sm font-bold text-white tracking-wide">{station.friendly_name}</h3>
                      <div className="text-[11px] text-slate-400 font-mono mt-0.5">
                        Code: <span className="uppercase text-slate-300">{station.name}</span>
                      </div>
                    </div>
                    <span className="text-[10px] font-mono px-2 py-0.5 bg-slate-800 text-slate-300 rounded border border-hairline">
                      {station.dishes.length} Dishes
                    </span>
                  </div>

                  {/* Static Coordinates Tag */}
                  <div className="mt-2.5 p-2 bg-canvas/60 border border-hairline rounded text-[11px] font-mono text-slate-400">
                    <div className="text-[10px] uppercase text-slate-400 font-semibold mb-0.5">
                      Static Coordinates [Datum]
                    </div>
                    <div className="text-slate-300 tabular-nums">
                      {staticCoord.lat}, {staticCoord.lon}
                    </div>
                    <div className="text-slate-400 text-[10px]">{staticCoord.location}</div>
                  </div>

                  {/* Dishes & Active Telemetry List */}
                  <div className="mt-3 space-y-2.5">
                    <div className="text-[10px] uppercase font-mono text-slate-400 font-semibold tracking-wider">
                      Live Dish Activity
                    </div>

                    {station.dishes.length === 0 ? (
                      <div className="text-xs text-slate-400 font-mono italic">No dishes reported active.</div>
                    ) : (
                      station.dishes.map((dish) => {
                        const target = dish.targets[0];
                        const isTracking = dish.targets.length > 0 || dish.up_signals.some((s) => s.active) || dish.down_signals.some((s) => s.active);

                        return (
                          <div
                            key={dish.name}
                            className={`p-2.5 rounded border text-xs font-mono transition ${
                              isTracking
                                ? 'bg-panel border-accent/40 text-slate-200'
                                : 'bg-panel/40 border-hairline text-slate-400'
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-bold text-white">{dish.name}</span>
                              <span
                                className={`text-[10px] px-1.5 py-0.5 rounded ${
                                  isTracking
                                    ? 'bg-sky-950 text-accent font-semibold border border-sky-800'
                                    : 'bg-slate-800 text-slate-400'
                                }`}
                              >
                                {isTracking ? (target ? target.name : 'TRACKING') : 'IDLE'}
                              </span>
                            </div>

                            <div className="mt-1.5 grid grid-cols-2 gap-1 text-[11px] text-slate-400">
                              <div>
                                Az: <span className="text-slate-300 tabular-nums">{dish.azimuth_deg != null ? `${dish.azimuth_deg.toFixed(1)}°` : '—'}</span>
                              </div>
                              <div>
                                El: <span className="text-slate-300 tabular-nums">{dish.elevation_deg != null ? `${dish.elevation_deg.toFixed(1)}°` : '—'}</span>
                              </div>
                              {dish.wind_speed_kmh != null && (
                                <div className="col-span-2">
                                  Wind: <span className="text-slate-300 tabular-nums">{dish.wind_speed_kmh.toFixed(0)} km/h</span>
                                </div>
                              )}
                            </div>

                            {target && (
                              <div className="mt-2 pt-1.5 border-t border-hairline/60 text-[10px] text-slate-400">
                                {target.downleg_range_km && (
                                  <div>
                                    Range: <span className="text-slate-200 tabular-nums">{(target.downleg_range_km / 1e6).toFixed(2)}M km</span>
                                  </div>
                                )}
                                {target.rtlt_seconds && (
                                  <div>
                                    RTLT: <span className="text-slate-200 tabular-nums">{target.rtlt_seconds.toFixed(1)} s</span>
                                  </div>
                                )}
                              </div>
                            )}

                            {/* Signal Carrier telemetry */}
                            {(dish.up_signals.length > 0 || dish.down_signals.length > 0) && (
                              <div className="mt-1.5 flex items-center space-x-2 text-[10px]">
                                {dish.up_signals.filter((s) => s.active).map((s, idx) => (
                                  <span key={`up-${idx}`} className="text-emerald-400 bg-emerald-950/60 px-1 py-0.2 rounded border border-emerald-800">
                                    UP: {s.band || 'RF'} {s.data_rate_bps ? `${(s.data_rate_bps / 1000).toFixed(1)}k` : ''}
                                  </span>
                                ))}
                                {dish.down_signals.filter((s) => s.active).map((s, idx) => (
                                  <span key={`down-${idx}`} className="text-sky-400 bg-sky-950/60 px-1 py-0.2 rounded border border-sky-800">
                                    DOWN: {s.band || 'RF'} {s.data_rate_bps ? `${(s.data_rate_bps / 1000).toFixed(1)}k` : ''}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>

                <div className="mt-4 pt-2 border-t border-hairline text-[10px] font-mono text-slate-400 flex justify-between">
                  <span>Site Datum: WGS-84</span>
                  <span>UTC Offset: {station.time_zone_offset_ms / 3600000}h</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Accessible Table Fallback View */}
      {feed && viewMode === 'table' && (
        <div className="overflow-x-auto border border-hairline rounded-lg" data-testid="dsn-table-fallback">
          <table className="w-full text-left text-xs font-mono" aria-label="Deep Space Network Active Passes and Telemetry Table">
            <thead className="bg-panel-raised text-slate-400 uppercase text-[10px] tracking-wider border-b border-hairline">
              <tr>
                <th scope="col" className="p-3">Complex</th>
                <th scope="col" className="p-3">Coordinates (Static)</th>
                <th scope="col" className="p-3">Dish</th>
                <th scope="col" className="p-3">Spacecraft / Target</th>
                <th scope="col" className="p-3">Pointing (Az/El)</th>
                <th scope="col" className="p-3">Distance (km)</th>
                <th scope="col" className="p-3">RTLT (s)</th>
                <th scope="col" className="p-3">Uplink (Live)</th>
                <th scope="col" className="p-3">Downlink (Live)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline bg-panel text-slate-200">
              {flattenedPasses.map((pass, index) => {
                const staticCoord = STATIC_STATION_COORDINATES[pass.stationCode] || {
                  lat: 'N/A',
                  lon: 'N/A',
                  location: pass.stationName,
                };

                return (
                  <tr key={`${pass.dishName}-${index}`} className="hover:bg-panel-raised/50 transition">
                    <td className="p-3 font-semibold text-white">{pass.stationName}</td>
                    <td className="p-3 text-slate-400 text-[11px] tabular-nums">
                      {staticCoord.lat}, {staticCoord.lon}
                    </td>
                    <td className="p-3 font-bold text-accent">{pass.dishName}</td>
                    <td className="p-3">
                      <span className="px-1.5 py-0.5 bg-slate-800 rounded text-slate-200 border border-hairline font-semibold">
                        {pass.targetName}
                      </span>
                    </td>
                    <td className="p-3 text-slate-300 tabular-nums">
                      {pass.azimuth != null ? `${pass.azimuth.toFixed(1)}°` : '—'} /{' '}
                      {pass.elevation != null ? `${pass.elevation.toFixed(1)}°` : '—'}
                    </td>
                    <td className="p-3 tabular-nums">
                      {pass.rangeKm ? `${(pass.rangeKm / 1e6).toFixed(2)}M km` : '—'}
                    </td>
                    <td className="p-3 tabular-nums">
                      {pass.rtltSec ? `${pass.rtltSec.toFixed(1)} s` : '—'}
                    </td>
                    <td className="p-3">
                      {pass.upBand ? (
                        <span className="text-emerald-400">
                          {pass.upBand}-band {pass.upRate ? `(${pass.upRate} bps)` : ''}
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td className="p-3">
                      {pass.downBand ? (
                        <span className="text-sky-400">
                          {pass.downBand}-band {pass.downRate ? `(${pass.downRate} bps)` : ''}
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};
