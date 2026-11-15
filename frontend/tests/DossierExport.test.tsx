import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MissionDossierCenter } from '../src/views/MissionDossierCenter';
import { api, DossierReportMetadata, DossierJobResponse } from '../src/lib/api';

describe('Phase 13 — Mission Dossier & Artifact Export Center', () => {
  const TEST_JSON_PAYLOAD = JSON.stringify({
    schema_version: '1.0.0',
    title: 'Mars Exploration Baseline Dossier',
    authoritative_disclaimer: 'Deterministic snapshot',
    mission: { target: 'MARS', budget_cap_usd: 500000000 },
  });
  // Real SHA-256 of TEST_JSON_PAYLOAD
  const TEST_JSON_SHA256 = 'e6bcccb000f044c76e09e7fa2bc32a6c59106c3b086d98e58f3ed28cebe11a26';

  const mockReports: DossierReportMetadata[] = [
    {
      id: 'dossier-report-1',
      job_id: 'job-101',
      mission_id: 'mission-mars',
      room_id: null,
      design_id: null,
      title: 'Mars Exploration Baseline Dossier',
      format: 'BOTH',
      pdf_size_bytes: 145000,
      pdf_sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
      json_size_bytes: 32000,
      json_sha256: TEST_JSON_SHA256,
      schema_version: '1.0.0',
      page_count: 8,
      created_at: '2026-11-15T11:00:00Z',
      download_url_pdf: '/api/v1/dossiers/dossier-report-1/download?format=pdf',
      download_url_json: '/api/v1/dossiers/dossier-report-1/download?format=json',
    },
  ];

  const mockJob: DossierJobResponse = {
    job_id: 'job-101',
    mission_id: 'mission-mars',
    status: 'RUNNING',
    format: 'BOTH',
    progress_percent: 65.0,
    report_id: null,
    error_message: null,
    created_at: '2026-11-15T11:00:00Z',
    completed_at: null,
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal('fetch', vi.fn());
  });

  it('renders dossier generator form with format selections and mission targets', async () => {
    vi.spyOn(api, 'getMissions').mockResolvedValue([
      {
        id: 'mission-mars',
        name: 'Mars Discovery Mission',
        description: 'Interplanetary exploration',
        target: 'MARS',
        mission_class: 'DISCOVERY',
        budget_cap_usd: 500000000,
        max_launch_mass_kg: 1500,
        min_delta_v_mps: 3800,
        min_power_margin_percent: 15,
      },
    ]);
    vi.spyOn(api, 'listMissionDossiers').mockResolvedValue({
      reports: mockReports,
      total: 1,
    });

    await act(async () => {
      render(<MissionDossierCenter />);
    });

    expect(screen.getByText(/Phase 13 — Mission Dossier & Artifact Export Center/i)).toBeInTheDocument();
    expect(screen.getByText(/Generate Certified Mission Dossier/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /COMPILE MISSION DOSSIER/i })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getAllByText('Mars Exploration Baseline Dossier')[0]).toBeInTheDocument();
      // Section 7 Requirement: Truthful initial state requires client verification rather than blind badge
      expect(screen.getByRole('button', { name: /VERIFY SHA-256 FOR Mars Exploration Baseline Dossier/i })).toBeInTheDocument();
    });
  });

  it('submits asynchronous compilation job and displays authoritative progress percent', async () => {
    vi.spyOn(api, 'getMissions').mockResolvedValue([
      {
        id: 'mission-mars',
        name: 'Mars Discovery Mission',
        description: 'Discovery',
        target: 'MARS',
        mission_class: 'DISCOVERY',
        budget_cap_usd: 500000000,
        max_launch_mass_kg: 1500,
        min_delta_v_mps: 3800,
        min_power_margin_percent: 15,
      },
    ]);
    vi.spyOn(api, 'listMissionDossiers').mockResolvedValue({
      reports: [],
      total: 0,
    });
    vi.spyOn(api, 'generateDossier').mockResolvedValue(mockJob);

    await act(async () => {
      render(<MissionDossierCenter />);
    });

    const compileBtn = screen.getByRole('button', { name: /COMPILE MISSION DOSSIER/i });
    await act(async () => {
      fireEvent.click(compileBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId('active-dossier-job')).toBeInTheDocument();
      expect(screen.getByText('65%')).toBeInTheDocument();
      expect(screen.getByText('RUNNING')).toBeInTheDocument();
    });
  });

  it('inspects frozen JSON snapshot in-browser without freezing UI and verifies SHA-256', async () => {
    vi.spyOn(api, 'getMissions').mockResolvedValue([
      {
        id: 'mission-mars',
        name: 'Mars Discovery Mission',
        description: 'Discovery',
        target: 'MARS',
        mission_class: 'DISCOVERY',
        budget_cap_usd: 500000000,
        max_launch_mass_kg: 1500,
        min_delta_v_mps: 3800,
        min_power_margin_percent: 15,
      },
    ]);
    vi.spyOn(api, 'listMissionDossiers').mockResolvedValue({
      reports: mockReports,
      total: 1,
    });

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      arrayBuffer: async () => new TextEncoder().encode(TEST_JSON_PAYLOAD).buffer,
    }));

    await act(async () => {
      render(<MissionDossierCenter />);
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Inspect JSON snapshot/i })).toBeInTheDocument();
    });

    const inspectJsonBtn = screen.getByRole('button', { name: /Inspect JSON snapshot/i });
    await act(async () => {
      fireEvent.click(inspectJsonBtn);
    });

    await waitFor(() => {
      expect(screen.getByText(/JSON Frozen Snapshot:/i)).toBeInTheDocument();
      expect(screen.getByText(/Deterministic snapshot/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /COPY JSON/i })).toBeInTheDocument();
      // Recomputed client-side SHA-256 verified badge appears
      expect(screen.getByText('SHA-256 VERIFIED')).toBeInTheDocument();
    });
  });

  it('cryptographically verifies artifact SHA-256 on demand and detects corrupted payloads', async () => {
    vi.spyOn(api, 'getMissions').mockResolvedValue([
      {
        id: 'mission-mars',
        name: 'Mars Discovery Mission',
        description: 'Discovery',
        target: 'MARS',
        mission_class: 'DISCOVERY',
        budget_cap_usd: 500000000,
        max_launch_mass_kg: 1500,
        min_delta_v_mps: 3800,
        min_power_margin_percent: 15,
      },
    ]);
    vi.spyOn(api, 'listMissionDossiers').mockResolvedValue({
      reports: [
        {
          ...mockReports[0],
          id: 'corrupt-report',
          title: 'Corrupted Dossier Record',
          json_sha256: '0000000000000000000000000000000000000000000000000000000000000000',
        },
      ],
      total: 1,
    });

    // Returns payload whose digest will NOT match '00000...'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      arrayBuffer: async () => new TextEncoder().encode('corrupted bytes').buffer,
    }));

    await act(async () => {
      render(<MissionDossierCenter />);
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /VERIFY SHA-256 FOR Corrupted Dossier Record/i })).toBeInTheDocument();
    });

    const verifyBtn = screen.getByRole('button', { name: /VERIFY SHA-256 FOR Corrupted Dossier Record/i });
    await act(async () => {
      fireEvent.click(verifyBtn);
    });

    await waitFor(() => {
      expect(screen.getByText('CHECKSUM MISMATCH')).toBeInTheDocument();
    });
  });

  it('displays cryptographic SHA-256 hashes and expiring cloud download link options', async () => {
    vi.spyOn(api, 'getMissions').mockResolvedValue([
      {
        id: 'mission-mars',
        name: 'Mars Discovery Mission',
        description: 'Discovery',
        target: 'MARS',
        mission_class: 'DISCOVERY',
        budget_cap_usd: 500000000,
        max_launch_mass_kg: 1500,
        min_delta_v_mps: 3800,
        min_power_margin_percent: 15,
      },
    ]);
    vi.spyOn(api, 'listMissionDossiers').mockResolvedValue({
      reports: mockReports,
      total: 1,
    });
    vi.spyOn(api, 'getDossierSignedUrl').mockResolvedValue({
      report_id: 'dossier-report-1',
      format: 'PDF',
      storage_provider: 'local',
      download_url: '/api/v1/dossiers/dossier-report-1/download?format=pdf',
      is_signed_cloud_url: false,
      expires_in_seconds: 3600,
    });

    await act(async () => {
      render(<MissionDossierCenter />);
    });

    await waitFor(() => {
      expect(screen.getByText(/PDF ARTIFACT SHA-256 DIGEST/i)).toBeInTheDocument();
      expect(screen.getByText('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')).toBeInTheDocument();
    });

    const cloudBtn = screen.getByRole('button', { name: /GET EXPIRING CLOUD URL/i });
    await act(async () => {
      fireEvent.click(cloudBtn);
    });

    await waitFor(() => {
      expect(screen.getByText(/Expiring Signed URL \(local\)/i)).toBeInTheDocument();
    });
  });
});
