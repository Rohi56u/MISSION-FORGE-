"""
Pydantic v2 Schemas for Deterministic Aerospace Physics Calculations
Mission Forge — Phase 1 Remediation
"""

from pydantic import BaseModel, Field


class TsiolkovskyRequest(BaseModel):
    """Calculates ideal velocity increment Delta-V using Tsiolkovsky's equation."""
    isp_seconds: float = Field(..., gt=0.0, description="Specific impulse in seconds (> 0 s)")
    wet_mass_kg: float = Field(
        ..., gt=0.0, description="Initial spacecraft wet mass in kg (> 0 kg)"
    )
    dry_mass_kg: float = Field(
        ..., gt=0.0, description="Final spacecraft dry mass in kg (> 0 kg)"
    )


class PropellantMassRequest(BaseModel):
    """Calculates required propellant mass given dry mass, Isp, and target Delta-V."""
    isp_seconds: float = Field(..., gt=0.0, description="Specific impulse in seconds (> 0 s)")
    dry_mass_kg: float = Field(..., gt=0.0, description="Spacecraft dry mass in kg (> 0 kg)")
    delta_v_mps: float = Field(
        ..., ge=0.0, description="Required velocity increment in m/s (>= 0 m/s)"
    )


class PropulsionTradeoffRequest(BaseModel):
    """Typed JSON request body for chemical vs electric propulsion tradeoff analysis."""
    m_dry_kg: float = Field(
        ...,
        gt=0.0,
        description="Spacecraft dry mass in kilograms (SI: kg, > 0 kg)",
    )
    delta_v_mps: float = Field(
        ...,
        ge=0.0,
        description="Required mission Delta-V increment in m/s (SI: m/s, >= 0 m/s)",
    )


class ChemicalPropulsionSummary(BaseModel):
    """Performance summary of chemical bipropellant baseline."""
    isp_seconds: float = Field(..., description="Specific impulse (s)")
    propellant_mass_kg: float = Field(..., description="Required propellant mass (kg)")
    wet_mass_kg: float = Field(..., description="Total wet mass (kg)")
    mass_fraction: float = Field(..., description="Propellant mass fraction (m_prop / m_wet)")
    burn_type: str = Field(..., description="Maneuver burn characterization")
    electrical_power_w: float = Field(
        ..., description="Electrical power consumed during operation (W)"
    )


class ElectricPropulsionSummary(BaseModel):
    """Performance summary of electric ion propulsion baseline."""
    isp_seconds: float = Field(..., description="Specific impulse (s)")
    propellant_mass_kg: float = Field(..., description="Required propellant mass (kg)")
    wet_mass_kg: float = Field(..., description="Total wet mass (kg)")
    mass_fraction: float = Field(..., description="Propellant mass fraction (m_prop / m_wet)")
    burn_type: str = Field(..., description="Maneuver burn characterization")
    electrical_power_w: float = Field(..., description="Electrical beam power required (W)")


class TradeoffAnalysis(BaseModel):
    """Comparative analysis metrics between chemical and electric propulsion."""
    propellant_mass_saved_kg: float = Field(..., description="Mass savings in kg")
    propellant_reduction_percent: float = Field(
        ..., description="Percentage reduction in propellant load"
    )
    key_friction: str = Field(
        ..., description="Primary engineering trade-off or architectural constraint"
    )


class PropulsionTradeoffResponse(BaseModel):
    """Documented typed response for chemical vs electric propulsion tradeoff analysis."""
    m_dry_kg: float = Field(..., description="Spacecraft dry mass in kg")
    delta_v_mps: float = Field(..., description="Mission Delta-V in m/s")
    chemical_bipropellant: ChemicalPropulsionSummary
    electric_ion_propulsion: ElectricPropulsionSummary
    trade_off_analysis: TradeoffAnalysis


class SolarPowerRequest(BaseModel):
    """Calculates solar irradiance and array electrical output at distance r."""
    distance_au: float = Field(
        ..., gt=0.0, description="Heliocentric distance in Astronomical Units (AU > 0)"
    )
    area_m2: float = Field(
        ..., gt=0.0, description="Active photovoltaic array surface area in m^2 (> 0)"
    )
    efficiency: float = Field(
        default=0.30, gt=0.0, le=1.0, description="Solar cell conversion efficiency (0 to 1)"
    )
    incidence_angle_deg: float = Field(
        default=0.0,
        ge=0.0,
        le=90.0,
        description="Sun incidence angle relative to array normal (0 to 90 deg)",
    )


class MMRTGRequest(BaseModel):
    """Models radioactive isotope decay and thermocouple degradation of an MMRTG."""
    p_bol_w: float = Field(
        default=110.0,
        ge=0.0,
        description="Beginning-of-life electrical power output in Watts (>= 0 W)",
    )
    time_years: float = Field(
        default=0.0, ge=0.0, description="Mission elapsed time in years (>= 0 yr)"
    )
    annual_decay_rate: float = Field(
        default=0.008,
        ge=0.0,
        lt=1.0,
        description="Annual fractional thermocouple degradation rate (e.g. 0.008 for 0.8%/yr)",
    )


class MMRTGDecayBreakdownResponse(BaseModel):
    """Detailed decomposition of isotopic half-life decay vs thermoelectric degradation."""
    initial_power_bol_w: float
    mission_time_years: float
    annual_thermocouple_degradation_rate: float
    pu238_isotope_fraction_remaining: float
    thermocouple_fraction_remaining: float
    combined_fraction_remaining: float
    power_output_w: float
    total_degradation_percent: float
    thermal_power_w: float
    notes: str


class LinkBudgetRequest(BaseModel):
    """Calculates deep-space RF telecom link budget using Friis transmission equation."""
    distance_m: float = Field(
        ..., gt=0.0, description="Distance from Earth ground station in meters (> 0 m)"
    )
    frequency_hz: float = Field(
        default=8.425e9,
        gt=0.0,
        description="Carrier frequency in Hz (default: X-band 8.425 GHz)",
    )
    tx_power_w: float = Field(
        ..., gt=0.0, description="Spacecraft transmitter RF output power in Watts (> 0 W)"
    )
    tx_antenna_diameter_m: float = Field(
        ..., gt=0.0, description="Spacecraft High-Gain Antenna (HGA) diameter in meters (> 0 m)"
    )
    rx_antenna_diameter_m: float = Field(
        default=70.0,
        gt=0.0,
        description="DSN ground station dish diameter in meters (default: 70 m)",
    )
    data_rate_bps: float = Field(
        default=10_000.0,
        gt=0.0,
        description="Required downlink transmission rate in bits per second (> 0 bps)",
    )
