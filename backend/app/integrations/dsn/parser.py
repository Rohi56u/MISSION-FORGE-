"""
Robust XML Parser for NASA DSN Now Feed
Extracts station complexes, dish antenna pointing, carrier signals, and space link metrics.
"""

from datetime import datetime, timezone
from typing import List, Optional, Tuple
import xml.etree.ElementTree as ET

from backend.app.core.cache import CacheStatus
from backend.app.integrations.dsn.exceptions import DSNParseError
from backend.app.integrations.dsn.models import (
    DSNDish,
    DSNFeedResponse,
    DSNSignal,
    DSNStation,
    DSNTarget,
)


def _safe_float(
    val: Optional[str], default_sentinels: Tuple[float, ...] = (-1.0,)
) -> Optional[float]:
    """Safely converts string to float, returning None for empty strings or sentinel values."""
    if val is None:
        return None
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ("none", "null", "undefined", "nan"):
        return None
    try:
        f = float(val_str)
        if f in default_sentinels:
            return None
        return f
    except ValueError:
        return None


def _safe_bool(val: Optional[str]) -> bool:
    """Converts string boolean representation to bool."""
    if not val:
        return False
    return str(val).strip().lower() in ("true", "1", "yes")


def parse_dsn_xml(
    xml_content: str,
    source_url: str,
    cache_status: CacheStatus = CacheStatus.LIVE,
    retrieved_at: Optional[datetime] = None,
) -> DSNFeedResponse:
    """
    Parses live DSN Now XML text into structured, typed DSNFeedResponse.
    Raises DSNParseError on malformed or empty feed.
    """
    if not xml_content or not xml_content.strip():
        raise DSNParseError("Empty or blank DSN Now XML feed content.")

    try:
        root = ET.fromstring(xml_content.strip())
    except ET.ParseError as err:
        raise DSNParseError(f"Malformed XML in DSN Now feed: {err}") from err

    if root.tag != "dsn":
        raise DSNParseError(f"Unexpected root tag '{root.tag}' in DSN feed; expected 'dsn'.")

    stations: List[DSNStation] = []
    current_station: Optional[DSNStation] = None
    feed_timestamp_ms: Optional[int] = None
    tracked_spacecraft_set: set[str] = set()
    active_dishes_count = 0

    for child in root:
        if child.tag == "station":
            name = child.attrib.get("name", "unknown")
            friendly_name = child.attrib.get("friendlyName", name.capitalize())
            time_utc_str = child.attrib.get("timeUTC", "0")
            time_zone_offset_str = child.attrib.get("timeZoneOffset", "0.0")

            time_utc = int(_safe_float(time_utc_str) or 0)
            tz_offset = _safe_float(time_zone_offset_str) or 0.0

            current_station = DSNStation(
                name=name,
                friendly_name=friendly_name,
                time_utc=time_utc,
                time_zone_offset_ms=tz_offset,
                dishes=[],
            )
            stations.append(current_station)

        elif child.tag == "dish":
            if current_station is None:
                continue

            dish_name = child.attrib.get("name", "Unknown-Dish")
            azimuth = _safe_float(child.attrib.get("azimuthAngle"))
            elevation = _safe_float(child.attrib.get("elevationAngle"))
            wind_speed = _safe_float(child.attrib.get("windSpeed"))
            is_mspa = _safe_bool(child.attrib.get("isMSPA"))
            is_array = _safe_bool(child.attrib.get("isArray"))
            is_ddor = _safe_bool(child.attrib.get("isDDOR"))
            activity = child.attrib.get("activity")

            targets: List[DSNTarget] = []
            up_signals: List[DSNSignal] = []
            down_signals: List[DSNSignal] = []
            dish_has_active_signal = False

            for elem in child:
                if elem.tag == "target":
                    tgt_name = elem.attrib.get("name", "UNKNOWN")
                    tgt_id = elem.attrib.get("id")
                    upleg = _safe_float(
                        elem.attrib.get("uplegRange"), default_sentinels=(-1.0, 0.0)
                    )
                    downleg = _safe_float(
                        elem.attrib.get("downlegRange"), default_sentinels=(-1.0, 0.0)
                    )
                    rtlt = _safe_float(elem.attrib.get("rtlt"), default_sentinels=(-1.0,))

                    targets.append(
                        DSNTarget(
                            name=tgt_name,
                            target_id=tgt_id,
                            upleg_range_km=upleg,
                            downleg_range_km=downleg,
                            rtlt_seconds=rtlt,
                        )
                    )
                    if tgt_name and tgt_name != "DSN" and tgt_name != "none":
                        tracked_spacecraft_set.add(tgt_name)

                elif elem.tag == "upSignal":
                    is_active = _safe_bool(elem.attrib.get("active"))
                    if is_active:
                        dish_has_active_signal = True

                    sc = elem.attrib.get("spacecraft")
                    if sc and sc != "none":
                        tracked_spacecraft_set.add(sc)

                    up_signals.append(
                        DSNSignal(
                            active=is_active,
                            signal_type=elem.attrib.get("signalType"),
                            data_rate_bps=_safe_float(elem.attrib.get("dataRate")),
                            frequency_hz=_safe_float(elem.attrib.get("frequency")),
                            band=elem.attrib.get("band"),
                            power_dbm_or_kw=_safe_float(elem.attrib.get("power")),
                            spacecraft=sc,
                            spacecraft_id=elem.attrib.get("spacecraftID"),
                        )
                    )

                elif elem.tag == "downSignal":
                    is_active = _safe_bool(elem.attrib.get("active"))
                    if is_active:
                        dish_has_active_signal = True

                    sc = elem.attrib.get("spacecraft")
                    if sc and sc != "none":
                        tracked_spacecraft_set.add(sc)

                    down_signals.append(
                        DSNSignal(
                            active=is_active,
                            signal_type=elem.attrib.get("signalType"),
                            data_rate_bps=_safe_float(elem.attrib.get("dataRate")),
                            frequency_hz=_safe_float(elem.attrib.get("frequency")),
                            band=elem.attrib.get("band"),
                            power_dbm_or_kw=_safe_float(elem.attrib.get("power")),
                            spacecraft=sc,
                            spacecraft_id=elem.attrib.get("spacecraftID"),
                        )
                    )

            if dish_has_active_signal or (targets and any(t.name != "DSN" for t in targets)):
                active_dishes_count += 1

            dish = DSNDish(
                name=dish_name,
                azimuth_deg=azimuth,
                elevation_deg=elevation,
                wind_speed_kmh=wind_speed,
                is_mspa=is_mspa,
                is_array=is_array,
                is_ddor=is_ddor,
                activity=activity,
                targets=targets,
                up_signals=up_signals,
                down_signals=down_signals,
            )
            current_station.dishes.append(dish)

        elif child.tag == "timestamp":
            ts_val = _safe_float(child.text)
            if ts_val is not None:
                feed_timestamp_ms = int(ts_val)

    source_ts: Optional[datetime] = None
    if feed_timestamp_ms:
        source_ts = datetime.fromtimestamp(feed_timestamp_ms / 1000.0, tz=timezone.utc)

    return DSNFeedResponse(
        stations=stations,
        timestamp_ms=feed_timestamp_ms,
        retrieved_at=retrieved_at or datetime.now(timezone.utc),
        source_timestamp=source_ts,
        cache_status=cache_status,
        source_url=source_url,
        active_tracking_count=active_dishes_count,
        tracked_spacecraft=sorted(list(tracked_spacecraft_set)),
    )
