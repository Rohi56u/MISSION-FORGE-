import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ActiveMissions } from '../src/components/bridge/ActiveMissions';
import { api, Mission } from '../src/lib/api';

describe('ActiveMissions Component (Command Bridge)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders loading state initially', () => {
    vi.spyOn(api, 'getMissions').mockReturnValue(new Promise(() => {}));
    render(<ActiveMissions />);
    expect(screen.getByText(/Querying mission registry/i)).toBeInTheDocument();
  });

  it('renders registered missions with full constraints and margins', async () => {
    const mockMissions: Mission[] = [
      {
        id: 'mission-01',
        name: 'Ares Pathfinder III',
        description: 'Atmospheric entry and rover deployment on Elysium Planitia.',
        target: 'MARS',
        mission_class: 'DISCOVERY',
        budget_cap_usd: 500000000,
        max_launch_mass_kg: 1800,
        min_delta_v_mps: 3800,
        min_power_margin_percent: 20,
        phase: 'Phase A: Formulation',
        launch_epoch: '2026-Q4 Window',
      },
    ];

    vi.spyOn(api, 'getMissions').mockResolvedValue(mockMissions);
    vi.spyOn(api, 'getMissionDesigns').mockResolvedValue([
      {
        id: 'des-01',
        mission_id: 'mission-01',
        name: 'Pathfinder Baseline',
        version: 1,
        dry_mass_kg: 720,
        wet_mass_kg: 1450,
        propellant_mass_kg: 730,
        power_draw_w: 420,
        power_generation_w: 580,
        delta_v_mps: 4100,
        total_cost_usd: 480000000,
        is_feasible: true,
        violations: [],
      },
    ]);

    render(<ActiveMissions />);

    await waitFor(() => {
      expect(screen.getByText('Ares Pathfinder III')).toBeInTheDocument();
    });

    expect(screen.getByText('Target: MARS')).toBeInTheDocument();
    expect(screen.getByText('DISCOVERY')).toBeInTheDocument();
    expect(screen.getByText('Phase A: Formulation')).toBeInTheDocument();
    expect(screen.getByText('2026-Q4 Window')).toBeInTheDocument();
    expect(screen.getByText('$500.0M')).toBeInTheDocument();
    expect(screen.getByText('1,800 kg')).toBeInTheDocument();
    expect(screen.getByText('3,800 m/s')).toBeInTheDocument();
    expect(screen.getByText('20%')).toBeInTheDocument();

    // Verify Dry and Wet Mass Margins
    const dryMarginEl = screen.getByTestId('dry-mass-margin');
    expect(dryMarginEl).toBeInTheDocument();
    expect(dryMarginEl).toHaveTextContent('DRY MASS MARGIN');
    // (1800 - 720) / 1800 * 100 = 60.0%
    expect(dryMarginEl).toHaveTextContent('+60.0%');

    const wetMarginEl = screen.getByTestId('wet-mass-margin');
    expect(wetMarginEl).toBeInTheDocument();
    expect(wetMarginEl).toHaveTextContent('WET MASS MARGIN');
    // (1800 - 1450) / 1800 * 100 = 19.4%
    expect(wetMarginEl).toHaveTextContent('+19.4%');
  });

  it('renders clean empty state with API instructions when no missions are present', async () => {
    vi.spyOn(api, 'getMissions').mockResolvedValue([]);
    render(<ActiveMissions />);

    await waitFor(() => {
      expect(screen.getByTestId('missions-empty-state')).toBeInTheDocument();
    });

    expect(screen.getByText(/No Active Missions Found/i)).toBeInTheDocument();
    expect(screen.getByText(/Endpoint: POST \/api\/v1\/missions/i)).toBeInTheDocument();
  });

  it('renders error state and handles retry button', async () => {
    const getMissionsSpy = vi.spyOn(api, 'getMissions')
      .mockRejectedValueOnce(new Error('Database lock error'))
      .mockResolvedValueOnce([]);

    render(<ActiveMissions />);

    await waitFor(() => {
      expect(screen.getByText('Database lock error')).toBeInTheDocument();
    });

    const retryBtn = screen.getByRole('button', { name: /retry/i });
    fireEvent.click(retryBtn);

    await waitFor(() => {
      expect(getMissionsSpy).toHaveBeenCalledTimes(2);
    });
  });
});
