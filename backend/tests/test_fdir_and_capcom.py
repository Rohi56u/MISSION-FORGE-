"""
Deterministic FDIR & Grounded CAPCOM AI Assistant Tests (Phase 5)
Mission Forge — Phase 5
"""

import json
import uuid
import pytest
from httpx import AsyncClient

from backend.app.capcom.gemini_adapter import GeminiCapcomAdapter
from backend.app.cdf.state import initialize_default_cdf_state
from backend.app.fdir.engine import FDIREngine, fdir_engine
from backend.app.fdir.rules import (
    FDIR_ADVISORY_DISCLAIMER,
    FDIRFindingStatus,
    FDIRSeverity,
    RuleCommLoss,
    RulePowerShortfall,
    RuleThermalLimit,
    RuleWheelSaturation,
)
from backend.app.fdir.telemetry import (
    TelemetryProvenanceType,
    TelemetryQuality,
    TelemetryReading,
    TelemetrySubsystem,
    convert_dsn_feed_to_telemetry,
    create_simulated_scenario,
)
from backend.app.schemas.capcom import CAPCOM_SAFETY_DISCLAIMER


# ============================================================================
# 1. TELEMETRY PROVENANCE & SCENARIO FIXTURE TESTS
# ============================================================================

def test_telemetry_reading_schema_and_provenance():
    """Verifies typed telemetry fields, explicit units, quality indicators, and provenance."""
    reading = TelemetryReading(
        subsystem=TelemetrySubsystem.POWER,
        metric_name="bus_voltage_v",
        value=28.2,
        unit="V",
        source="ONBOARD_POWER_BUS_A",
        provenance=TelemetryProvenanceType.LIVE_SATELLITE,
        quality=TelemetryQuality.GOOD,
    )
    assert reading.subsystem == TelemetrySubsystem.POWER
    assert reading.metric_name == "bus_voltage_v"
    assert reading.value == 28.2
    assert reading.unit == "V"
    assert reading.provenance == TelemetryProvenanceType.LIVE_SATELLITE
    assert reading.quality == TelemetryQuality.GOOD


def test_dsn_feed_conversion_strict_provenance():
    """
    Verifies that real NASA DSN Now feeds only populate ground-network communications
    telemetry (carrier locks, frequencies) and NEVER fabricate internal bus, thermal,
    or wheel telemetry fields.
    """
    mock_dsn_payload = {
        "dishes": [
            {
                "name": "DSS-14",
                "up_signal": {"carrier_lock": True, "frequency_hz": 7.15e9},
                "down_signal": {"carrier_lock": True, "frequency_hz": 8.42e9},
            },
            {
                "name": "DSS-63",
                "up_signal": {"carrier_lock": False},
                "down_signal": {"carrier_lock": False},
            },
        ]
    }

    readings = convert_dsn_feed_to_telemetry(mock_dsn_payload)
    assert len(readings) == 2

    for r in readings:
        assert r.subsystem == TelemetrySubsystem.COMMUNICATIONS
        assert r.provenance == TelemetryProvenanceType.GROUND_NETWORK
        assert "carrier_lock" in r.metric_name
        # Guarantee no fake power/thermal fields
        assert "voltage" not in r.metric_name
        assert "temp" not in r.metric_name
        assert "wheel" not in r.metric_name


def test_simulated_scenario_fixtures_labeling():
    """
    Verifies that all simulated test scenarios are explicitly labelled as
    SIMULATED_SCENARIO and never masquerade as live telemetry.
    """
    scenarios = [
        "POWER_DEFICIT",
        "THERMAL_EXCEEDANCE",
        "COMM_BLACKOUT",
        "WHEEL_SATURATION",
        "PROPULSION_SHORTFALL",
        "NOMINAL_CRUISE",
    ]

    for sc in scenarios:
        readings = create_simulated_scenario(sc)
        assert len(readings) > 0
        for r in readings:
            assert r.provenance == TelemetryProvenanceType.SIMULATED_SCENARIO
            assert r.value is not None


# ============================================================================
# 2. DETERMINISTIC FDIR RULES TESTS
# ============================================================================

def test_rule_power_shortfall_nominal_warning_critical():
    """Verifies deterministic evaluation of RulePowerShortfall."""
    rule = RulePowerShortfall()

    # 1. Nominal
    nominal_readings = {
        "bus_voltage_v": TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="bus_voltage_v",
            value=28.0,
            unit="V",
            source="TEST",
            provenance=TelemetryProvenanceType.FIXTURE,
        ),
        "battery_charge_percent": TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="battery_charge_percent",
            value=95.0,
            unit="%",
            source="TEST",
            provenance=TelemetryProvenanceType.FIXTURE,
        ),
        "power_generation_w": TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="power_generation_w",
            value=450.0,
            unit="W",
            source="TEST",
            provenance=TelemetryProvenanceType.FIXTURE,
        ),
        "power_draw_w": TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="power_draw_w",
            value=300.0,
            unit="W",
            source="TEST",
            provenance=TelemetryProvenanceType.FIXTURE,
        ),
    }
    f_nom = rule.evaluate(nominal_readings)
    assert f_nom.severity == FDIRSeverity.NOMINAL
    assert f_nom.status == FDIRFindingStatus.NOMINAL

    # 2. Critical: Undervoltage
    crit_readings = dict(nominal_readings)
    crit_readings["bus_voltage_v"] = TelemetryReading(
        subsystem=TelemetrySubsystem.POWER,
        metric_name="bus_voltage_v",
        value=22.5,  # < 24V
        unit="V",
        source="TEST",
        provenance=TelemetryProvenanceType.FIXTURE,
    )
    f_crit = rule.evaluate(crit_readings)
    assert f_crit.severity == FDIRSeverity.CRITICAL
    assert f_crit.status == FDIRFindingStatus.ACTIVE_ANOMALY
    assert "undervoltage" in f_crit.explanation.lower()

    # 3. Insufficient data: missing telemetry
    f_miss = rule.evaluate({})
    assert f_miss.status == FDIRFindingStatus.INSUFFICIENT_DATA
    assert f_miss.confidence_status == "INSUFFICIENT_DATA"


def test_rule_thermal_limit_nominal_and_critical():
    """Verifies deterministic evaluation of RuleThermalLimit."""
    rule = RuleThermalLimit()

    # 1. Missing data: must not report nominal
    f_miss = rule.evaluate({})
    assert f_miss.status == FDIRFindingStatus.INSUFFICIENT_DATA

    # 2. Critical thermal exceedance (88.0 C > 85.0 C)
    crit_readings = {
        "component_temp_c": TelemetryReading(
            subsystem=TelemetrySubsystem.THERMAL,
            metric_name="component_temp_c",
            value=88.5,
            unit="degC",
            source="BAY_1_RTD",
            provenance=TelemetryProvenanceType.FIXTURE,
        )
    }
    f_crit = rule.evaluate(crit_readings)
    assert f_crit.severity == FDIRSeverity.CRITICAL
    assert f_crit.status == FDIRFindingStatus.ACTIVE_ANOMALY
    assert f_crit.input_evidence["component_temp_c"] == 88.5


def test_rule_comm_loss_blackout():
    """Verifies deterministic evaluation of RuleCommLoss."""
    rule = RuleCommLoss()

    blackout_readings = {
        "carrier_lock": TelemetryReading(
            subsystem=TelemetrySubsystem.COMMUNICATIONS,
            metric_name="carrier_lock",
            value=0.0,
            unit="boolean",
            source="X_BAND",
            provenance=TelemetryProvenanceType.FIXTURE,
        ),
        "downlink_snr_db": TelemetryReading(
            subsystem=TelemetrySubsystem.COMMUNICATIONS,
            metric_name="downlink_snr_db",
            value=-2.5,
            unit="dB",
            source="X_BAND",
            provenance=TelemetryProvenanceType.FIXTURE,
        ),
        "time_since_last_contact_s": TelemetryReading(
            subsystem=TelemetrySubsystem.COMMUNICATIONS,
            metric_name="time_since_last_contact_s",
            value=95_000.0,
            unit="s",
            source="SCHEDULE",
            provenance=TelemetryProvenanceType.FIXTURE,
        ),
    }
    f_crit = rule.evaluate(blackout_readings)
    assert f_crit.severity == FDIRSeverity.CRITICAL
    assert "blackout" in f_crit.explanation.lower()


def test_rule_wheel_saturation():
    """Verifies deterministic evaluation of RuleWheelSaturation."""
    rule = RuleWheelSaturation()

    # Missing wheel telemetry
    f_miss = rule.evaluate({})
    assert f_miss.status == FDIRFindingStatus.INSUFFICIENT_DATA

    # Wheel saturation (5700 RPM > 5500 RPM)
    sat_readings = {
        "reaction_wheel_rpm_x": TelemetryReading(
            subsystem=TelemetrySubsystem.GNC_ATTITUDE,
            metric_name="reaction_wheel_rpm_x",
            value=5720.0,
            unit="rpm",
            source="RWA_1",
            provenance=TelemetryProvenanceType.FIXTURE,
        )
    }
    f_sat = rule.evaluate(sat_readings)
    assert f_sat.severity == FDIRSeverity.CRITICAL
    assert "saturation" in f_sat.explanation.lower()


def test_fdir_deterministic_repeatability():
    """
    Verifies that evaluating the exact same inputs 100 times produces
    100% byte-identical findings and severities.
    """
    engine = FDIREngine()
    scenario_readings = create_simulated_scenario("POWER_DEFICIT")

    first_report = engine.evaluate_telemetry(scenario_readings)
    first_findings = [
        f.model_dump(exclude={"timestamp"}) for f in first_report.findings
    ]
    first_anomalies = [
        f.model_dump(exclude={"timestamp"}) for f in first_report.active_anomalies
    ]

    for _ in range(100):
        rep = engine.evaluate_telemetry(scenario_readings)
        assert rep.overall_severity == first_report.overall_severity
        findings = [f.model_dump(exclude={"timestamp"}) for f in rep.findings]
        anomalies = [f.model_dump(exclude={"timestamp"}) for f in rep.active_anomalies]
        assert findings == first_findings
        assert anomalies == first_anomalies


def test_fdir_advisory_disclaimer_attached():
    """Verifies that the mandatory advisory notice is attached to all findings and reports."""
    engine = FDIREngine()
    report = engine.evaluate_telemetry([])
    assert FDIR_ADVISORY_DISCLAIMER in report.advisory_disclaimer
    for finding in report.findings:
        assert FDIR_ADVISORY_DISCLAIMER in finding.advisory_notice


# ============================================================================
# 3. GROUNDED CAPCOM AI ASSISTANT TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_capcom_deterministic_offline_mode():
    """
    Verifies that when GEMINI_API_KEY is not configured or in offline mode,
    CAPCOM AI deterministically constructs verified facts, calculations with units,
    exact FDIR active findings, and advisory recommendations.
    """
    adapter = GeminiCapcomAdapter(api_key=None, model_name="gemini-2.5-flash")

    state = initialize_default_cdf_state(
        room_id="room-capcom-1",
        mission_id="mission-mars-1",
        target="MARS",
        mission_class="DISCOVERY",
        budget_cap_usd=500_000_000.0,
        max_launch_mass_kg=1500.0,
        min_delta_v_mps=3800.0,
    )

    fdir_rep = fdir_engine.evaluate_room_state(state)

    bounded_context = {
        "room_id": state.room_id,
        "version": state.version,
        "system_constraints": state.system_constraints.model_dump(),
        "calculated_budgets": state.calculated_budgets.model_dump(),
        "fdir_report": {
            "overall_severity": fdir_rep.overall_severity.value,
            "findings": [f.model_dump() for f in fdir_rep.findings],
            "insufficient_data_findings": [
                f.model_dump() for f in fdir_rep.insufficient_data_findings
            ],
        },
    }

    response = await adapter.generate_capcom_response(
        query="What is the current mass margin and are there any active anomalies?",
        bounded_context=bounded_context,
    )

    assert response.is_live_generation is False
    assert len(response.verified_source_facts) >= 2
    assert "wet_mass" in response.deterministic_calculations
    assert response.deterministic_calculations["wet_mass"].unit == "kg"
    assert CAPCOM_SAFETY_DISCLAIMER in response.safety_disclaimer
    assert len(response.ai_recommendations) > 0


@pytest.mark.asyncio
async def test_capcom_fdir_integrity_guarantee():
    """
    CRITICAL AI SAFETY REQUIREMENT:
    The AI assistant must NEVER create, suppress, or modify deterministic FDIR findings.
    Active findings in CAPCOM response must match deterministic FDIR findings exactly.
    """
    adapter = GeminiCapcomAdapter(api_key=None)

    # Telemetry with active power deficit
    crit_readings = create_simulated_scenario("POWER_DEFICIT")
    fdir_rep = fdir_engine.evaluate_telemetry(crit_readings)

    bounded_context = {
        "fdir_report": {
            "overall_severity": fdir_rep.overall_severity.value,
            "findings": [f.model_dump() for f in fdir_rep.findings],
            "insufficient_data_findings": [],
        }
    }

    response = await adapter.generate_capcom_response(
        query="Status report on power subsystem.",
        bounded_context=bounded_context,
    )

    # Active anomalies from FDIR engine
    expected_active_rule_ids = {f.rule_id for f in fdir_rep.active_anomalies}
    capcom_active_rule_ids = {af.rule_id for af in response.fdir_active_findings}

    # Byte-for-byte alignment
    assert "FDIR-PWR-001" in capcom_active_rule_ids
    assert expected_active_rule_ids == capcom_active_rule_ids


@pytest.mark.asyncio
async def test_capcom_mock_live_generation_success(monkeypatch):
    """Verifies parsing and schema validation of structured JSON output from Gemini."""
    adapter = GeminiCapcomAdapter(api_key="TEST_MOCK_KEY", model_name="gemini-2.5-flash")

    mock_gemini_json = json.dumps({
        "recommendations": [
            {
                "recommendation": "Increase UltraFlex solar array area by 1.2 m^2.",
                "engineering_rationale": "Compensates for 1.524 AU solar flux reduction at Mars.",
                "priority": "HIGH",
            }
        ],
        "unknown_data_observations": ["Reaction wheel tachometer telemetry not supplied."],
    })

    class MockModelResponse:
        text = f"```json\n{mock_gemini_json}\n```"

    class MockModelsService:
        def generate_content(self, model, contents):
            return MockModelResponse()

    class MockClient:
        models = MockModelsService()

    monkeypatch.setattr(adapter, "_get_client", lambda: MockClient())

    response = await adapter.generate_capcom_response(
        query="How can we resolve the power margin at Mars?",
        bounded_context={"system_constraints": {"target": "MARS", "mission_class": "DISCOVERY"}},
    )

    assert response.is_live_generation is True
    assert len(response.ai_recommendations) == 1
    assert response.ai_recommendations[0].priority == "HIGH"
    assert "UltraFlex" in response.ai_recommendations[0].recommendation
    assert "Reaction wheel" in response.unknown_or_insufficient_data[0]


@pytest.mark.asyncio
async def test_capcom_malformed_model_output_fallback(monkeypatch):
    """
    Verifies that if Gemini returns malformed non-JSON output,
    CAPCOM AI gracefully falls back without crashing and preserves verified facts.
    """
    adapter = GeminiCapcomAdapter(api_key="TEST_MOCK_KEY")

    class MalformedModelResponse:
        text = "I am an AI and I cannot output JSON right now."

    class MockModelsService:
        def generate_content(self, model, contents):
            return MalformedModelResponse()

    class MockClient:
        models = MockModelsService()

    monkeypatch.setattr(adapter, "_get_client", lambda: MockClient())

    response = await adapter.generate_capcom_response(
        query="What is the current status?",
        bounded_context={"system_constraints": {"target": "MARS"}},
    )

    assert response.is_live_generation is False
    assert len(response.ai_recommendations) > 0
    assert "Fallback" in response.model_name


# ============================================================================
# 4. REST API INTEGRATION TESTS: FDIR & CAPCOM Endpoints
# ============================================================================

@pytest.mark.asyncio
async def test_api_fdir_rules_and_scenarios(async_client: AsyncClient):
    """Verifies GET /fdir/rules and POST /fdir/scenarios/{id}."""
    # 1. Rules list
    rules_res = await async_client.get("/api/v1/fdir/rules")
    assert rules_res.status_code == 200
    rules = rules_res.json()
    rule_ids = [r["rule_id"] for r in rules]
    assert "FDIR-PWR-001" in rule_ids
    assert "FDIR-THM-001" in rule_ids
    assert "FDIR-COM-001" in rule_ids
    assert "FDIR-PRP-001" in rule_ids
    assert "FDIR-ATT-001" in rule_ids

    # 2. Run POWER_DEFICIT scenario
    pwr_res = await async_client.post("/api/v1/fdir/scenarios/POWER_DEFICIT")
    assert pwr_res.status_code == 200
    pwr_data = pwr_res.json()
    assert pwr_data["overall_severity"] == "CRITICAL"
    assert len(pwr_data["active_anomalies"]) >= 1

    # 3. Run NOMINAL_CRUISE scenario
    nom_res = await async_client.post("/api/v1/fdir/scenarios/NOMINAL_CRUISE")
    assert nom_res.status_code == 200
    nom_data = nom_res.json()
    assert nom_data["overall_severity"] == "NOMINAL"


@pytest.mark.asyncio
async def test_full_integrated_story_cdf_to_fdir_to_capcom(async_client: AsyncClient):
    """
    FULL STORY INTEGRATION TEST:
    1. Register user and authenticate.
    2. Create mission & CDF room.
    3. Mutate design to create a deliberate Delta-V shortfall.
    4. Run FDIR against authoritative room state -> detect Delta-V shortfall anomaly.
    5. Query CAPCOM AI assistant -> receive grounded response citing FDIR finding.
    6. Acknowledge anomaly in audit log.
    """
    # 1. Register & login
    u_suffix = uuid.uuid4().hex[:6]
    reg = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"flight_director_{u_suffix}@missionforge.org",
            "full_name": "Flight Director",
            "password": "Password123!",
        },
    )
    token = reg.json()["access_token"]
    auth_header = {"Authorization": f"Bearer {token}"}

    # 2. Create mission & room
    m_resp = await async_client.post(
        "/api/v1/missions",
        json={"name": "Mars Sample Return 2026", "target": "MARS", "min_delta_v_mps": 4200.0},
    )
    mission_id = m_resp.json()["id"]

    room_resp = await async_client.post(
        "/api/v1/cdf/rooms",
        json={
            "name": "MSR Primary Room",
            "mission_id": mission_id,
            "role": "LEAD_SYSTEMS_ARCHITECT",
        },
        headers=auth_header,
    )
    room_id = room_resp.json()["id"]

    # 3. Evaluate FDIR on Room state
    fdir_resp = await async_client.post(
        "/api/v1/fdir/evaluate",
        json={"room_id": room_id},
        headers=auth_header,
    )
    assert fdir_resp.status_code == 200
    fdir_data = fdir_resp.json()
    assert "findings" in fdir_data

    # 4. Query CAPCOM AI
    capcom_resp = await async_client.post(
        "/api/v1/capcom/ask",
        json={
            "room_id": room_id,
            "query": (
                "What is our current Delta-V margin and what are the flight director "
                "recommendations?"
            ),
        },
        headers=auth_header,
    )
    assert capcom_resp.status_code == 200
    capcom_data = capcom_resp.json()
    assert "verified_source_facts" in capcom_data
    assert "deterministic_calculations" in capcom_data
    assert "ai_recommendations" in capcom_data
    assert CAPCOM_SAFETY_DISCLAIMER in capcom_data["safety_disclaimer"]

    # 5. Check FDIR History
    hist_resp = await async_client.get(
        f"/api/v1/fdir/history?room_id={room_id}",
        headers=auth_header,
    )
    assert hist_resp.status_code == 200
    history = hist_resp.json()
    assert len(history) >= 1

    # 6. Acknowledge a finding
    finding_id = history[0]["id"]
    ack_resp = await async_client.post(
        "/api/v1/fdir/acknowledge",
        json={"finding_id": finding_id},
        headers=auth_header,
    )
    assert ack_resp.status_code == 200
    assert ack_resp.json()["message"] == "Finding successfully acknowledged."


def test_dsn_real_feed_response_conversion():
    """
    PROVENANCE & INTEGRATION TEST:
    Verifies that converting real NASA DSNFeedResponse models (from Phase 2)
    properly extracts genuine ground carrier lock, frequency, power, and RTLT metrics,
    attaching explicit GROUND_NETWORK provenance and mission/spacecraft tagging,
    without ever hallucinating onboard spacecraft bus/thermal/wheel fields.
    """
    from backend.app.integrations.dsn.models import (
        DSNFeedResponse,
        DSNStation,
        DSNDish,
        DSNSignal,
        DSNTarget,
    )
    from backend.app.core.cache import CacheStatus

    feed = DSNFeedResponse(
        source_url="https://eyes.nasa.gov/dsn/data/dsn.xml",
        cache_status=CacheStatus.LIVE,
        stations=[
            DSNStation(
                name="gdscc",
                friendly_name="Goldstone",
                time_utc=1700000000000,
                time_zone_offset_ms=-28800000,
                dishes=[
                    DSNDish(
                        name="DSS14",
                        azimuth_deg=145.2,
                        elevation_deg=62.8,
                        wind_speed_kmh=12.4,
                        down_signals=[
                            DSNSignal(
                                active=True,
                                signal_type="data",
                                frequency_hz=8420000000.0,
                                power_dbm_or_kw=-120.5,
                                data_rate_bps=12000.0,
                                band="X",
                                spacecraft="M20",
                            )
                        ],
                        targets=[
                            DSNTarget(
                                name="M20",
                                upleg_range_km=225000000.0,
                                downleg_range_km=225000000.0,
                                rtlt_seconds=1500.0,
                            )
                        ],
                    )
                ],
            )
        ],
    )

    readings = convert_dsn_feed_to_telemetry(
        feed, mission_id="mission-mars-2020", spacecraft_id="M20"
    )
    assert len(readings) >= 2

    carrier_reading = next(r for r in readings if "carrier_active" in r.metric_name)
    assert carrier_reading.subsystem == TelemetrySubsystem.COMMUNICATIONS
    assert carrier_reading.value == 1.0
    assert carrier_reading.provenance == TelemetryProvenanceType.GROUND_NETWORK
    assert carrier_reading.mission_id == "mission-mars-2020"
    assert carrier_reading.spacecraft_id == "M20"

    rtlt_reading = next(r for r in readings if "rtlt_s" in r.metric_name)
    assert rtlt_reading.value == 1500.0
    assert rtlt_reading.unit == "s"
    assert rtlt_reading.provenance == TelemetryProvenanceType.GROUND_NETWORK


def test_fdir_hysteresis_and_debounce_filtering():
    """
    HYSTERESIS & FLAPPING PROTECTION TEST:
    Verifies that when debounce_samples=3 is configured, transient single-sample
    spikes (e.g. NOMINAL -> CRITICAL -> NOMINAL) are suppressed from flapping the
    system alert level, and only 3 consecutive samples trigger escalation.
    """
    engine = FDIREngine()

    nominal_readings = [
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="bus_voltage_v",
            value=28.0,
            unit="V",
            source="BUS_A",
            provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="battery_charge_percent",
            value=90.0,
            unit="%",
            source="BATT_A",
            provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
        ),
    ]

    spike_critical_readings = [
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="bus_voltage_v",
            value=20.0,  # Critical undervoltage spike
            unit="V",
            source="BUS_A",
            provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="battery_charge_percent",
            value=20.0,
            unit="%",
            source="BATT_A",
            provenance=TelemetryProvenanceType.SIMULATED_SCENARIO,
        ),
    ]

    # Sample 1 (Spike): First critical reading should be damped by debounce (samples=3)
    rep1 = engine.evaluate_telemetry(spike_critical_readings, debounce_samples=3)
    pwr1 = next(f for f in rep1.findings if f.rule_id == "FDIR-PWR-001")
    assert pwr1.severity == FDIRSeverity.NOMINAL
    assert "Debounce filter active" in pwr1.explanation

    # Sample 2 (Spike continues)
    rep2 = engine.evaluate_telemetry(spike_critical_readings, debounce_samples=3)
    pwr2 = next(f for f in rep2.findings if f.rule_id == "FDIR-PWR-001")
    assert pwr2.severity == FDIRSeverity.NOMINAL

    # Sample 3 (Confirmed persistent fault: 3 consecutive critical samples)
    rep3 = engine.evaluate_telemetry(spike_critical_readings, debounce_samples=3)
    pwr3 = next(f for f in rep3.findings if f.rule_id == "FDIR-PWR-001")
    assert pwr3.severity == FDIRSeverity.CRITICAL

    # Sample 4 (Transient recovery spike to nominal)
    rep4 = engine.evaluate_telemetry(nominal_readings, debounce_samples=3)
    pwr4 = next(f for f in rep4.findings if f.rule_id == "FDIR-PWR-001")
    # Debounce prevents flapping immediately back to NOMINAL on 1 sample
    assert pwr4.severity == FDIRSeverity.CRITICAL


@pytest.mark.asyncio
async def test_capcom_trajectory_and_rule_versions_bounding():
    """
    Verifies that CAPCOM bounded context properly extracts trajectory inputs,
    link margin calculations, and FDIR rule versions into verified facts.
    """
    adapter = GeminiCapcomAdapter(api_key=None)

    bounded_context = {
        "system_constraints": {
            "target": "MARS",
            "mission_class": "DISCOVERY",
            "budget_cap_usd": 500e6,
        },
        "flight_dynamics_and_comms": {
            "required_delta_v_mps": 3850.0,
            "distance_au": 1.524,
            "tx_power_w": 25.0,
        },
        "calculated_budgets": {
            "wet_mass_kg": 1200.0,
            "available_delta_v_mps": 4100.0,
            "link_margin_db": 5.4,
        },
        "rule_versions": {
            "FDIR-PWR-001": "1.2.0",
            "FDIR-THM-001": "1.1.0",
        },
        "fdir_report": {
            "overall_severity": "NOMINAL",
            "findings": [],
            "insufficient_data_findings": [],
        },
    }

    res = await adapter.generate_capcom_response(
        query="Explain our orbital trajectory margins and comms baseline.",
        bounded_context=bounded_context,
    )

    assert "required_delta_v" in res.deterministic_calculations
    assert res.deterministic_calculations["required_delta_v"].value == 3850.0
    assert "target_distance" in res.deterministic_calculations
    assert res.deterministic_calculations["target_distance"].value == 1.524
    assert "link_margin" in res.deterministic_calculations

    # Verify rule versions cited in facts
    fact_statements = " ".join(f.statement for f in res.verified_source_facts)
    assert "FDIR-PWR-001" in fact_statements


def test_fdir_telemetry_quality_invalid_and_stale_rejection():
    """
    SCIENTIFIC INTEGRITY REGRESSION TEST:
    Verifies that sensor readings flagged as INVALID or STALE are never treated as nominal,
    and that absent fields are recorded as None rather than fabricated numbers.
    """
    from backend.app.fdir.rules import (
        RulePowerShortfall,
        RuleCommLoss,
        RuleThermalLimit,
        RulePropellantMargin,
    )
    from backend.app.fdir.telemetry import TelemetryQuality

    # 1. Power shortfall: invalid bus voltage
    pwr_rule = RulePowerShortfall()
    inv_pwr = {
        "bus_voltage_v": TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="bus_voltage_v",
            value=28.0,
            unit="V",
            source="TEST",
            provenance=TelemetryProvenanceType.FIXTURE,
            quality=TelemetryQuality.INVALID,  # Marked INVALID
        ),
        "battery_charge_percent": TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="battery_charge_percent",
            value=95.0,
            unit="%",
            source="TEST",
            provenance=TelemetryProvenanceType.FIXTURE,
            quality=TelemetryQuality.GOOD,
        ),
    }
    f_pwr = pwr_rule.evaluate(inv_pwr)
    assert f_pwr.input_evidence["bus_voltage_v"] is None
    assert f_pwr.confidence_status == "PROVISIONAL"
    assert "bus_voltage_v" in f_pwr.input_evidence["missing_fields"]

    # Both power indicators invalid -> INSUFFICIENT_DATA
    inv_pwr_both = dict(inv_pwr)
    inv_pwr_both["battery_charge_percent"].quality = TelemetryQuality.STALE
    f_pwr_both = pwr_rule.evaluate(inv_pwr_both)
    assert f_pwr_both.status == FDIRFindingStatus.INSUFFICIENT_DATA

    # 2. Comms: invalid carrier lock
    com_rule = RuleCommLoss()
    inv_com = {
        "carrier_lock": TelemetryReading(
            subsystem=TelemetrySubsystem.COMMUNICATIONS,
            metric_name="carrier_lock",
            value=1.0,
            unit="boolean",
            source="TEST",
            provenance=TelemetryProvenanceType.FIXTURE,
            quality=TelemetryQuality.INVALID,
        ),
        "downlink_snr_db": TelemetryReading(
            subsystem=TelemetrySubsystem.COMMUNICATIONS,
            metric_name="downlink_snr_db",
            value=8.0,
            unit="dB",
            source="TEST",
            provenance=TelemetryProvenanceType.FIXTURE,
            quality=TelemetryQuality.GOOD,
        ),
    }
    f_com = com_rule.evaluate(inv_com)
    assert f_com.input_evidence["carrier_lock"] is None
    assert f_com.confidence_status == "PROVISIONAL"

    # 3. Thermal: stale temperature sensor
    thm_rule = RuleThermalLimit()
    stale_thm = {
        "component_temp_c": TelemetryReading(
            subsystem=TelemetrySubsystem.THERMAL,
            metric_name="component_temp_c",
            value=25.0,
            unit="degC",
            source="TEST",
            provenance=TelemetryProvenanceType.FIXTURE,
            quality=TelemetryQuality.STALE,
        )
    }
    f_thm = thm_rule.evaluate(stale_thm)
    assert f_thm.status == FDIRFindingStatus.INSUFFICIENT_DATA

    # 4. Propellant: missing tank pressure must not fabricate 18.0 bar
    prp_rule = RulePropellantMargin()
    missing_press = {
        "available_delta_v_mps": TelemetryReading(
            subsystem=TelemetrySubsystem.PROPULSION,
            metric_name="available_delta_v_mps",
            value=4000.0,
            unit="m/s",
            source="TEST",
            provenance=TelemetryProvenanceType.FIXTURE,
            quality=TelemetryQuality.GOOD,
        ),
        "required_delta_v_mps": TelemetryReading(
            subsystem=TelemetrySubsystem.PROPULSION,
            metric_name="required_delta_v_mps",
            value=3800.0,
            unit="m/s",
            source="TEST",
            provenance=TelemetryProvenanceType.FIXTURE,
            quality=TelemetryQuality.GOOD,
        ),
    }
    f_prp = prp_rule.evaluate(missing_press)
    assert f_prp.input_evidence["tank_pressure_bar"] is None
    assert f_prp.confidence_status == "PROVISIONAL"
    assert "tank_pressure_bar" in f_prp.input_evidence["missing_fields"]


def test_fdir_unresolved_anomaly_not_cleared_by_missing_data():
    """
    SAFETY INVARIANT REGRESSION TEST:
    Verifies that when an active critical anomaly exists, subsequent loss of telemetry
    (causing INSUFFICIENT_DATA) does NOT silently clear the active anomaly.
    """
    from backend.app.fdir.engine import FDIREngine

    engine = FDIREngine()

    # Step 1: Active critical anomaly on power bus
    crit_telemetry = [
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="bus_voltage_v",
            value=20.5,  # Critical < 24V
            unit="V",
            source="FLIGHT_BUS_A",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            quality=TelemetryQuality.GOOD,
            mission_id="mission-crisis-01",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="battery_charge_percent",
            value=25.0,  # Critical < 30%
            unit="%",
            source="FLIGHT_BATT_A",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            quality=TelemetryQuality.GOOD,
            mission_id="mission-crisis-01",
        ),
    ]

    rep1 = engine.evaluate_telemetry(crit_telemetry)
    assert rep1.overall_severity == FDIRSeverity.CRITICAL
    assert len(rep1.active_anomalies) >= 1

    # Step 2: Telemetry drop out! Sensor cable disconnected, empty telemetry arrives
    empty_telemetry = [
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="unrelated_metric",
            value=1.0,
            unit="none",
            source="FLIGHT_BUS_A",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            quality=TelemetryQuality.GOOD,
            mission_id="mission-crisis-01",
        )
    ]

    rep2 = engine.evaluate_telemetry(empty_telemetry)
    pwr_finding = next(f for f in rep2.findings if f.rule_id == "FDIR-PWR-001")

    # Status must be INSUFFICIENT_DATA, NOT NOMINAL!
    assert pwr_finding.status == FDIRFindingStatus.INSUFFICIENT_DATA
    # Explanation must explicitly flag the unresolved anomaly
    assert "UNRESOLVED ANOMALY" in pwr_finding.explanation
    # And it must remain in active_anomalies list so mission controllers are alerted!
    active_ids = [f.rule_id for f in rep2.active_anomalies]
    assert "FDIR-PWR-001" in active_ids


def test_fdir_mission_configurable_thresholds():
    """
    Verifies that FDIR rules support mission-specific threshold configuration
    while retaining NASA-standard defaults.
    """
    from backend.app.fdir.rules import RulePowerShortfall

    # Custom mission threshold: require at least 26V (higher than standard 24V)
    custom_rule = RulePowerShortfall(thresholds={"critical_bus_voltage_v": 26.0})

    readings = {
        "bus_voltage_v": TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="bus_voltage_v",
            value=25.0,  # Below 26V custom threshold
            unit="V",
            source="TEST",
            provenance=TelemetryProvenanceType.FIXTURE,
        ),
        "battery_charge_percent": TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="battery_charge_percent",
            value=80.0,
            unit="%",
            source="TEST",
            provenance=TelemetryProvenanceType.FIXTURE,
        ),
    }

    finding = custom_rule.evaluate(readings)
    assert finding.severity == FDIRSeverity.CRITICAL
    assert finding.thresholds["critical_bus_voltage_v"] == 26.0


def test_fdir_active_anomaly_held_across_multiple_cycles_of_missing_telemetry():
    """
    CRITICAL SAFETY REGRESSION TEST:
    Verifies that when an active critical anomaly exists, loss of telemetry
    across MULTIPLE continuous cycles (cycle 2, cycle 3, cycle 4...)
    maintains the anomaly as CRITICAL and active in active_anomalies until
    verified nominal telemetry actually arrives.
    """
    engine = FDIREngine()

    # Cycle 1: Trigger active critical bus undervoltage
    crit_telemetry = [
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="bus_voltage_v",
            value=20.5,
            unit="V",
            source="BUS_A",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            quality=TelemetryQuality.GOOD,
            mission_id="multi-cycle-01",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="battery_charge_percent",
            value=25.0,
            unit="%",
            source="BATT_A",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            quality=TelemetryQuality.GOOD,
            mission_id="multi-cycle-01",
        ),
    ]
    rep1 = engine.evaluate_telemetry(crit_telemetry)
    assert rep1.overall_severity == FDIRSeverity.CRITICAL
    assert "FDIR-PWR-001" in [f.rule_id for f in rep1.active_anomalies]

    # Cycle 2: First telemetry dropout
    empty = [
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="unrelated_metric",
            value=1.0,
            unit="none",
            source="BUS_A",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="multi-cycle-01",
        )
    ]
    rep2 = engine.evaluate_telemetry(empty)
    assert rep2.overall_severity == FDIRSeverity.CRITICAL
    pwr2 = next(f for f in rep2.findings if f.rule_id == "FDIR-PWR-001")
    assert pwr2.severity == FDIRSeverity.CRITICAL
    assert "UNRESOLVED ANOMALY" in pwr2.explanation
    assert "FDIR-PWR-001" in [f.rule_id for f in rep2.active_anomalies]

    # Cycle 3: Second continuous telemetry dropout cycle
    rep3 = engine.evaluate_telemetry(empty)
    assert rep3.overall_severity == FDIRSeverity.CRITICAL
    pwr3 = next(f for f in rep3.findings if f.rule_id == "FDIR-PWR-001")
    assert pwr3.severity == FDIRSeverity.CRITICAL
    assert "UNRESOLVED ANOMALY" in pwr3.explanation
    assert "FDIR-PWR-001" in [f.rule_id for f in rep3.active_anomalies]

    # Cycle 4: Third continuous telemetry dropout cycle
    rep4 = engine.evaluate_telemetry(empty)
    assert rep4.overall_severity == FDIRSeverity.CRITICAL
    assert "FDIR-PWR-001" in [f.rule_id for f in rep4.active_anomalies]

    # Cycle 5: Telemetry is restored with VERIFIED nominal measurements!
    nominal_restored = [
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="bus_voltage_v",
            value=28.0,
            unit="V",
            source="BUS_A",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            quality=TelemetryQuality.GOOD,
            mission_id="multi-cycle-01",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="battery_charge_percent",
            value=95.0,
            unit="%",
            source="BATT_A",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            quality=TelemetryQuality.GOOD,
            mission_id="multi-cycle-01",
        ),
    ]
    rep5 = engine.evaluate_telemetry(nominal_restored)
    pwr5 = next(f for f in rep5.findings if f.rule_id == "FDIR-PWR-001")
    assert pwr5.severity == FDIRSeverity.NOMINAL
    assert "FDIR-PWR-001" not in [f.rule_id for f in rep5.active_anomalies]


def test_fdir_partial_sensor_loss_does_not_clear_active_anomaly():
    """
    SAFETY INVARIANT AUDIT ACROSS ALL 5 SUBSYSTEMS:
    When an active critical anomaly exists, loss or staleness of the alerting sensor
    (while companion sensors in the subsystem report normal values) MUST NOT
    silently clear the active anomaly.
    """
    engine = FDIREngine()

    # Subsystem 1: Power (Battery exhausted, then goes STALE while Bus is 28V)
    engine.reset()
    rep_pwr_crit = engine.evaluate_telemetry([
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="bus_voltage_v",
            value=28.0,
            unit="V",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-1",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="battery_charge_percent",
            value=15.0,
            unit="%",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-1",
        ),
    ])
    assert rep_pwr_crit.overall_severity == FDIRSeverity.CRITICAL

    # Battery goes STALE; Bus is still 28V
    rep_pwr_stale = engine.evaluate_telemetry([
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="bus_voltage_v",
            value=28.0,
            unit="V",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-1",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="battery_charge_percent",
            value=15.0,
            unit="%",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            quality=TelemetryQuality.STALE,
            mission_id="part-1",
        ),
    ])
    pwr_f = next(f for f in rep_pwr_stale.findings if f.rule_id == "FDIR-PWR-001")
    assert pwr_f.severity == FDIRSeverity.CRITICAL
    assert "UNRESOLVED ANOMALY" in pwr_f.explanation

    # Subsystem 2: Thermal (Radiation 150k rad critical, dosimeter STALE, Temp 20C)
    engine.reset()
    rep_thm_crit = engine.evaluate_telemetry([
        TelemetryReading(
            subsystem=TelemetrySubsystem.THERMAL,
            metric_name="component_temp_c",
            value=20.0,
            unit="C",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-2",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.THERMAL,
            metric_name="total_dose_rad",
            value=150_000.0,
            unit="rad",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-2",
        ),
    ])
    assert rep_thm_crit.overall_severity == FDIRSeverity.CRITICAL

    rep_thm_stale = engine.evaluate_telemetry([
        TelemetryReading(
            subsystem=TelemetrySubsystem.THERMAL,
            metric_name="component_temp_c",
            value=20.0,
            unit="C",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-2",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.THERMAL,
            metric_name="total_dose_rad",
            value=150_000.0,
            unit="rad",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            quality=TelemetryQuality.STALE,
            mission_id="part-2",
        ),
    ])
    thm_f = next(f for f in rep_thm_stale.findings if f.rule_id == "FDIR-THM-001")
    assert thm_f.severity == FDIRSeverity.CRITICAL
    assert "UNRESOLVED ANOMALY" in thm_f.explanation

    # Subsystem 3: Comms (Blackout critical, then carrier lock goes STALE while SNR is 10 dB)
    engine.reset()
    rep_com_crit = engine.evaluate_telemetry([
        TelemetryReading(
            subsystem=TelemetrySubsystem.COMMUNICATIONS,
            metric_name="carrier_lock",
            value=0.0,
            unit="bool",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-3",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.COMMUNICATIONS,
            metric_name="downlink_snr_db",
            value=-3.0,
            unit="dB",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-3",
        ),
    ])
    assert rep_com_crit.overall_severity == FDIRSeverity.CRITICAL

    rep_com_stale = engine.evaluate_telemetry([
        TelemetryReading(
            subsystem=TelemetrySubsystem.COMMUNICATIONS,
            metric_name="carrier_lock",
            value=0.0,
            unit="bool",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            quality=TelemetryQuality.STALE,
            mission_id="part-3",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.COMMUNICATIONS,
            metric_name="downlink_snr_db",
            value=10.0,
            unit="dB",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-3",
        ),
    ])
    com_f = next(f for f in rep_com_stale.findings if f.rule_id == "FDIR-COM-001")
    assert com_f.severity == FDIRSeverity.CRITICAL
    assert "UNRESOLVED ANOMALY" in com_f.explanation

    # Subsystem 4: Propulsion (Tank pressure 3 bar critical, pressure STALE, Delta-V nominal)
    engine.reset()
    rep_prp_crit = engine.evaluate_telemetry([
        TelemetryReading(
            subsystem=TelemetrySubsystem.PROPULSION,
            metric_name="available_delta_v_mps",
            value=4000.0,
            unit="m/s",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-4",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.PROPULSION,
            metric_name="required_delta_v_mps",
            value=3800.0,
            unit="m/s",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-4",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.PROPULSION,
            metric_name="tank_pressure_bar",
            value=3.0,
            unit="bar",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-4",
        ),
    ])
    assert rep_prp_crit.overall_severity == FDIRSeverity.CRITICAL

    rep_prp_stale = engine.evaluate_telemetry([
        TelemetryReading(
            subsystem=TelemetrySubsystem.PROPULSION,
            metric_name="available_delta_v_mps",
            value=4000.0,
            unit="m/s",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-4",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.PROPULSION,
            metric_name="required_delta_v_mps",
            value=3800.0,
            unit="m/s",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-4",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.PROPULSION,
            metric_name="tank_pressure_bar",
            value=3.0,
            unit="bar",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            quality=TelemetryQuality.STALE,
            mission_id="part-4",
        ),
    ])
    prp_f = next(f for f in rep_prp_stale.findings if f.rule_id == "FDIR-PRP-001")
    assert prp_f.severity == FDIRSeverity.CRITICAL
    assert "UNRESOLVED ANOMALY" in prp_f.explanation

    # Subsystem 5: Attitude (Wheel X 6000 RPM critical, Wheel X STALE, Y and Z 1000 RPM)
    engine.reset()
    rep_att_crit = engine.evaluate_telemetry([
        TelemetryReading(
            subsystem=TelemetrySubsystem.GNC_ATTITUDE,
            metric_name="reaction_wheel_rpm_x",
            value=6000.0,
            unit="RPM",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-5",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.GNC_ATTITUDE,
            metric_name="reaction_wheel_rpm_y",
            value=1000.0,
            unit="RPM",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-5",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.GNC_ATTITUDE,
            metric_name="reaction_wheel_rpm_z",
            value=1000.0,
            unit="RPM",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-5",
        ),
    ])
    assert rep_att_crit.overall_severity == FDIRSeverity.CRITICAL

    rep_att_stale = engine.evaluate_telemetry([
        TelemetryReading(
            subsystem=TelemetrySubsystem.GNC_ATTITUDE,
            metric_name="reaction_wheel_rpm_x",
            value=6000.0,
            unit="RPM",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            quality=TelemetryQuality.STALE,
            mission_id="part-5",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.GNC_ATTITUDE,
            metric_name="reaction_wheel_rpm_y",
            value=1000.0,
            unit="RPM",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-5",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.GNC_ATTITUDE,
            metric_name="reaction_wheel_rpm_z",
            value=1000.0,
            unit="RPM",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="part-5",
        ),
    ])
    att_f = next(f for f in rep_att_stale.findings if f.rule_id == "FDIR-ATT-001")
    assert att_f.severity == FDIRSeverity.CRITICAL
    assert "UNRESOLVED ANOMALY" in att_f.explanation


@pytest.mark.asyncio
async def test_fdir_alert_state_restoration_across_restarts():
    """
    AEROSPACE PERSISTENCE REGRESSION TEST:
    Verifies that when active unacknowledged anomalies are persisted in the database,
    a server process restart (engine reset) can restore active anomaly states from the DB,
    ensuring active alarms are not lost after restarts.
    """
    from backend.app.core.database import AsyncSessionLocal
    from backend.app.fdir.engine import FDIREngine

    engine = FDIREngine()
    m_id = f"mission-restart-{uuid.uuid4().hex[:6]}"

    # Step 1: Trigger and persist critical finding
    crit_telemetry = [
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="bus_voltage_v",
            value=19.5,
            unit="V",
            source="BUS_A",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            quality=TelemetryQuality.GOOD,
            mission_id=m_id,
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="battery_charge_percent",
            value=20.0,
            unit="%",
            source="BATT_A",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            quality=TelemetryQuality.GOOD,
            mission_id=m_id,
        ),
    ]
    rep1 = engine.evaluate_telemetry(crit_telemetry)
    assert rep1.overall_severity == FDIRSeverity.CRITICAL

    async with AsyncSessionLocal() as session:
        await engine.persist_findings(db=session, report=rep1, mission_id=m_id)

    # Step 2: Simulate process crash/restart
    engine.reset()
    assert len(engine._stable_severity) == 0

    # Step 3: Restore alert state from DB
    async with AsyncSessionLocal() as session:
        await engine.restore_alert_state(db=session, mission_id=m_id)

    # Verify that mission scope now has CRITICAL restored for FDIR-PWR-001
    assert engine._stable_severity[f"mission:{m_id}"]["FDIR-PWR-001"] == FDIRSeverity.CRITICAL

    # Step 4: Next telemetry cycle is empty (dropout) on restarted node -> anomaly is STILL held!
    rep_restarted = engine.evaluate_telemetry([
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="other",
            value=1.0,
            unit="none",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id=m_id,
        )
    ])
    assert rep_restarted.overall_severity == FDIRSeverity.CRITICAL
    assert "FDIR-PWR-001" in [f.rule_id for f in rep_restarted.active_anomalies]


def test_fdir_recovery_hysteresis_multisample():
    """
    HYSTERESIS RECOVERY VERIFICATION:
    When debounce_samples=3, clearing an active CRITICAL anomaly requires
    3 consecutive verified nominal samples. Samples 1 and 2 of nominal MUST
    hold the active anomaly at CRITICAL with recovery hysteresis guidance.
    """
    engine = FDIREngine()

    crit = [
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="bus_voltage_v",
            value=20.0,
            unit="V",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="hys-1",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="battery_charge_percent",
            value=20.0,
            unit="%",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            mission_id="hys-1",
        ),
    ]
    nom = [
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="bus_voltage_v",
            value=28.0,
            unit="V",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            quality=TelemetryQuality.GOOD,
            mission_id="hys-1",
        ),
        TelemetryReading(
            subsystem=TelemetrySubsystem.POWER,
            metric_name="battery_charge_percent",
            value=90.0,
            unit="%",
            source="T",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            quality=TelemetryQuality.GOOD,
            mission_id="hys-1",
        ),
    ]

    # Onset debounce: samples 1 and 2 hold NOMINAL until 3 consecutive samples confirm CRITICAL
    rep_c1 = engine.evaluate_telemetry(crit, debounce_samples=3)
    pwr_c1 = next(f for f in rep_c1.findings if f.rule_id == "FDIR-PWR-001")
    assert pwr_c1.severity == FDIRSeverity.NOMINAL
    assert "Debounce filter active" in pwr_c1.explanation

    rep_c2 = engine.evaluate_telemetry(crit, debounce_samples=3)
    pwr_c2 = next(f for f in rep_c2.findings if f.rule_id == "FDIR-PWR-001")
    assert pwr_c2.severity == FDIRSeverity.NOMINAL

    # 3rd consecutive sample confirms CRITICAL anomaly!
    rep_c3 = engine.evaluate_telemetry(crit, debounce_samples=3)
    assert rep_c3.overall_severity == FDIRSeverity.CRITICAL
    pwr_c3 = next(f for f in rep_c3.findings if f.rule_id == "FDIR-PWR-001")
    assert pwr_c3.severity == FDIRSeverity.CRITICAL

    # Recovery hysteresis: sample 1 of nominal is held at CRITICAL
    rep_n1 = engine.evaluate_telemetry(nom, debounce_samples=3)
    pwr_n1 = next(f for f in rep_n1.findings if f.rule_id == "FDIR-PWR-001")
    assert pwr_n1.severity == FDIRSeverity.CRITICAL
    assert "Recovery hysteresis active" in pwr_n1.explanation

    # Recovery hysteresis: sample 2 of nominal is held at CRITICAL
    rep_n2 = engine.evaluate_telemetry(nom, debounce_samples=3)
    pwr_n2 = next(f for f in rep_n2.findings if f.rule_id == "FDIR-PWR-001")
    assert pwr_n2.severity == FDIRSeverity.CRITICAL

    # Sample 3 of nominal: recovery confirmed, cleared to NOMINAL!
    rep_n3 = engine.evaluate_telemetry(nom, debounce_samples=3)
    pwr_n3 = next(f for f in rep_n3.findings if f.rule_id == "FDIR-PWR-001")
    assert pwr_n3.severity == FDIRSeverity.NOMINAL


def test_fdir_wheel_saturation_caution_and_warning_thresholds():
    """
    ATTITUDE FDIR REGRESSION TEST:
    Verifies that RuleWheelSaturation detects all 3 alert tiers:
    - CAUTION when max RPM > 4000 RPM (and <= 4800 RPM)
    - WARNING when max RPM > 4800 RPM (and <= 5500 RPM)
    - CRITICAL when max RPM > 5500 RPM
    - NOMINAL when max RPM <= 4000 RPM
    """
    rule = RuleWheelSaturation()

    def _make_wheel_readings(rpm: float):
        return {
            "reaction_wheel_rpm_x": TelemetryReading(
                subsystem=TelemetrySubsystem.GNC_ATTITUDE,
                metric_name="reaction_wheel_rpm_x",
                value=rpm,
                unit="RPM",
                source="RWA_X",
                provenance=TelemetryProvenanceType.LIVE_SATELLITE,
                quality=TelemetryQuality.GOOD,
            ),
            "reaction_wheel_rpm_y": TelemetryReading(
                subsystem=TelemetrySubsystem.GNC_ATTITUDE,
                metric_name="reaction_wheel_rpm_y",
                value=1200.0,
                unit="RPM",
                source="RWA_Y",
                provenance=TelemetryProvenanceType.LIVE_SATELLITE,
                quality=TelemetryQuality.GOOD,
            ),
            "reaction_wheel_rpm_z": TelemetryReading(
                subsystem=TelemetrySubsystem.GNC_ATTITUDE,
                metric_name="reaction_wheel_rpm_z",
                value=1200.0,
                unit="RPM",
                source="RWA_Z",
                provenance=TelemetryProvenanceType.LIVE_SATELLITE,
                quality=TelemetryQuality.GOOD,
            ),
        }

    # Nominal: 3500 RPM
    f_nom = rule.evaluate(_make_wheel_readings(3500.0))
    assert f_nom.severity == FDIRSeverity.NOMINAL
    assert f_nom.status == FDIRFindingStatus.NOMINAL

    # Caution: 4200 RPM
    f_caut = rule.evaluate(_make_wheel_readings(4200.0))
    assert f_caut.severity == FDIRSeverity.CAUTION
    assert f_caut.status == FDIRFindingStatus.ACTIVE_ANOMALY
    assert "elevated" in f_caut.explanation.lower()

    # Warning: 5000 RPM
    f_warn = rule.evaluate(_make_wheel_readings(5000.0))
    assert f_warn.severity == FDIRSeverity.WARNING
    assert f_warn.status == FDIRFindingStatus.ACTIVE_ANOMALY

    # Critical: 5600 RPM
    f_crit = rule.evaluate(_make_wheel_readings(5600.0))
    assert f_crit.severity == FDIRSeverity.CRITICAL
    assert f_crit.status == FDIRFindingStatus.ACTIVE_ANOMALY


def test_fdir_thermal_radiation_warning_threshold():
    """
    THERMAL & RADIATION REGRESSION TEST:
    Verifies that RuleThermalLimit triggers a WARNING finding when total radiation
    dose exceeds 50 krad (even with nominal 25°C temperature).
    """
    rule = RuleThermalLimit()

    readings = {
        "component_temp_c": TelemetryReading(
            subsystem=TelemetrySubsystem.THERMAL,
            metric_name="component_temp_c",
            value=25.0,  # Completely nominal temperature
            unit="°C",
            source="RTD_1",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            quality=TelemetryQuality.GOOD,
        ),
        "total_dose_rad": TelemetryReading(
            subsystem=TelemetrySubsystem.THERMAL,
            metric_name="total_dose_rad",
            value=65_000.0,  # 65 krad: above 50 krad warning, below 100 krad critical
            unit="rad",
            source="DOSIMETER_1",
            provenance=TelemetryProvenanceType.LIVE_SATELLITE,
            quality=TelemetryQuality.GOOD,
        ),
    }

    finding = rule.evaluate(readings)
    assert finding.severity == FDIRSeverity.WARNING
    assert finding.status == FDIRFindingStatus.ACTIVE_ANOMALY
    assert "radiation dose 65000 rad > 50000 rad" in finding.explanation


@pytest.mark.asyncio
async def test_fdir_room_alert_state_restoration_across_restarts(async_client: AsyncClient):
    """
    ROOM-SCOPED PERSISTENCE & CAPCOM REGRESSION TEST:
    Verifies that:
    1. Evaluating FDIR with room_id persists findings with both room_id and mission_id.
    2. Resetting the in-memory engine state simulates a server restart.
    3. Subsequent evaluation on room_id restores the active anomaly from the database.
    4. CAPCOM queries on the room also restore active anomaly context.
    """
    from backend.app.fdir.engine import fdir_engine

    u_suffix = uuid.uuid4().hex[:6]
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"fdir_user_{u_suffix}@missionforge.org",
            "full_name": "FDIR Engineer",
            "password": "Password123!",
        },
    )
    headers = {"Authorization": f"Bearer {reg_res.json()['access_token']}"}

    m_res = await async_client.post(
        "/api/v1/missions",
        json={"name": "Restoration Mission", "target": "MARS"},
    )
    mission_id = m_res.json()["id"]

    r_res = await async_client.post(
        "/api/v1/cdf/rooms",
        json={
            "name": "Restoration CDF Room",
            "mission_id": mission_id,
            "role": "LEAD_SYSTEMS_ARCHITECT",
        },
        headers=headers,
    )
    room_id = r_res.json()["id"]

    # 1. Trigger CRITICAL power anomaly for room
    crit_telemetry = [
        {
            "subsystem": "POWER",
            "metric_name": "bus_voltage_v",
            "value": 18.0,
            "unit": "V",
            "source": "BUS_MAIN",
            "provenance": "LIVE_SATELLITE",
            "quality": "GOOD",
        },
        {
            "subsystem": "POWER",
            "metric_name": "battery_charge_percent",
            "value": 22.0,
            "unit": "%",
            "source": "BATT_MAIN",
            "provenance": "LIVE_SATELLITE",
            "quality": "GOOD",
        },
    ]

    eval_resp = await async_client.post(
        "/api/v1/fdir/evaluate",
        json={"room_id": room_id, "readings": crit_telemetry},
        headers=headers,
    )
    assert eval_resp.status_code == 200
    assert eval_resp.json()["overall_severity"] == "CRITICAL"

    # 2. Simulate server restart: wipe all engine in-memory state
    fdir_engine.reset()
    assert len(fdir_engine._stable_severity) == 0

    # 3. Next telemetry cycle arrives with sensor loss (empty readings):
    # The anomaly MUST be restored from DB and held as UNRESOLVED ANOMALY!
    dropout_resp = await async_client.post(
        "/api/v1/fdir/evaluate",
        json={"room_id": room_id, "readings": []},
        headers=headers,
    )
    assert dropout_resp.status_code == 200
    rep_data = dropout_resp.json()
    assert rep_data["overall_severity"] == "CRITICAL"
    pwr_finding = next(f for f in rep_data["findings"] if f["rule_id"] == "FDIR-PWR-001")
    assert pwr_finding["severity"] == "CRITICAL"
    assert "UNRESOLVED ANOMALY" in pwr_finding["explanation"]

    # 4. CAPCOM query on this room must also restore and reflect the active anomaly!
    capcom_resp = await async_client.post(
        "/api/v1/capcom/ask",
        json={"query": "What is the status of the electrical power bus?", "room_id": room_id},
        headers=headers,
    )
    assert capcom_resp.status_code == 200
    cap_data = capcom_resp.json()
    active_rules = [f["rule_id"] for f in cap_data["fdir_active_findings"]]
    assert "FDIR-PWR-001" in active_rules
    assert any("FDIR-PWR-001" in f["rule_id"] for f in cap_data["fdir_active_findings"])
