import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { CommandBridge } from '../src/views/CommandBridge';
import { api } from '../src/lib/api';

describe('CommandBridge View Integration', () => {
  it('mounts active missions, DSN monitor, and TechPort feed sections', async () => {
    vi.spyOn(api, 'getMissions').mockResolvedValue([]);
    vi.spyOn(api, 'getMissionDesigns').mockResolvedValue([]);
    vi.spyOn(api, 'getDsnNow').mockResolvedValue({
      stations: [],
      timestamp_ms: null,
      retrieved_at: '',
      source_timestamp: null,
      cache_status: 'LIVE',
      source_url: '',
      active_tracking_count: 0,
      tracked_spacecraft: [],
    });
    vi.spyOn(api, 'getTechPortProjects').mockResolvedValue({
      total_count: 0,
      projects: [],
      retrieved_at: '',
      cache_status: 'LIVE',
      rate_limit: null,
      rate_limit_remaining: null,
      source_url: '',
    });

    render(<CommandBridge />);
    expect(screen.getByTestId('command-bridge-view')).toBeInTheDocument();
    expect(screen.getByTestId('active-missions-section')).toBeInTheDocument();
    expect(screen.getByTestId('dsn-monitor-section')).toBeInTheDocument();
    expect(screen.getByTestId('techport-feed-section')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('missions-empty-state')).toBeInTheDocument();
    });
  });
});
