"""
Comprehensive Deterministic Aerospace Physics Engine Tests
Mission Forge — NASA Space Apps Challenge 2026

Remediation Test Suite:
  - Multi-thruster effective specific impulse (simultaneous firing derivation)
  - Propulsion: Tsiolkovsky Rocket Equation & mass sizing
  - Power: Solar Irradiance (Kopp & Lean 2011 / IAU 2015), MMRTG dual-decay model
  - Telecom: Free-Space Path Loss & Link Budget
  - SWaP-C: Full Systems Engineering Integration & constraint audits
"""

import math
import pytest

from backend.app.physics.propulsion import (
    tsiolkovsky_delta_v,
    propellant_mass_required,
    calculate_multithruster_effective_isp,
    calculate_staged_propulsion_systems,
    ThrusterOperatingSpec,
)
from backend.app.physics.power import (
    solar_irradiance,
    solar_array_power,
    mmrtg_power_at_time,
    mmrtg_decay_breakdown,
    evaluate_power_balance,
)
from backend.app.physics.telecom import (
    free_space_path_loss_db,
    deep_space_link_budget,
)
from backend.app.physics.swapc import calculate_swapc
from backend.app.schemas.swapc import (
    SWaPCAnalysisRequest,
    ComponentSpecSchema,
)
from backend.app.models.mission import MissionTarget, MissionClass
from backend.app.models.component import SubsystemType
from backend.app.physics.constants import (
    STANDARD_GRAVITY,
    SOLAR_CONSTANT_1AU,
)
from backend.app.physics.citations import SCIENTIFIC_CITATIONS


# ===========================================================================
# SECTION 1 — PROPULSION & MULTI-THRUSTER TESTS
# ===========================================================================

class TestTsiolkovsky:
    """Tests for tsiolkovsky_delta_v and propellant_mass_required."""

    def test_tsiolkovsky_basic(self):
        """Isp=315 s, m_wet=1000 kg, m_dry=500 kg -> exact analytical Delta-V."""
        isp = 315.0
        m_wet = 1000.0
        m_dry = 500.0
        expected = isp * STANDARD_GRAVITY * math.log(m_wet / m_dry)
        result = tsiolkovsky_delta_v(isp, m_wet, m_dry)
        assert result == pytest.approx(expected, rel=1e-6)
        assert 2140.0 < result < 2142.0

    def test_tsiolkovsky_zero_propellant(self):
        """m_wet == m_dry -> zero delta-v."""
        result = tsiolkovsky_delta_v(isp_s=315.0, m_wet_kg=500.0, m_dry_kg=500.0)
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_tsiolkovsky_invalid_negative_dry_mass(self):
        with pytest.raises(ValueError, match="[Dd]ry mass"):
            tsiolkovsky_delta_v(isp_s=315.0, m_wet_kg=1000.0, m_dry_kg=0.0)

    def test_tsiolkovsky_invalid_wet_less_than_dry(self):
        with pytest.raises(ValueError, match="[Ww]et mass"):
            tsiolkovsky_delta_v(isp_s=315.0, m_wet_kg=400.0, m_dry_kg=500.0)

    def test_tsiolkovsky_invalid_zero_isp(self):
        with pytest.raises(ValueError, match="[Ss]pecific impulse"):
            tsiolkovsky_delta_v(isp_s=0.0, m_wet_kg=1000.0, m_dry_kg=500.0)

    def test_propellant_mass_round_trip(self):
        isp = 315.0
        m_wet = 1000.0
        m_dry = 500.0
        delta_v = tsiolkovsky_delta_v(isp, m_wet, m_dry)
        m_prop_back = propellant_mass_required(isp, m_dry, delta_v)
        assert m_prop_back == pytest.approx(m_wet - m_dry, rel=1e-9)

    def test_propellant_mass_zero_delta_v(self):
        result = propellant_mass_required(isp_s=315.0, m_dry_kg=500.0, delta_v_mps=0.0)
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_tsiolkovsky_high_isp_ion_thruster(self):
        result_chem = tsiolkovsky_delta_v(315.0, 1000.0, 500.0)
        result_ion = tsiolkovsky_delta_v(3500.0, 1000.0, 500.0)
        assert result_ion > result_chem * 10


class TestMultiThrusterEffectiveIsp:
    """Rigorous verification of simultaneous multi-thruster effective Isp."""

    def test_single_thruster_equivalence(self):
        """Single thruster must return exactly its own Isp without modification."""
        thruster = ThrusterOperatingSpec(thrust_newtons=440.0, isp_seconds=318.0)
        result = calculate_multithruster_effective_isp([thruster])
        assert result == pytest.approx(318.0, rel=1e-9)

    def test_audit_example_equal_thrust_different_isp(self):
        """
        Audit benchmark: 100 N at 300 s plus 100 N at 3000 s.
        Derivation:
          F_tot = 200 N
          m_dot * g_0 = 100/300 + 100/3000 = 1/3 + 1/30 = 11/30
          Isp_eff = 200 / (11/30) = 6000 / 11 = 545.4545... s
        """
        t1 = ThrusterOperatingSpec(thrust_newtons=100.0, isp_seconds=300.0, name="Chem")
        t2 = ThrusterOperatingSpec(thrust_newtons=100.0, isp_seconds=3000.0, name="EP")
        result = calculate_multithruster_effective_isp([t1, t2])
        expected = 6000.0 / 11.0  # ≈ 545.454545 s
        assert result == pytest.approx(expected, rel=1e-6)
        assert 545.45 < result < 545.46

    def test_disproves_arithmetic_mean(self):
        """
        Demonstrates that an arithmetic mean (1650 s) violently overestimates performance
        and violates propellant mass conservation. The true Isp is ~545.45 s.
        """
        t1 = (100.0, 300.0)
        t2 = (100.0, 3000.0)
        true_isp = calculate_multithruster_effective_isp([t1, t2])
        arithmetic_mean = (300.0 + 3000.0) / 2.0  # 1650 s
        assert true_isp < 600.0
        assert arithmetic_mean > 1600.0
        assert (arithmetic_mean - true_isp) > 1000.0

    def test_unequal_thrust_and_isp(self):
        """Main engine (1000 N @ 320 s) + vernier thruster (10 N @ 220 s)."""
        t1 = ThrusterOperatingSpec(thrust_newtons=1000.0, isp_seconds=320.0)
        t2 = ThrusterOperatingSpec(thrust_newtons=10.0, isp_seconds=220.0)
        f_tot = 1010.0
        flow_denom = (1000.0 / 320.0) + (10.0 / 220.0)
        expected = f_tot / flow_denom
        result = calculate_multithruster_effective_isp([t1, t2])
        assert result == pytest.approx(expected, rel=1e-7)

    def test_empty_thrusters_raises(self):
        with pytest.raises(ValueError, match="No thrusters provided"):
            calculate_multithruster_effective_isp([])

    def test_all_inactive_thrusters_raises(self):
        t1 = ThrusterOperatingSpec(thrust_newtons=100.0, isp_seconds=300.0, is_active=False)
        with pytest.raises(ValueError, match="No active thrusters"):
            calculate_multithruster_effective_isp([t1])

    def test_inactive_thrusters_filtered_out(self):
        t_active = ThrusterOperatingSpec(thrust_newtons=200.0, isp_seconds=310.0, is_active=True)
        t_inactive = ThrusterOperatingSpec(
            thrust_newtons=500.0, isp_seconds=4500.0, is_active=False
        )
        result = calculate_multithruster_effective_isp([t_active, t_inactive])
        assert result == pytest.approx(310.0, rel=1e-9)

    def test_zero_or_negative_thrust_raises(self):
        with pytest.raises(ValueError, match="invalid thrust"):
            calculate_multithruster_effective_isp([
                ThrusterOperatingSpec(thrust_newtons=0.0, isp_seconds=300.0),
                ThrusterOperatingSpec(thrust_newtons=100.0, isp_seconds=300.0),
            ])
        with pytest.raises(ValueError, match="invalid thrust"):
            calculate_multithruster_effective_isp([
                ThrusterOperatingSpec(thrust_newtons=-50.0, isp_seconds=300.0),
                ThrusterOperatingSpec(thrust_newtons=100.0, isp_seconds=300.0),
            ])

    def test_zero_or_negative_isp_raises(self):
        with pytest.raises(ValueError, match="invalid Isp"):
            calculate_multithruster_effective_isp([
                ThrusterOperatingSpec(thrust_newtons=100.0, isp_seconds=0.0),
            ])
        with pytest.raises(ValueError, match="invalid Isp"):
            calculate_multithruster_effective_isp([
                ThrusterOperatingSpec(thrust_newtons=100.0, isp_seconds=-300.0),
            ])

    def test_system_filter_isolation(self):
        """Separate RCS thrusters from PRIMARY main engine."""
        primary = ThrusterOperatingSpec(
            thrust_newtons=500.0, isp_seconds=325.0, maneuver_system="PRIMARY"
        )
        rcs = ThrusterOperatingSpec(
            thrust_newtons=10.0, isp_seconds=220.0, maneuver_system="RCS"
        )
        result_primary = calculate_multithruster_effective_isp(
            [primary, rcs], system_filter="PRIMARY"
        )
        assert result_primary == pytest.approx(325.0, rel=1e-9)

    def test_non_finite_thrust_and_isp_raises(self):
        """Infinite or NaN values must be rejected."""
        with pytest.raises(ValueError, match="invalid thrust"):
            calculate_multithruster_effective_isp([
                ThrusterOperatingSpec(thrust_newtons=float("inf"), isp_seconds=300.0),
            ])
        with pytest.raises(ValueError, match="invalid thrust"):
            calculate_multithruster_effective_isp([
                ThrusterOperatingSpec(thrust_newtons=float("nan"), isp_seconds=300.0),
            ])
        with pytest.raises(ValueError, match="invalid Isp"):
            calculate_multithruster_effective_isp([
                ThrusterOperatingSpec(thrust_newtons=100.0, isp_seconds=float("inf")),
            ])
        with pytest.raises(ValueError, match="invalid Isp"):
            calculate_multithruster_effective_isp([
                ThrusterOperatingSpec(thrust_newtons=100.0, isp_seconds=float("-inf")),
            ])

    def test_incompatible_maneuver_systems_mixed_raises(self):
        """
        Remediation 1: Mixing thrusters from different maneuver stages (e.g. PRIMARY and RCS)
        without an explicit filter must raise ValueError to prevent misleading composite Isp.
        """
        primary = ThrusterOperatingSpec(
            thrust_newtons=500.0, isp_seconds=325.0, maneuver_system="PRIMARY"
        )
        rcs = ThrusterOperatingSpec(thrust_newtons=10.0, isp_seconds=220.0, maneuver_system="RCS")
        with pytest.raises(ValueError, match="distinct maneuver systems"):
            calculate_multithruster_effective_isp([primary, rcs])

    def test_calculate_staged_propulsion_systems(self):
        """Calculates and isolates propulsion systems by maneuver system."""
        thrusters = [
            ThrusterOperatingSpec(
                thrust_newtons=400.0, isp_seconds=320.0, maneuver_system="PRIMARY"
            ),
            ThrusterOperatingSpec(
                thrust_newtons=400.0, isp_seconds=320.0, maneuver_system="PRIMARY"
            ),
            ThrusterOperatingSpec(thrust_newtons=10.0, isp_seconds=220.0, maneuver_system="RCS"),
        ]
        staged = calculate_staged_propulsion_systems(thrusters)
        assert "PRIMARY" in staged
        assert "RCS" in staged
        assert staged["PRIMARY"]["effective_isp_s"] == pytest.approx(320.0, rel=1e-5)
        assert staged["PRIMARY"]["total_thrust_n"] == 800.0
        assert staged["PRIMARY"]["thruster_count"] == 2
        assert staged["RCS"]["effective_isp_s"] == pytest.approx(220.0, rel=1e-5)
        assert staged["RCS"]["total_thrust_n"] == 10.0
        assert staged["RCS"]["thruster_count"] == 1


# ===========================================================================
# SECTION 2 — POWER & MMRTG TESTS
# ===========================================================================

class TestSolarPower:
    """Tests for solar irradiance and MMRTG power output."""

    def test_solar_irradiance_1au(self):
        """At 1 AU -> exactly 1361.0 W/m^2 (Kopp & Lean 2011 / IAU 2015)."""
        result = solar_irradiance(1.0)
        assert result == pytest.approx(1361.0, rel=1e-6)
        assert result == pytest.approx(SOLAR_CONSTANT_1AU, rel=1e-9)

    def test_solar_irradiance_europa(self):
        result = solar_irradiance(5.204)
        expected = 1361.0 / (5.204 ** 2)
        assert result == pytest.approx(expected, rel=1e-5)
        assert 45.0 < result < 55.0

    def test_solar_irradiance_inverse_square(self):
        s_1au = solar_irradiance(1.0)
        s_2au = solar_irradiance(2.0)
        assert s_2au == pytest.approx(s_1au / 4.0, rel=1e-9)

    def test_solar_irradiance_negative_distance_raises(self):
        with pytest.raises(ValueError):
            solar_irradiance(0.0)
        with pytest.raises(ValueError):
            solar_irradiance(-1.0)

    def test_solar_power_europa_deficit(self):
        p_small = solar_array_power(distance_au=5.204, area_m2=1.0, efficiency=0.30)
        assert p_small < 20.0
        p_large = solar_array_power(distance_au=5.204, area_m2=220.0, efficiency=0.30)
        assert p_large > 100.0

    def test_mmrtg_at_zero_time(self):
        result = mmrtg_power_at_time(p_bol_w=110.0, time_years=0.0)
        assert result == pytest.approx(110.0, rel=1e-9)

    def test_mmrtg_decay_at_10_years(self):
        p_bol = 110.0
        p_10yr = mmrtg_power_at_time(p_bol_w=p_bol, time_years=10.0)
        assert p_10yr < p_bol
        assert 80.0 < p_10yr < 105.0

    def test_mmrtg_monotonically_decreasing(self):
        powers = [mmrtg_power_at_time(110.0, t) for t in [0, 1, 5, 10, 20, 50]]
        assert all(powers[i] > powers[i + 1] for i in range(len(powers) - 1))

    def test_mmrtg_custom_bol_power(self):
        result = mmrtg_power_at_time(p_bol_w=150.0, time_years=0.0)
        assert result == pytest.approx(150.0, rel=1e-9)

    def test_mmrtg_invalid_inputs_raise(self):
        with pytest.raises(ValueError, match="Beginning of life power"):
            mmrtg_power_at_time(p_bol_w=-10.0, time_years=1.0)
        with pytest.raises(ValueError, match="Time elapsed"):
            mmrtg_power_at_time(p_bol_w=110.0, time_years=-2.0)
        with pytest.raises(ValueError, match="Thermocouple decay rate"):
            mmrtg_power_at_time(p_bol_w=110.0, time_years=1.0, annual_thermocouple_decay=1.0)
        with pytest.raises(ValueError, match="Thermocouple decay rate"):
            mmrtg_power_at_time(p_bol_w=110.0, time_years=1.0, annual_thermocouple_decay=-0.05)

    def test_evaluate_power_balance(self):
        nom = evaluate_power_balance(150.0, 100.0, min_margin_percent=15.0)
        assert nom["is_sufficient"] is True
        assert nom["status"] == "NOMINAL"
        assert nom["margin_w"] == 50.0
        assert nom["margin_percent"] == 50.0

        crit = evaluate_power_balance(80.0, 100.0, min_margin_percent=15.0)
        assert crit["is_sufficient"] is False
        assert crit["status"] == "CRITICAL"

    def test_mmrtg_decay_breakdown(self):
        """
        Remediation 4: Verifies explicit separation of isotopic decay from thermocouple degradation.
        """
        bd = mmrtg_decay_breakdown(p_bol_w=110.0, time_years=10.0, annual_thermocouple_decay=0.008)
        assert "pu238_isotope_fraction_remaining" in bd
        assert "thermocouple_fraction_remaining" in bd
        assert "power_output_w" in bd
        assert "thermal_power_w" in bd
        # Isotope fraction at 10 yr (half-life 87.7 yr): exp(-ln(2)*10/87.7) ≈ 0.9242
        assert 0.92 < bd["pu238_isotope_fraction_remaining"] < 0.93
        # Thermocouple fraction: (1 - 0.008)^10 ≈ 0.9227
        assert 0.92 < bd["thermocouple_fraction_remaining"] < 0.93
        # Combined power output: 110 * 0.9242 * 0.9227 ≈ 93.8 W
        assert 92.0 < bd["power_output_w"] < 96.0


# ===========================================================================
# SECTION 3 — TELECOM TESTS
# ===========================================================================

class TestTelecom:
    """Tests for Free-Space Path Loss and deep-space link budgets."""

    def test_fspl_increases_with_distance(self):
        freq = 8.425e9
        fspl_near = free_space_path_loss_db(1e6, freq)
        fspl_far = free_space_path_loss_db(1e9, freq)
        assert fspl_far > fspl_near

    def test_fspl_doubles_per_decade(self):
        freq = 8.425e9
        fspl_1 = free_space_path_loss_db(1e6, freq)
        fspl_10 = free_space_path_loss_db(1e7, freq)
        assert (fspl_10 - fspl_1) == pytest.approx(20.0, abs=0.01)

    def test_fspl_invalid_distance_raises(self):
        with pytest.raises(ValueError):
            free_space_path_loss_db(0.0, 8.425e9)

    def test_link_budget_mars(self):
        distance_m = 2.279e11
        result = deep_space_link_budget(
            distance_m=distance_m,
            frequency_hz=8.425e9,
            tx_power_w=20.0,
            tx_antenna_diameter_m=1.5,
            rx_antenna_diameter_m=70.0,
            data_rate_bps=10_000.0,
        )
        assert "link_margin_db" in result
        assert result["path_loss_db"] > 250.0
        assert isinstance(result["link_margin_db"], float)


# ===========================================================================
# SECTION 4 — SWaP-C INTEGRATION TESTS
# ===========================================================================

def _make_mmrtg_component(name="MMRTG Unit", power_gen=110.0) -> ComponentSpecSchema:
    return ComponentSpecSchema(
        name=name,
        subsystem=SubsystemType.POWER,
        mass_kg=44.0,
        power_draw_w=0.0,
        power_generation_w=power_gen,
        cost_usd=70_000_000.0,
        is_radioisotope=True,
        annual_decay_rate=0.008,
    )


def _make_propulsion_component(
    name="Bi-prop Thruster", isp=316.0, thrust=440.0
) -> ComponentSpecSchema:
    return ComponentSpecSchema(
        name=name,
        subsystem=SubsystemType.PROPULSION,
        mass_kg=50.0,
        power_draw_w=25.0,
        cost_usd=5_000_000.0,
        isp_seconds=isp,
        thrust_newtons=thrust,
    )


def _make_structure_component(mass: float = 300.0) -> ComponentSpecSchema:
    return ComponentSpecSchema(
        name="Spacecraft Bus",
        subsystem=SubsystemType.STRUCTURE,
        mass_kg=mass,
        power_draw_w=30.0,
        cost_usd=30_000_000.0,
    )


def _make_telecom_component() -> ComponentSpecSchema:
    return ComponentSpecSchema(
        name="HGA X-Band",
        subsystem=SubsystemType.TELECOM,
        mass_kg=15.0,
        power_draw_w=20.0,
        cost_usd=10_000_000.0,
        antenna_diameter_m=1.5,
        tx_power_w=20.0,
        frequency_hz=8.425e9,
    )


class TestSWaPCIntegration:
    """Integration tests for the full SWaP-C analysis engine."""

    def test_swapc_nominal_europa_mmrtg_dual_feasible(self):
        """
        Europa FLAGSHIP mission with 2 MMRTGs (~215 W generated vs 100 W load).
        Must verify COMPLETE FEASIBILITY:
          - is_feasible is True
          - status is NOMINAL
          - violations list is EMPTY
          - margin > 10%
        """
        request = SWaPCAnalysisRequest(
            target=MissionTarget.EUROPA,
            mission_class=MissionClass.FLAGSHIP,
            components=[
                _make_mmrtg_component(name="MMRTG Unit 1"),
                _make_mmrtg_component(name="MMRTG Unit 2"),
                _make_propulsion_component(),
                _make_structure_component(mass=300.0),
                _make_telecom_component(),
            ],
            required_delta_v_mps=2000.0,
            min_power_margin_percent=10.0,
        )
        result = calculate_swapc(request)

        # Assert actual feasibility verdict
        assert result.is_feasible is True, (
            f"Expected feasible design, got: {[v.message for v in result.violations]}"
        )
        assert result.status == "NOMINAL"
        assert len(result.violations) == 0

        # Assert power budget
        assert result.total_power_generated_w > 200.0
        assert result.power_margin_percent > 10.0

        # Assert delta-v and mass
        assert result.available_delta_v_mps >= 2000.0
        assert result.wet_mass_kg > result.dry_mass_kg

    def test_swapc_europa_single_mmrtg_power_deficit_detected(self):
        """
        Europa mission with 1 MMRTG (~107 W generated) but 150 W load.
        Must explicitly verify that POWER_DEFICIT is triggered and is_feasible is False.
        Inspects violation details.
        """
        heavy_load = ComponentSpecSchema(
            name="Heavy Science Suite",
            subsystem=SubsystemType.SCIENCE,
            mass_kg=60.0,
            power_draw_w=120.0,
            cost_usd=40_000_000.0,
        )
        request = SWaPCAnalysisRequest(
            target=MissionTarget.EUROPA,
            mission_class=MissionClass.FLAGSHIP,
            components=[
                _make_mmrtg_component(),
                heavy_load,
                _make_propulsion_component(),
                _make_structure_component(),
            ],
            required_delta_v_mps=1500.0,
        )
        result = calculate_swapc(request)

        assert result.is_feasible is False
        assert result.status == "INFEASIBLE"
        power_violation = next(
            (v for v in result.violations if v.constraint_type == "POWER_DEFICIT"), None
        )
        assert power_violation is not None
        assert power_violation.actual_value < power_violation.limit_value
        assert "POWER_DEFICIT" in [v.constraint_type for v in result.violations]

    def test_swapc_multithruster_simultaneous_integration(self):
        """
        Tests multi-thruster propulsion integration in SWaP-C.
        Two 100 N thrusters (300 s and 3000 s) -> effective Isp = 545.45 s.
        """
        t1 = ComponentSpecSchema(
            name="Thruster A",
            subsystem=SubsystemType.PROPULSION,
            mass_kg=20.0,
            thrust_newtons=100.0,
            isp_seconds=300.0,
        )
        t2 = ComponentSpecSchema(
            name="Thruster B",
            subsystem=SubsystemType.PROPULSION,
            mass_kg=20.0,
            thrust_newtons=100.0,
            isp_seconds=3000.0,
        )
        request = SWaPCAnalysisRequest(
            target=MissionTarget.MARS,
            mission_class=MissionClass.DISCOVERY,
            components=[t1, t2, _make_structure_component(100.0)],
            required_delta_v_mps=1000.0,
        )
        result = calculate_swapc(request)
        expected_isp = 6000.0 / 11.0  # ≈ 545.45 s
        assert result.effective_isp_s == pytest.approx(expected_isp, abs=0.1)

    def test_swapc_multithruster_missing_thrust_rejected(self):
        """Multi-thruster design with missing thrust_newtons must be rejected."""
        t1 = ComponentSpecSchema(
            name="Thruster A",
            subsystem=SubsystemType.PROPULSION,
            mass_kg=20.0,
            thrust_newtons=None,  # Missing!
            isp_seconds=300.0,
        )
        t2 = ComponentSpecSchema(
            name="Thruster B",
            subsystem=SubsystemType.PROPULSION,
            mass_kg=20.0,
            thrust_newtons=100.0,
            isp_seconds=3000.0,
        )
        request = SWaPCAnalysisRequest(
            target=MissionTarget.MARS,
            mission_class=MissionClass.DISCOVERY,
            components=[t1, t2],
        )
        with pytest.raises(ValueError, match="Arbitrary defaults .* are rejected"):
            calculate_swapc(request)

    def test_swapc_staged_propulsion_isolation(self):
        """
        Remediation 1: Spacecraft with PRIMARY engine and RCS thrusters must NOT collapse
        them into one composite Isp for mission Delta-V.
        """
        main_engine = ComponentSpecSchema(
            name="Main Biprop Engine",
            subsystem=SubsystemType.PROPULSION,
            mass_kg=45.0,
            thrust_newtons=440.0,
            isp_seconds=320.0,
            maneuver_system="PRIMARY",
        )
        rcs_thruster = ComponentSpecSchema(
            name="RCS Attitude Thrusters",
            subsystem=SubsystemType.PROPULSION,
            mass_kg=12.0,
            thrust_newtons=10.0,
            isp_seconds=220.0,
            maneuver_system="RCS",
        )
        req = SWaPCAnalysisRequest(
            target=MissionTarget.MARS,
            mission_class=MissionClass.DISCOVERY,
            components=[main_engine, rcs_thruster, _make_structure_component(200.0)],
            required_delta_v_mps=1500.0,
        )
        result = calculate_swapc(req)
        # Sizing must use PRIMARY engine Isp (320 s), not a collapsed combination (~317 s)
        assert result.effective_isp_s == pytest.approx(320.0, rel=1e-5)
        # Both stages must be reported separately in propulsion_systems
        assert "PRIMARY" in result.propulsion_systems
        assert "RCS" in result.propulsion_systems
        primary_sys = result.propulsion_systems["PRIMARY"]
        rcs_sys = result.propulsion_systems["RCS"]
        assert primary_sys["effective_isp_s"] == pytest.approx(320.0, rel=1e-5)
        assert rcs_sys["effective_isp_s"] == pytest.approx(220.0, rel=1e-5)


# ===========================================================================
# SECTION 5 — CITATIONS & SCIENTIFIC CONSTANTS
# ===========================================================================

class TestScientificCitations:
    """Verifies that all scientific citations and reference values are traceable."""

    def test_citations_registry_completeness(self):
        required_keys = [
            "SOLAR_IRRADIANCE_1AU",
            "STANDARD_GRAVITY",
            "SPEED_OF_LIGHT",
            "BOLTZMANN_CONSTANT",
            "ASTRONOMICAL_UNIT",
            "PU238_HALF_LIFE",
            "MMRTG_DEGRADATION_MODEL",
            "POWER_MARGIN_STANDARD",
            "MULTI_THRUSTER_EFFECTIVE_ISP",
        ]
        for key in required_keys:
            assert key in SCIENTIFIC_CITATIONS
            citation = SCIENTIFIC_CITATIONS[key]
            assert "title" in citation
            assert len(citation["title"]) > 5

    def test_solar_constant_provenance(self):
        """Confirms 1361.0 W/m^2 citation is correctly attributed to Kopp & Lean 2011 / IAU 2015."""
        c = SCIENTIFIC_CITATIONS["SOLAR_IRRADIANCE_1AU"]
        assert c["value"] == 1361.0
        assert "Kopp" in c["authors"]
        assert "ASTM E490" in c["notes"]  # Explains distinction from older ASTM 1366.1 value
