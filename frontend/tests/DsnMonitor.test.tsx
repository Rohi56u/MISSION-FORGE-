import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DsnMonitor } from '../src/components/bridge/DsnMonitor';
import { api, DSNFeedResponse } from '../src/lib/api';

describe('DsnMonitor Component (Command Bridge)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockDsnFeed: DSNFeedResponse = {
    stations: [
      {
        name: 'gdscc',
        friendly_name: 'Goldstone',
        time_utc: 1770000000000,
        time_zone_offset_ms: -28800000,
        dishes: [
          {
            name: 'DSS14',
            azimuth_deg: 184.2,
            elevation_deg: 42.5,
            wind_speed_kmh: 12.0,
            is_mspa: false,
            is_array: false,
            is_ddor: false,
            activity: 'TRACKING_MARS',
            targets: [
              {
                name: 'M20',
                target_id: '101',
                upleg_range_km: 215000000,
                downleg_range_km: 215000000,
                rtlt_seconds: 1434.3,
              },
            ],
            up_signals: [
              {
                active: true,
                signal_type: 'carrier',
                data_rate_bps: 2000,
                frequency_hz: 7150000000,
                band: 'X',
                power_dbm_or_kw: 20,
                spacecraft: 'M20',
                spacecraft_id: '101',
              },
            ],
            down_signals: [
              {
                active: true,
                signal_type: 'data',
                data_rate_bps: 120000,
                frequency_hz: 8400000000,
                band: 'Ka',
                power_dbm_or_kw: -125.4,
                spacecraft: 'M20',
                spacecraft_id: '101',
              },
            ],
          },
        ],
      },
      {
        name: 'mdscc',
        friendly_name: 'Madrid',
        time_utc: 1770000000000,
        time_zone_offset_ms: 3600000,
        dishes: [],
      },
      {
        name: 'cdscc',
        friendly_name: 'Canberra',
        time_utc: 1770000000000,
        time_zone_offset_ms: 36000000,
        dishes: [],
      },
    ],
    timestamp_ms: 1770000000000,
    retrieved_at: '2026-11-15T11:00:00Z',
    source_timestamp: '2026-11-15T11:00:00Z',
    cache_status: 'LIVE',
    source_url: 'https://eyes.nasa.gov/dsn/data/dsn.xml',
    active_tracking_count: 1,
    tracked_spacecraft: ['M20'],
  };

  it('renders distinction between static metadata and live telemetry feed', async () => {
    vi.spyOn(api, 'getDsnNow').mockResolvedValue(mockDsnFeed);
    render(<DsnMonitor />);

    await waitFor(() => {
      expect(screen.getByText('STATIC METADATA')).toBeInTheDocument();
      expect(screen.getByText('LIVE FEED DATA')).toBeInTheDocument();
      expect(screen.getAllByText(/M20/i)[0]).toBeInTheDocument();
    });

    // Verify static coordinates definition for Goldstone
    expect(screen.getAllByText(/35.4267°N, 116.8900°W/)[0]).toBeInTheDocument();
    // Verify static coordinates definition for Madrid
    expect(screen.getAllByText(/40.4272°N, 4.2500°W/)[0]).toBeInTheDocument();
    // Verify static coordinates definition for Canberra
    expect(screen.getAllByText(/35.4014°S, 148.9817°E/)[0]).toBeInTheDocument();
    expect(screen.getByText('LIVE FEED DATA')).toBeInTheDocument();
  });

  it('displays the three international complexes: Goldstone, Madrid, and Canberra', async () => {
    vi.spyOn(api, 'getDsnNow').mockResolvedValue(mockDsnFeed);
    render(<DsnMonitor />);

    await waitFor(() => {
      expect(screen.getByTestId('dsn-station-gdscc')).toBeInTheDocument();
      expect(screen.getByTestId('dsn-station-mdscc')).toBeInTheDocument();
      expect(screen.getByTestId('dsn-station-cdscc')).toBeInTheDocument();
    });

    expect(screen.getByText('DSS14')).toBeInTheDocument();
    expect(screen.getByText('184.2°')).toBeInTheDocument();
    expect(screen.getByText('42.5°')).toBeInTheDocument();
  });

  it('toggles to accessible table fallback with tracking passes and coordinates', async () => {
    vi.spyOn(api, 'getDsnNow').mockResolvedValue(mockDsnFeed);
    render(<DsnMonitor />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Table/i })).toBeInTheDocument();
    });

    const tableToggle = screen.getByRole('button', { name: /Table/i });
    fireEvent.click(tableToggle);

    expect(screen.getByTestId('dsn-table-fallback')).toBeInTheDocument();
    expect(screen.getByRole('table', { name: /Deep Space Network Active Passes and Telemetry Table/i })).toBeInTheDocument();
    expect(screen.getByText('Goldstone')).toBeInTheDocument();
    expect(screen.getByText('DSS14')).toBeInTheDocument();
  });
});
