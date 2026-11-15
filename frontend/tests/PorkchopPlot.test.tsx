import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { PorkchopPlot } from '../src/components/astrodynamics/PorkchopPlot';
import { api, PorkchopResponse } from '../src/lib/api';

describe('PorkchopPlot Component (Astrodynamics Lab)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockPorkchopData: PorkchopResponse = {
    job_id: 'job-123',
    origin_body: 'EARTH',
    target_body: 'MARS',
    departure_dates: ['2026-06-01', '2026-06-15', '2026-07-01'],
    arrival_dates: ['2026-12-01', '2027-01-15'],
    step_size_days: 15.0,
    total_grid_points: 6,
    valid_cells_count: 5,
    c3_grid: [
      [18.5, 14.2, null], // Notice null represents non-converged/gap
      [22.1, 16.8, 19.4],
    ],
    vinf_dep_grid: [
      [4.3, 3.77, null],
      [4.7, 4.1, 4.4],
    ],
    vinf_arr_grid: [
      [2.9, 2.65, null],
      [3.4, 2.9, 3.1],
    ],
    tof_days_grid: [
      [183, 169, null],
      [228, 214, 198],
    ],
    dv_inj_grid: [
      [3.6, 3.4, null],
      [3.8, 3.5, 3.7],
    ],
    dv_arr_grid: [
      [2.1, 1.9, null],
      [2.4, 2.1, 2.2],
    ],
    dv_total_grid: [
      [5.7, 5.3, null],
      [6.2, 5.6, 5.9],
    ],
    valid_mask: [
      [true, true, false], // cell [0][2] is invalid / non-converged
      [true, true, true],
    ],
    minima: {
      c3: {
        c3: 14.2,
        tof_days: 169,
        departure_date: '2026-06-15',
        arrival_date: '2026-12-01',
        dep_idx: 1,
        arr_idx: 0,
      },
    },
    units: { c3: 'km^2/s^2', velocity: 'km/s', time: 'days' },
    provenance: { engine: 'pykep-lambert' },
  };

  it('computes porkchop grid on mount and auto-selects global minimum C3', async () => {
    const calcSpy = vi.spyOn(api, 'calculatePorkchop').mockResolvedValue(mockPorkchopData);
    const selectCallback = vi.fn();

    render(<PorkchopPlot onSelectOpportunity={selectCallback} />);

    await waitFor(() => {
      expect(calcSpy).toHaveBeenCalled();
    });

    // Inspector should show selected minimum opportunity
    await waitFor(() => {
      expect(screen.getByTestId('porkchop-inspector')).toBeInTheDocument();
      expect(screen.getByText('2026-06-15 UTC')).toBeInTheDocument();
      expect(screen.getByText('2026-12-01 UTC')).toBeInTheDocument();
      expect(screen.getByText('14.20')).toBeInTheDocument(); // C3
    });

    expect(selectCallback).toHaveBeenCalledWith(
      expect.objectContaining({
        departureDate: '2026-06-15',
        arrivalDate: '2026-12-01',
        c3: 14.2,
      })
    );
  });

  it('handles non-converged / null cells cleanly without rendering zero values', async () => {
    vi.spyOn(api, 'calculatePorkchop').mockResolvedValue(mockPorkchopData);
    render(<PorkchopPlot />);

    await waitFor(() => {
      expect(screen.getByText('5')).toBeInTheDocument();
      expect(screen.getByText(/valid \/ 6 total/i)).toBeInTheDocument();
    });

    // Verify non-converged legend indicator is present
    expect(screen.getByText(/Non-converged gap/i)).toBeInTheDocument();
  });

  it('renders accessible table fallback with Pareto-optimal transfer opportunities', async () => {
    vi.spyOn(api, 'calculatePorkchop').mockResolvedValue(mockPorkchopData);
    render(<PorkchopPlot />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Opportunities Table/i })).toBeInTheDocument();
    });

    const tableToggle = screen.getByRole('button', { name: /Opportunities Table/i });
    fireEvent.click(tableToggle);

    expect(screen.getByTestId('porkchop-table-fallback')).toBeInTheDocument();
    expect(screen.getByRole('table', { name: /Optimal Minimum C3 Trajectory Windows Table/i })).toBeInTheDocument();
    expect(screen.getByText('#1')).toBeInTheDocument();
    expect(screen.getByText('14.20')).toBeInTheDocument();
  });

  it('catches and displays validation errors when origin and target bodies are identical', async () => {
    vi.spyOn(api, 'calculatePorkchop').mockResolvedValue(mockPorkchopData);
    render(<PorkchopPlot />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Compute/i })).toBeInTheDocument();
    });

    const targetSelect = screen.getByLabelText(/Target Body/i);
    fireEvent.change(targetSelect, { target: { value: 'EARTH' } });

    const computeBtn = screen.getByRole('button', { name: /Compute/i });
    fireEvent.click(computeBtn);

    expect(screen.getByText(/Origin body and target destination cannot be identical/i)).toBeInTheDocument();
  });

  it('purges stale plot data and selected opportunity when calculation fails (DEF-03 regression)', async () => {
    vi.spyOn(api, 'calculatePorkchop')
      .mockResolvedValueOnce(mockPorkchopData)
      .mockRejectedValueOnce(new Error('Ephemeris provider unreachable'));

    render(<PorkchopPlot />);

    await waitFor(() => {
      expect(screen.getByTestId('porkchop-inspector')).toBeInTheDocument();
    });

    const computeBtn = screen.getByRole('button', { name: /Compute/i });
    fireEvent.click(computeBtn);

    await waitFor(() => {
      expect(screen.getByText(/Ephemeris provider unreachable/i)).toBeInTheDocument();
    });

    // Previous inspector and data must be purged
    expect(screen.queryByTestId('porkchop-inspector')).not.toBeInTheDocument();
  });
});
