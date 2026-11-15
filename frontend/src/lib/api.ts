/**
 * Mission Forge Typed API Client
 * Connects to FastAPI backend endpoints with strict error boundaries and timeouts.
 */

export class ApiError extends Error {
  public status: number;
  public data: any;

  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
    // Prevent prototype chain break in transpilation
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  environment: string;
}

export interface Mission {
  id: string;
  name: string;
  description: string | null;
  target: string;
  mission_class: string;
  budget_cap_usd: number;
  max_launch_mass_kg: number;
  min_delta_v_mps: number;
  min_power_margin_percent: number;
  phase?: string;
  launch_epoch?: string;
}

export interface SpacecraftDesign {
  id: string;
  mission_id: string;
  name: string;
  version: number;
  dry_mass_kg: number;
  wet_mass_kg: number;
  propellant_mass_kg: number;
  power_draw_w: number;
  power_generation_w: number;
  delta_v_mps: number;
  total_cost_usd: number;
  is_feasible: boolean;
  violations: Array<Record<string, any>>;
}

export interface DSNSignal {
  active: boolean;
  signal_type: string | null;
  data_rate_bps: number | null;
  frequency_hz: number | null;
  band: string | null;
  power_dbm_or_kw: number | null;
  spacecraft: string | null;
  spacecraft_id: string | null;
}

export interface DSNTarget {
  name: string;
  target_id: string | null;
  upleg_range_km: number | null;
  downleg_range_km: number | null;
  rtlt_seconds: number | null;
}

export interface DSNDish {
  name: string;
  azimuth_deg: number | null;
  elevation_deg: number | null;
  wind_speed_kmh: number | null;
  is_mspa: boolean;
  is_array: boolean;
  is_ddor: boolean;
  activity: string | null;
  targets: DSNTarget[];
  up_signals: DSNSignal[];
  down_signals: DSNSignal[];
}

export interface DSNStation {
  name: string;
  friendly_name: string;
  time_utc: number;
  time_zone_offset_ms: number;
  dishes: DSNDish[];
}

export interface DSNFeedResponse {
  stations: DSNStation[];
  timestamp_ms: number | null;
  retrieved_at: string;
  source_timestamp: string | null;
  cache_status: string;
  source_url: string;
  active_tracking_count: number;
  tracked_spacecraft: string[];
}

export interface TechPortProjectSummary {
  id: number;
  title: string;
  last_updated: string | null;
}

export interface TechPortProjectDetail {
  id: number;
  title: string;
  status: string | null;
  description: string | null;
  benefits?: string | null;
  lead_organization: string | null;
  program: string | null;
  trl_begin: number | null;
  trl_current: number | null;
  trl_end: number | null;
  last_updated: string | null;
  canonical_url: string;
}

export interface TechPortListResponse {
  total_count: number;
  projects: TechPortProjectSummary[];
  retrieved_at: string;
  cache_status: string;
  rate_limit: number | null;
  rate_limit_remaining: number | null;
  source_url: string;
}

export interface Vector3D {
  x: number;
  y: number;
  z: number;
}

export interface LambertSolveRequest {
  r1_km: Vector3D;
  r2_km: Vector3D;
  time_of_flight_s: number;
  mu_km3_s2?: number;
  prograde?: boolean;
  transfer_angle_type?: 'auto' | 'short' | 'long';
  max_iterations?: number;
  tolerance?: number;
}

export interface LambertSolveResponse {
  v1_kms: Vector3D;
  v2_kms: Vector3D;
  converged: boolean;
  iterations: number;
  residual: number;
  semi_major_axis_km: number;
  eccentricity: number;
  transfer_angle_deg: number;
  time_of_flight_s: number;
  solution_branch: string;
  stumpff_z: number;
  units: Record<string, string>;
}

export interface PorkchopRequest {
  origin_body: string;
  target_body: string;
  departure_start_date: string;
  departure_end_date: string;
  arrival_start_date: string;
  arrival_end_date: string;
  step_size_days: number;
  dep_parking_alt_km?: number | null;
  arr_parking_alt_km?: number | null;
  prograde?: boolean;
}

export interface PorkchopMinimaPoint {
  c3?: number;
  tof_days?: number;
  departure_date?: string;
  arrival_date?: string;
  dep_idx?: number;
  arr_idx?: number;
  dv_total?: number;
  vinf_dep?: number;
  vinf_arr?: number;
  [key: string]: any;
}

export interface PorkchopResponse {
  job_id?: string | null;
  origin_body: string;
  target_body: string;
  departure_dates: string[];
  arrival_dates: string[];
  step_size_days: number;
  total_grid_points: number;
  valid_cells_count: number;
  c3_grid: (number | null)[][];
  vinf_dep_grid: (number | null)[][];
  vinf_arr_grid: (number | null)[][];
  tof_days_grid: (number | null)[][];
  dv_inj_grid: (number | null)[][];
  dv_arr_grid: (number | null)[][];
  dv_total_grid: (number | null)[][];
  valid_mask: boolean[][];
  minima: Record<string, PorkchopMinimaPoint | null>;
  units: Record<string, string>;
  solver_diagnostics?: Record<string, any>;
  provenance: Record<string, any>;
}

export interface PorkchopJobCreateResponse {
  job_id: string;
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  created_at: string;
}

export interface PorkchopJobStatusResponse {
  job_id: string;
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  progress_percent: number;
  origin_body: string;
  target_body: string;
  departure_window: { start: string; end: string };
  arrival_window: { start: string; end: string };
  step_size_days: number;
  created_at: string;
  completed_at: string | null;
  error_message: string | null;
}

export interface HorizonsVectorEntry {
  epoch_jd: number;
  calendar_date: string;
  position_km: Vector3D;
  velocity_kms: Vector3D;
  light_time_s?: number | null;
  range_km?: number | null;
  range_rate_kms?: number | null;
}

export interface HorizonsQueryResponse {
  target_id: string;
  target_name: string;
  center_id: string;
  center_name: string;
  coordinate_frame: string;
  origin_center: string;
  time_scale: string;
  units: Record<string, string>;
  vectors: HorizonsVectorEntry[];
  elements?: any[];
  source_url: string;
  retrieved_at: string;
  cache_status: string;
}

// Default request timeout in milliseconds
const DEFAULT_TIMEOUT_MS = 25000;

// Auth Token Store (session / local storage)
let currentAuthToken: string | null =
  typeof localStorage !== 'undefined' ? localStorage.getItem('mf_auth_token') : null;

export function setAuthToken(token: string | null): void {
  currentAuthToken = token;
  if (typeof localStorage !== 'undefined') {
    if (token) {
      localStorage.setItem('mf_auth_token', token);
    } else {
      localStorage.removeItem('mf_auth_token');
    }
  }
}

export function getAuthToken(): string | null {
  if (currentAuthToken) return currentAuthToken;
  if (typeof localStorage !== 'undefined') {
    return localStorage.getItem('mf_auth_token');
  }
  return null;
}

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at?: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: UserProfile;
}

// Phase 10: Component Catalog & Spacecraft Models
export interface ComponentItem {
  id: string;
  name: string;
  subsystem: string;
  description: string | null;
  mass_kg: number;
  power_draw_w: number;
  power_generation_w: number;
  cost_usd: number;
  isp_seconds: number | null;
  thrust_newtons: number | null;
  propellant_type: string | null;
  solar_area_m2: number | null;
  solar_efficiency: number | null;
  decay_rate_annual: number | null;
  antenna_diameter_m: number | null;
  frequency_band: string | null;
  tx_power_w: number | null;
  trl: number | null;
  flight_heritage: string | null;
  techport_id: string | null;
  source_url: string | null;
  source_system: string | null;
  raw_source_hash: string | null;
  verification_status: string;
  field_provenance: Record<string, any>;
  specifications: Record<string, any>;
  is_active: boolean;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ComponentListResponse {
  total: number;
  items: ComponentItem[];
  limit: number;
  offset: number;
}

export interface CatalogStatusResponse {
  total_components: number;
  subsystems_breakdown: Record<string, number>;
  verification_status_breakdown: Record<string, number>;
  components_with_provenance: number;
  provenance_coverage_percent: number;
  source_systems: string[];
  last_synced_at: string | null;
  audit_timestamp: string;
}

export interface ComponentProvenanceResponse {
  component_id: string;
  component_name: string;
  subsystem: string;
  verification_status: string;
  source_system: string | null;
  source_url: string | null;
  techport_id: string | null;
  raw_source_hash: string | null;
  last_synced_at: string | null;
  field_provenance: Record<string, any>;
  audit_timestamp: string;
}

export interface ComponentSpecInput {
  id?: string;
  name: string;
  subsystem: string;
  mass_kg: number;
  power_draw_w: number;
  power_generation_w: number;
  cost_usd: number;
  isp_seconds?: number | null;
  thrust_newtons?: number | null;
  maneuver_system?: string;
  is_active?: boolean;
  solar_area_m2?: number | null;
  solar_efficiency?: number | null;
  is_radioisotope?: boolean;
  annual_decay_rate?: number | null;
  antenna_diameter_m?: number | null;
  tx_power_w?: number | null;
  frequency_hz?: number | null;
}

export interface ConstraintViolation {
  constraint_type: string;
  severity: string;
  message: string;
  limit_value: number;
  actual_value: number;
  unit: string;
  actionable_fix: string;
}

export interface SWaPCAnalysisRequest {
  target?: string;
  mission_class?: string;
  distance_au?: number | null;
  components: ComponentSpecInput[];
  propellant_mass_kg?: number | null;
  required_delta_v_mps?: number;
  mission_duration_years?: number | null;
  custom_budget_cap_usd?: number | null;
  custom_max_mass_kg?: number | null;
  min_power_margin_percent?: number;
}

export interface SWaPCAnalysisResponse {
  target: string;
  distance_au: number;
  mission_class: string;
  dry_mass_kg: number;
  propellant_mass_kg: number;
  wet_mass_kg: number;
  mass_by_subsystem: Record<string, number>;
  total_power_draw_w: number;
  total_power_generated_w: number;
  power_margin_w: number;
  power_margin_percent: number;
  power_by_subsystem: Record<string, number>;
  available_delta_v_mps: number;
  required_delta_v_mps: number;
  delta_v_margin_mps: number;
  effective_isp_s: number;
  propulsion_systems: Record<string, any>;
  mission_duration_years: number;
  downlink_margin_db: number | null;
  round_trip_light_time_seconds: number;
  rtlt_formatted: string;
  hardware_cost_usd: number;
  launch_vehicle_cost_usd: number;
  total_mission_cost_usd: number;
  budget_cap_usd: number;
  budget_margin_usd: number;
  is_feasible: boolean;
  status: 'NOMINAL' | 'MARGINAL' | 'INFEASIBLE';
  violations: ConstraintViolation[];
  warnings: string[];
}

export interface DesignCreateRequest {
  name: string;
  components: ComponentSpecInput[];
  propellant_mass_kg?: number | null;
}

// Phase 11: CDF Collaboration Models
export type CDFRole =
  | 'LEAD_SYSTEMS_ARCHITECT'
  | 'PROPULSION_POWER_OFFICER'
  | 'SCIENCE_OFFICER'
  | 'FLIGHT_DYNAMICS_COMMS_OFFICER';

export type CDFRoomStatus = 'ACTIVE' | 'LOCKED' | 'ARCHIVED';

export interface CDFParticipant {
  id: string;
  user_id: string;
  full_name: string;
  email: string;
  role: CDFRole;
  is_connected: boolean;
  joined_at: string;
  last_seen_at: string;
}

export interface ConstraintAlert {
  alert_code: string;
  severity: 'NOMINAL' | 'CAUTION' | 'WARNING' | 'CRITICAL';
  subsystem: string;
  message: string;
  actionable_guidance: string;
  threshold: number;
  current_value: number;
  unit: string;
}

export interface CalculatedBudgets {
  dry_mass_kg: number;
  wet_mass_kg: number;
  mass_margin_percent: number;
  total_power_draw_w: number;
  total_power_generated_w: number;
  power_margin_percent: number;
  available_delta_v_mps: number;
  delta_v_margin_percent: number;
  total_cost_usd: number;
  cost_margin_percent: number;
  link_margin_db: number | null;
  is_feasible: boolean;
  violations: Array<Record<string, any>>;
}

export interface CDFAuthoritativeState {
  room_id: string;
  mission_id: string;
  version: number;
  system_constraints: {
    target: string;
    mission_class: string;
    budget_cap_usd: number;
    max_launch_mass_kg: number;
    min_delta_v_mps: number;
    min_power_margin_percent: number;
  };
  propulsion_and_power: {
    propellant_mass_kg: number;
    components: Array<Record<string, any>>;
  };
  science_payload: {
    components: Array<Record<string, any>>;
  };
  flight_dynamics_and_comms: {
    required_delta_v_mps: number;
    departure_window: { start: string; end: string };
    arrival_window: { start: string; end: string };
    parking_orbit_alt_km: number;
    distance_au: number;
    tx_power_w: number;
    antenna_diameter_m: number;
    carrier_frequency_hz: number;
    components: Array<Record<string, any>>;
  };
  calculated_budgets: CalculatedBudgets;
  provenance_map: Record<string, any>;
  constraint_alerts: ConstraintAlert[];
}

export interface CDFRoom {
  id: string;
  name: string;
  mission_id: string;
  status: CDFRoomStatus;
  max_participants: number;
  current_version: number;
  participant_count: number;
  created_at: string;
}

export interface CDFRoomDetail {
  id: string;
  name: string;
  mission_id: string;
  status: CDFRoomStatus;
  max_participants: number;
  current_version: number;
  participants: CDFParticipant[];
  state: CDFAuthoritativeState;
  created_at: string;
}

export interface CDFRevision {
  id: string;
  room_id: string;
  version: number;
  author_id: string;
  author_role: string;
  mutation_type: string;
  patch_data: Record<string, any>;
  swapc_snapshot: Record<string, any>;
  created_at: string;
}

export interface CDFEvent {
  id: string;
  room_id: string;
  event_type: string;
  version: number;
  actor_id: string;
  actor_role: string | null;
  payload: Record<string, any>;
  created_at: string;
}

export interface StateMutationRequest {
  base_version: number;
  mutation_category: 'SYSTEM_CONSTRAINTS' | 'PROPULSION_POWER' | 'SCIENCE_PAYLOAD' | 'FLIGHT_DYNAMICS_COMMS';
  patch_data: Record<string, any>;
  client_message_id?: string;
}

export interface StateMutationResponse {
  success: boolean;
  new_version: number;
  mutation_type: string;
  state: CDFAuthoritativeState;
  constraint_alerts: ConstraintAlert[];
}

export interface RoomInviteResponse {
  invite_token: string;
  room_id: string;
  role: CDFRole;
  expires_at: string;
}

// Phase 12: FDIR & CAPCOM Models
export interface FDIRRuleInfo {
  rule_id: string;
  rule_version: string;
  subsystem: string;
  name: string;
}

export interface FDIRFinding {
  rule_id: string;
  rule_version: string;
  severity: 'NOMINAL' | 'CAUTION' | 'WARNING' | 'CRITICAL';
  status: 'NOMINAL' | 'ACTIVE_ANOMALY' | 'INSUFFICIENT_DATA';
  affected_subsystem: string;
  input_evidence: Record<string, any>;
  thresholds: Record<string, any>;
  timestamp: string;
  explanation: string;
  confidence_status: 'VERIFIED' | 'PROVISIONAL' | 'INSUFFICIENT_DATA';
  triage_guidance: string;
  advisory_notice: string;
}

export interface FDIRReportResponse {
  eval_timestamp: string;
  overall_severity: 'NOMINAL' | 'CAUTION' | 'WARNING' | 'CRITICAL';
  findings: FDIRFinding[];
  active_anomalies: FDIRFinding[];
  insufficient_data_findings: FDIRFinding[];
  advisory_disclaimer: string;
}

export interface FDIRFindingLog {
  id: string;
  room_id: string | null;
  mission_id: string | null;
  rule_id: string;
  rule_version: string;
  severity: string;
  status: string;
  affected_subsystem: string;
  explanation: string;
  confidence_status: string;
  triage_guidance: string;
  acknowledged: boolean;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  created_at: string;
}

export interface VerifiedFact {
  statement: string;
  source: string;
  citation: string;
}

export interface FormattedCalculation {
  name: string;
  value: number;
  unit: string;
  formula_reference: string;
}

export interface AIRecommendation {
  recommendation: string;
  engineering_rationale: string;
  priority: 'HIGH' | 'MEDIUM' | 'LOW';
}

export interface FDIRFindingSummary {
  rule_id: string;
  severity: string;
  affected_subsystem: string;
  explanation: string;
  triage_guidance: string;
}

export interface CAPCOMRequest {
  query: string;
  room_id?: string | null;
  telemetry_readings?: Array<Record<string, any>> | null;
}

export interface CAPCOMResponse {
  query: string;
  verified_source_facts: VerifiedFact[];
  deterministic_calculations: Record<string, FormattedCalculation>;
  ai_recommendations: AIRecommendation[];
  unknown_or_insufficient_data: string[];
  fdir_active_findings: FDIRFindingSummary[];
  safety_disclaimer: string;
  model_name: string;
  is_live_generation: boolean;
  generation_timestamp: string;
}

// Phase 13: Dossier & Export Models
export interface DossierGenerateRequest {
  mission_id: string;
  room_id?: string | null;
  design_id?: string | null;
  format?: 'PDF' | 'JSON' | 'BOTH';
  title?: string | null;
  include_cdf_history?: boolean;
  include_fdir_audit?: boolean;
  include_capcom_summary?: boolean;
  trajectory_job_id?: string | null;
}

export interface DossierJobResponse {
  job_id: string;
  mission_id: string;
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  format: 'PDF' | 'JSON' | 'BOTH';
  progress_percent: number;
  report_id: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface DossierReportMetadata {
  id: string;
  job_id: string | null;
  mission_id: string;
  room_id: string | null;
  design_id: string | null;
  title: string;
  format: string;
  pdf_size_bytes: number | null;
  pdf_sha256: string | null;
  json_size_bytes: number | null;
  json_sha256: string | null;
  schema_version: string;
  page_count: number;
  created_at: string;
  download_url_pdf: string | null;
  download_url_json: string | null;
}

export interface DossierReportListResponse {
  reports: DossierReportMetadata[];
  total: number;
}

async function request<T>(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = DEFAULT_TIMEOUT_MS
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };

  const authToken = getAuthToken();
  if (authToken && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  if (options.body && typeof options.body === 'string' && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal,
    });

    if (!response.ok) {
      let errorBody: any = null;
      try {
        errorBody = await response.json();
      } catch {
        errorBody = await response.text().catch(() => null);
      }

      let errorMsg = `API request failed with HTTP status ${response.status}`;
      if (errorBody && typeof errorBody === 'object') {
        if (typeof errorBody.detail === 'string') {
          errorMsg = errorBody.detail;
        } else if (Array.isArray(errorBody.detail)) {
          errorMsg = errorBody.detail.map((d: any) => d.msg || JSON.stringify(d)).join(', ');
        } else if (errorBody.message) {
          errorMsg = errorBody.message;
        }
      }

      throw new ApiError(errorMsg, response.status, errorBody);
    }

    // 204 No Content
    if (response.status === 204) {
      return {} as T;
    }

    return (await response.json()) as T;
  } catch (error: any) {
    if (error.name === 'AbortError') {
      throw new ApiError(`Request timeout after ${timeoutMs}ms: ${url}`, 408);
    }
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(error.message || 'Network communication error', 0, error);
  } finally {
    clearTimeout(timeoutId);
  }
}

export const api = {
  // Health & Diagnostic
  getHealth: (): Promise<HealthResponse> => {
    return request<HealthResponse>('/health');
  },

  getReady: (): Promise<Record<string, any>> => {
    return request<Record<string, any>>('/ready');
  },

  // Missions
  getMissions: (): Promise<Mission[]> => {
    return request<Mission[]>('/api/v1/missions');
  },

  getMission: (missionId: string): Promise<Mission> => {
    return request<Mission>(`/api/v1/missions/${encodeURIComponent(missionId)}`);
  },

  getMissionDesigns: (missionId: string): Promise<SpacecraftDesign[]> => {
    return request<SpacecraftDesign[]>(`/api/v1/missions/${encodeURIComponent(missionId)}/designs`);
  },

  createMission: (data: Partial<Mission>): Promise<Mission> => {
    return request<Mission>('/api/v1/missions', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // Deep Space Network
  getDsnNow: (allowStale: boolean = true): Promise<DSNFeedResponse> => {
    return request<DSNFeedResponse>(`/api/v1/dsn/now?allow_stale=${allowStale}`);
  },

  // NASA TechPort
  getTechPortProjects: (search?: string, allowStale: boolean = true): Promise<TechPortListResponse> => {
    const params = new URLSearchParams();
    if (search && search.trim()) {
      params.set('search', search.trim());
    }
    params.set('allow_stale', String(allowStale));
    return request<TechPortListResponse>(`/api/v1/techport/projects?${params.toString()}`);
  },

  getTechPortProject: (projectId: number, allowStale: boolean = true): Promise<TechPortProjectDetail> => {
    return request<TechPortProjectDetail>(
      `/api/v1/techport/projects/${projectId}?allow_stale=${allowStale}`
    );
  },

  // Astrodynamics - Lambert Solver
  solveLambert: (req: LambertSolveRequest): Promise<LambertSolveResponse> => {
    return request<LambertSolveResponse>('/api/v1/trajectory/lambert', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  },

  // Astrodynamics - Porkchop Direct Calculation
  calculatePorkchop: (req: PorkchopRequest): Promise<PorkchopResponse> => {
    return request<PorkchopResponse>('/api/v1/trajectory/porkchop/calculate', {
      method: 'POST',
      body: JSON.stringify(req),
    }, 45000); // Higher timeout for numerical porkchop calculation
  },

  // Astrodynamics - Porkchop Async Job submission
  submitPorkchopJob: (req: PorkchopRequest): Promise<PorkchopJobCreateResponse> => {
    return request<PorkchopJobCreateResponse>('/api/v1/trajectory/porkchop', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  },

  // Astrodynamics - Porkchop Job Status
  getPorkchopJobStatus: (jobId: string): Promise<PorkchopJobStatusResponse> => {
    return request<PorkchopJobStatusResponse>(
      `/api/v1/trajectory/porkchop/${encodeURIComponent(jobId)}`
    );
  },

  // Astrodynamics - Porkchop Job Result
  getPorkchopJobResult: (jobId: string): Promise<PorkchopResponse> => {
    return request<PorkchopResponse>(
      `/api/v1/trajectory/porkchop/jobs/${encodeURIComponent(jobId)}/result`
    );
  },

  // JPL Horizons Ephemeris Vectors
  getHorizonsVectors: (
    target: string,
    center: string = '500@0',
    startTime: string = '2026-01-01',
    stopTime: string = '2026-01-02',
    stepSize: string = '1d',
    allowStale: boolean = true
  ): Promise<HorizonsQueryResponse> => {
    const params = new URLSearchParams({
      target,
      center,
      start_time: startTime,
      stop_time: stopTime,
      step_size: stepSize,
      allow_stale: String(allowStale),
    });
    return request<HorizonsQueryResponse>(`/api/v1/horizons/vectors?${params.toString()}`);
  },

  // --- Authentication ---
  login: (email: string, password: string): Promise<TokenResponse> => {
    return request<TokenResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  },

  register: (email: string, password: string, fullName: string): Promise<TokenResponse> => {
    return request<TokenResponse>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name: fullName }),
    });
  },

  getMe: (): Promise<UserProfile> => {
    return request<UserProfile>('/api/v1/auth/me');
  },

  // --- Phase 10: Component Catalog & Spacecraft Design ---
  getComponents: (filters: {
    subsystem?: string;
    verification_status?: string;
    min_trl?: number;
    search?: string;
    limit?: number;
    offset?: number;
  } = {}): Promise<ComponentListResponse> => {
    const params = new URLSearchParams();
    if (filters.subsystem) params.set('subsystem', filters.subsystem);
    if (filters.verification_status) params.set('verification_status', filters.verification_status);
    if (filters.min_trl !== undefined) params.set('min_trl', String(filters.min_trl));
    if (filters.search) params.set('search', filters.search);
    if (filters.limit !== undefined) params.set('limit', String(filters.limit));
    if (filters.offset !== undefined) params.set('offset', String(filters.offset));
    const query = params.toString();
    return request<ComponentListResponse>(`/api/v1/components${query ? `?${query}` : ''}`);
  },

  getComponent: (componentId: string): Promise<ComponentItem> => {
    return request<ComponentItem>(`/api/v1/components/${encodeURIComponent(componentId)}`);
  },

  getComponentProvenance: (componentId: string): Promise<ComponentProvenanceResponse> => {
    return request<ComponentProvenanceResponse>(
      `/api/v1/components/provenance/${encodeURIComponent(componentId)}`
    );
  },

  getCatalogStatus: (): Promise<CatalogStatusResponse> => {
    return request<CatalogStatusResponse>('/api/v1/components/status');
  },

  createDesign: (missionId: string, req: DesignCreateRequest): Promise<SpacecraftDesign> => {
    return request<SpacecraftDesign>(`/api/v1/missions/${encodeURIComponent(missionId)}/designs`, {
      method: 'POST',
      body: JSON.stringify(req),
    });
  },

  analyzeSwapc: (req: SWaPCAnalysisRequest): Promise<SWaPCAnalysisResponse> => {
    return request<SWaPCAnalysisResponse>('/api/v1/physics/swapc', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  },

  // --- Phase 11: CDF Room Collaboration ---
  listCdfRooms: (): Promise<CDFRoom[]> => {
    return request<CDFRoom[]>('/api/v1/cdf/rooms');
  },

  createCdfRoom: (name: string, missionId: string, role: CDFRole = 'LEAD_SYSTEMS_ARCHITECT'): Promise<CDFRoom> => {
    return request<CDFRoom>('/api/v1/cdf/rooms', {
      method: 'POST',
      body: JSON.stringify({ name, mission_id: missionId, role }),
    });
  },

  getCdfRoom: (roomId: string): Promise<CDFRoomDetail> => {
    return request<CDFRoomDetail>(`/api/v1/cdf/rooms/${encodeURIComponent(roomId)}`);
  },

  joinCdfRoom: (roomId: string, role: CDFRole): Promise<CDFParticipant> => {
    return request<CDFParticipant>(`/api/v1/cdf/rooms/${encodeURIComponent(roomId)}/join`, {
      method: 'POST',
      body: JSON.stringify({ role }),
    });
  },

  leaveCdfRoom: (roomId: string): Promise<{ message: string }> => {
    return request<{ message: string }>(`/api/v1/cdf/rooms/${encodeURIComponent(roomId)}/leave`, {
      method: 'POST',
    });
  },

  getCdfState: (roomId: string): Promise<CDFAuthoritativeState> => {
    return request<CDFAuthoritativeState>(`/api/v1/cdf/rooms/${encodeURIComponent(roomId)}/state`);
  },

  listCdfRevisions: (roomId: string): Promise<CDFRevision[]> => {
    return request<CDFRevision[]>(`/api/v1/cdf/rooms/${encodeURIComponent(roomId)}/revisions`);
  },

  listCdfEvents: (roomId: string, limit: number = 50): Promise<CDFEvent[]> => {
    return request<CDFEvent[]>(`/api/v1/cdf/rooms/${encodeURIComponent(roomId)}/events?limit=${limit}`);
  },

  mutateCdfState: (roomId: string, mutation: StateMutationRequest): Promise<StateMutationResponse> => {
    return request<StateMutationResponse>(`/api/v1/cdf/rooms/${encodeURIComponent(roomId)}/mutate`, {
      method: 'POST',
      body: JSON.stringify(mutation),
    });
  },

  createCdfInvitation: (roomId: string, role: CDFRole, expiresInHours: number = 24): Promise<RoomInviteResponse> => {
    return request<RoomInviteResponse>(`/api/v1/cdf/rooms/${encodeURIComponent(roomId)}/invitations`, {
      method: 'POST',
      body: JSON.stringify({ role, expires_in_hours: expiresInHours }),
    });
  },

  revokeCdfInvitation: (roomId: string, inviteToken: string): Promise<{ message: string }> => {
    return request<{ message: string }>(`/api/v1/cdf/rooms/${encodeURIComponent(roomId)}/invitations/revoke`, {
      method: 'POST',
      body: JSON.stringify({ invite_token: inviteToken }),
    });
  },

  joinCdfWithInvite: (inviteToken: string): Promise<CDFParticipant> => {
    return request<CDFParticipant>('/api/v1/cdf/rooms/join-with-invite', {
      method: 'POST',
      body: JSON.stringify({ invite_token: inviteToken }),
    });
  },

  updateCdfRoomStatus: (roomId: string, status: CDFRoomStatus): Promise<CDFRoom> => {
    return request<CDFRoom>(`/api/v1/cdf/rooms/${encodeURIComponent(roomId)}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    });
  },

  // --- Phase 12: FDIR & CAPCOM ---
  listFdirRules: (): Promise<FDIRRuleInfo[]> => {
    return request<FDIRRuleInfo[]>('/api/v1/fdir/rules');
  },

  evaluateFdir: (req: {
    room_id?: string;
    mission_id?: string;
    readings?: Array<Record<string, any>>;
    scenario_id?: string;
    debounce_samples?: number;
  }): Promise<FDIRReportResponse> => {
    return request<FDIRReportResponse>('/api/v1/fdir/evaluate', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  },

  runFdirScenario: (scenarioId: string): Promise<FDIRReportResponse> => {
    return request<FDIRReportResponse>(`/api/v1/fdir/scenarios/${encodeURIComponent(scenarioId)}`, {
      method: 'POST',
    });
  },

  acknowledgeFdirFinding: (findingId: string): Promise<{ message: string }> => {
    return request<{ message: string }>('/api/v1/fdir/acknowledge', {
      method: 'POST',
      body: JSON.stringify({ finding_id: findingId }),
    });
  },

  getFdirHistory: (filters: {
    room_id?: string;
    mission_id?: string;
    limit?: number;
  } = {}): Promise<FDIRFindingLog[]> => {
    const params = new URLSearchParams();
    if (filters.room_id) params.set('room_id', filters.room_id);
    if (filters.mission_id) params.set('mission_id', filters.mission_id);
    if (filters.limit) params.set('limit', String(filters.limit));
    const query = params.toString();
    return request<FDIRFindingLog[]>(`/api/v1/fdir/history${query ? `?${query}` : ''}`);
  },

  askCapcom: (req: CAPCOMRequest): Promise<CAPCOMResponse> => {
    return request<CAPCOMResponse>('/api/v1/capcom/ask', {
      method: 'POST',
      body: JSON.stringify(req),
    }, 45000); // 45s for model generation
  },

  // --- Phase 13: Mission Dossier Center ---
  generateDossier: (req: DossierGenerateRequest): Promise<DossierJobResponse> => {
    return request<DossierJobResponse>('/api/v1/dossiers/generate', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  },

  getDossierJobStatus: (jobId: string): Promise<DossierJobResponse> => {
    return request<DossierJobResponse>(`/api/v1/dossiers/jobs/${encodeURIComponent(jobId)}`);
  },

  getDossierReport: (reportId: string): Promise<DossierReportMetadata> => {
    return request<DossierReportMetadata>(`/api/v1/dossiers/${encodeURIComponent(reportId)}`);
  },

  listMissionDossiers: (missionId: string): Promise<DossierReportListResponse> => {
    return request<DossierReportListResponse>(`/api/v1/dossiers/missions/${encodeURIComponent(missionId)}`);
  },

  getDossierSignedUrl: (reportId: string, format: 'pdf' | 'json' = 'pdf', expiresIn?: number): Promise<{
    report_id: string;
    format: string;
    storage_provider: string;
    download_url: string;
    is_signed_cloud_url: boolean;
    expires_in_seconds?: number;
  }> => {
    const params = new URLSearchParams({ format });
    if (expiresIn) params.set('expires_in', String(expiresIn));
    return request<{
      report_id: string;
      format: string;
      storage_provider: string;
      download_url: string;
      is_signed_cloud_url: boolean;
      expires_in_seconds?: number;
    }>(`/api/v1/dossiers/${encodeURIComponent(reportId)}/signed-url?${params.toString()}`);
  },
};
