# Database Migration Runbook (Alembic)

Mission Forge Phase 1 — Database Architecture and Schema Evolution

## Overview

Mission Forge uses [Alembic](https://alembic.sqlalchemy.org/) configured for SQLAlchemy 2.0 with asynchronous drivers (`aiosqlite` for local development/testing, and `asyncpg` for production PostgreSQL).

In non-production environments, `Base.metadata.create_all` initializes schema tables on startup for rapid local prototyping. In production environments (`ENVIRONMENT=production`), automatic `create_all` is disabled to ensure all schema migrations are version-controlled, reviewed, and executed deterministically via Alembic.

---

## Prerequisites

Ensure the Python environment is active and dependencies are installed:

```bash
cd "c:\Users\Mohit\Misson Forge\backend"
C:\Python314\python.exe -m pip install -r requirements.txt
```

Verify that Alembic can locate the application modules by setting `PYTHONPATH`:

```powershell
$env:PYTHONPATH = "c:\Users\Mohit\Misson Forge"
```

---

## Database Configuration

The database connection URL is controlled via the `DATABASE_URL` setting in `app/core/config.py` or `.env`:

- **Development / Local CI (SQLite Async)**:
  ```env
  DATABASE_URL=sqlite+aiosqlite:///./mission_forge.db
  ```
- **Production (PostgreSQL Async)**:
  ```env
  DATABASE_URL=postgresql+asyncpg://user:password@hostname:5432/mission_forge
  ```

Alembic automatically reads `DATABASE_URL` from the environment when executing online migrations.

---

## Migration Commands

### 1. Inspect Current Migration Status

Check the currently applied migration revision against the database:

```powershell
C:\Python314\python.exe -m alembic current
```

Check the latest available migration in the repository:

```powershell
C:\Python314\python.exe -m alembic heads
```

View the complete version history:

```powershell
C:\Python314\python.exe -m alembic history --verbose
```

Check for schema drift between SQLAlchemy models and the active database:

```powershell
C:\Python314\python.exe -m alembic check
```

---

### 2. Generate a New Migration

When modifying SQLAlchemy models in `app/models/`:

1. Ensure the new model is registered in `app/models/__init__.py`.
2. Generate an autodetected migration revision:

```powershell
C:\Python314\python.exe -m alembic revision --autogenerate -m "describe_changes_here"
```

3. Review the generated file in `alembic/versions/` to verify operations, constraints, and batch alterations.

---

### 3. Apply Migrations (Upgrade)

Apply all pending migrations up to the latest revision (`head`):

```powershell
C:\Python314\python.exe -m alembic upgrade head
```

To apply a specific revision:

```powershell
C:\Python314\python.exe -m alembic upgrade <revision_id>
```

To apply relative increments (e.g. +1 revision):

```powershell
C:\Python314\python.exe -m alembic upgrade +1
```

---

### 4. Roll Back Migrations (Downgrade)

> [!NOTE]
> SQLite has limited native support for `ALTER TABLE DROP COLUMN`. Alembic is configured with `render_as_batch=True` to support table reconstruction on SQLite. On PostgreSQL, native DDL transactions are used.

Roll back the most recent migration (-1 revision):

```powershell
C:\Python314\python.exe -m alembic downgrade -1
```

Roll back all migrations to clean state:

```powershell
C:\Python314\python.exe -m alembic downgrade base
```

---

### Phase 6: Mission Dossiers & Production Hardening (`d4e5f6a7b8c9`)

- Introduces `dossier_jobs` table to manage asynchronous compilation, rendering progress, and failure tracking.
- Introduces `dossier_reports` table to store immutable frozen JSON data snapshots, PDF/JSON storage file paths, SHA-256 checksums, and schema versions.
- Enforces cascading foreign key deletion when parent missions or users are purged.

---

## Production Deployment Workflow

1. Prior to deploying code changes, run automated tests and schema verification:
   ```powershell
   C:\Python314\python.exe -m pytest tests/test_migrations.py -v
   ```
2. In the deployment pipeline (e.g. Docker entrypoint, Kubernetes initContainer, or release phase):
   ```bash
   alembic upgrade head
   ```
3. Start the application:
   ```bash
   uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
   ```
