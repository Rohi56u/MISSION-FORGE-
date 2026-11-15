"""
Verification script for Live Google Gemini CAPCOM Integration
Mission Forge — Phase 5
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.capcom.gemini_adapter import GeminiCapcomAdapter  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.schemas.capcom import CAPCOM_SAFETY_DISCLAIMER  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("verify_gemini")


async def main() -> int:
    logger.info("Initializing Live Gemini CAPCOM verification...")
    logger.info("Model: %s", settings.GEMINI_MODEL)
    key_prefix = settings.GEMINI_API_KEY[:6] if settings.GEMINI_API_KEY else "NONE"
    logger.info("Key configured: %s...", key_prefix)

    adapter = GeminiCapcomAdapter(timeout_seconds=20.0)

    sample_context = {
        "room_id": "cdf-room-europa-clipper-test",
        "system_constraints": {
            "target": "Jupiter (Europa)",
            "mission_class": "Flagship",
            "budget_cap_usd": 4250000000.0,
            "max_launch_mass_kg": 6000.0,
        },
        "calculated_budgets": {
            "wet_mass_kg": 5820.0,
            "dry_mass_kg": 2750.0,
            "available_delta_v_mps": 2450.0,
            "total_power_generated_w": 750.0,
            "total_power_draw_w": 620.0,
            "total_cost_usd": 3980000000.0,
            "link_margin_db": 3.8,
        },
        "flight_dynamics_and_comms": {
            "required_delta_v_mps": 2380.0,
            "distance_au": 5.2,
        },
        "fdir_report": {
            "findings": [
                {
                    "rule_id": "COMM_LINK_MARGIN_RULE",
                    "severity": "WARNING",
                    "affected_subsystem": "Telecommunications",
                    "status": "ACTIVE_ANOMALY",
                    "explanation": (
                        "Downlink link margin (3.8 dB) is within 1.0 dB of 3.0 dB threshold."
                    ),
                    "triage_guidance": (
                        "Recommend adjusting HGA pointing or stepping down downlink data rate."
                    ),
                }
            ],
            "insufficient_data_findings": [],
        },
        "rule_versions": {
            "COMM_LINK_MARGIN_RULE": "1.0.0",
            "POWER_POSITIVE_MARGIN_RULE": "1.0.0",
        },
        "unknown_fields": [],
    }

    query = (
        "What is our communication link status and what actions do you recommend "
        "before orbital insertion?"
    )

    logger.info("Sending query to CAPCOM adapter...")
    response = await adapter.generate_capcom_response(query=query, bounded_context=sample_context)

    logger.info("Response received:")
    logger.info("  Is Live Generation: %s", response.is_live_generation)
    logger.info("  Model Name: %s", response.model_name)
    logger.info("  Verified Source Facts Count: %d", len(response.verified_source_facts))
    logger.info("  Calculations Count: %d", len(response.deterministic_calculations))
    logger.info("  Active FDIR Findings Count: %d", len(response.fdir_active_findings))
    logger.info("  AI Recommendations Count: %d", len(response.ai_recommendations))

    for idx, rec in enumerate(response.ai_recommendations, 1):
        logger.info("  [Rec %d] (%s) %s", idx, rec.priority, rec.recommendation)
        logger.info("          Rationale: %s", rec.engineering_rationale)

    logger.info("  Safety Disclaimer: %s", response.safety_disclaimer)

    # Verification Assertions
    assert response.is_live_generation is True, "Expected is_live_generation to be True!"
    assert response.safety_disclaimer == CAPCOM_SAFETY_DISCLAIMER, "Safety disclaimer mismatch!"
    assert len(response.ai_recommendations) > 0, "Expected at least one AI recommendation!"
    assert len(response.verified_source_facts) > 0, "Preserved source facts required!"
    assert "wet_mass" in response.deterministic_calculations, "Calculation missing!"

    logger.info("SUCCESS: Live Gemini CAPCOM integration fully verified and validated!")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
