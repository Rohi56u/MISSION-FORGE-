"""
Robust Parser for NASA/JPL Horizons Ephemeris Responses
Extracts Cartesian state vectors, orbital elements, and target ambiguities.
"""

from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional

from backend.app.core.cache import CacheStatus
from backend.app.integrations.horizons.exceptions import (
    HorizonsAmbiguousTargetError,
    HorizonsParseError,
    HorizonsTargetNotFoundError,
    HorizonsValidationError,
)
from backend.app.integrations.horizons.models import (
    HorizonsElementEntry,
    HorizonsEphemType,
    HorizonsQueryResponse,
    HorizonsTargetCandidate,
    HorizonsVectorEntry,
    Vector3D,
)

# Compiled regex patterns for vectors
_RE_FLOAT = r"[+-]?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?"
_RE_EPOCH_LINE = re.compile(
    r"^\s*(\d+\.\d+)\s*=\s*(?:A\.D\.\s*)?([0-9A-Za-z\-: \.]+?)\s*$", re.MULTILINE
)
_RE_VEC_XYZ = re.compile(
    rf"X\s*=\s*({_RE_FLOAT})\s+Y\s*=\s*({_RE_FLOAT})\s+Z\s*=\s*({_RE_FLOAT})"
)
_RE_VEC_VXYZ = re.compile(
    rf"VX\s*=\s*({_RE_FLOAT})\s+VY\s*=\s*({_RE_FLOAT})\s+VZ\s*=\s*({_RE_FLOAT})"
)
_RE_VEC_LTRGRR = re.compile(
    rf"LT\s*=\s*({_RE_FLOAT})\s+RG\s*=\s*({_RE_FLOAT})\s+RR\s*=\s*({_RE_FLOAT})"
)

# Compiled regex patterns for elements
_RE_ELEM_EC_QR_IN = re.compile(
    rf"EC\s*=\s*({_RE_FLOAT})\s+QR\s*=\s*({_RE_FLOAT})\s+IN\s*=\s*({_RE_FLOAT})"
)
_RE_ELEM_OM_W = re.compile(
    rf"OM\s*=\s*({_RE_FLOAT})\s+W\s*=\s*({_RE_FLOAT})"
)
_RE_ELEM_MA_TA = re.compile(
    rf"MA\s*=\s*({_RE_FLOAT})\s+TA\s*=\s*({_RE_FLOAT})"
)
_RE_ELEM_A = re.compile(rf"\bA\s*=\s*({_RE_FLOAT})")
_RE_ELEM_AD = re.compile(rf"\bAD\s*=\s*({_RE_FLOAT})")
_RE_ELEM_PR = re.compile(rf"\bPR\s*=\s*({_RE_FLOAT})")

# Header metadata patterns
_RE_TARGET_NAME = re.compile(
    r"Target body name:\s*([^\n\r{]+?)(?:\s*\{[^\}]*\})?\s*$", re.MULTILINE
)
_RE_CENTER_NAME = re.compile(
    r"Center body name:\s*([^\n\r{]+?)(?:\s*\{[^\}]*\})?\s*$", re.MULTILINE
)
_RE_REF_FRAME = re.compile(
    r"Reference frame\s*:\s*([^\n\r]+?)\s*$", re.MULTILINE
)


def parse_ambiguous_targets(text: str) -> List[HorizonsTargetCandidate]:
    """
    Parses ambiguous target listings from Horizons output.
    Example table:
      ID# Name Designation IAU/aliases/other
      ------- ---------------------------------- ----------- -------------------
            4 Mars Barycenter
          499 Mars
           -3 Mars Orbiter Mission (spacecraft) 2013-060A MOM Mangalyaan
    """
    candidates: List[HorizonsTargetCandidate] = []
    lines = text.splitlines()
    in_table = False

    for line in lines:
        stripped = line.strip()
        if "-------" in stripped:
            in_table = True
            continue
        if in_table:
            if not stripped or stripped.startswith("***") or stripped.startswith("To SELECT"):
                break
            parts = [p.strip() for p in re.split(r"\s{2,}", stripped) if p.strip()]
            if parts:
                tid = parts[0]
                name = parts[1] if len(parts) > 1 else tid
                designation = parts[2] if len(parts) > 2 else None
                aliases = parts[3] if len(parts) > 3 else None
                candidates.append(
                    HorizonsTargetCandidate(
                        target_id=tid,
                        name=name,
                        designation=designation,
                        aliases=aliases,
                    )
                )
    return candidates


def parse_horizons_response(
    raw_json: Dict[str, Any],
    query_params: Dict[str, Any],
    source_url: str,
    cache_status: CacheStatus = CacheStatus.LIVE,
    retrieved_at: Optional[datetime] = None,
) -> HorizonsQueryResponse:
    """
    Parses raw Horizons API JSON response into a normalized HorizonsQueryResponse.
    Raises specific, actionable exceptions on validation, ambiguity, or missing data.
    """
    if "error" in raw_json and raw_json["error"]:
        err_msg = str(raw_json["error"])
        raise HorizonsValidationError(f"JPL Horizons parameter error: {err_msg}")

    result_text = raw_json.get("result", "")
    if not result_text:
        raise HorizonsParseError("Empty or missing 'result' field in Horizons response.")

    # 1. Check for missing command / execution error
    if "Missing COMMAND specification" in result_text or "cannot proceed" in result_text:
        raise HorizonsValidationError(f"JPL Horizons query error: {result_text.strip()[:300]}")

    # 2. Check for target not found
    if (
        "No matches found" in result_text
        or "Matching small-bodies: \n    No matches found" in result_text
    ):
        target_name = query_params.get("COMMAND") or query_params.get("target") or "unknown"
        raise HorizonsTargetNotFoundError(
            f"No matching celestial body or spacecraft found for target '{target_name}'."
        )

    # 3. Check for ambiguous target matches
    if "Multiple major-bodies match" in result_text or "Multiple small-bodies match" in result_text:
        candidates = parse_ambiguous_targets(result_text)
        target_name = query_params.get("COMMAND") or query_params.get("target") or "unknown"
        raise HorizonsAmbiguousTargetError(
            f"Target identifier '{target_name}' is ambiguous. "
            f"Found {len(candidates)} candidate bodies.",
            candidates=candidates,
        )

    # 4. Check for Start of Ephemeris ($$SOE) and End of Ephemeris ($$EOE)
    soe_idx = result_text.find("$$SOE")
    eoe_idx = result_text.find("$$EOE")
    if soe_idx == -1 or eoe_idx == -1 or eoe_idx <= soe_idx:
        raise HorizonsParseError(
            "Horizons response does not contain valid ephemeris block delimited by $$SOE and $$EOE."
        )

    after_soe = result_text.find("\n", soe_idx)
    if after_soe == -1 or after_soe >= eoe_idx:
        raise HorizonsParseError("Malformed ephemeris data block after $$SOE.")

    header_text = result_text[:soe_idx]
    data_text = result_text[after_soe + 1 : eoe_idx].strip()

    # Extract metadata from header
    target_match = _RE_TARGET_NAME.search(header_text)
    if target_match:
        target_name_raw = target_match.group(1).strip()
    else:
        target_name_raw = str(query_params.get("target", "unknown"))

    center_match = _RE_CENTER_NAME.search(header_text)
    if center_match:
        center_name_raw = center_match.group(1).strip()
    else:
        center_name_raw = str(query_params.get("center", "unknown"))

    ref_frame_match = _RE_REF_FRAME.search(header_text)
    coord_frame = ref_frame_match.group(1).strip() if ref_frame_match else "ICRF / J2000"

    raw_ephem = query_params.get("ephem_type", "VECTORS")
    if isinstance(raw_ephem, HorizonsEphemType):
        ephem_type = raw_ephem
    else:
        ephem_str = raw_ephem.value if hasattr(raw_ephem, "value") else str(raw_ephem)
        if "." in ephem_str:
            ephem_str = ephem_str.split(".")[-1]
        ephem_type = HorizonsEphemType(ephem_str.upper())

    vectors: List[HorizonsVectorEntry] = []
    elements: List[HorizonsElementEntry] = []

    if ephem_type == HorizonsEphemType.VECTORS:
        vectors = _parse_vector_block(data_text)
    elif ephem_type == HorizonsEphemType.ELEMENTS:
        elements = _parse_elements_block(data_text)

    raw_ts = query_params.get("time_scale", "TDB")
    if hasattr(raw_ts, "value"):
        clean_ts = str(raw_ts.value)
    elif "." in str(raw_ts):
        clean_ts = str(raw_ts).split(".")[-1]
    else:
        clean_ts = str(raw_ts)
    clean_ts = clean_ts.upper()

    units = {
        "position": "kilometers (km)",
        "velocity": "kilometers per second (km/s)",
        "angles": "degrees",
        "time": f"{clean_ts} Julian Date / ISO calendar",
    }

    return HorizonsQueryResponse(
        target_id=str(query_params.get("target", target_name_raw)),
        target_name=target_name_raw,
        center_id=str(query_params.get("center", center_name_raw)),
        center_name=center_name_raw,
        ephem_type=ephem_type,
        coordinate_frame=coord_frame,
        origin_center=center_name_raw,
        time_scale=clean_ts,
        units=units,
        vectors=vectors,
        elements=elements,
        raw_signature=raw_json.get("signature", {}),
        query_params=query_params,
        source_url=source_url,
        retrieved_at=retrieved_at or datetime.now(timezone.utc),
        cache_status=cache_status,
    )


def _parse_vector_block(data_text: str) -> List[HorizonsVectorEntry]:
    """Parses $$SOE ... $$EOE vector rows."""
    vectors: List[HorizonsVectorEntry] = []
    chunks = data_text.splitlines()

    i = 0
    while i < len(chunks):
        line = chunks[i].strip()
        if not line:
            i += 1
            continue

        epoch_match = _RE_EPOCH_LINE.match(line)
        if epoch_match and i + 2 < len(chunks):
            epoch_jd = float(epoch_match.group(1))
            cal_date = epoch_match.group(2).strip()

            xyz_line = chunks[i + 1].strip()
            vxyz_line = chunks[i + 2].strip()

            xyz_match = _RE_VEC_XYZ.search(xyz_line)
            vxyz_match = _RE_VEC_VXYZ.search(vxyz_line)

            if xyz_match and vxyz_match:
                pos = Vector3D(
                    x=float(xyz_match.group(1)),
                    y=float(xyz_match.group(2)),
                    z=float(xyz_match.group(3)),
                )
                vel = Vector3D(
                    x=float(vxyz_match.group(1)),
                    y=float(vxyz_match.group(2)),
                    z=float(vxyz_match.group(3)),
                )

                lt: Optional[float] = None
                rg: Optional[float] = None
                rr: Optional[float] = None

                # Optional fourth line with LT, RG, RR
                if i + 3 < len(chunks):
                    ltrgrr_line = chunks[i + 3].strip()
                    ltrgrr_match = _RE_VEC_LTRGRR.search(ltrgrr_line)
                    if ltrgrr_match:
                        lt = float(ltrgrr_match.group(1))
                        rg = float(ltrgrr_match.group(2))
                        rr = float(ltrgrr_match.group(3))
                        i += 1

                vectors.append(
                    HorizonsVectorEntry(
                        epoch_jd=epoch_jd,
                        calendar_date=cal_date,
                        position_km=pos,
                        velocity_kms=vel,
                        light_time_s=lt,
                        range_km=rg,
                        range_rate_kms=rr,
                    )
                )
                i += 3
                continue
        i += 1

    return vectors


def _parse_elements_block(data_text: str) -> List[HorizonsElementEntry]:
    """Parses $$SOE ... $$EOE osculating orbital elements rows."""
    elements: List[HorizonsElementEntry] = []
    chunks = data_text.splitlines()

    i = 0
    while i < len(chunks):
        line = chunks[i].strip()
        if not line:
            i += 1
            continue

        epoch_match = _RE_EPOCH_LINE.match(line)
        if epoch_match and i + 4 < len(chunks):
            epoch_jd = float(epoch_match.group(1))
            cal_date = epoch_match.group(2).strip()

            line1 = chunks[i + 1]
            line2 = chunks[i + 2]
            line3 = chunks[i + 3]
            line4 = chunks[i + 4]

            m1 = _RE_ELEM_EC_QR_IN.search(line1)
            m2 = _RE_ELEM_OM_W.search(line2)
            m3 = _RE_ELEM_MA_TA.search(line3)

            if m1 and m2 and m3:
                eccentricity = float(m1.group(1))
                periapsis_dist_km = float(m1.group(2))
                inclination_deg = float(m1.group(3))

                om_deg = float(m2.group(1))
                w_deg = float(m2.group(2))

                ma_deg = float(m3.group(1))
                ta_deg = float(m3.group(2))

                m_a = _RE_ELEM_A.search(line4)
                m_ad = _RE_ELEM_AD.search(line4)
                m_pr = _RE_ELEM_PR.search(line4)

                a_km = float(m_a.group(1)) if m_a else None
                ad_km = float(m_ad.group(1)) if m_ad else None
                pr_s = float(m_pr.group(1)) if m_pr else None

                elements.append(
                    HorizonsElementEntry(
                        epoch_jd=epoch_jd,
                        calendar_date=cal_date,
                        eccentricity=eccentricity,
                        periapsis_dist_km=periapsis_dist_km,
                        inclination_deg=inclination_deg,
                        longitude_asc_node_deg=om_deg,
                        arg_perifocus_deg=w_deg,
                        mean_anomaly_deg=ma_deg,
                        true_anomaly_deg=ta_deg,
                        semi_major_axis_km=a_km,
                        apoapsis_dist_km=ad_km,
                        orbital_period_s=pr_s,
                    )
                )
                i += 5
                continue
        i += 1

    return elements
