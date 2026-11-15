import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SpacecraftVisualizer3D } from '../src/components/spacecraft/SpacecraftVisualizer3D';
import { ComponentLedger } from '../src/components/spacecraft/ComponentLedger';
import { SpacecraftDesigner } from '../src/views/SpacecraftDesigner';
import { api, ComponentItem } from '../src/lib/api';

describe('Phase 10 — Spacecraft Visualizer & Component Ledger', () => {
  const mockComponents: ComponentItem[] = [
    {
      id: 'comp-1',
      name: 'UltraTripleJunction Solar Array',
      subsystem: 'POWER',
      description: 'High efficiency photovoltaic array',
      mass_kg: 45.0,
      power_draw_w: 0.0,
      power_generation_w: 1200.0,
      cost_usd: 15000000,
      isp_seconds: null,
      thrust_newtons: null,
      propellant_type: null,
      solar_area_m2: 12.0,
      solar_efficiency: 0.32,
      decay_rate_annual: 0.01,
      antenna_diameter_m: null,
      frequency_band: null,
      tx_power_w: null,
      trl: 9,
      flight_heritage: 'Curiosity, Psyche',
      techport_id: 'TP-101',
      source_url: 'https://techport.nasa.gov/view/101',
      source_system: 'NASA_TECHPORT',
      raw_source_hash: 'abc123hash',
      verification_status: 'VERIFIED_AUTHORITATIVE',
      field_provenance: {
        solar_efficiency: { citation: 'AIAA-2023-Power', source: 'NASA JPL' },
      },
      specifications: {},
      is_active: true,
      last_synced_at: '2026-11-15T10:00:00Z',
      created_at: '2026-11-15T00:00:00Z',
      updated_at: '2026-11-15T00:00:00Z',
    },
    {
      id: 'comp-2',
      name: 'Experimental Ion Engine Proto',
      subsystem: 'PROPULSION',
      description: 'Next-gen Hall thruster',
      mass_kg: 28.0,
      power_draw_w: 800.0,
      power_generation_w: 0.0,
      cost_usd: 22000000,
      isp_seconds: 3200.0,
      thrust_newtons: 0.25,
      propellant_type: 'Xenon',
      solar_area_m2: null,
      solar_efficiency: null,
      decay_rate_annual: null,
      antenna_diameter_m: null,
      frequency_band: null,
      tx_power_w: null,
      trl: null, // Test truthful "Not assessed"
      flight_heritage: null,
      techport_id: null,
      source_url: null,
      source_system: 'NASA_NTRS',
      raw_source_hash: null,
      verification_status: 'ESTIMATED',
      field_provenance: {},
      specifications: {},
      is_active: true,
      last_synced_at: null,
      created_at: '2026-11-15T00:00:00Z',
      updated_at: '2026-11-15T00:00:00Z',
    },
  ];

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders schematic procedural layout notice and non-flight CAD disclosure', async () => {
    await act(async () => {
      render(
        <SpacecraftVisualizer3D
          components={[
            {
              id: 'comp-1',
              name: 'Solar Array',
              subsystem: 'POWER',
              mass_kg: 45,
              power_draw_w: 0,
              power_generation_w: 1200,
              cost_usd: 15000000,
            },
          ]}
          dryMassKg={120}
          wetMassKg={450}
          powerDrawW={300}
          powerGenW={1200}
        />
      );
    });

    expect(screen.getByText(/SCHEMATIC SUBSYSTEM VIEW/i)).toBeInTheDocument();
    expect(screen.getByText(/Procedural layout represents subsystem architecture/i)).toBeInTheDocument();
    expect(screen.getByText(/Non-flight geometric CAD/i)).toBeInTheDocument();
  });

  it('toggles to accessible tabular fallback with full component breakdown', async () => {
    await act(async () => {
      render(
        <SpacecraftVisualizer3D
          components={[
            {
              id: 'comp-1',
              name: 'UltraTripleJunction Solar Array',
              subsystem: 'POWER',
              mass_kg: 45.0,
              power_draw_w: 0.0,
              power_generation_w: 1200.0,
              cost_usd: 15000000,
            },
          ]}
          dryMassKg={45}
          wetMassKg={45}
          powerDrawW={0}
          powerGenW={1200}
        />
      );
    });

    const toggleBtn = screen.getByRole('button', { name: /toggle accessible tabular view/i });
    await act(async () => {
      fireEvent.click(toggleBtn);
    });

    const table = screen.getByTestId('accessible-component-table');
    expect(table).toBeInTheDocument();
    expect(screen.getByText('UltraTripleJunction Solar Array')).toBeInTheDocument();
    expect(screen.getByText('45.00')).toBeInTheDocument();
    expect(screen.getByText('1200.0')).toBeInTheDocument();
  });

  it('displays truthful "Not assessed" for missing TRL in Component Ledger', async () => {
    vi.spyOn(api, 'getComponents').mockResolvedValue({
      total: 2,
      items: mockComponents,
      limit: 50,
      offset: 0,
    });

    vi.spyOn(api, 'getComponentProvenance').mockResolvedValue({
      component_id: 'comp-1',
      component_name: 'UltraTripleJunction Solar Array',
      subsystem: 'POWER',
      verification_status: 'VERIFIED_AUTHORITATIVE',
      source_system: 'NASA_TECHPORT',
      source_url: 'https://techport.nasa.gov/view/101',
      techport_id: 'TP-101',
      raw_source_hash: 'abc123hash',
      last_synced_at: '2026-11-15T10:00:00Z',
      field_provenance: {
        solar_efficiency: { citation: 'AIAA-2023-Power', source: 'NASA JPL' },
      },
      audit_timestamp: '2026-11-15T10:00:00Z',
    });

    await act(async () => {
      render(
        <ComponentLedger
          configuredComponents={[]}
          onAddComponent={vi.fn()}
          onRemoveComponent={vi.fn()}
        />
      );
    });

    await waitFor(() => {
      expect(screen.getByText('UltraTripleJunction Solar Array')).toBeInTheDocument();
      expect(screen.getByText('Experimental Ion Engine Proto')).toBeInTheDocument();
    });

    // Check TRL 9 rendered for first component
    expect(screen.getByText('TRL 9')).toBeInTheDocument();

    // Check truthful "Not assessed" rendered for missing TRL
    expect(screen.getByText('Not assessed')).toBeInTheDocument();
  });

  it('renders field-level provenance records and citations when component is selected', async () => {
    vi.spyOn(api, 'getComponents').mockResolvedValue({
      total: 2,
      items: mockComponents,
      limit: 50,
      offset: 0,
    });

    vi.spyOn(api, 'getComponentProvenance').mockResolvedValue({
      component_id: 'comp-1',
      component_name: 'UltraTripleJunction Solar Array',
      subsystem: 'POWER',
      verification_status: 'VERIFIED_AUTHORITATIVE',
      source_system: 'NASA_TECHPORT',
      source_url: 'https://techport.nasa.gov/view/101',
      techport_id: 'TP-101',
      raw_source_hash: 'abc123hash',
      last_synced_at: '2026-11-15T10:00:00Z',
      field_provenance: {
        solar_efficiency: { citation: 'AIAA-2023-Power', source: 'NASA JPL' },
      },
      audit_timestamp: '2026-11-15T10:00:00Z',
    });

    const handleSelect = vi.fn();
    await act(async () => {
      render(
        <ComponentLedger
          configuredComponents={[]}
          onAddComponent={vi.fn()}
          onRemoveComponent={vi.fn()}
          selectedComponentId="comp-1"
          onSelectComponent={handleSelect}
        />
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId('provenance-detail')).toBeInTheDocument();
    });

    expect(screen.getByText('TP-101')).toBeInTheDocument();
    expect(screen.getByText(/AIAA-2023-Power/i)).toBeInTheDocument();
    expect(screen.getByText('NASA JPL')).toBeInTheDocument();
  });

  it('renders SpacecraftDesigner view with SWaP-C feasibility verdict', async () => {
    vi.spyOn(api, 'getMissions').mockResolvedValue([
      {
        id: 'mission-mars',
        name: 'Mars Sample Return',
        description: 'Sample retrieval',
        target: 'MARS',
        mission_class: 'FLAGSHIP',
        budget_cap_usd: 1200000000,
        max_launch_mass_kg: 2200,
        min_delta_v_mps: 4200,
        min_power_margin_percent: 15,
      },
    ]);

    vi.spyOn(api, 'getCatalogStatus').mockResolvedValue({
      total_components: 24,
      subsystems_breakdown: { POWER: 6, PROPULSION: 8 },
      verification_status_breakdown: { VERIFIED_AUTHORITATIVE: 20 },
      components_with_provenance: 22,
      provenance_coverage_percent: 91.67,
      source_systems: ['NASA_TECHPORT', 'NASA_NTRS'],
      last_synced_at: '2026-11-15T10:00:00Z',
      audit_timestamp: '2026-11-15T10:00:00Z',
    });

    vi.spyOn(api, 'getMissionDesigns').mockResolvedValue([]);

    vi.spyOn(api, 'analyzeSwapc').mockResolvedValue({
      target: 'MARS',
      distance_au: 1.524,
      mission_class: 'FLAGSHIP',
      dry_mass_kg: 420.0,
      propellant_mass_kg: 450.0,
      wet_mass_kg: 870.0,
      mass_by_subsystem: { POWER: 120, STRUCTURE: 300 },
      total_power_draw_w: 400.0,
      total_power_generated_w: 800.0,
      power_margin_w: 400.0,
      power_margin_percent: 50.0,
      power_by_subsystem: { POWER: 400 },
      available_delta_v_mps: 4500.0,
      required_delta_v_mps: 4200.0,
      delta_v_margin_mps: 300.0,
      effective_isp_s: 310.0,
      propulsion_systems: {},
      mission_duration_years: 1.5,
      downlink_margin_db: 6.2,
      round_trip_light_time_seconds: 1200,
      rtlt_formatted: '20m 00s',
      hardware_cost_usd: 85000000,
      launch_vehicle_cost_usd: 120000000,
      total_mission_cost_usd: 205000000,
      budget_cap_usd: 1200000000,
      budget_margin_usd: 995000000,
      is_feasible: true,
      status: 'NOMINAL',
      violations: [],
      warnings: [],
    });

    vi.spyOn(api, 'getComponents').mockResolvedValue({
      total: 0,
      items: [],
      limit: 50,
      offset: 0,
    });

    await act(async () => {
      render(<SpacecraftDesigner />);
    });

    await waitFor(() => {
      expect(screen.getByText(/Phase 10 — Spacecraft Visualizer/i)).toBeInTheDocument();
      expect(screen.getByText(/VERDICT: NOMINAL — FEASIBLE FLIGHT ARCHITECTURE/i)).toBeInTheDocument();
      expect(screen.getByText('91.67%')).toBeInTheDocument();
    });
  });
});
