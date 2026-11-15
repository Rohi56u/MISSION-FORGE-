"""
CLI Runner for Component Catalog Seeding.
Usage:
    python backend/scripts/seed_components.py
    python scripts/seed_components.py
"""
import asyncio
import sys
from pathlib import Path


def run_seed() -> None:
    _backend_dir = Path(__file__).resolve().parent.parent
    if str(_backend_dir) not in sys.path:
        sys.path.insert(0, str(_backend_dir))
    if str(_backend_dir.parent) not in sys.path:
        sys.path.insert(0, str(_backend_dir.parent))

    from backend.app.db.seed_components import main
    asyncio.run(main())


if __name__ == "__main__":
    run_seed()
