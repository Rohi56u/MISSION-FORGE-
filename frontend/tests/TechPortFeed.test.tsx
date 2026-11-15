import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { TechPortFeed } from '../src/components/bridge/TechPortFeed';
import { api, TechPortListResponse, TechPortProjectDetail } from '../src/lib/api';

describe('TechPortFeed Component (Command Bridge)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockListResponse: TechPortListResponse = {
    total_count: 2,
    projects: [
      {
        id: 94101,
        title: 'Deep Space Optical Communications (DSOC)',
        last_updated: '2026-03-12',
      },
      {
        id: 94102,
        title: 'Nuclear Electric Propulsion Scaled Core Test',
        last_updated: '2026-04-01',
      },
    ],
    retrieved_at: '2026-11-15T11:00:00Z',
    cache_status: 'LIVE',
    rate_limit: 1000,
    rate_limit_remaining: 998,
    source_url: 'https://techport.nasa.gov/api/projects',
  };

  const mockDetail: TechPortProjectDetail = {
    id: 94101,
    title: 'Deep Space Optical Communications (DSOC)',
    status: 'Active',
    description: 'Gigabit-class laser communication uplink and downlink demonstration beyond Mars orbit.',
    benefits: '10x to 100x higher telemetry bandwidth for flagship planetary exploration missions.',
    lead_organization: 'Jet Propulsion Laboratory (JPL)',
    program: 'Space Technology Mission Directorate',
    trl_begin: 4,
    trl_current: 7,
    trl_end: 9,
    last_updated: '2026-03-12',
    canonical_url: 'https://techport.nasa.gov/view/94101',
  };

  it('renders project list and fetches detail for first project', async () => {
    vi.spyOn(api, 'getTechPortProjects').mockResolvedValue(mockListResponse);
    vi.spyOn(api, 'getTechPortProject').mockResolvedValue(mockDetail);

    render(<TechPortFeed />);

    await waitFor(() => {
      expect(screen.getAllByText('Deep Space Optical Communications (DSOC)')[0]).toBeInTheDocument();
      expect(screen.getByText('Nuclear Electric Propulsion Scaled Core Test')).toBeInTheDocument();
    });

    // Verify detail panel rendered with TRL progression
    await waitFor(() => {
      expect(screen.getByTestId('techport-detail-panel')).toBeInTheDocument();
      expect(screen.getByText(/Current: TRL 7/i)).toBeInTheDocument();
      expect(screen.getByText('Jet Propulsion Laboratory (JPL)')).toBeInTheDocument();
    });
  });

  it('triggers search filter on submission', async () => {
    const searchSpy = vi.spyOn(api, 'getTechPortProjects').mockResolvedValue(mockListResponse);
    vi.spyOn(api, 'getTechPortProject').mockResolvedValue(mockDetail);

    render(<TechPortFeed />);

    const searchInput = screen.getByLabelText(/Search NASA TechPort projects/i);
    fireEvent.change(searchInput, { target: { value: 'nuclear' } });

    const form = searchInput.closest('form')!;
    fireEvent.submit(form);

    await waitFor(() => {
      expect(searchSpy).toHaveBeenCalledWith('nuclear');
    });
  });
});
