import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api, ApiError } from '../src/lib/api';

describe('Mission Forge API Client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('successfully fetches health probe', async () => {
    const mockHealth = {
      status: 'healthy',
      service: 'Mission Forge',
      version: '1.0.0',
      environment: 'development',
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockHealth,
    } as Response);

    const result = await api.getHealth();
    expect(result).toEqual(mockHealth);
    expect(globalThis.fetch).toHaveBeenCalledWith('/health', expect.objectContaining({
      headers: expect.objectContaining({ Accept: 'application/json' }),
    }));
  });

  it('handles HTTP error responses by throwing ApiError with details', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'Mission record not found in database.' }),
    } as Response);

    await expect(api.getMission('missing-id')).rejects.toThrow(ApiError);
    await expect(api.getMission('missing-id')).rejects.toMatchObject({
      status: 404,
      message: 'Mission record not found in database.',
    });
  });

  it('properly serializes payload for solveLambert', async () => {
    const mockSolution = {
      v1_kms: { x: 30, y: 5, z: 1 },
      v2_kms: { x: 15, y: -2, z: 0 },
      converged: true,
      iterations: 6,
      residual: 1e-9,
      semi_major_axis_km: 180000000,
      eccentricity: 0.2,
      transfer_angle_deg: 165.2,
      time_of_flight_s: 18000000,
      solution_branch: 'ELLIPTIC_PROGRADE',
      stumpff_z: 0.12,
      units: { time: 's', velocity: 'km/s' },
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockSolution,
    } as Response);

    const payload = {
      r1_km: { x: 149597870, y: 0, z: 0 },
      r2_km: { x: 0, y: 227900000, z: 0 },
      time_of_flight_s: 18000000,
    };

    const res = await api.solveLambert(payload);
    expect(res.converged).toBe(true);
    expect(res.iterations).toBe(6);
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/v1/trajectory/lambert', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify(payload),
    }));
  });

  it('correctly maps search parameters for TechPort projects', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ total_count: 1, projects: [] }),
    } as Response);

    await api.getTechPortProjects('propulsion', true);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/techport/projects?search=propulsion&allow_stale=true',
      expect.anything()
    );
  });

  it('correctly requests spacecraft designs for a given mission id', async () => {
    const mockDesigns = [
      {
        id: 'des-1',
        mission_id: 'm-1',
        name: 'Baseline Sizing',
        version: 1,
        dry_mass_kg: 500,
        wet_mass_kg: 1200,
        propellant_mass_kg: 700,
        power_draw_w: 300,
        power_generation_w: 450,
        delta_v_mps: 3900,
        total_cost_usd: 400000000,
        is_feasible: true,
        violations: [],
      },
    ];

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockDesigns,
    } as Response);

    const res = await api.getMissionDesigns('m-1');
    expect(res).toEqual(mockDesigns);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/missions/m-1/designs',
      expect.anything()
    );
  });

  it('throws ApiError on network communication failures', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('Failed to fetch'));

    await expect(api.getMissions()).rejects.toThrow(ApiError);
    await expect(api.getMissions()).rejects.toMatchObject({
      status: 0,
      message: 'Failed to fetch',
    });
  });

  it('correctly invokes Phase 10 component and SWaP-C endpoints', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ total: 1, items: [], limit: 20, offset: 0 }),
    } as Response);

    await api.getComponents({ subsystem: 'POWER', min_trl: 8 });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/components?subsystem=POWER&min_trl=8',
      expect.anything()
    );

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ is_feasible: true, dry_mass_kg: 500 }),
    } as Response);

    const swapcRes = await api.analyzeSwapc({
      components: [],
      propellant_mass_kg: 400,
    });
    expect(swapcRes.is_feasible).toBe(true);
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/v1/physics/swapc', expect.anything());
  });

  it('correctly invokes Phase 11 CDF mutation endpoint', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ success: true, new_version: 4 }),
    } as Response);

    const mutationRes = await api.mutateCdfState('room-1', {
      base_version: 3,
      mutation_category: 'SYSTEM_CONSTRAINTS',
      patch_data: { budget_cap_usd: 600000000 },
    });
    expect(mutationRes.new_version).toBe(4);
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/v1/cdf/rooms/room-1/mutate', expect.anything());
  });

  it('correctly invokes Phase 12 FDIR and CAPCOM endpoints', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ overall_severity: 'NOMINAL', findings: [] }),
    } as Response);

    await api.runFdirScenario('POWER_DEFICIT');
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/v1/fdir/scenarios/POWER_DEFICIT', expect.anything());

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ model_name: 'gemini', ai_recommendations: [] }),
    } as Response);

    const capcomRes = await api.askCapcom({ query: 'Power check' });
    expect(capcomRes.model_name).toBe('gemini');
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/v1/capcom/ask', expect.anything());
  });

  it('correctly invokes Phase 13 dossier generation and report endpoints', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 202,
      json: async () => ({ job_id: 'job-1', status: 'QUEUED' }),
    } as Response);

    const genRes = await api.generateDossier({ mission_id: 'm-1', format: 'BOTH' });
    expect(genRes.job_id).toBe('job-1');
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/v1/dossiers/generate', expect.anything());

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'rep-1', format: 'BOTH', pdf_sha256: 'digest' }),
    } as Response);

    const rep = await api.getDossierReport('rep-1');
    expect(rep.pdf_sha256).toBe('digest');
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/v1/dossiers/rep-1', expect.anything());
  });
});
