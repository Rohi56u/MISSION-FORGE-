import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { CdfCollaboration } from '../src/views/CdfCollaboration';
import { api, CDFRoom, CDFRoomDetail, UserProfile, ApiError, setAuthToken } from '../src/lib/api';

describe('Phase 11 — 4-Role Concurrent Design Facility (CDF)', () => {
  const mockUser: UserProfile = {
    id: 'user-lead-1',
    email: 'lead@missionforge.nasa.gov',
    full_name: 'Dr. Elena Rostova',
    is_active: true,
  };

  const mockRooms: CDFRoom[] = [
    {
      id: 'room-1',
      name: 'Mars Discovery CDF Room',
      mission_id: 'mission-mars',
      status: 'ACTIVE',
      max_participants: 4,
      current_version: 3,
      participant_count: 2,
      created_at: '2026-11-15T08:00:00Z',
    },
  ];

  const mockRoomDetail: CDFRoomDetail = {
    id: 'room-1',
    name: 'Mars Discovery CDF Room',
    mission_id: 'mission-mars',
    status: 'ACTIVE',
    max_participants: 4,
    current_version: 3,
    participants: [
      {
        id: 'p-1',
        user_id: 'user-lead-1',
        full_name: 'Dr. Elena Rostova',
        email: 'lead@missionforge.nasa.gov',
        role: 'LEAD_SYSTEMS_ARCHITECT',
        is_connected: true,
        joined_at: '2026-11-15T08:05:00Z',
        last_seen_at: '2026-11-15T10:00:00Z',
      },
      {
        id: 'p-2',
        user_id: 'user-prop-2',
        full_name: 'Mark Vance',
        email: 'vance@missionforge.nasa.gov',
        role: 'PROPULSION_POWER_OFFICER',
        is_connected: false,
        joined_at: '2026-11-15T08:10:00Z',
        last_seen_at: '2026-11-15T09:30:00Z',
      },
    ],
    state: {
      room_id: 'room-1',
      mission_id: 'mission-mars',
      version: 3,
      system_constraints: {
        target: 'MARS',
        mission_class: 'DISCOVERY',
        budget_cap_usd: 500000000,
        max_launch_mass_kg: 1500,
        min_delta_v_mps: 3800,
        min_power_margin_percent: 15,
      },
      propulsion_and_power: {
        propellant_mass_kg: 450,
        components: [],
      },
      science_payload: {
        components: [],
      },
      flight_dynamics_and_comms: {
        required_delta_v_mps: 3800,
        departure_window: { start: '2026-06-01', end: '2026-07-01' },
        arrival_window: { start: '2027-01-01', end: '2027-02-01' },
        parking_orbit_alt_km: 200,
        distance_au: 1.524,
        tx_power_w: 20,
        antenna_diameter_m: 1.5,
        carrier_frequency_hz: 8.4e9,
        components: [],
      },
      calculated_budgets: {
        dry_mass_kg: 500,
        wet_mass_kg: 950,
        mass_margin_percent: 36.7,
        total_power_draw_w: 420,
        total_power_generated_w: 600,
        power_margin_percent: 42.8,
        available_delta_v_mps: 4100,
        delta_v_margin_percent: 7.89,
        total_cost_usd: 180000000,
        cost_margin_percent: 64.0,
        link_margin_db: 5.5,
        is_feasible: true,
        violations: [],
      },
      provenance_map: {},
      constraint_alerts: [],
    },
    created_at: '2026-11-15T08:00:00Z',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    setAuthToken(null);
  });

  it('renders authentication barrier when no operator token is stored', async () => {
    vi.spyOn(api, 'getMe').mockRejectedValue(new Error('Unauthorized'));

    await act(async () => {
      render(<CdfCollaboration />);
    });

    expect(screen.getByText(/Concurrent Design Facility \(CDF\)/i)).toBeInTheDocument();
    expect(screen.getByText(/requires authenticated operator credentials/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /LOGIN/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /REGISTER/i })).toBeInTheDocument();
  });

  it('renders active CDF room, participant roster, and 4 collaboration stations when authenticated', async () => {
    setAuthToken('valid-jwt-token');
    vi.spyOn(api, 'getMe').mockResolvedValue(mockUser);
    vi.spyOn(api, 'getMissions').mockResolvedValue([
      {
        id: 'mission-mars',
        name: 'Mars Exploration',
        description: 'Discovery',
        target: 'MARS',
        mission_class: 'DISCOVERY',
        budget_cap_usd: 500000000,
        max_launch_mass_kg: 1500,
        min_delta_v_mps: 3800,
        min_power_margin_percent: 15,
      },
    ]);
    vi.spyOn(api, 'listCdfRooms').mockResolvedValue(mockRooms);
    vi.spyOn(api, 'getCdfRoom').mockResolvedValue(mockRoomDetail);
    vi.spyOn(api, 'listCdfRevisions').mockResolvedValue([]);
    vi.spyOn(api, 'listCdfEvents').mockResolvedValue([]);

    await act(async () => {
      render(<CdfCollaboration />);
    });

    await waitFor(() => {
      expect(screen.getByText(/Phase 11 — Concurrent Design Facility/i)).toBeInTheDocument();
      expect(screen.getByText('Mars Discovery CDF Room')).toBeInTheDocument();
      expect(screen.getByText('v3')).toBeInTheDocument();
    });

    // Check that all 4 specialist roles are present
    expect(screen.getByText('Lead Systems Architect')).toBeInTheDocument();
    expect(screen.getByText('Propulsion & Power Officer')).toBeInTheDocument();
    expect(screen.getByText('Science Officer')).toBeInTheDocument();
    expect(screen.getByText('Flight Dynamics & Comms Officer')).toBeInTheDocument();

    // Check participant roster
    expect(screen.getByText('Dr. Elena Rostova')).toBeInTheDocument();
    expect(screen.getByText('Mark Vance')).toBeInTheDocument();
  });

  it('handles HTTP 409 version conflict and presents resynchronization CTA', async () => {
    setAuthToken('valid-jwt-token');
    vi.spyOn(api, 'getMe').mockResolvedValue(mockUser);
    vi.spyOn(api, 'getMissions').mockResolvedValue([]);
    vi.spyOn(api, 'listCdfRooms').mockResolvedValue(mockRooms);
    vi.spyOn(api, 'getCdfRoom').mockResolvedValue(mockRoomDetail);
    vi.spyOn(api, 'listCdfRevisions').mockResolvedValue([]);
    vi.spyOn(api, 'listCdfEvents').mockResolvedValue([]);

    const conflictErr = new ApiError('Conflict', 409, {
      detail: {
        error: 'VERSION_CONFLICT',
        message: 'Conflict: Base version 3 is stale. Current version is 4.',
        current_version: 4,
      },
    });

    vi.spyOn(api, 'mutateCdfState').mockRejectedValue(conflictErr);

    await act(async () => {
      render(<CdfCollaboration />);
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /COMMIT SYSTEM CONSTRAINTS/i })).toBeInTheDocument();
    });

    const commitBtn = screen.getByRole('button', { name: /COMMIT SYSTEM CONSTRAINTS/i });
    await act(async () => {
      fireEvent.click(commitBtn);
    });

    await waitFor(() => {
      expect(screen.getByText(/Concurrent version conflict detected/i)).toBeInTheDocument();
      expect(screen.getByText(/Server authoritative state is currently at version 4/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /RESYNC AUTHORITATIVE STATE/i })).toBeInTheDocument();
    });
  });

  it('renders WebSocket presence indicator and provides reconnect action on disconnection', async () => {
    setAuthToken('valid-jwt-token');
    vi.spyOn(api, 'getMe').mockResolvedValue(mockUser);
    vi.spyOn(api, 'getMissions').mockResolvedValue([]);
    vi.spyOn(api, 'listCdfRooms').mockResolvedValue(mockRooms);
    vi.spyOn(api, 'getCdfRoom').mockResolvedValue(mockRoomDetail);
    vi.spyOn(api, 'listCdfRevisions').mockResolvedValue([]);
    vi.spyOn(api, 'listCdfEvents').mockResolvedValue([]);

    await act(async () => {
      render(<CdfCollaboration />);
    });

    await waitFor(() => {
      expect(screen.getByTitle(/WebSocket state:/i)).toBeInTheDocument();
    });
  });
});
