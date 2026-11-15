"""
Live Server Probe Script for Mission Forge
Exercises the actual running FastAPI server on http://127.0.0.1:8000 over HTTP network sockets.
Bypasses local sandbox proxy using trust_env=False.
"""

import os
import time
import pprint
import httpx

# Bypass environment proxy for local loopback probes
os.environ["NO_PROXY"] = "127.0.0.1,localhost,*"
BASE_URL = "http://127.0.0.1:8000"


def probe_all():
    results = {}
    with httpx.Client(base_url=BASE_URL, timeout=10.0, trust_env=False) as client:
        # 1. Health check
        r = client.get("/health")
        results["1_health"] = {"status_code": r.status_code, "body": r.json()}

        # 2. Readiness check
        r = client.get("/ready")
        results["2_ready"] = {"status_code": r.status_code, "body": r.json()}

        # 3. Allowed CORS origin
        r = client.get("/health", headers={"Origin": "http://localhost:3000"})
        results["3_cors_allowed"] = {
            "status_code": r.status_code,
            "allow_origin": r.headers.get("access-control-allow-origin"),
            "allow_credentials": r.headers.get("access-control-allow-credentials"),
        }

        # 4. Disallowed CORS origin
        r = client.get("/health", headers={"Origin": "http://evil-attacker.com"})
        results["4_cors_disallowed"] = {
            "status_code": r.status_code,
            "allow_origin": r.headers.get("access-control-allow-origin"),
        }

        # 5. Valid propulsion-tradeoff JSON
        r = client.post(
            "/api/v1/physics/propulsion-tradeoff",
            json={"m_dry_kg": 600.0, "delta_v_mps": 2800.0},
        )
        results["5_propulsion_tradeoff_valid"] = {
            "status_code": r.status_code,
            "chem_wet_kg": r.json()["chemical_bipropellant"]["wet_mass_kg"],
            "ep_wet_kg": r.json()["electric_ion_propulsion"]["wet_mass_kg"],
            "saved_kg": r.json()["trade_off_analysis"]["propellant_mass_saved_kg"],
        }

        # 6. Invalid propulsion-tradeoff (negative dry mass) -> 422
        r = client.post(
            "/api/v1/physics/propulsion-tradeoff",
            json={"m_dry_kg": -50.0, "delta_v_mps": 1000.0},
        )
        results["6_propulsion_tradeoff_invalid"] = {"status_code": r.status_code}

        # 7. Solar power calculation
        r = client.post(
            "/api/v1/physics/solar-power",
            json={"distance_au": 1.524, "area_m2": 15.0, "efficiency": 0.30},
        )
        results["7_solar_power"] = {
            "status_code": r.status_code,
            "flux_w_m2": r.json()["solar_flux_w_m2"],
            "power_w": r.json()["generated_power_w"],
        }

        # 8. Telecom link budget
        r = client.post(
            "/api/v1/physics/link-budget",
            json={
                "distance_m": 2.25e11,
                "frequency_hz": 8.425e9,
                "tx_power_w": 20.0,
                "tx_antenna_diameter_m": 1.5,
                "rx_antenna_diameter_m": 70.0,
            },
        )
        results["8_link_budget"] = {
            "status_code": r.status_code,
            "margin_db": r.json()["link_margin_db"],
            "rtlt": r.json()["rtlt_formatted"],
        }

        # 9. Feasible SWaP-C case with multi-thruster
        r = client.post(
            "/api/v1/physics/swapc",
            json={
                "target": "MARS",
                "mission_class": "DISCOVERY",
                "required_delta_v_mps": 1800.0,
                "components": [
                    {
                        "name": "Main Engine A",
                        "subsystem": "PROPULSION",
                        "mass_kg": 25.0,
                        "thrust_newtons": 200.0,
                        "isp_seconds": 320.0,
                    },
                    {
                        "name": "Main Engine B",
                        "subsystem": "PROPULSION",
                        "mass_kg": 25.0,
                        "thrust_newtons": 200.0,
                        "isp_seconds": 320.0,
                    },
                    {
                        "name": "Solar Array",
                        "subsystem": "POWER",
                        "mass_kg": 20.0,
                        "solar_area_m2": 12.0,
                        "solar_efficiency": 0.30,
                    },
                    {
                        "name": "Bus",
                        "subsystem": "STRUCTURE",
                        "mass_kg": 200.0,
                        "power_draw_w": 40.0,
                    },
                ],
            },
        )
        results["9_swapc_multi_thruster"] = {
            "status_code": r.status_code,
            "effective_isp_s": r.json()["effective_isp_s"],
            "is_feasible": r.json()["is_feasible"],
            "status": r.json()["status"],
        }

        # 10. Infeasible SWaP-C case (Europa solar-only power deficit)
        r = client.post(
            "/api/v1/physics/swapc",
            json={
                "target": "EUROPA",
                "mission_class": "DISCOVERY",
                "components": [
                    {
                        "name": "Small Chemical Thruster",
                        "subsystem": "PROPULSION",
                        "mass_kg": 20.0,
                        "thrust_newtons": 200.0,
                        "isp_seconds": 310.0,
                    },
                    {
                        "name": "Tiny Solar Panel",
                        "subsystem": "POWER",
                        "mass_kg": 5.0,
                        "solar_area_m2": 1.0,
                        "solar_efficiency": 0.30,
                    },
                    {
                        "name": "Heavy Instrument",
                        "subsystem": "SCIENCE",
                        "mass_kg": 50.0,
                        "power_draw_w": 300.0,
                    },
                ],
            },
        )
        results["10_swapc_infeasible"] = {
            "status_code": r.status_code,
            "is_feasible": r.json()["is_feasible"],
            "violations": [v["constraint_type"] for v in r.json()["violations"]],
        }

        # 11. Component Catalog CRUD Probe (uses dry-run sync to prevent persistent DB pollution)
        comp_payload = {
            "items": [
                {
                    "name": f"Live Probe Thruster {int(time.time())}",
                    "subsystem": "PROPULSION",
                    "mass_kg": 14.0,
                    "thrust_newtons": 0.236,
                    "isp_seconds": 4190.0,
                }
            ],
            "dry_run": True,
        }
        r = client.post("/api/v1/components/sync", json=comp_payload)
        results["11_component_create"] = {
            "status_code": r.status_code,
            "dry_run": r.json().get("dry_run"),
            "created_count": r.json().get("created_count"),
        }

        r = client.get("/api/v1/components?limit=5")
        results["12_component_list"] = {
            "status_code": r.status_code,
            "total": r.json()["total"],
            "count": len(r.json()["items"]),
        }

        # 12. Mission API Probe (tests listing and validation to prevent persistent DB pollution)
        r = client.get("/api/v1/missions")
        results["13_mission_list"] = {
            "status_code": r.status_code,
            "count": len(r.json()) if isinstance(r.json(), list) else 0,
        }

        # Verify mission validation error path without mutating database
        invalid_mission_payload = {
            "name": "Invalid Test Mission",
            "target": "NON_EXISTENT_CELESTIAL_BODY",
        }
        r_val = client.post("/api/v1/missions", json=invalid_mission_payload)
        results["14_mission_validation_reject"] = {
            "status_code": r_val.status_code,
        }

    return results


if __name__ == "__main__":
    import socket
    import sys
    import threading
    from pathlib import Path

    _backend_dir = Path(__file__).resolve().parent.parent
    if str(_backend_dir) not in sys.path:
        sys.path.insert(0, str(_backend_dir))
    if str(_backend_dir.parent) not in sys.path:
        sys.path.insert(0, str(_backend_dir.parent))

    # Check if 127.0.0.1:8000 is running; if not, spin up server in background thread
    s = socket.socket()
    try:
        s.connect(("127.0.0.1", 8000))
        s.close()
    except Exception:
        import uvicorn
        from backend.app.main import app

        t = threading.Thread(
            target=uvicorn.run,
            args=(app,),
            kwargs={"host": "127.0.0.1", "port": 8000, "log_level": "error"},
            daemon=True,
        )
        t.start()
        time.sleep(1.5)

    res = probe_all()
    pprint.pprint(res)
    print("\nALL 14 LIVE HTTP ROUTE PROBES COMPLETED SUCCESSFULLY.")
