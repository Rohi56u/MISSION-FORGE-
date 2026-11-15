import { render, screen, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { TrajectoryView3D } from '../src/components/astrodynamics/TrajectoryView3D';
import { api, LambertSolveResponse, HorizonsQueryResponse } from '../src/lib/api';

describe('TrajectoryView3D Component (Astrodynamics Lab)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockHorizonsResponse: HorizonsQueryResponse = {
    target_id: '399',
    target_name: 'Earth',
    center_id: '500@10',
    center_name: 'Sun',
    coordinate_frame: 'ICRF',
    origin_center: 'Sun',
    time_scale: 'TDB',
    units: {},
    vectors: [
      {
        epoch_jd: 2460000,
        calendar_date: '2026-06-15',
        position_km: { x: 149597870.7, y: 0, z: 0 },
        velocity_kms: { x: 0, y: 29.8, z: 0 },
      },
    ],
    source_url: 'https://ssd.jpl.nasa.gov',
    retrieved_at: '2026-11-15T11:00:00Z',
    cache_status: 'LIVE',
  };

  const mockLambertSolution: LambertSolveResponse = {
    v1_kms: { x: 29.8, y: 5.4, z: 1.2 },
    v2_kms: { x: 12.1, y: -21.4, z: -0.8 },
    converged: true,
    iterations: 7,
    residual: 3.4e-8,
    semi_major_axis_km: 188000000,
    eccentricity: 0.2075,
    transfer_angle_deg: 154.3,
    time_of_flight_s: 18057600, // ~209 days
    solution_branch: 'ELLIPTIC_PROGRADE',
    stumpff_z: 0.142,
    units: {
      position: 'km',
      velocity: 'km/s',
      time: 'seconds',
      angle: 'degrees',
    },
  };

  it('renders patched-conic model limitations notice prominently', async () => {
    vi.spyOn(api, 'getHorizonsVectors').mockResolvedValue(mockHorizonsResponse);
    vi.spyOn(api, 'solveLambert').mockResolvedValue(mockLambertSolution);

    render(
      <TrajectoryView3D
        departureDate="2026-06-15"
        arrivalDate="2027-01-10"
        tofDays={209}
        initialC3={15.4}
        initialDvTotal={5.64}
      />
    );

    await waitFor(() => {
      expect(screen.getByRole('note')).toBeInTheDocument();
    });
    expect(
      screen.getByText(/Two-body patched-conic approximation; perturbations and mid-course maneuvers excluded/i)
    ).toBeInTheDocument();
  });

  it('displays converged Lambert parameters, Delta-V, and velocity vector readouts', async () => {
    vi.spyOn(api, 'getHorizonsVectors').mockResolvedValue(mockHorizonsResponse);
    vi.spyOn(api, 'solveLambert').mockResolvedValue(mockLambertSolution);

    render(
      <TrajectoryView3D
        departureDate="2026-06-15"
        arrivalDate="2027-01-10"
        tofDays={209}
        initialC3={15.4}
        initialDvTotal={5.64}
      />
    );

    await waitFor(() => {
      const telemetry = screen.getByTestId('lambert-telemetry');
      expect(within(telemetry).getByText('CONVERGED')).toBeInTheDocument();
    });

    const telemetry = screen.getByTestId('lambert-telemetry');
    expect(within(telemetry).getByText('CONVERGED')).toBeInTheDocument();
    expect(within(telemetry).getByText('209.0')).toBeInTheDocument(); // Days
    expect(within(telemetry).getByText('15.40')).toBeInTheDocument(); // C3
    expect(within(telemetry).getByTestId('telemetry-delta-v')).toHaveTextContent('5.64'); // Delta-V
    expect(within(telemetry).getByText('0.2075')).toBeInTheDocument(); // Eccentricity
    expect(within(telemetry).getByText('154.30°')).toBeInTheDocument(); // Transfer Angle
    expect(within(telemetry).getByText(/\[29.80, 5.40, 1.20\] km\/s/)).toBeInTheDocument(); // v1 vector
  });

  it('renders accessible tabular fallback with full state vectors and Delta-V when WebGL is inactive or toggled', async () => {
    vi.spyOn(api, 'getHorizonsVectors').mockResolvedValue(mockHorizonsResponse);
    vi.spyOn(api, 'solveLambert').mockResolvedValue(mockLambertSolution);

    render(
      <TrajectoryView3D
        departureDate="2026-06-15"
        arrivalDate="2027-01-10"
        tofDays={209}
        initialC3={15.4}
        initialDvTotal={5.64}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('webgl-fallback-view')).toBeInTheDocument();
      expect(screen.getByRole('table', { name: /Lambert Transfer Parameters Table/i })).toBeInTheDocument();
    });

    expect(screen.getByText(/ACCESSIBLE TABULAR TRAJECTORY TELEMETRY/i)).toBeInTheDocument();
    expect(screen.getByText('Total Transfer ΔV (Budget)')).toBeInTheDocument();
    expect(screen.getByText('5.640')).toBeInTheDocument();
    expect(screen.getByText(/Departure State \(Earth\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Arrival State \(Mars\)/i)).toBeInTheDocument();
  });
});
