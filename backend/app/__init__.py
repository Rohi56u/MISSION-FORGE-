"""Mission Forge Aerospace Backend API"""

import sys
from pathlib import Path

# Ensure the workspace root (parent directory of `backend`) is in sys.path
# so that absolute imports (`from backend.app...`) resolve cleanly when running
# from inside the `backend` directory or when `backend` is on sys.path.
_backend_dir = Path(__file__).resolve().parent.parent
_workspace_root = _backend_dir.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

__version__ = "1.0.0"
