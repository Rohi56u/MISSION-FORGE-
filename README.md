# 🚀 MISSION FORGE — Autonomous Aerospace Mission Design & Real-Time Simulation Platform

[![Build & Test Status](https://img.shields.io/badge/Tests-333%20Passed%20(100%25)-10B981?style=for-the-badge&logo=pytest)](https://github.com/Rohi56u/MISSION-FORGE-)
[![Frontend Architecture](https://img.shields.io/badge/Frontend-React%2019%20%7C%20TypeScript%20%7C%20Three.js-0284C7?style=for-the-badge&logo=react)](https://github.com/Rohi56u/MISSION-FORGE-)
[![Backend Architecture](https://img.shields.io/badge/Backend-FastAPI%20%7C%20SQLAlchemy%20%7C%20Alembic-009688?style=for-the-badge&logo=fastapi)](https://github.com/Rohi56u/MISSION-FORGE-)
[![Astrodynamics](https://img.shields.io/badge/Astrodynamics-Vallado%20Conics%20%7C%20Lambert%20%7C%20Porkchop-F59E0B?style=for-the-badge&logo=nasa)](https://github.com/Rohi56u/MISSION-FORGE-)
[![Security](https://img.shields.io/badge/Security-RBAC%20%7C%20SHA--256%20Cryptographic%20Attestation-8B5CF6?style=for-the-badge&logo=shield)](https://github.com/Rohi56u/MISSION-FORGE-)

> **NASA Space Apps Challenge 2026**  
> An integrated, real-world aerospace platform engineered for end-to-end space mission design, four-player Concurrent Design Facility (CDF) multi-disciplinary collaboration, deterministic Fault Detection, Isolation & Recovery (FDIR), grounded CAPCOM mission intelligence, and cryptographically verified mission dossiers.

---

## 🌌 Overview

Modern space exploration requires synthesizing massive quantities of astrodynamic calculations, subsystem trade-offs (SWaP-C: Size, Weight, Power, and Cost), international ground telemetry, and fault-tolerant system monitoring. Traditional space mission planning tools are siloed, requiring days to reconcile changes between orbital trajectory planners, power engineers, and thermal leads.

**Mission Forge** solves this by unifying:
1. **Astrodynamics Laboratory:** Universal variable Lambert mechanics, 2D porkchop energy contour generation, and exact heliocentric Keplerian conic transfer arcs.
2. **Concurrent Design Facility (CDF):** Real-time 4-officer concurrent design facility with WebSocket synchronization, optimistic version checking, and role-based permissions.
3. **Spacecraft Designer & Provenance Ledger:** Procedural 3D bus visualization, component catalog with flight heritage/TRL filters, and automated SWaP-C feasibility validation.
4. **Deterministic FDIR & Grounded CAPCOM:** Zero-hallucination spacecraft telemetry safety rules with discrete `NOMINAL` vs `INSUFFICIENT_DATA` quality flags and grounded Gemini advisory assistant.
5. **Mission Control Command Bridge:** Live NASA Deep Space Network (DSN) ground station tracking and NASA TechPort technology roadmap feeds.
6. **Auditable Mission Dossier Service:** Asynchronous ReportLab PDF compilation, structured JSON architecture snapshots, and in-browser cryptographic SHA-256 verification.

---

## 📐 System Architecture

```mermaid
flowchart TD
    subgraph Frontend["Frontend Client (React 19 + TypeScript + Three.js)"]
        UI_Shell["Shell & Global Navigation (UTC / Julian Chronometer)"]
        CB["Command Bridge (DSN Feed & TechPort)"]
        Astro["Astrodynamics Lab (Porkchop & 3D Conic Arc)"]
        CAD["Spacecraft Designer (3D Bus & Component Ledger)"]
        CDF_UI["CDF Real-Time 4-Role Collaboration Room"]
        FDIR_UI["FDIR Operations & CAPCOM Advisory Interface"]
        Dossier_UI["Mission Dossier Export & SHA-256 Verification"]
    end

    subgraph Gateway["Vite Dev Server / Production Reverse Proxy"]
        Proxy["Proxy Layer (/api, /ws, /health, /ready)"]
    end

    subgraph Backend["FastAPI Aerospace Application Server"]
        AuthModule["RBAC & JWT / Firebase Authentication"]
        AstroEngine["Astrodynamics Solver (Universal Variable Lambert)"]
        SWaPCEngine["SWaP-C Physics & Constraint Engine"]
        CDFBroker["CDF Room State Machine & WebSocket Broadcast"]
        FDIREngine["Deterministic FDIR Telemetry Evaluation Engine"]
        CAPCOMAdapter["Grounded CAPCOM AI Assistant (Google Gemini 2.5 Flash)"]
        DossierCompiler["Dossier Builder & ReportLab PDF Generator"]
    end

    subgraph DataIntegrations["External Telemetry & Aerospace Ephemeris"]
        Horizons["NASA JPL Horizons Ephemeris API"]
        DSN_Live["NASA DSN XML Telemetry Stream"]
        TechPort["NASA TechPort R&D Database"]
    end

    subgraph Storage["Persistence & Integrity Layer"]
        DB[(PostgreSQL / Async SQLite + Alembic)]
        DossierStore[("Artifact Storage (Signed Cloud / Local Storage)")]
    end

    Frontend --> Gateway
    Gateway --> Backend
    Backend --> DataIntegrations
    Backend --> Storage
```

---

## 🛰️ 13 Engineering Phases Breakdown

| Phase | Subsystem | Engineering Delivery |
|:---:|:---|:---|
| **Phase 1** | **Core Database & Physics Engine** | Relational schemas, Tsiolkovsky rocket equation, staged propulsion, solar irradiance inverse-square modeling, MMRTG Pu-238 radioactive decay curves, telecom free-space path loss (FSPL), and SWaP-C constraint checking. |
| **Phase 2** | **Aerospace Connectors** | Live HTTP/XML parsers for NASA Deep Space Network (`/api/v1/dsn/now`), JPL Horizons Cartesian orbital state vectors (`/api/v1/horizons/vectors`), and NASA TechPort technology readiness level queries. |
| **Phase 3** | **Astrodynamics Engine** | Exact universal variable Lambert boundary problem solver (Vallado algorithm 58), background asynchronous worker for interplanetary departure/arrival porkchop plots, and idempotent job lifecycle. |
| **Phase 4** | **Concurrent Design Facility (CDF)** | Real-time multi-officer design room (`SYSTEMS_LEAD`, `PROPULSION_POWER`, `AVIONICS_GNC`, `SCIENCE_PAYLOAD`) with WebSocket message broadcasts, optimistic concurrency control, and HTTP 409 conflict detection. |
| **Phase 5** | **Deterministic FDIR & CAPCOM** | Deterministic telemetry safety rules (power deficit, thermal runaway, communication loss), anomaly clearance audit log, and grounded CAPCOM AI assistant powered by Gemini. |
| **Phase 6** | **Mission Dossiers & Deployment** | Automated ReportLab PDF generation, multi-page component registries, JSON snapshot exports, and hardened deployment configurations (Dockerfile, docker-compose). |
| **Phase 7** | **Aerospace Foundation & Tokens** | Deep-space carbon/navy tokens (`#05080E`, `#0B0F17`, `#1E293B`, `#0284C7`), tabular numerals, live UTC/Julian Date chronometer, dual `/health` + `/ready` connection probes, and typed API client (`src/lib/api.ts`). |
| **Phase 8** | **Mission Control Command Bridge** | Active exploration missions listing, live DSN telemetry view with distinct static geographic facility coordinates (Goldstone, Madrid, Canberra), TechPort TRL progression bars, and accessible table fallbacks. |
| **Phase 9** | **Astrodynamics Lab** | 2D interactive porkchop contour plot rendering non-converged/null cells as dark hatched void gaps (never zeroes), and Three.js 3D heliocentric Keplerian conic transfer arc with patched-conic limitation disclosure. |
| **Phase 10** | **Spacecraft Visualizer & Ledger** | Procedural 3D spacecraft bus with subsystem meshes, component catalog ledger with TRL 1–9 and flight heritage filters, real-time SWaP-C analysis, and accessible tabular fallback. |
| **Phase 11** | **CDF Collaborative Workspace** | Four-role design station UI, 30-second WebSocket keepalive heartbeats, exponential backoff auto-reconnect, and operator login drawer. |
| **Phase 12** | **FDIR Operations & CAPCOM UI** | Fault detection dashboard, explicit distinction between `NOMINAL` and `INSUFFICIENT_DATA`, persistent finding UUID resolution for anomaly clearance, and grounded CAPCOM advisory interface. |
| **Phase 13** | **Dossier & Artifact Export Center** | Asynchronous PDF/JSON compilation tracking, in-browser cryptographic SHA-256 verification via Web Crypto API, embedded PDF viewer, and large payload DOM truncation protections. |

---

## 🛠️ Technology Stack

### Frontend Architecture
- **Framework:** React 19 + TypeScript 5.7
- **Bundler & Tooling:** Vite 6 (with manual Rollup chunk splitting for `three.js` and all views)
- **Styling & Icons:** Tailwind CSS 3.4, Lucide React
- **3D Graphics & Conics:** Three.js 0.170 (exact two-body Keplerian conic propagation, WebGL canvas cleanup)
- **Testing:** Vitest 2.1, React Testing Library, JSDOM

### Backend Architecture
- **Framework:** FastAPI (Python 3.11 / 3.14 compatible)
- **ORM & Migrations:** SQLAlchemy 2.0 (asyncio + aiosqlite / asyncpg), Alembic
- **Document Generation:** ReportLab 4.2 (vector PDF generation)
- **Real-Time Communication:** Starlette WebSockets with JSON protocol
- **Artificial Intelligence:** Google GenAI SDK (Gemini 2.5 Flash / Flash Lite)
- **Testing:** Pytest 9.0, pytest-asyncio, HTTPX

---

## 🚀 Getting Started

### Prerequisites
- **Python:** 3.11+
- **Node.js:** 18.0.0+
- **Package Manager:** `pnpm` (recommended), `npm`, or `yarn`

---

### Step 1: Backend Setup
```bash
# 1. Navigate to backend directory
cd backend

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create environment file from template
cp .env.example .env

# 4. Run database migrations
alembic upgrade head

# 5. Start the FastAPI server
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
- **Backend API:** `http://127.0.0.1:8000`
- **Interactive Swagger Docs:** `http://127.0.0.1:8000/docs`
- **Health Check:** `http://127.0.0.1:8000/health`
- **Readiness Probe:** `http://127.0.0.1:8000/ready`

---

### Step 2: Frontend Setup
```bash
# 1. Navigate to frontend directory in a separate terminal
cd frontend

# 2. Install dependencies
pnpm install

# 3. Start development server
pnpm dev
```
- **Web Application URL:** `http://localhost:3000`
- *All REST calls (`/api`, `/health`, `/ready`) and WebSockets (`/api/v1/cdf/ws`) automatically route to the FastAPI backend via Vite proxy.*

---

## 🧪 Comprehensive Verification & Test Suites

The entire Mission Forge codebase has undergone rigorous mathematical, contract, and end-to-end verification:

### 1. Backend Regression Suite (281 Tests Passed)
```bash
cd backend
python -m pytest tests -q
# Result: 281 passed, 3 warnings in 24.64s (Exit Code: 0)
```
- Includes Vallado algorithm verification, parabolic/hyperbolic transfer arc validation, Alembic upgrade/downgrade migration cycles, CDF concurrency conflict isolation, FDIR rule execution, and ReportLab PDF layout tests.

### 2. Frontend Test Suite (52 Tests Passed across 13 Suites)
```bash
cd frontend
pnpm test --run
# Result: 13 test files passed, 52 tests passed in 23.40s (Exit Code: 0)
```
- Covers component rendering, API client error boundaries, DSN live/static telemetry separation, porkchop null-cell void rendering, Three.js conic math, WebSocket keepalives, and Web Crypto SHA-256 verification.

### 3. TypeScript Strict Type-Checking
```bash
cd frontend
npx tsc --noEmit
# Result: 0 errors (Exit Code: 0)
```

### 4. Production Build & Chunk Isolation
```bash
cd frontend
pnpm build
# Result: 1598 modules transformed in 9.69s (Exit Code: 0)
# Bundles:
#   dist/assets/three-CNp_z5uV.js               478.24 kB
#   dist/assets/index-Bq1SMmqr.js               286.86 kB
#   dist/assets/SpacecraftDesigner-DWMCpuJN.js   41.28 kB
#   dist/assets/CdfCollaboration-D-rgR4hT.js     32.73 kB
#   dist/assets/FdirCapcomOperations-DdMYJF-g.js 27.36 kB
#   dist/assets/MissionDossierCenter-qEC1qFeU.js 25.17 kB
#   dist/assets/AstrodynamicsLab-CltZx_Ds.js     45.19 kB
```

---

## 🛡️ Security, Privacy & Integrity Guarantees

1. **Zero Secret Leaks:** Real API keys, database credentials, private service account JSONs, and `.env` files are strictly excluded from version control via `.gitignore`.
2. **Authoritative Access Control:** Backend authorization remains strictly authoritative. UI controls do not masquerade as security boundaries.
3. **Cryptographic Artifact Attestation:** Dossier PDFs and JSONs feature true in-browser SHA-256 recalculation via `crypto.subtle.digest`. A `"SHA-256 VERIFIED"` badge appears only when client-calculated hashes match server metadata.
4. **Truthful Data Provenance:** Telemetry streams clearly distinguish between `LIVE`, `CACHED`, `STATIC`, and `SIMULATED` modes. Missing sensors render as `INSUFFICIENT_DATA`, never as nominal zeroes.

---

## 📚 Scientific Citations & References

- **Vallado, David A.** *Fundamentals of Astrodynamics and Applications*, 4th ed., Microcosm Press, 2013. (Lambert solver universal variable algorithm, Section 5.4).
- **Battin, Richard H.** *An Introduction to the Mathematics and Methods of Astrodynamics*, AIAA Education Series, 1999.
- **NASA JPL Horizons On-Line Ephemeris System:** Cartesian solar system barycentric vector queries.
- **NASA Deep Space Network (DSN):** Real-time ground station tracking feeds from Goldstone (GDSCC), Madrid (MDSCC), and Canberra (CDSCC).
- **ECSS Standards:** European Cooperation for Space Standardization (ECSS-E-TM-10-25A) for Concurrent Design Facility parameter exchange and SWaP-C margins.

---

## 🏷️ Tags & Keywords

`aerospace-engineering` • `nasa-space-apps-challenge` • `astrodynamics` • `orbital-mechanics` • `lambert-problem` • `porkchop-plot` • `threejs` • `react19` • `typescript` • `fastapi` • `concurrent-design-facility` • `spacecraft-fdir` • `capcom-ai` • `gemini-api` • `deep-space-network` • `space-mission-design`

---

## 📄 License
Licensed under the **MIT License**. Created for the NASA Space Apps Challenge 2026.
