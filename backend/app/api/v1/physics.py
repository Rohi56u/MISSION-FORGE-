"""
Aerospace Physics and Engineering Calculation Endpoints
"""

from fastapi import APIRouter, HTTPException, status

from backend.app.schemas.swapc import SWaPCAnalysisRequest, SWaPCAnalysisResponse
from backend.app.schemas.physics import (
    TsiolkovskyRequest,
    PropellantMassRequest,
    PropulsionTradeoffRequest,
    PropulsionTradeoffResponse,
    SolarPowerRequest,
    MMRTGRequest,
    MMRTGDecayBreakdownResponse,
    LinkBudgetRequest,
)
from backend.app.physics.propulsion import (
    tsiolkovsky_delta_v,
    propellant_mass_required,
    compare_propulsion_technologies,
)
from backend.app.physics.power import (
    solar_irradiance,
    solar_array_power,
    mmrtg_power_at_time,
    mmrtg_decay_breakdown,
)
from backend.app.physics.telecom import deep_space_link_budget
from backend.app.physics.swapc import calculate_swapc

router = APIRouter(prefix="/physics", tags=["Deterministic Aerospace Physics"])


# --- Endpoints ---
@router.post("/tsiolkovsky", status_code=status.HTTP_200_OK)
def calculate_tsiolkovsky(req: TsiolkovskyRequest):
    """Calculates ideal velocity increment Delta-V using Tsiolkovsky's equation."""
    try:
        dv = tsiolkovsky_delta_v(req.isp_seconds, req.wet_mass_kg, req.dry_mass_kg)
        return {
            "isp_seconds": req.isp_seconds,
            "wet_mass_kg": req.wet_mass_kg,
            "dry_mass_kg": req.dry_mass_kg,
            "propellant_mass_kg": round(req.wet_mass_kg - req.dry_mass_kg, 2),
            "delta_v_mps": round(dv, 2),
            "formula": "Delta-V = Isp * g_0 * ln(m_wet / m_dry)",
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/propellant-mass", status_code=status.HTTP_200_OK)
def calculate_propellant_mass(req: PropellantMassRequest):
    """Calculates required propellant mass given dry mass, Isp, and target Delta-V."""
    try:
        m_prop = propellant_mass_required(req.isp_seconds, req.dry_mass_kg, req.delta_v_mps)
        return {
            "isp_seconds": req.isp_seconds,
            "dry_mass_kg": req.dry_mass_kg,
            "delta_v_mps": req.delta_v_mps,
            "propellant_mass_kg": round(m_prop, 2),
            "wet_mass_kg": round(req.dry_mass_kg + m_prop, 2),
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/propulsion-tradeoff",
    response_model=PropulsionTradeoffResponse,
    status_code=status.HTTP_200_OK,
)
def compare_propulsion(req: PropulsionTradeoffRequest):
    """
    Compares Chemical Bipropellant vs Hall/Ion Electric Propulsion trade-offs.
    Accepts a validated JSON request body.
    """
    try:
        return compare_propulsion_technologies(req.m_dry_kg, req.delta_v_mps)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/solar-power", status_code=status.HTTP_200_OK)
def calculate_solar_power(req: SolarPowerRequest):
    """Calculates solar irradiance and array electrical output at distance r."""
    try:
        flux = solar_irradiance(req.distance_au)
        power_w = solar_array_power(
            req.distance_au, req.area_m2, req.efficiency, req.incidence_angle_deg
        )
        return {
            "distance_au": req.distance_au,
            "solar_flux_w_m2": round(flux, 2),
            "irradiance_percentage_of_1au": round((flux / 1361.0) * 100.0, 2),
            "array_area_m2": req.area_m2,
            "cell_efficiency": req.efficiency,
            "incidence_angle_deg": req.incidence_angle_deg,
            "generated_power_w": round(power_w, 2),
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/mmrtg-decay", status_code=status.HTTP_200_OK)
def calculate_mmrtg_power(req: MMRTGRequest):
    """Models radioactive isotope decay and thermocouple degradation of an MMRTG."""
    try:
        power_w = mmrtg_power_at_time(req.p_bol_w, req.time_years, req.annual_decay_rate)
        return {
            "initial_power_bol_w": req.p_bol_w,
            "mission_time_years": req.time_years,
            "annual_degradation_rate": req.annual_decay_rate,
            "power_output_w": round(power_w, 2),
            "total_degradation_percent": (
                round(((req.p_bol_w - power_w) / req.p_bol_w) * 100.0, 2)
                if req.p_bol_w > 0
                else 0.0
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/mmrtg-decay/breakdown",
    response_model=MMRTGDecayBreakdownResponse,
    status_code=status.HTTP_200_OK,
)
def calculate_mmrtg_breakdown(req: MMRTGRequest):
    """
    Decomposes MMRTG electrical power output into distinct isotopic half-life decay
    and solid-state thermoelectric thermocouple degradation factors.
    """
    try:
        return mmrtg_decay_breakdown(req.p_bol_w, req.time_years, req.annual_decay_rate)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/link-budget", status_code=status.HTTP_200_OK)
def calculate_telecom_link(req: LinkBudgetRequest):
    """Calculates deep space RF link budget, received power, Eb/N0, and margin."""
    try:
        return deep_space_link_budget(
            distance_m=req.distance_m,
            frequency_hz=req.frequency_hz,
            tx_power_w=req.tx_power_w,
            tx_antenna_diameter_m=req.tx_antenna_diameter_m,
            rx_antenna_diameter_m=req.rx_antenna_diameter_m,
            data_rate_bps=req.data_rate_bps,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/swapc", response_model=SWaPCAnalysisResponse, status_code=status.HTTP_200_OK)
def analyze_spacecraft_swapc(request: SWaPCAnalysisRequest):
    """
    Performs full systems engineering aggregation:
    Mass Budget, Power Balance, Delta-V propellant sizing, Cost, and Constraint Validation.
    """
    try:
        return calculate_swapc(request)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
