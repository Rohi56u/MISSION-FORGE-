import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { FdirCapcomOperations } from '../src/views/FdirCapcomOperations';
import { api, FDIRReportResponse, FDIRRuleInfo, CAPCOMResponse, FDIRFindingLog, setAuthToken } from '../src/lib/api';

describe('Phase 12 — FDIR Operations & Grounded CAPCOM', () => {
  const mockRules: FDIRRuleInfo[] = [
    {
      rule_id: 'R-PWR-001',
      rule_version: '1.2.0',
      subsystem: 'POWER',
      name: 'Power Margin Deficit Detector',
    },
    {
      rule_id: 'R-THM-002',
      rule_version: '1.0.1',
      subsystem: 'THERMAL',
      name: 'Thermal Boundary Exceedance',
    },
  ];

  const mockReport: FDIRReportResponse = {
    eval_timestamp: '2026-11-15T12:00:00Z',
    overall_severity: 'CRITICAL',
    findings: [
      {
        rule_id: 'R-PWR-001',
        rule_version: '1.2.0',
        severity: 'CRITICAL',
        status: 'ACTIVE_ANOMALY',
        affected_subsystem: 'POWER',
        input_evidence: { power_margin_percent: -4.2, battery_soc: 0.38 },
        thresholds: { min_margin_percent: 15.0 },
        timestamp: '2026-11-15T12:00:00Z',
        explanation: 'Power margin is negative (-4.2%) due to solar distance drop.',
        confidence_status: 'VERIFIED',
        triage_guidance: 'Shed non-essential science instruments and re-orient solar arrays.',
        advisory_notice: 'ADVISORY NOTICE: Simulation only.',
      },
      {
        rule_id: 'R-THM-002',
        rule_version: '1.0.1',
        severity: 'CAUTION',
        status: 'INSUFFICIENT_DATA',
        affected_subsystem: 'THERMAL',
        input_evidence: { thermistor_1_degc: null },
        thresholds: { max_temp_degc: 65.0 },
        timestamp: '2026-11-15T12:00:00Z',
        explanation: 'Thermistor telemetry packet missing or sensor invalid.',
        confidence_status: 'INSUFFICIENT_DATA',
        triage_guidance: 'Verify telemetry lock with DSN station.',
        advisory_notice: 'ADVISORY NOTICE: Simulation only.',
      },
    ],
    active_anomalies: [],
    insufficient_data_findings: [],
    advisory_disclaimer: 'ADVISORY NOTICE: Engineering simulation only.',
  };

  const mockCapcomResponse: CAPCOMResponse = {
    query: 'Assess power deficit risks and triage recommendations for battery storage.',
    verified_source_facts: [
      {
        statement: 'At 1.524 AU, solar irradiance decreases to 43.1% of 1 AU flux.',
        source: 'NASA Planetary Fact Sheet',
        citation: 'NASA JPL SP-8005',
      },
    ],
    deterministic_calculations: {
      solar_power_flux: {
        name: 'Solar Flux at Mars',
        value: 589.2,
        unit: 'W/m²',
        formula_reference: 'S = S_0 / r_AU²',
      },
    },
    ai_recommendations: [
      {
        recommendation: 'Inhibit reaction wheel heater while array is off-sun.',
        engineering_rationale: 'Preserves 45W bus capacity during eclipse phase.',
        priority: 'HIGH',
      },
    ],
    unknown_or_insufficient_data: [
      'Battery cell 3 degradation coefficient not measured in flight.',
    ],
    fdir_active_findings: [
      {
        rule_id: 'R-PWR-001',
        severity: 'CRITICAL',
        affected_subsystem: 'POWER',
        explanation: 'Negative power margin detected.',
        triage_guidance: 'Shed science load.',
      },
    ],
    safety_disclaimer:
      'ADVISORY SIMULATION ONLY: CAPCOM AI is an advisory systems assistant.',
    model_name: 'gemini-1.5-flash-grounded',
    is_live_generation: true,
    generation_timestamp: '2026-11-15T12:00:05Z',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders advisory simulation safety notice and lists registered FDIR rules', async () => {
    vi.spyOn(api, 'listFdirRules').mockResolvedValue(mockRules);
    vi.spyOn(api, 'runFdirScenario').mockResolvedValue(mockReport);

    await act(async () => {
      render(<FdirCapcomOperations />);
    });

    expect(screen.getByText(/ADVISORY SIMULATION SAFETY NOTICE/i)).toBeInTheDocument();
    expect(screen.getByText(/Phase 12 — FDIR Operations & Grounded CAPCOM/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getAllByText('R-PWR-001')[0]).toBeInTheDocument();
      expect(screen.getAllByText('R-THM-002')[0]).toBeInTheDocument();
    });
  });

  it('distinguishes INSUFFICIENT_DATA distinctly from NOMINAL findings', async () => {
    vi.spyOn(api, 'listFdirRules').mockResolvedValue(mockRules);
    vi.spyOn(api, 'runFdirScenario').mockResolvedValue(mockReport);

    await act(async () => {
      render(<FdirCapcomOperations />);
    });

    await waitFor(() => {
      expect(screen.getByTestId('finding-card-R-PWR-001')).toBeInTheDocument();
      expect(screen.getByTestId('finding-card-R-THM-002')).toBeInTheDocument();
    });

    // R-PWR-001 is ACTIVE_ANOMALY • CRITICAL
    expect(screen.getByText(/ACTIVE_ANOMALY • CRITICAL/i)).toBeInTheDocument();

    // R-THM-002 is INSUFFICIENT_DATA • CAUTION
    expect(screen.getByText(/INSUFFICIENT_DATA • CAUTION/i)).toBeInTheDocument();
  });

  it('renders grounded CAPCOM assistant with verified facts, calculations, and recommendations', async () => {
    vi.spyOn(api, 'listFdirRules').mockResolvedValue(mockRules);
    vi.spyOn(api, 'runFdirScenario').mockResolvedValue(mockReport);
    vi.spyOn(api, 'askCapcom').mockResolvedValue(mockCapcomResponse);

    await act(async () => {
      render(<FdirCapcomOperations />);
    });

    // Switch to CAPCOM tab
    const capcomTab = screen.getByRole('button', { name: /GROUNDED CAPCOM/i });
    await act(async () => {
      fireEvent.click(capcomTab);
    });

    expect(screen.getByText(/Grounded CAPCOM AI Assistant/i)).toBeInTheDocument();

    // Submit query
    const queryBtn = screen.getByRole('button', { name: /QUERY CAPCOM/i });
    await act(async () => {
      fireEvent.click(queryBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId('capcom-response-container')).toBeInTheDocument();
    });

    // 1. Verified Source Facts
    expect(screen.getByText(/At 1.524 AU, solar irradiance decreases/i)).toBeInTheDocument();
    expect(screen.getByText(/NASA Planetary Fact Sheet/i)).toBeInTheDocument();

    // 2. Deterministic Calculations
    expect(screen.getByText('Solar Flux at Mars')).toBeInTheDocument();
    expect(screen.getByText('589.2 W/m²')).toBeInTheDocument();
    expect(screen.getByText(/S = S_0 \/ r_AU²/i)).toBeInTheDocument();

    // 3. AI Recommendations
    expect(screen.getByText(/Inhibit reaction wheel heater/i)).toBeInTheDocument();
    expect(screen.getByText(/HIGH PRIORITY/i)).toBeInTheDocument();
  });

  it('resolves persistent log UUID and acknowledges active anomaly from findings card', async () => {
    setAuthToken('test-operator-jwt');
    const mockFindingLog: FDIRFindingLog = {
      id: 'fdir-log-uuid-1234',
      room_id: null,
      mission_id: 'mission-mars',
      rule_id: 'R-PWR-001',
      rule_version: '1.2.0',
      severity: 'CRITICAL',
      status: 'ACTIVE_ANOMALY',
      affected_subsystem: 'POWER',
      explanation: 'Power deficit anomaly',
      confidence_status: 'VERIFIED',
      triage_guidance: 'Shed load',
      acknowledged: false,
      acknowledged_by: null,
      acknowledged_at: null,
      created_at: '2026-11-15T12:00:00Z',
    };

    vi.spyOn(api, 'listFdirRules').mockResolvedValue(mockRules);
    vi.spyOn(api, 'runFdirScenario').mockResolvedValue(mockReport);
    vi.spyOn(api, 'getFdirHistory').mockResolvedValue([mockFindingLog]);
    const ackSpy = vi.spyOn(api, 'acknowledgeFdirFinding').mockResolvedValue({ message: 'Success' });

    await act(async () => {
      render(<FdirCapcomOperations />);
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Acknowledge anomaly for R-PWR-001/i })).toBeInTheDocument();
    });

    const ackBtn = screen.getByRole('button', { name: /Acknowledge anomaly for R-PWR-001/i });
    await act(async () => {
      fireEvent.click(ackBtn);
    });

    // Validates that the persistent log UUID 'fdir-log-uuid-1234' was sent to backend, NOT 'R-PWR-001'
    expect(ackSpy).toHaveBeenCalledWith('fdir-log-uuid-1234');
  });

  it('acknowledges unacknowledged finding directly from Audit Trail view with log UUID', async () => {
    setAuthToken('test-operator-jwt');
    const mockFindingLog: FDIRFindingLog = {
      id: 'fdir-log-uuid-5678',
      room_id: null,
      mission_id: 'mission-mars',
      rule_id: 'R-THM-002',
      rule_version: '1.0.1',
      severity: 'WARNING',
      status: 'ACTIVE_ANOMALY',
      affected_subsystem: 'THERMAL',
      explanation: 'Overheating detected',
      confidence_status: 'VERIFIED',
      triage_guidance: 'Reorient radiators',
      acknowledged: false,
      acknowledged_by: null,
      acknowledged_at: null,
      created_at: '2026-11-15T12:05:00Z',
    };

    vi.spyOn(api, 'listFdirRules').mockResolvedValue(mockRules);
    vi.spyOn(api, 'runFdirScenario').mockResolvedValue(mockReport);
    vi.spyOn(api, 'getFdirHistory').mockResolvedValue([mockFindingLog]);
    const ackSpy = vi.spyOn(api, 'acknowledgeFdirFinding').mockResolvedValue({ message: 'Success' });

    await act(async () => {
      render(<FdirCapcomOperations />);
    });

    // Switch to Audit tab
    const auditTab = screen.getByRole('button', { name: /AUDIT TRAIL/i });
    await act(async () => {
      fireEvent.click(auditTab);
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Acknowledge audit finding fdir-log-uuid-5678/i })).toBeInTheDocument();
    });

    const ackBtn = screen.getByRole('button', { name: /Acknowledge audit finding fdir-log-uuid-5678/i });
    await act(async () => {
      fireEvent.click(ackBtn);
    });

    expect(ackSpy).toHaveBeenCalledWith('fdir-log-uuid-5678');
  });
});
