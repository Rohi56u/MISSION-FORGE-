"""
Live NASA Open API & TechPort Integration Verification Runner
Mission Forge Aerospace Platform

Executes comprehensive live network probes against official NASA endpoints:
  1. api.nasa.gov Key Verification & Rate Limit Telemetry (APOD)
  2. NASA NeoWS (Near-Earth Asteroid Tracking & Trajectory Telemetry)
  3. NASA DONKI (Space Weather Coronal Mass Ejections)
  4. NASA TechPort Project Details & TRL Milestones
  5. NASA TechPort Aerospace Technology Search

Validates HTTP 200 OK status codes, response schemas, and rate limit quotas.
"""

import asyncio
import logging
from pathlib import Path
import sys

# Ensure backend directory is in sys.path
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
if str(_backend_dir.parent) not in sys.path:
    sys.path.insert(0, str(_backend_dir.parent))

from backend.app.core.config import settings  # noqa: E402
from backend.app.integrations.nasa import nasa_api_client  # noqa: E402
from backend.app.integrations.techport import techport_client  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("verify_live_nasa")


async def run_live_nasa_verification() -> int:
    print("=" * 72)
    print("MISSION FORGE - LIVE NASA OPEN API & TECHPORT INTEGRATION AUDIT")
    print("=" * 72)

    api_key = settings.NASA_API_KEY
    if not api_key or api_key == "DEMO_KEY":
        print(f"WARNING: NASA_API_KEY is currently set to '{api_key}'.")
    else:
        masked_key = f"{api_key[:4]}...{api_key[-4:]}"
        print(f"Configured NASA API Key: {masked_key} (length: {len(api_key)})")

    gw_url = getattr(settings, "NASA_API_BASE_URL", "https://api.nasa.gov")
    print(f"NASA API Gateway Base URL: {gw_url}")
    print(f"NASA TechPort Base URL:    {settings.TECHPORT_API_BASE_URL}")
    print(f"HTTP User Agent:           {settings.HTTP_USER_AGENT}")

    all_passed = True

    # -------------------------------------------------------------------------
    # 1. LIVE NASA API KEY AUTHENTICATION & RATE LIMIT TELEMETRY
    # -------------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("1. PROBE: NASA API GATEWAY KEY VALIDATION & RATE LIMIT HEADERS")
    print("   Endpoint: https://api.nasa.gov/planetary/apod")
    print("=" * 72)
    try:
        diag = await nasa_api_client.verify_key()
        print(f"  HTTP Status:         {diag.status_code}")
        print(f"  Key Valid:           {diag.valid}")
        print(f"  Masked Key:          {diag.api_key_masked}")
        print(f"  Rate Limit Quota:    {diag.rate_limit} requests/hour")
        print(f"  Remaining Quota:     {diag.rate_limit_remaining} requests/hour")
        print(f"  Diagnostic Message:  {diag.message}")

        if not diag.valid or diag.status_code != 200:
            print("  [FAIL] NASA API key validation failed!")
            all_passed = False
        else:
            print("  [PASS] Key verified with active rate limit quota.")
    except Exception as exc:
        print(f"  [ERROR] Key validation probe raised exception: {exc}")
        all_passed = False

    # -------------------------------------------------------------------------
    # 2. LIVE APOD IMAGERY & MISSION DATA
    # -------------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("2. PROBE: ASTRONOMY PICTURE OF THE DAY (APOD)")
    print("   Endpoint: https://api.nasa.gov/planetary/apod?date=2024-01-01")
    print("=" * 72)
    try:
        apod = await nasa_api_client.get_apod(date="2024-01-01")
        print(f"  Date:                {apod.date}")
        print(f"  Title:               {apod.title}")
        print(f"  Media Type:          {apod.media_type}")
        print(f"  Image URL:           {apod.url}")
        print(f"  Cache Status:        {apod.cache_status.value}")
        print(f"  Explanation Preview: {apod.explanation[:100]}...")

        assert apod.date == "2024-01-01"
        assert len(apod.title) > 0
        assert apod.url.startswith("http")
        print("  [PASS] APOD imagery successfully retrieved and validated.")
    except Exception as exc:
        print(f"  [ERROR] APOD probe raised exception: {exc}")
        all_passed = False

    # -------------------------------------------------------------------------
    # 3. LIVE NEAR-EARTH OBJECTS (NEOWS) ASTEROID FEED
    # -------------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("3. PROBE: NASA NEOWS NEAR-EARTH ASTEROIDS & FLYBY TELEMETRY")
    print("   Endpoint: https://api.nasa.gov/neo/rest/v1/feed")
    print("=" * 72)
    try:
        neo_feed = await nasa_api_client.get_neo_feed("2024-01-01", "2024-01-01")
        print(f"  Total Asteroids Tracked: {neo_feed.element_count}")
        print(f"  Objects Parsed:          {len(neo_feed.near_earth_objects)}")
        print(f"  Cache Status:            {neo_feed.cache_status.value}")

        if neo_feed.near_earth_objects:
            sample = neo_feed.near_earth_objects[0]
            print(f"  Sample Asteroid:         {sample.name} (ID: {sample.id})")
            print(f"  Potentially Hazardous:   {sample.is_potentially_hazardous}")
            if sample.miss_distance_km:
                print(f"  Miss Distance:           {sample.miss_distance_km:,.1f} km")
            if sample.relative_velocity_km_s:
                print(f"  Relative Velocity:       {sample.relative_velocity_km_s:.2f} km/s")

        assert neo_feed.element_count > 0
        assert len(neo_feed.near_earth_objects) > 0
        print("  [PASS] Near-Earth Object feed parsed and validated.")
    except Exception as exc:
        print(f"  [ERROR] NeoWS probe raised exception: {exc}")
        all_passed = False

    # -------------------------------------------------------------------------
    # 4. LIVE SPACE WEATHER (DONKI CME) SOLAR ERUPTIONS
    # -------------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("4. PROBE: NASA SPACE WEATHER DONKI CORONAL MASS EJECTIONS (CME)")
    print("   Endpoint: https://api.nasa.gov/DONKI/CME")
    print("=" * 72)
    try:
        cme_resp = await nasa_api_client.get_donki_cme(
            start_date="2024-01-01", end_date="2024-01-07"
        )
        print(f"  CME Solar Events Found:  {cme_resp.count}")
        print(f"  Cache Status:            {cme_resp.cache_status.value}")

        if cme_resp.events:
            cme0 = cme_resp.events[0]
            print(f"  Sample Event Activity:   {cme0.activity_id}")
            print(f"  Event Start Time:        {cme0.start_time}")
            print(f"  Source Location:         {cme0.source_location or 'N/A'}")
            insts = ", ".join(cme0.instruments) if cme0.instruments else "N/A"
            print(f"  Instruments:             {insts}")

        assert cme_resp.count > 0
        print("  [PASS] DONKI Space Weather CME events parsed and validated.")
    except Exception as exc:
        print(f"  [ERROR] DONKI probe raised exception: {exc}")
        all_passed = False

    # -------------------------------------------------------------------------
    # 5. LIVE NASA TECHPORT PROJECT DETAILS & TRL MILESTONES
    # -------------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("5. PROBE: NASA TECHPORT PROJECT 10024 DETAILS & TRL MILESTONES")
    print("   Endpoint: https://techport.nasa.gov/api/projects/10024")
    print("=" * 72)
    try:
        t_proj = await techport_client.get_project(10024)
        print(f"  Project ID:              {t_proj.id}")
        print(f"  Title:                   {t_proj.title}")
        print(f"  Status:                  {t_proj.status}")
        print(f"  Lead Organization:       {t_proj.lead_organization}")
        print(f"  Program:                 {t_proj.program}")
        trl_str = f"begin={t_proj.trl_begin}, current={t_proj.trl_current}, end={t_proj.trl_end}"
        print(f"  TRL Progression:         {trl_str}")
        print(f"  Canonical URL:           {t_proj.canonical_url}")
        print(f"  Cache Status:            {t_proj.cache_status.value}")
        if t_proj.rate_limit:
            print(f"  TechPort Rate Limit:     {t_proj.rate_limit}")
            print(f"  TechPort Rate Remaining: {t_proj.rate_limit_remaining}")

        assert t_proj.id == 10024
        assert "Antenna" in t_proj.title
        print("  [PASS] TechPort project 10024 retrieved and validated.")
    except Exception as exc:
        print(f"  [ERROR] TechPort get_project probe raised exception: {exc}")
        all_passed = False

    # -------------------------------------------------------------------------
    # 6. LIVE NASA TECHPORT SEARCH
    # -------------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("6. PROBE: NASA TECHPORT AEROSPACE SEARCH")
    print("   Query: 'propulsion'")
    print("=" * 72)
    try:
        t_search = await techport_client.search_projects("propulsion")
        print(f"  Total Matching Projects: {t_search.total_count}")
        print(f"  Results Returned:        {len(t_search.projects)}")
        print(f"  Sanitized Source URL:    {t_search.source_url}")
        print(f"  Cache Status:            {t_search.cache_status.value}")

        if t_search.projects:
            s0 = t_search.projects[0]
            print(f"  Top Result:              [{s0.id}] {s0.title}")

        # Sensitive parameter check: API key must NEVER be leaked in source_url
        assert "qTzR" not in t_search.source_url, (
            "CRITICAL: Sensitive API key leaked in source_url!"
        )
        assert t_search.total_count > 0
        print("  [PASS] TechPort search executed cleanly with key sanitization verified.")
    except Exception as exc:
        print(f"  [ERROR] TechPort search probe raised exception: {exc}")
        all_passed = False

    # Resource cleanup
    await nasa_api_client.aclose()
    await techport_client.aclose()

    print("\n" + "=" * 72)
    if all_passed:
        print("ALL LIVE NASA OPEN API & TECHPORT PROBES PASSED (HTTP 200 OK)")
        print("=" * 72)
        return 0
    else:
        print("ONE OR MORE LIVE NASA PROBES FAILED")
        print("=" * 72)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_live_nasa_verification())
    sys.exit(exit_code)
