import socket
import sys
import threading
import time
from pathlib import Path

_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
if str(_backend_dir.parent) not in sys.path:
    sys.path.insert(0, str(_backend_dir.parent))

import requests  # noqa: E402
import uvicorn  # noqa: E402
from backend.app.main import app  # noqa: E402


def test_live_server():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    t = threading.Thread(
        target=uvicorn.run,
        args=(app,),
        kwargs={"host": "127.0.0.1", "port": port, "log_level": "error"},
        daemon=True,
    )
    t.start()

    # Bypass environment proxy for local loopback probe
    session = requests.Session()
    session.trust_env = False

    # Poll until up
    for _ in range(10):
        try:
            res = session.get(f"http://127.0.0.1:{port}/health", timeout=1.0)
            if res.status_code == 200:
                break
        except Exception:
            time.sleep(0.5)

    # 1. Health check
    res = session.get(f"http://127.0.0.1:{port}/health")
    print(f"LIVE_PROBE: /health -> status={res.status_code}, json={res.json()}")
    assert res.status_code == 200

    # 2. CORS Preflight
    res_cors = session.options(
        f"http://127.0.0.1:{port}/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    print(f"LIVE_PROBE: CORS preflight -> {res_cors.status_code} "
          f"Allow-Origin={res_cors.headers.get('access-control-allow-origin')}")
    assert res_cors.headers.get("access-control-allow-origin") == "http://localhost:3000"

    # 3. Physics API
    res_physics = session.post(
        f"http://127.0.0.1:{port}/api/v1/physics/tsiolkovsky",
        json={"dry_mass_kg": 500.0, "wet_mass_kg": 1500.0, "isp_seconds": 320.0},
    )
    print(f"LIVE_PROBE: /physics/tsiolkovsky -> {res_physics.status_code} {res_physics.json()}")
    assert res_physics.status_code == 200

    # 4. Component Catalog API
    res_comp = session.get(f"http://127.0.0.1:{port}/api/v1/components")
    print(f"LIVE_PROBE: /api/v1/components -> {res_comp.status_code} "
          f"count={res_comp.json().get('total')}")
    assert res_comp.status_code == 200

    print("ALL LIVE NETWORK PROBES COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    test_live_server()
