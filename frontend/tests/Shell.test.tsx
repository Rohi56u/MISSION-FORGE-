import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { Shell } from '../src/components/layout/Shell';
import * as healthHook from '../src/hooks/useBackendHealth';

describe('Application Shell Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders application brand, header, and footer notices', async () => {
    vi.spyOn(healthHook, 'useBackendHealth').mockReturnValue({
      status: 'nominal',
      latencyMs: 45,
      lastChecked: new Date('2026-11-15T10:00:00Z'),
      data: {
        status: 'healthy',
        service: 'Mission Forge',
        version: '1.0.0',
        environment: 'production',
      },
      error: null,
      checkHealth: vi.fn(),
    });

    await act(async () => {
      render(
        <Shell currentPath="/" onNavigate={vi.fn()}>
          <div>Child Content</div>
        </Shell>
      );
    });

    expect(screen.getByText('MISSION FORGE')).toBeInTheDocument();
    expect(screen.getByText('Aerospace Mission Design & Autonomous Simulation')).toBeInTheDocument();
    expect(screen.getByText('Child Content')).toBeInTheDocument();
    expect(screen.getByText(/AEROSPACE MISSION PLATFORM/i)).toBeInTheDocument();
  });

  it('displays real-time UTC chronometer with tabular numerals', async () => {
    vi.spyOn(healthHook, 'useBackendHealth').mockReturnValue({
      status: 'nominal',
      latencyMs: 45,
      lastChecked: new Date('2026-11-15T10:00:00Z'),
      data: null,
      error: null,
      checkHealth: vi.fn(),
    });

    await act(async () => {
      render(
        <Shell currentPath="/" onNavigate={vi.fn()}>
          <div>Content</div>
        </Shell>
      );
    });

    const chronometer = screen.getByTestId('utc-chronometer');
    expect(chronometer).toBeInTheDocument();
    expect(chronometer.textContent).toMatch(/UTC/);
  });

  it('triggers onNavigate callback when clicking navigation links', async () => {
    vi.spyOn(healthHook, 'useBackendHealth').mockReturnValue({
      status: 'nominal',
      latencyMs: 45,
      lastChecked: new Date(),
      data: null,
      error: null,
      checkHealth: vi.fn(),
    });

    const handleNavigate = vi.fn();
    await act(async () => {
      render(
        <Shell currentPath="/" onNavigate={handleNavigate}>
          <div>Content</div>
        </Shell>
      );
    });

    const astrodynamicsBtn = screen.getByRole('button', { name: /ASTRODYNAMICS LAB/i });
    fireEvent.click(astrodynamicsBtn);
    expect(handleNavigate).toHaveBeenCalledWith('/trajectory');

    const commandBridgeBtn = screen.getByRole('button', { name: /COMMAND BRIDGE/i });
    fireEvent.click(commandBridgeBtn);
    expect(handleNavigate).toHaveBeenCalledWith('/');

    const spacecraftBtn = screen.getByRole('button', { name: /SPACECRAFT/i });
    fireEvent.click(spacecraftBtn);
    expect(handleNavigate).toHaveBeenCalledWith('/spacecraft');

    const cdfBtn = screen.getByRole('button', { name: /CDF COLLAB/i });
    fireEvent.click(cdfBtn);
    expect(handleNavigate).toHaveBeenCalledWith('/cdf');

    const fdirBtn = screen.getByRole('button', { name: /FDIR & CAPCOM/i });
    fireEvent.click(fdirBtn);
    expect(handleNavigate).toHaveBeenCalledWith('/fdir');

    const dossierBtn = screen.getByRole('button', { name: /MISSION DOSSIER/i });
    fireEvent.click(dossierBtn);
    expect(handleNavigate).toHaveBeenCalledWith('/dossier');
  });

  it('displays telemetry offline banner when backend health is unreachable', async () => {
    vi.spyOn(healthHook, 'useBackendHealth').mockReturnValue({
      status: 'offline',
      latencyMs: 120,
      lastChecked: new Date(),
      data: null,
      error: 'Backend connection refused',
      checkHealth: vi.fn(),
    });

    await act(async () => {
      render(
        <Shell currentPath="/" onNavigate={vi.fn()}>
          <div>Content</div>
        </Shell>
      );
    });

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/Telemetry Link Severed/i)).toBeInTheDocument();
    expect(screen.getByText(/Backend connection refused/i)).toBeInTheDocument();
  });
});
