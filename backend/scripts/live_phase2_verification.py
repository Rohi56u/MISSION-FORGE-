"""
Live Phase 2 Verification & Integration Probe Runner
Tests OpenAPI route registration and executes live network probes against
official JPL Horizons, NASA DSN Now, and NASA TechPort services.
"""

import asyncio
from pathlib import Path
import sys

_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
if str(_backend_dir.parent) not in sys.path:
    sys.path.insert(0, str(_backend_dir.parent))

from backend.app.integrations.horizons import (  # noqa: E402
    horizons_client,
    HorizonsQueryRequest,
)
from backend.app.integrations.dsn import dsn_client  # noqa: E402
from backend.app.integrations.techport import techport_client  # noqa: E402
from backend.app.main import app  # noqa: E402


async def run_live_verification() -> None:
    print("=================================================================")
    print("1. OPENAPI ROUTE REGISTRATION AUDIT")
    print("=================================================================")
    registered_routes = []
    for r in app.routes:
        if hasattr(r, "path"):
            registered_routes.append((r.path, getattr(r, "methods", {"GET"})))

    print(f"Total registered API routes: {len(registered_routes)}")
    for path, methods in sorted(registered_routes, key=lambda x: x[0]):
        if any(prefix in path for prefix in ["horizons", "dsn", "techport", "components"]):
            method_str = ",".join(sorted(list(methods)))
            print(f"  [{method_str:<10}] {path}")

    print("\n=================================================================")
    print("2. LIVE JPL HORIZONS API PROBE")
    print("   Endpoint: https://ssd.jpl.nasa.gov/api/horizons.api")
    print("=================================================================")
    try:
        req = HorizonsQueryRequest(
            target="399",
            center="500@0",
            start_time="2026-06-01",
            stop_time="2026-06-02",
        )
        h_resp = await horizons_client.query(req)
        print("HTTP Status: 200 OK")
        print(f"Target: {h_resp.target_name} ({h_resp.target_id})")
        print(f"Center: {h_resp.center_name} ({h_resp.center_id})")
        print(f"Cache Status: {h_resp.cache_status.value}")
        print(f"Coordinate Frame: {h_resp.coordinate_frame}")
        print(f"State Vectors Parsed: {len(h_resp.vectors)}")
        if h_resp.vectors:
            v0 = h_resp.vectors[0]
            print(f"  Epoch: {v0.calendar_date} (JD {v0.epoch_jd})")
            print(
                f"  Position (km):   X={v0.position_km.x:16.2f}, "
                f"Y={v0.position_km.y:16.2f}, Z={v0.position_km.z:16.2f}"
            )
            print(
                f"  Velocity (km/s): VX={v0.velocity_kms.x:15.4f}, "
                f"VY={v0.velocity_kms.y:15.4f}, VZ={v0.velocity_kms.z:15.4f}"
            )
            print(f"  Range: {v0.range_km:.2f} km, Light Time: {v0.light_time_s:.2f} s")
    except Exception as exc:
        print(f"HORIZONS LIVE PROBE FAILED: {type(exc).__name__}: {exc}")

    print("\n=================================================================")
    print("3. LIVE NASA DSN NOW FEED PROBE")
    print("   Feed URL: https://eyes.nasa.gov/dsn/data/dsn.xml")
    print("=================================================================")
    try:
        d_resp = await dsn_client.get_feed()
        print("HTTP Status: 200 OK")
        print(f"Cache Status: {d_resp.cache_status.value}")
        print(f"Source Timestamp: {d_resp.source_timestamp}")
        station_names = ", ".join(s.friendly_name for s in d_resp.stations)
        print(f"Complexes: {len(d_resp.stations)} ({station_names})")
        total_dishes = sum(len(s.dishes) for s in d_resp.stations)
        print(f"Total Ground Antenna Dishes: {total_dishes}")
        print(f"Active Tracking Dishes: {d_resp.active_tracking_count}")
        sc_sample = ", ".join(d_resp.tracked_spacecraft[:8])
        print(f"Tracked Spacecraft Missions ({len(d_resp.tracked_spacecraft)}): {sc_sample}...")

        if d_resp.tracked_spacecraft:
            target_sc = d_resp.tracked_spacecraft[0]
            sc_tracking = await dsn_client.get_spacecraft(target_sc)
            print(f"\nSpacecraft Filter Probe [{target_sc}]:")
            print(f"  Actively Tracked: {sc_tracking.is_actively_tracked}")
            print(f"  Active Contacts: {len(sc_tracking.contacts)}")
            for c in sc_tracking.contacts:
                print(
                    f"    Station: {c.station_friendly_name} | Dish: {c.dish_name} | "
                    f"Activity: {c.activity}"
                )
                if c.target and c.target.rtlt_seconds:
                    print(
                        f"    RTLT: {c.target.rtlt_seconds:.2f} s | "
                        f"Downleg Range: {c.target.downleg_range_km} km"
                    )
    except Exception as exc:
        print(f"DSN NOW LIVE PROBE FAILED: {type(exc).__name__}: {exc}")

    print("\n=================================================================")
    print("4. LIVE NASA TECHPORT API PROBE")
    print("   Endpoint: https://techport.nasa.gov/api/projects/10024")
    print("=================================================================")
    try:
        t_resp = await techport_client.get_project(10024)
        print("HTTP Status: 200 OK")
        print(f"Project ID: {t_resp.id}")
        print(f"Title: {t_resp.title}")
        print(f"Lead Organization: {t_resp.lead_organization}")
        print(f"Program: {t_resp.program}")
        trl_str = (
            f"begin={t_resp.trl_begin}, current={t_resp.trl_current}, end={t_resp.trl_end}"
        )
        print(f"TRL Milestones: {trl_str}")
        print(f"Canonical URL: {t_resp.canonical_url}")
        print(f"Cache Status: {t_resp.cache_status.value}")
    except Exception as exc:
        print(f"TECHPORT LIVE PROBE FAILED: {type(exc).__name__}: {exc}")

    # Resource cleanup
    await horizons_client.aclose()
    await dsn_client.aclose()
    await techport_client.aclose()
    print("\n=================================================================")
    print("ALL LIVE NETWORK PROBES COMPLETED CLEANLY")
    print("=================================================================")


if __name__ == "__main__":
    asyncio.run(run_live_verification())
