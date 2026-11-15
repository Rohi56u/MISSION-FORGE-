"""
Deterministic Deep-Space Telecom Physics
Implements Free-Space Path Loss (FSPL), Antenna Gain, Link Budget, SNR,
and Round-Trip Light Time (RTLT).
"""

import math
from typing import Dict, Any
from backend.app.physics.constants import (
    SPEED_OF_LIGHT,
    BOLTZMANN_CONSTANT,
    DSN_ANTENNA_DIAMETER_M,
    DSN_SYSTEM_NOISE_TEMP_K,
)


def round_trip_light_time_seconds(distance_m: float) -> float:
    """
    Calculates Round-Trip Light Time (RTLT) in seconds.

    Formula:
        tau = 2 * distance / c
    """
    if distance_m < 0.0:
        raise ValueError(f"Distance cannot be negative, got {distance_m} m.")
    return float((2.0 * distance_m) / SPEED_OF_LIGHT)


def free_space_path_loss_db(distance_m: float, frequency_hz: float) -> float:
    """
    Calculates Free-Space Path Loss (FSPL) in decibels (dB).

    Formula:
        FSPL = (4 * pi * d * f / c)^2
        FSPL_dB = 20 * log10(d) + 20 * log10(f) + 20 * log10(4 * pi / c)

    Args:
        distance_m: Distance between transmitter and receiver in meters (> 0).
        frequency_hz: Carrier frequency in Hertz (> 0).

    Returns:
        Loss in dB (positive value indicating attenuation).
    """
    if distance_m <= 0.0:
        raise ValueError(f"Distance must be positive, got {distance_m} m.")
    if frequency_hz <= 0.0:
        raise ValueError(f"Frequency must be positive, got {frequency_hz} Hz.")

    wavelength = SPEED_OF_LIGHT / frequency_hz
    loss_linear = ((4.0 * math.pi * distance_m) / wavelength) ** 2
    return float(10.0 * math.log10(loss_linear))


def parabolic_antenna_gain_dbi(
    diameter_m: float, frequency_hz: float, efficiency: float = 0.55
) -> float:
    """
    Calculates boresight gain of a parabolic reflector antenna in dBi.

    Formula:
        G = eta * (pi * D * f / c)^2
        G_dBi = 10 * log10(G)

    Args:
        diameter_m: Dish aperture diameter in meters (> 0).
        frequency_hz: Operating RF frequency in Hz (> 0).
        efficiency: Aperture illumination efficiency (typically 0.50 to 0.65).

    Returns:
        Antenna gain in dBi.
    """
    if diameter_m <= 0.0:
        raise ValueError(f"Antenna diameter must be positive, got {diameter_m} m.")
    if frequency_hz <= 0.0:
        raise ValueError(f"Frequency must be positive, got {frequency_hz} Hz.")
    if not (0.0 < efficiency <= 1.0):
        raise ValueError(f"Efficiency must be between 0 and 1, got {efficiency}.")

    wavelength = SPEED_OF_LIGHT / frequency_hz
    gain_linear = efficiency * ((math.pi * diameter_m) / wavelength) ** 2
    return float(10.0 * math.log10(gain_linear))


def deep_space_link_budget(
    distance_m: float,
    frequency_hz: float,
    tx_power_w: float,
    tx_antenna_diameter_m: float,
    rx_antenna_diameter_m: float = DSN_ANTENNA_DIAMETER_M,
    data_rate_bps: float = 10_000.0,
    system_noise_temp_k: float = DSN_SYSTEM_NOISE_TEMP_K,
    required_eb_n0_db: float = 4.5,
) -> Dict[str, Any]:
    """
    Calculates complete deep-space link budget using the Friis transmission equation.

    Calculates:
      - Transmitter Power (dBW)
      - Transmit & Receive Antenna Gains (dBi)
      - Free-Space Path Loss (dB)
      - Received Power (dBW and dBm)
      - Noise Spectral Density N_0 = k * T_sys (dBW/Hz)
      - Energy-per-bit to Noise Density ratio (Eb/N0 in dB)
      - Link Margin (dB)
    """
    if tx_power_w <= 0.0:
        raise ValueError(f"Transmitter power must be positive, got {tx_power_w} W.")
    if data_rate_bps <= 0.0:
        raise ValueError(f"Data rate must be positive, got {data_rate_bps} bps.")

    # 1. Powers and Gains
    p_tx_dbw = 10.0 * math.log10(tx_power_w)
    g_tx_dbi = parabolic_antenna_gain_dbi(tx_antenna_diameter_m, frequency_hz)
    g_rx_dbi = parabolic_antenna_gain_dbi(rx_antenna_diameter_m, frequency_hz)
    path_loss_db = free_space_path_loss_db(distance_m, frequency_hz)

    # 2. Received Power (dBW)
    pointing_cable_loss_db = 2.0
    p_rx_dbw = p_tx_dbw + g_tx_dbi + g_rx_dbi - path_loss_db - pointing_cable_loss_db
    p_rx_dbm = p_rx_dbw + 30.0

    # 3. Noise Density N_0 = k * T_sys
    n0_dbw_hz = 10.0 * math.log10(BOLTZMANN_CONSTANT) + 10.0 * math.log10(
        system_noise_temp_k
    )

    # 4. Bit Energy to Noise Ratio Eb/N0
    rate_db = 10.0 * math.log10(data_rate_bps)
    eb_n0_db = p_rx_dbw - n0_dbw_hz - rate_db

    # 5. Link Margin
    link_margin_db = eb_n0_db - required_eb_n0_db
    rtlt_s = round_trip_light_time_seconds(distance_m)

    return {
        "distance_km": round(distance_m / 1000.0, 1),
        "rtlt_seconds": round(rtlt_s, 2),
        "rtlt_formatted": f"{int(rtlt_s // 60)}m {int(rtlt_s % 60)}s",
        "carrier_frequency_ghz": round(frequency_hz / 1e9, 3),
        "tx_power_watts": tx_power_w,
        "tx_gain_dbi": round(g_tx_dbi, 2),
        "rx_gain_dbi": round(g_rx_dbi, 2),
        "path_loss_db": round(path_loss_db, 2),
        "received_power_dbm": round(p_rx_dbm, 2),
        "eb_n0_db": round(eb_n0_db, 2),
        "required_eb_n0_db": required_eb_n0_db,
        "link_margin_db": round(link_margin_db, 2),
        "is_link_closed": link_margin_db >= 0.0,
        "data_rate_kbps": round(data_rate_bps / 1000.0, 2),
    }
