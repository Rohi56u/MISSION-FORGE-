"""
Comprehensive Integration Smoke Test for Mission Forge
Exercises all 6 core subsystems through Vite Frontend Proxy (port 3000) and Backend (port 8000).
"""

import os
import sys
import time
import json
import uuid
import httpx

# Bypass environment proxies for local loopback probes
os.environ["NO_PROXY"] = "127.0.0.1,localhost,*"
FRONTEND_PROXY_URL = "http://127.0.0.1:3000"
BACKEND_DIRECT_URL = "http://127.0.0.1:8000"

def run_all_smoke_tests():
    print("=" * 80)
    print("MISSION FORGE — COMPREHENSIVE INTEGRATION SMOKE TEST SUITE")
    print("=" * 80)
    
    results = {}
    
    with httpx.Client(base_url=FRONTEND_PROXY_URL, timeout=25.0, trust_env=False) as client:
        # -----------------------------------------------------------------
        # TEST 1: Health & Readiness through Vite Proxy
        # -----------------------------------------------------------------
        print("\n[1/6] Testing Health & Readiness through Frontend Proxy...")
        r_health = client.get("/health")
        r_ready = client.get("/ready")
        print(f"  /health: {r_health.status_code} -> {r_health.json()}")
        print(f"  /ready:  {r_ready.status_code} -> {r_ready.json()}")
        assert r_health.status_code == 200, "Health check failed"
        assert r_ready.status_code == 200, "Readiness check failed"
        results["1_health_readiness"] = "PASSED"

        # -----------------------------------------------------------------
        # TEST 2: Command Bridge Data Feeds
        # -----------------------------------------------------------------
        print("\n[2/6] Testing Command Bridge Endpoints...")
        r_missions = client.get("/api/v1/missions")
        missions = r_missions.json()
        print(f"  Missions: {r_missions.status_code} ({len(missions)} loaded)")
        assert r_missions.status_code == 200 and len(missions) > 0, "Failed to load missions"
        
        r_dsn = client.get("/api/v1/dsn/now")
        print(f"  DSN Now: {r_dsn.status_code} (Cache: {r_dsn.json().get('cache_status', 'N/A')})")
        
        r_techport = client.get("/api/v1/techport/projects?limit=5")
        print(f"  TechPort: {r_techport.status_code} (Projects: {len(r_techport.json().get('projects', []))})")
        results["2_command_bridge"] = "PASSED"

        # -----------------------------------------------------------------
        # TEST 3: Astrodynamics Lab (Lambert & Porkchop)
        # -----------------------------------------------------------------
        print("\n[3/6] Testing Astrodynamics Calculations...")
        lambert_body = {
            "r1_km": {"x": 149597870.7, "y": 0.0, "z": 0.0},
            "r2_km": {"x": 0.0, "y": 227939200.0, "z": 0.0},
            "time_of_flight_s": 200 * 86400.0,
            "prograde": True,
        }
        r_lambert = client.post("/api/v1/trajectory/lambert", json=lambert_body)
        print(f"  Lambert: {r_lambert.status_code} (Converged: {r_lambert.json().get('converged')}, Iterations: {r_lambert.json().get('iterations')})")
        assert r_lambert.status_code == 200 and r_lambert.json().get("converged") is True

        porkchop_body = {
            "origin_body": "399",
            "target_body": "499",
            "departure_start_date": "2026-10-01",
            "departure_end_date": "2026-10-15",
            "arrival_start_date": "2027-05-01",
            "arrival_end_date": "2027-05-15",
            "step_size_days": 5,
        }
        r_pk = client.post("/api/v1/trajectory/porkchop", json=porkchop_body)
        assert r_pk.status_code == 202
        pk_job_id = r_pk.json().get("job_id")
        print(f"  Porkchop Submitted: {r_pk.status_code} (Job ID: {pk_job_id})")

        # Test Astrodynamics Validation Failure
        r_pk_err = client.post("/api/v1/trajectory/porkchop", json={**porkchop_body, "target_body": "399"})
        print(f"  Porkchop Identical Bodies Validation: {r_pk_err.status_code} (Expected 422)")
        assert r_pk_err.status_code == 422

        # Poll porkchop job to completion
        for _ in range(10):
            r_poll = client.get(f"/api/v1/trajectory/porkchop/{pk_job_id}")
            pk_status = r_poll.json().get("status")
            if pk_status in ("COMPLETED", "FAILED"):
                print(f"  Porkchop Final State: {pk_status} (Progress: {r_poll.json().get('progress_percent')}%)")
                break
            time.sleep(1)
        results["3_astrodynamics"] = "PASSED"

        # -----------------------------------------------------------------
        # TEST 4: Spacecraft Designer & SWaP-C Physics Engine
        # -----------------------------------------------------------------
        print("\n[4/6] Testing Spacecraft Designer & SWaP-C Engine...")
        r_comp = client.get("/api/v1/components?limit=5")
        r_cat = client.get("/api/v1/components/catalog/status")
        print(f"  Catalog Status: {r_cat.status_code} (Components: {r_cat.json().get('total_components')})")
        
        swapc_payload = {
            "target": "MARS",
            "mission_class": "DISCOVERY",
            "distance_au": 1.52,
            "components": [
                {
                    "name": "NEXT-C Ion Thruster",
                    "subsystem": "PROPULSION",
                    "mass_kg": 58.2,
                    "power_draw_w": 3500.0,
                    "power_generation_w": 0.0,
                    "cost_usd": 12000000.0,
                    "isp_seconds": 4190.0,
                    "thrust_newtons": 0.236,
                    "maneuver_system": "PRIMARY",
                },
                {
                    "name": "UltraFlex Solar Array Wing",
                    "subsystem": "POWER",
                    "mass_kg": 42.0,
                    "power_draw_w": 0.0,
                    "power_generation_w": 4200.0,
                    "cost_usd": 5500000.0,
                    "solar_area_m2": 18.0,
                    "solar_efficiency": 0.32,
                },
            ],
            "propellant_mass_kg": 150.0,
            "required_delta_v_mps": 2400.0,
        }
        r_swapc = client.post("/api/v1/physics/swapc", json=swapc_payload)
        swapc_data = r_swapc.json()
        print(f"  SWaP-C Status: {r_swapc.status_code} (Verdict: {swapc_data.get('status')}, Feasible: {swapc_data.get('is_feasible')}, Wet Mass: {swapc_data.get('wet_mass_kg')} kg)")
        assert r_swapc.status_code == 200 and "dry_mass_kg" in swapc_data
        results["4_spacecraft_swapc"] = "PASSED"

        # -----------------------------------------------------------------
        # TEST 5: Auth & Concurrent Design Facility (CDF)
        # -----------------------------------------------------------------
        print("\n[5/6] Testing Authentication & CDF Collaboration...")
        unique_token = uuid.uuid4().hex[:6]
        user_email = f"lead-engineer-{unique_token}@nasa.gov"
        user_pass = "Engineering123!Secure"
        
        r_reg = client.post("/api/v1/auth/register", json={
            "email": user_email,
            "password": user_pass,
            "callsign": f"LEAD-{unique_token}",
            "full_name": "Chief Mission Architect",
            "role": "LEAD_SYSTEMS_ARCHITECT",
        })
        assert r_reg.status_code == 201
        token = r_reg.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        print(f"  Auth Register: {r_reg.status_code} (User: {user_email})")

        r_me = client.get("/api/v1/auth/me", headers=auth_headers)
        print(f"  Auth Me: {r_me.status_code} (Role: {r_me.json().get('role')})")
        assert r_me.status_code == 200

        target_mission_id = missions[0]["id"]
        r_room = client.post("/api/v1/cdf/rooms", json={
            "name": f"CDF Delta-V Trade Study {unique_token}",
            "mission_id": target_mission_id,
            "initial_role": "LEAD_SYSTEMS_ARCHITECT",
        }, headers=auth_headers)
        print(f"  CDF Room Creation: {r_room.status_code} (Room ID: {r_room.json().get('id')})")
        assert r_room.status_code == 201
        room_id = r_room.json()["id"]

        r_room_detail = client.get(f"/api/v1/cdf/rooms/{room_id}", headers=auth_headers)
        print(f"  CDF Room Detail: {r_room_detail.status_code} (Participants: {len(r_room_detail.json().get('participants', []))})")
        assert r_room_detail.status_code == 200
        results["5_auth_cdf"] = "PASSED"

        # -----------------------------------------------------------------
        # TEST 6: FDIR Operations, Grounded CAPCOM & Dossier Export
        # -----------------------------------------------------------------
        print("\n[6/6] Testing FDIR Rules, Grounded CAPCOM, & Mission Dossier Export...")
        r_rules = client.get("/api/v1/fdir/rules")
        print(f"  FDIR Registered Rules: {r_rules.status_code} ({len(r_rules.json())} rules)")
        assert r_rules.status_code == 200 and len(r_rules.json()) >= 5

        # Run simulated scenario
        r_scen = client.post("/api/v1/fdir/scenarios/POWER_DEFICIT")
        print(f"  FDIR Simulation Scenario (POWER_DEFICIT): {r_scen.status_code} (Overall: {r_scen.json().get('overall_severity')})")
        assert r_scen.status_code == 200

        # Query Grounded CAPCOM Assistant
        r_capcom = client.post("/api/v1/capcom/ask", json={
            "query": "What is our current power margin and what actions should we take for the power deficit?",
            "room_id": room_id,
        }, headers=auth_headers)
        capcom_res = r_capcom.json()
        recs = capcom_res.get("ai_recommendations", [])
        facts = capcom_res.get("verified_source_facts", [])
        print(f"  Grounded CAPCOM Query: {r_capcom.status_code} (Model: {capcom_res.get('model_name')}, Recommendations: {len(recs)}, Facts: {len(facts)})")
        assert r_capcom.status_code == 200 and (len(recs) > 0 or len(facts) > 0)

        # Generate Mission Dossier (BOTH formats: PDF and JSON)
        dossier_req = {
            "mission_id": target_mission_id,
            "room_id": room_id,
            "format": "BOTH",
            "title": f"Integration Smoke Test Dossier {unique_token}",
            "include_cdf_history": True,
            "include_fdir_audit": True,
            "include_capcom_summary": True,
        }
        r_dossier_job = client.post("/api/v1/dossiers/generate", json=dossier_req, headers=auth_headers)
        print(f"  Dossier Job Submitted: {r_dossier_job.status_code} (Job ID: {r_dossier_job.json().get('job_id')})")
        assert r_dossier_job.status_code == 202
        dossier_job_id = r_dossier_job.json().get("job_id")

        # Poll dossier generation job
        report_id = None
        for _ in range(12):
            time.sleep(1)
            r_djob = client.get(f"/api/v1/dossiers/jobs/{dossier_job_id}", headers=auth_headers)
            job_data = r_djob.json()
            if job_data.get("status") in ("COMPLETED", "FAILED"):
                print(f"  Dossier Job Status: {job_data.get('status')} (Progress: {job_data.get('progress_percent')}%)")
                report_id = job_data.get("report_id")
                break

        assert report_id is not None, "Dossier job did not complete with a report_id"
        print(f"  Dossier Report ID: {report_id}")

        # Download PDF and JSON artifacts
        r_pdf = client.get(f"/api/v1/dossiers/{report_id}/download?format=pdf", headers=auth_headers)
        r_json = client.get(f"/api/v1/dossiers/{report_id}/download?format=json", headers=auth_headers)
        print(f"  Dossier Download PDF: {r_pdf.status_code} ({len(r_pdf.content)} bytes, ETag SHA-256: {r_pdf.headers.get('etag')})")
        print(f"  Dossier Download JSON: {r_json.status_code} ({len(r_json.content)} bytes, ETag SHA-256: {r_json.headers.get('etag')})")
        assert r_pdf.status_code == 200 and len(r_pdf.content) > 1000
        assert r_json.status_code == 200 and len(r_json.content) > 500
        results["6_fdir_capcom_dossier"] = "PASSED"

    print("\n" + "=" * 80)
    print("ALL 6 INTEGRATION SMOKE TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 80)
    for test_name, status in results.items():
        print(f"  ✓ {test_name}: {status}")

if __name__ == "__main__":
    run_all_smoke_tests()
