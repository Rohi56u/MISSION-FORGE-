"""
Google Gemini Adapter & Grounded Flight Advisory Engine
Mission Forge — Phase 5
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional

from backend.app.core.config import settings
from backend.app.schemas.capcom import (
    AIRecommendation,
    CAPCOM_SAFETY_DISCLAIMER,
    CAPCOMResponse,
    FDIRFindingSummary,
    FormattedCalculation,
    VerifiedFact,
)

logger = logging.getLogger(__name__)


class GeminiCapcomAdapter:
    """
    Adapter for Google Gemini AI assistant with strict context bounding,
    schema validation, and deterministic backend alignment.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self.timeout_seconds = timeout_seconds
        self._client: Any = None

    def _get_client(self) -> Optional[Any]:
        if not self.api_key:
            return None
        if self._client is None:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception as exc:
                logger.error("Failed to initialize Google GenAI Client: %s", exc)
                return None
        return self._client

    async def generate_capcom_response(
        self,
        query: str,
        bounded_context: Dict[str, Any],
    ) -> CAPCOMResponse:
        """
        Generates a grounded CAPCOM advisory response.
        The deterministic backend calculations and FDIR findings are AUTHORITATIVE.
        The AI assistant is strictly bounded to the provided context and cannot mutate state.
        """
        now = datetime.now(timezone.utc)

        # 1. Deterministically extract verified facts from bounded context
        verified_facts: List[VerifiedFact] = []
        constraints = bounded_context.get("system_constraints", {})
        if constraints:
            tgt = constraints.get("target", "UNKNOWN")
            cls_name = constraints.get("mission_class", "UNKNOWN")
            verified_facts.append(
                VerifiedFact(
                    statement=f"Mission Target is designated as {tgt} under NASA {cls_name} class.",
                    source="CDF Authoritative System Constraints",
                    citation="NASA Space Flight Constraints Registry",
                )
            )
            cap_m = constraints.get('budget_cap_usd', 0) / 1e6
            verified_facts.append(
                VerifiedFact(
                    statement=f"Authorized Budget Cap is ${cap_m:.1f}M.",
                    source="CDF System Constraints",
                    citation="NASA Discovery/New Frontiers Budget Guidelines",
                )
            )

        # FDIR Rule Versions fact
        rule_vers = bounded_context.get("rule_versions", {})
        if rule_vers:
            rule_str = ", ".join(f"{k} (v{v})" for k, v in list(rule_vers.items())[:3])
            verified_facts.append(
                VerifiedFact(
                    statement=f"Active FDIR Rules: {rule_str}.",
                    source="Deterministic FDIR Engine",
                    citation="Mission Forge Autonomous Safety Ruleset",
                )
            )

        # 2. Extract deterministic SWaP-C & trajectory calculations with exact units
        calculations: Dict[str, FormattedCalculation] = {}
        budgets = bounded_context.get("calculated_budgets", {})
        if budgets:
            calculations["wet_mass"] = FormattedCalculation(
                name="Wet Launch Mass",
                value=budgets.get("wet_mass_kg", 0.0),
                unit="kg",
                formula_reference="Tsiolkovsky: m_wet = m_dry * exp(Delta_V / (Isp * g_0))",
            )
            calculations["available_delta_v"] = FormattedCalculation(
                name="Available Delta-V",
                value=budgets.get("available_delta_v_mps", 0.0),
                unit="m/s",
                formula_reference="Ideal Rocket Equation: Delta_V = g_0 * Isp * ln(m_wet / m_dry)",
            )
            calculations["total_power_generated"] = FormattedCalculation(
                name="Total Power Generated",
                value=budgets.get("total_power_generated_w", 0.0),
                unit="W",
                formula_reference="P = S_0 * (1/R_au^2) * Area * Efficiency",
            )
            calculations["total_power_draw"] = FormattedCalculation(
                name="Total Power Draw",
                value=budgets.get("total_power_draw_w", 0.0),
                unit="W",
                formula_reference="Sigma(P_components) * Subsystem Operating Contingency",
            )
            calculations["total_mission_cost"] = FormattedCalculation(
                name="Total Estimated Mission Cost",
                value=budgets.get("total_cost_usd", 0.0),
                unit="USD",
                formula_reference="NASA Cost Estimating Handbook (CEH) COTS + Payload Aggregation",
            )
            if budgets.get("link_margin_db") is not None:
                calculations["link_margin"] = FormattedCalculation(
                    name="Downlink Margin",
                    value=budgets.get("link_margin_db", 0.0),
                    unit="dB",
                    formula_reference="Friis Transmission Equation & Thermal Noise Floor",
                )

        flight_comms = bounded_context.get("flight_dynamics_and_comms", {})
        if flight_comms:
            if "required_delta_v_mps" in flight_comms:
                calculations["required_delta_v"] = FormattedCalculation(
                    name="Required Delta-V",
                    value=flight_comms.get("required_delta_v_mps", 0.0),
                    unit="m/s",
                    formula_reference="Lambert Arc & Orbital Transfer Budget",
                )
            if "distance_au" in flight_comms:
                calculations["target_distance"] = FormattedCalculation(
                    name="Heliocentric Distance",
                    value=flight_comms.get("distance_au", 1.0),
                    unit="AU",
                    formula_reference="Solar System Ephemeris",
                )

        # 3. Extract Authoritative Deterministic FDIR Findings (CANNOT be altered by AI!)
        fdir_report = bounded_context.get("fdir_report", {})
        raw_findings = fdir_report.get("findings", [])
        active_fdir_summaries: List[FDIRFindingSummary] = []
        for rf in raw_findings:
            sev = rf.get("severity", "NOMINAL")
            stat = rf.get("status", "NOMINAL")
            if sev in ("WARNING", "CRITICAL") or stat == "ACTIVE_ANOMALY":
                active_fdir_summaries.append(
                    FDIRFindingSummary(
                        rule_id=rf.get("rule_id", "UNKNOWN"),
                        severity=sev,
                        affected_subsystem=rf.get("affected_subsystem", "UNKNOWN"),
                        explanation=rf.get("explanation", ""),
                        triage_guidance=rf.get("triage_guidance", ""),
                    )
                )

        # 4. Identify unknown or insufficient data
        unknowns: List[str] = list(bounded_context.get("unknown_fields", []))
        insufficient = fdir_report.get("insufficient_data_findings", [])
        for item in insufficient:
            unknowns.append(
                f"{item.get('rule_id')}: {item.get('explanation')} "
                f"Missing: {item.get('input_evidence', {}).get('missing_fields')}"
            )

        client = self._get_client()

        # Offline / Mock Fallback if no valid live API key
        if not client:
            logger.info("Operating in deterministic offline CAPCOM advisory mode.")
            recommendations: List[AIRecommendation] = []
            if active_fdir_summaries:
                for af in active_fdir_summaries:
                    recommendations.append(
                        AIRecommendation(
                            recommendation=f"Resolve active anomaly on {af.affected_subsystem}.",
                            engineering_rationale=af.triage_guidance,
                            priority="HIGH" if af.severity == "CRITICAL" else "MEDIUM",
                        )
                    )
            else:
                recommendations.append(
                    AIRecommendation(
                        recommendation="Current spacecraft baseline is nominal.",
                        engineering_rationale=(
                            "All SWaP-C budgets and deterministic FDIR rules satisfied."
                        ),
                        priority="LOW",
                    )
                )

            return CAPCOMResponse(
                query=query,
                verified_source_facts=verified_facts,
                deterministic_calculations=calculations,
                ai_recommendations=recommendations,
                unknown_or_insufficient_data=unknowns,
                fdir_active_findings=active_fdir_summaries,
                safety_disclaimer=CAPCOM_SAFETY_DISCLAIMER,
                model_name=f"{self.model_name} (Deterministic Fallback Mode)",
                is_live_generation=False,
                generation_timestamp=now,
            )

        # Live Gemini Generation
        prompt = (
            "You are CAPCOM, an advisory mission assistant for Mission Forge.\n"
            "Analyze the provided spacecraft design state and user question.\n\n"
            f"USER QUERY: {query}\n\n"
            f"BOUNDED STATE CONTEXT:\n{json.dumps(bounded_context, default=str)}\n\n"
            "RULES:\n"
            "1. Ground all answers strictly in the supplied context.\n"
            "2. Never hallucinate NASA flight telemetry or command real spacecraft.\n"
            "3. Provide actionable engineering recommendations.\n"
            "4. Respond with valid JSON in this schema:\n"
            "{\n"
            '  "recommendations": [{"recommendation": "...", '
            '"engineering_rationale": "...", "priority": "HIGH|MEDIUM|LOW"}],\n'
            '  "unknown_data_observations": ["..."]\n'
            "}"
        )

        try:
            actual_model = self.model_name
            candidate_models = [self.model_name]
            for fallback in ("gemini-3.5-flash-lite", "gemini-3.8-flash"):
                if fallback not in candidate_models:
                    candidate_models.append(fallback)

            def _sync_call() -> tuple[str, str]:
                last_err = None
                for m in candidate_models:
                    try:
                        res = client.models.generate_content(
                            model=m,
                            contents=prompt,
                        )
                        text = getattr(res, "text", "") or ""
                        if text:
                            return text, m
                    except Exception as err:
                        logger.warning("Gemini model candidate '%s' failed: %s", m, err)
                        last_err = err
                if last_err:
                    raise last_err
                return "", self.model_name

            raw_response, actual_model = await asyncio.wait_for(
                asyncio.to_thread(_sync_call), timeout=self.timeout_seconds
            )

            # Robust JSON extraction from LLM response
            # (handles markdown fences, whitespace, and casing)
            cleaned_text = raw_response.strip()
            import re
            json_match = re.search(r"(\{.*\})", cleaned_text, re.DOTALL)
            if json_match:
                cleaned_text = json_match.group(1)
            else:
                if cleaned_text.lower().startswith("```json"):
                    cleaned_text = cleaned_text[7:]
                elif cleaned_text.startswith("```"):
                    cleaned_text = cleaned_text[3:]
                if cleaned_text.endswith("```"):
                    cleaned_text = cleaned_text[:-3]

            parsed_json = json.loads(cleaned_text.strip())
            ai_recs: List[AIRecommendation] = []
            for rec_dict in parsed_json.get("recommendations", []):
                ai_recs.append(
                    AIRecommendation(
                        recommendation=rec_dict.get("recommendation", ""),
                        engineering_rationale=rec_dict.get("engineering_rationale", ""),
                        priority=rec_dict.get("priority", "MEDIUM"),
                    )
                )

            for obs in parsed_json.get("unknown_data_observations", []):
                if obs not in unknowns:
                    unknowns.append(str(obs))

            return CAPCOMResponse(
                query=query,
                verified_source_facts=verified_facts,
                deterministic_calculations=calculations,
                ai_recommendations=ai_recs,
                unknown_or_insufficient_data=unknowns,
                fdir_active_findings=active_fdir_summaries,
                safety_disclaimer=CAPCOM_SAFETY_DISCLAIMER,
                model_name=actual_model,
                is_live_generation=True,
                generation_timestamp=now,
            )

        except Exception as exc:
            logger.warning("Live Gemini API call failed or timed out (%s); using fallback.", exc)
            return CAPCOMResponse(
                query=query,
                verified_source_facts=verified_facts,
                deterministic_calculations=calculations,
                ai_recommendations=[
                    AIRecommendation(
                        recommendation="Advisory fallback active.",
                        engineering_rationale=f"Model provider query failed: {exc}",
                        priority="LOW",
                    )
                ],
                unknown_or_insufficient_data=unknowns,
                fdir_active_findings=active_fdir_summaries,
                safety_disclaimer=CAPCOM_SAFETY_DISCLAIMER,
                model_name=f"{self.model_name} (Fallback)",
                is_live_generation=False,
                generation_timestamp=now,
            )


# Singleton CAPCOM Gemini Adapter
capcom_adapter = GeminiCapcomAdapter()
