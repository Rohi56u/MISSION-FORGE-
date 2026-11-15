"""
Release Packager for Mission Forge
Creates a clean, production-ready source distribution ZIP archive.
Ensures zero secrets, zero build artifacts, and zero bulky cache folders.
"""

import os
import zipfile
import re
from pathlib import Path

WORKSPACE_ROOT = Path("C:/Users/Mohit/Misson Forge").resolve()
OUTPUT_ZIP = WORKSPACE_ROOT / "mission_forge_release.zip"

# Strict exclusion rules
EXCLUDE_DIRS = {
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    ".git",
    "tmp_wheels",
    "wheels",
    "artifacts",
}

EXCLUDE_PATTERNS = [
    re.compile(r"^pytest-cache-files", re.IGNORECASE),
    re.compile(r"\.pyc$", re.IGNORECASE),
    re.compile(r"\.pyo$", re.IGNORECASE),
    re.compile(r"^\.env$", re.IGNORECASE),
    re.compile(r"^\.env\..*$", re.IGNORECASE),
    re.compile(r"\.db$", re.IGNORECASE),
    re.compile(r"\.db-shm$", re.IGNORECASE),
    re.compile(r"\.db-wal$", re.IGNORECASE),
    re.compile(r"\.sqlite$", re.IGNORECASE),
    re.compile(r"\.sqlite3$", re.IGNORECASE),
    re.compile(r"\.log$", re.IGNORECASE),
    re.compile(r"test_write\.txt$", re.IGNORECASE),
    re.compile(r"mission_forge_release\.zip$", re.IGNORECASE),
]

# Ensure safe example templates are included even if .env match
SAFE_FILES = {".env.example", ".gitignore", ".flake8"}

def should_exclude(rel_path: Path) -> bool:
    # 1. First check all directory components
    for part in rel_path.parts[:-1]:
        if part in EXCLUDE_DIRS:
            return True
        for pat in EXCLUDE_PATTERNS:
            if pat.search(part):
                return True

    file_name = rel_path.name

    # 2. If in a clean directory, allow explicit safe configuration templates
    if file_name in SAFE_FILES:
        return False

    # 3. Check excluded filenames
    if file_name == "mission_forge_release.zip":
        return True
    if file_name == "create_release_zip.py":
        return True
    if file_name.startswith("prd") and file_name.endswith(".pdf"):
        return True

    for pat in EXCLUDE_PATTERNS:
        if pat.search(file_name):
            return True

    # Exclude generated dossiers PDFs and JSONs
    if "dossiers" in rel_path.parts and (file_name.endswith(".pdf") or file_name.endswith(".json")):
        return True

    return False

def package_project():
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()

    included_count = 0
    excluded_count = 0
    
    print(f"Packaging Mission Forge source archive from {WORKSPACE_ROOT}...")

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(WORKSPACE_ROOT):
            root_path = Path(root)
            
            # Prune excluded directories in-place
            dirs[:] = [
                d for d in dirs 
                if not should_exclude((root_path / d).relative_to(WORKSPACE_ROOT))
            ]

            for file in files:
                full_path = root_path / file
                rel_path = full_path.relative_to(WORKSPACE_ROOT)

                if should_exclude(rel_path):
                    excluded_count += 1
                    continue

                # Add to ZIP under mission_forge/ prefix
                archive_name = Path("mission_forge") / rel_path
                zf.write(full_path, str(archive_name))
                included_count += 1

    zip_size_mb = OUTPUT_ZIP.stat().st_size / (1024 * 1024)
    print(f"Archive successfully created: {OUTPUT_ZIP}")
    print(f"Total files included: {included_count}")
    print(f"Total files excluded: {excluded_count}")
    print(f"Archive size: {zip_size_mb:.2f} MB ({OUTPUT_ZIP.stat().st_size} bytes)")

def verify_zip():
    print("\nVerifying archive integrity and contents...")
    with zipfile.ZipFile(OUTPUT_ZIP, "r") as zf:
        # Integrity test (CRC-32)
        bad_file = zf.testzip()
        if bad_file:
            raise RuntimeError(f"Corrupted file detected in ZIP: {bad_file}")
        print("✓ ZIP CRC-32 integrity test passed: No corruptions.")

        names = zf.namelist()
        
        # Verify essential files are present
        essential_files = [
            "mission_forge/README.md",
            "mission_forge/.gitignore",
            "mission_forge/backend/pyproject.toml",
            "mission_forge/backend/requirements.txt",
            "mission_forge/backend/.env.example",
            "mission_forge/backend/alembic.ini",
            "mission_forge/backend/Dockerfile",
            "mission_forge/backend/app/main.py",
            "mission_forge/frontend/package.json",
            "mission_forge/frontend/pnpm-lock.yaml",
            "mission_forge/frontend/vite.config.ts",
            "mission_forge/frontend/src/App.tsx",
            "mission_forge/frontend/src/views/CommandBridge.tsx",
            "mission_forge/frontend/src/views/AstrodynamicsLab.tsx",
            "mission_forge/frontend/src/views/SpacecraftDesigner.tsx",
            "mission_forge/frontend/src/views/CdfCollaboration.tsx",
            "mission_forge/frontend/src/views/FdirCapcomOperations.tsx",
            "mission_forge/frontend/src/views/MissionDossierCenter.tsx",
        ]

        for ef in essential_files:
            assert ef in names, f"Missing critical file in archive: {ef}"
        print(f"✓ All {len(essential_files)} essential project files verified present.")

        # Verify no prohibited files are present
        prohibited_violations = []
        for name in names:
            lower = name.lower()
            if any(s in lower for s in ["node_modules", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache"]):
                prohibited_violations.append(name)
            if lower.endswith(".pyc") or lower.endswith(".db") or lower.endswith(".sqlite"):
                prohibited_violations.append(name)
            if lower.endswith("/.env") or lower.endswith("\\.env"):
                prohibited_violations.append(name)

        if prohibited_violations:
            raise RuntimeError(f"Prohibited files leaked into ZIP: {prohibited_violations[:5]}")
        print("✓ Zero secrets, node_modules, .venv, or SQLite database files in archive.")

if __name__ == "__main__":
    package_project()
    verify_zip()
