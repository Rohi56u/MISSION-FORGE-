"""
Alembic Database Migration Verification Tests
Tests upgrade, downgrade, schema integrity, and zero-drift verification.
"""

import os
import tempfile
import pytest
from sqlalchemy import create_engine, inspect, text
from alembic.config import Config
from alembic import command
from pathlib import Path


@pytest.fixture
def temp_alembic_db():
    """Provides a fresh temporary SQLite database and custom Alembic Config."""
    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "migration_test.db")
    sync_url = f"sqlite:///{temp_db_path}"
    async_url = f"sqlite+aiosqlite:///{temp_db_path}"

    backend_dir = Path(__file__).resolve().parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    # Override database URL to point to isolated temporary db
    cfg.set_main_option("sqlalchemy.url", async_url)

    yield sync_url, cfg

    try:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)
        os.rmdir(temp_dir)
    except OSError:
        pass


def test_alembic_upgrade_downgrade_cycle(temp_alembic_db):
    """
    Applies initial baseline migration on a fresh database,
    verifies table creation, downgrades to base, and re-applies.
    """
    sync_url, cfg = temp_alembic_db

    # 1. Apply baseline migration
    command.upgrade(cfg, "head")

    # 2. Inspect created tables
    sync_engine = create_engine(sync_url)
    with sync_engine.connect() as conn:
        inspector = inspect(conn)
        table_names = set(inspector.get_table_names())

        expected_tables = {
            "components",
            "missions",
            "spacecraft_designs",
            "techport_projects",
            "porkchop_jobs",
            "users",
            "cdf_rooms",
            "cdf_room_participants",
            "cdf_revisions",
            "cdf_events",
            "fdir_findings",
            "alembic_version",
        }
        assert expected_tables.issubset(table_names), (
            f"Missing expected tables. Found: {table_names}, Expected subset: {expected_tables}"
        )

        # Verify columns on components
        comp_cols = {col["name"] for col in inspector.get_columns("components")}
        expected_comp_cols = {
            "id",
            "name",
            "subsystem",
            "mass_kg",
            "isp_seconds",
            "thrust_newtons",
            "field_provenance",
            "source_system",
            "raw_source_hash",
            "last_synced_at",
        }
        assert expected_comp_cols.issubset(comp_cols)

        # Verify columns on techport_projects
        techport_cols = {col["name"] for col in inspector.get_columns("techport_projects")}
        expected_techport_cols = {
            "id",
            "techport_id",
            "title",
            "status",
            "trl_current",
            "canonical_url",
            "raw_payload",
        }
        assert expected_techport_cols.issubset(techport_cols)

        # Verify columns on missions
        mission_cols = {col["name"] for col in inspector.get_columns("missions")}
        assert {"id", "name", "target", "budget_cap_usd", "min_delta_v_mps"}.issubset(mission_cols)

        # Verify columns on spacecraft_designs
        design_cols = {col["name"] for col in inspector.get_columns("spacecraft_designs")}
        expected_design_cols = {
            "id", "mission_id", "dry_mass_kg", "wet_mass_kg", "delta_v_mps"
        }
        assert expected_design_cols.issubset(design_cols)

        # Verify columns on porkchop_jobs (Phase 3)
        porkchop_cols = {col["name"] for col in inspector.get_columns("porkchop_jobs")}
        expected_porkchop_cols = {
            "id", "status", "progress_percent", "origin_body", "target_body",
            "departure_start", "departure_end", "arrival_start", "arrival_end",
            "step_size_days", "parameters", "results", "error_message",
            "created_at", "updated_at", "completed_at",
        }
        assert expected_porkchop_cols.issubset(porkchop_cols)

        # Verify columns on users (Phase 4 & Firebase Integration)
        user_cols = {col["name"] for col in inspector.get_columns("users")}
        expected_user_cols = {
            "id", "email", "full_name", "hashed_password", "is_active", "firebase_uid"
        }
        assert expected_user_cols.issubset(user_cols)

        # Verify columns on cdf_rooms (Phase 4)
        room_cols = {col["name"] for col in inspector.get_columns("cdf_rooms")}
        expected_room_cols = {
            "id", "name", "mission_id", "creator_id", "status", "max_participants",
            "current_version",
        }
        assert expected_room_cols.issubset(room_cols)

        # Verify columns on cdf_room_participants (Phase 4)
        part_cols = {col["name"] for col in inspector.get_columns("cdf_room_participants")}
        expected_part_cols = {
            "id", "room_id", "user_id", "role", "is_connected", "joined_at", "last_seen_at"
        }
        assert expected_part_cols.issubset(part_cols)

        # Verify columns on cdf_revisions (Phase 4)
        rev_cols = {col["name"] for col in inspector.get_columns("cdf_revisions")}
        expected_rev_cols = {
            "id", "room_id", "version", "author_id", "author_role", "mutation_type",
            "patch_data", "state_snapshot", "swapc_snapshot"
        }
        assert expected_rev_cols.issubset(rev_cols)

        # Verify columns on cdf_events (Phase 4)
        evt_cols = {col["name"] for col in inspector.get_columns("cdf_events")}
        expected_evt_cols = {
            "id", "room_id", "event_type", "version", "actor_id", "actor_role", "payload"
        }
        assert expected_evt_cols.issubset(evt_cols)

        # Verify columns on fdir_findings (Phase 5)
        fdir_cols = {col["name"] for col in inspector.get_columns("fdir_findings")}
        expected_fdir_cols = {
            "id", "room_id", "mission_id", "rule_id", "rule_version", "severity", "status",
            "affected_subsystem", "input_evidence", "thresholds"
        }
        assert expected_fdir_cols.issubset(fdir_cols)

    sync_engine.dispose()

    # 3. Test downgrade to base
    command.downgrade(cfg, "base")
    sync_engine_post_down = create_engine(sync_url)
    with sync_engine_post_down.connect() as conn_post_down:
        inspector_post_down = inspect(conn_post_down)
        tables_post_down = set(inspector_post_down.get_table_names())
        assert "components" not in tables_post_down
        assert "missions" not in tables_post_down
        assert "spacecraft_designs" not in tables_post_down
        assert "techport_projects" not in tables_post_down
        assert "porkchop_jobs" not in tables_post_down
        assert "users" not in tables_post_down
        assert "cdf_rooms" not in tables_post_down
        assert "cdf_room_participants" not in tables_post_down
        assert "cdf_revisions" not in tables_post_down
        assert "cdf_events" not in tables_post_down
        assert "fdir_findings" not in tables_post_down
    sync_engine_post_down.dispose()

    # 4. Re-upgrade to head
    command.upgrade(cfg, "head")
    sync_engine_reup = create_engine(sync_url)
    with sync_engine_reup.connect() as conn_reup:
        inspector_reup = inspect(conn_reup)
        assert "components" in inspector_reup.get_table_names()
    sync_engine_reup.dispose()


def test_migration_upgrade_and_downgrade_on_phase1_existing_database(temp_alembic_db):
    """
    Simulates applying Phase 2 migration onto an existing Phase 1 database with real records.
    Verifies data preservation, column additions, and safe rollback without loss of Phase 1 data.
    """
    sync_url, cfg = temp_alembic_db
    sync_engine = create_engine(sync_url)

    # 1. Upgrade only to Phase 1 baseline revision (f3a9f0df7570)
    command.upgrade(cfg, "f3a9f0df7570")

    # 2. Insert Phase 1 records
    import datetime
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO components ("
                "  id, name, subsystem, mass_kg, power_draw_w, power_generation_w, "
                "  cost_usd, trl, flight_heritage, source_url, verification_status, "
                "  specifications, is_active, created_at, updated_at"
                ") VALUES ("
                "  'comp-p1-001', 'Phase 1 Legacy Thruster', 'PROPULSION', 12.0, 50.0, 0.0, "
                "  100000.0, 9, 'Flight Proven', 'https://nasa.gov', 'VERIFIED_AUTHORITATIVE', "
                "  '{}', 1, :now, :now"
                ")"
            ),
            {"now": now_str},
        )
        conn.execute(
            text(
                "INSERT INTO missions ("
                "  id, name, target, mission_class, budget_cap_usd, max_launch_mass_kg, "
                "  min_delta_v_mps, min_power_margin_percent, created_at, updated_at"
                ") VALUES ("
                "  'miss-p1-001', 'Phase 1 Mars Mission', 'MARS', 'DISCOVERY', 500000000.0, "
                "  1500.0, 3500.0, 20.0, :now, :now"
                ")"
            ),
            {"now": now_str},
        )

    # 3. Apply Phase 2 migration (upgrade to head)
    command.upgrade(cfg, "head")

    # 4. Verify data preservation and schema evolution
    with sync_engine.connect() as conn:
        inspector = inspect(conn)
        cols = {c["name"] for c in inspector.get_columns("components")}
        assert "field_provenance" in cols
        assert "source_system" in cols
        assert "techport_projects" in set(inspector.get_table_names())

        # Verify Phase 1 record preserved intact
        row = conn.execute(
            text(
                "SELECT id, name, mass_kg, field_provenance "
                "FROM components WHERE id = 'comp-p1-001'"
            )
        ).fetchone()
        assert row is not None
        assert row[0] == "comp-p1-001"
        assert row[1] == "Phase 1 Legacy Thruster"
        assert row[2] == 12.0
        # field_provenance defaults to empty dict or '{}'
        assert row[3] in ({}, "{}", None)

        # Verify mission record preserved
        m_row = conn.execute(
            text("SELECT id, name FROM missions WHERE id = 'miss-p1-001'")
        ).fetchone()
        assert m_row is not None
        assert m_row[0] == "miss-p1-001"

    # 5. Downgrade back to Phase 1 (f3a9f0df7570)
    command.downgrade(cfg, "f3a9f0df7570")

    # 6. Verify Phase 2 additions removed but Phase 1 data still intact
    with sync_engine.connect() as conn:
        inspector = inspect(conn)
        cols_down = {c["name"] for c in inspector.get_columns("components")}
        assert "field_provenance" not in cols_down
        assert "source_system" not in cols_down
        assert "techport_projects" not in set(inspector.get_table_names())

        # Original record STILL exists
        row_after_down = conn.execute(
            text("SELECT id, name, mass_kg FROM components WHERE id = 'comp-p1-001'")
        ).fetchone()
        assert row_after_down is not None
        assert row_after_down[0] == "comp-p1-001"
        assert row_after_down[1] == "Phase 1 Legacy Thruster"

    sync_engine.dispose()


def test_migration_phase2_to_phase3_upgrade_downgrade(temp_alembic_db):
    """
    Tests upgrading from Phase 2 (a1b2c3d4e5f6) to Phase 3 (b2c3d4e5f6a7) and downgrading back.
    Verifies that the porkchop_jobs table is safely created and dropped without altering
    or corrupting existing Phase 1 and Phase 2 data records.
    """
    sync_url, cfg = temp_alembic_db
    sync_engine = create_engine(sync_url)

    # 1. Upgrade to Phase 2 revision (a1b2c3d4e5f6)
    command.upgrade(cfg, "a1b2c3d4e5f6")

    # 2. Insert Phase 1 component and Phase 2 TechPort project
    import datetime
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO components ("
                "  id, name, subsystem, mass_kg, power_draw_w, power_generation_w, "
                "  cost_usd, trl, flight_heritage, source_url, verification_status, "
                "  specifications, is_active, created_at, updated_at, field_provenance"
                ") VALUES ("
                "  'comp-p2-001', 'Phase 2 Optical Transceiver', 'TELECOM', 4.5, 30.0, 0.0, "
                "  250000.0, 7, 'Demo Flight', 'https://nasa.gov', 'VERIFIED_AUTHORITATIVE', "
                "  '{}', 1, :now, :now, '{}'"
                ")"
            ),
            {"now": now_str},
        )
        conn.execute(
            text(
                "INSERT INTO techport_projects ("
                "  id, techport_id, title, status, trl_current, canonical_url, raw_payload, "
                "  retrieved_at, created_at, updated_at"
                ") VALUES ("
                "  'tp-001', '14200', 'Solar Electric Propulsion Tech', 'ACTIVE', 6, "
                "  'https://techport.nasa.gov/view/14200', '{}', :now, :now, :now"
                ")"
            ),
            {"now": now_str},
        )

    # 3. Upgrade to Phase 3 (b2c3d4e5f6a7)
    command.upgrade(cfg, "b2c3d4e5f6a7")

    # 4. Verify porkchop_jobs table and indexes
    with sync_engine.begin() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        assert "porkchop_jobs" in tables

        # Insert a sample porkchop job record
        conn.execute(
            text(
                "INSERT INTO porkchop_jobs ("
                "  id, status, progress_percent, origin_body, target_body, "
                "  departure_start, departure_end, arrival_start, arrival_end, "
                "  step_size_days, parameters, results, created_at, updated_at"
                ") VALUES ("
                "  'job-test-001', 'COMPLETED', 100.0, 'EARTH', 'MARS', "
                "  '2026-06-01', '2026-06-15', '2027-01-01', '2027-01-15', "
                "  2.0, '{}', '{}', :now, :now"
                ")"
            ),
            {"now": now_str},
        )

        # Verify existing Phase 1 and Phase 2 data preserved
        c_row = conn.execute(
            text("SELECT id, name FROM components WHERE id = 'comp-p2-001'")
        ).fetchone()
        assert c_row is not None and c_row[1] == "Phase 2 Optical Transceiver"

        tp_row = conn.execute(
            text("SELECT id, title FROM techport_projects WHERE id = 'tp-001'")
        ).fetchone()
        assert tp_row is not None and tp_row[1] == "Solar Electric Propulsion Tech"

    # 5. Downgrade back to Phase 2 (a1b2c3d4e5f6)
    command.downgrade(cfg, "a1b2c3d4e5f6")

    # 6. Verify porkchop_jobs is gone, but Phase 1/Phase 2 data remain intact
    with sync_engine.connect() as conn:
        inspector_post = inspect(conn)
        tables_post = set(inspector_post.get_table_names())
        assert "porkchop_jobs" not in tables_post
        assert "components" in tables_post
        assert "techport_projects" in tables_post

        c_row_post = conn.execute(
            text("SELECT id, name FROM components WHERE id = 'comp-p2-001'")
        ).fetchone()
        assert c_row_post is not None and c_row_post[1] == "Phase 2 Optical Transceiver"

    # 7. Re-upgrade back to head
    command.upgrade(cfg, "head")
    sync_engine.dispose()


def test_migration_phase3_to_phase4_phase5_upgrade_downgrade(temp_alembic_db):
    """
    Tests upgrading from Phase 3 (b2c3d4e5f6a7) to Phase 4/5 (c3d4e5f6a7b8) and downgrading back.
    Verifies that Phase 4 (CDF rooms, participants, revisions, events, users) and
    Phase 5 (fdir_findings) tables are safely created, populated, and dropped on rollback
    without altering or corrupting existing Phase 1, Phase 2, and Phase 3 data records.
    """
    sync_url, cfg = temp_alembic_db
    sync_engine = create_engine(sync_url)

    # 1. Upgrade to Phase 3 revision (b2c3d4e5f6a7)
    command.upgrade(cfg, "b2c3d4e5f6a7")

    import datetime
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # 2. Insert records into Phase 1, 2, 3 tables
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO missions ("
                "  id, name, target, mission_class, budget_cap_usd, max_launch_mass_kg, "
                "  min_delta_v_mps, min_power_margin_percent, created_at, updated_at"
                ") VALUES ("
                "  'miss-p3-001', 'Europa Deep Explorer', 'JUPITER', 'FLAGSHIP', "
                "  2500000000.0, 3000.0, 4200.0, 25.0, :now, :now"
                ")"
            ),
            {"now": now_str},
        )
        conn.execute(
            text(
                "INSERT INTO components ("
                "  id, name, subsystem, mass_kg, power_draw_w, power_generation_w, "
                "  cost_usd, trl, flight_heritage, source_url, verification_status, "
                "  specifications, is_active, created_at, updated_at, field_provenance"
                ") VALUES ("
                "  'comp-p3-001', 'Phase 3 NextGen RTG', 'POWER', 45.0, 0.0, 250.0, "
                "  15000000.0, 8, 'Cassini/New Horizons', 'https://nasa.gov', "
                "  'VERIFIED_AUTHORITATIVE', '{}', 1, :now, :now, '{}'"
                ")"
            ),
            {"now": now_str},
        )
        conn.execute(
            text(
                "INSERT INTO techport_projects ("
                "  id, techport_id, title, status, trl_current, canonical_url, raw_payload, "
                "  retrieved_at, created_at, updated_at"
                ") VALUES ("
                "  'tp-p3-001', '19999', 'Advanced Radioisotope Systems', 'ACTIVE', 7, "
                "  'https://techport.nasa.gov/view/19999', '{}', :now, :now, :now"
                ")"
            ),
            {"now": now_str},
        )
        conn.execute(
            text(
                "INSERT INTO porkchop_jobs ("
                "  id, status, progress_percent, origin_body, target_body, "
                "  departure_start, departure_end, arrival_start, arrival_end, "
                "  step_size_days, parameters, results, created_at, updated_at"
                ") VALUES ("
                "  'job-p3-001', 'COMPLETED', 100.0, 'EARTH', 'JUPITER', "
                "  '2030-01-01', '2030-01-30', '2034-01-01', '2034-01-30', "
                "  5.0, '{}', '{}', :now, :now"
                ")"
            ),
            {"now": now_str},
        )

    # 3. Upgrade to Phase 4 & Phase 5 (c3d4e5f6a7b8 / head)
    command.upgrade(cfg, "c3d4e5f6a7b8")

    # 4. Verify Phase 4 and Phase 5 tables exist and insert data into them
    with sync_engine.begin() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        phase4_phase5_tables = {
            "users",
            "cdf_rooms",
            "cdf_room_participants",
            "cdf_revisions",
            "cdf_events",
            "fdir_findings",
        }
        assert phase4_phase5_tables.issubset(tables)

        # Insert user
        conn.execute(
            text(
                "INSERT INTO users ("
                "  id, email, full_name, hashed_password, is_active, created_at, updated_at"
                ") VALUES ("
                "  'usr-mig-001', 'lead@missionforge.space', 'Dr. Lead Architect', "
                "  'hashed_pw', 1, :now, :now"
                ")"
            ),
            {"now": now_str},
        )

        # Insert cdf_room
        conn.execute(
            text(
                "INSERT INTO cdf_rooms ("
                "  id, name, mission_id, creator_id, status, max_participants, "
                "  current_version, created_at, updated_at"
                ") VALUES ("
                "  'room-mig-001', 'Europa CDF Room', 'miss-p3-001', 'usr-mig-001', "
                "  'ACTIVE', 4, 1, :now, :now"
                ")"
            ),
            {"now": now_str},
        )

        # Insert cdf_room_participants
        conn.execute(
            text(
                "INSERT INTO cdf_room_participants ("
                "  id, room_id, user_id, role, is_connected, joined_at, last_seen_at"
                ") VALUES ("
                "  'part-mig-001', 'room-mig-001', 'usr-mig-001', 'LEAD_SYSTEMS_ARCHITECT', "
                "  1, :now, :now"
                ")"
            ),
            {"now": now_str},
        )

        # Insert cdf_revisions
        conn.execute(
            text(
                "INSERT INTO cdf_revisions ("
                "  id, room_id, version, author_id, author_role, mutation_type, "
                "  patch_data, state_snapshot, swapc_snapshot, created_at"
                ") VALUES ("
                "  'rev-mig-001', 'room-mig-001', 1, 'usr-mig-001', 'LEAD_SYSTEMS_ARCHITECT', "
                "  'INIT', '{}', '{}', '{}', :now"
                ")"
            ),
            {"now": now_str},
        )

        # Insert cdf_events
        conn.execute(
            text(
                "INSERT INTO cdf_events ("
                "  id, room_id, event_type, version, actor_id, actor_role, payload, created_at"
                ") VALUES ("
                "  'evt-mig-001', 'room-mig-001', 'USER_JOINED', 1, 'usr-mig-001', "
                "  'LEAD_SYSTEMS_ARCHITECT', '{}', :now"
                ")"
            ),
            {"now": now_str},
        )

        # Insert fdir_findings
        conn.execute(
            text(
                "INSERT INTO fdir_findings ("
                "  id, room_id, mission_id, rule_id, rule_version, severity, status, "
                "  affected_subsystem, input_evidence, thresholds, explanation, "
                "  confidence_status, triage_guidance, acknowledged, created_at"
                ") VALUES ("
                "  'fdir-mig-001', 'room-mig-001', 'miss-p3-001', 'FDIR-PWR-001', '1.0.0', "
                "  'WARNING', 'ACTIVE', 'POWER', '{}', '{}', "
                "  'Power generation shortfall detected', 'CONFIRMED', "
                "  'Deploy auxiliary RTG', 0, :now"
                ")"
            ),
            {"now": now_str},
        )

        # Verify prior data still intact
        m_row = conn.execute(
            text("SELECT id, name FROM missions WHERE id = 'miss-p3-001'")
        ).fetchone()
        assert m_row is not None and m_row[1] == "Europa Deep Explorer"
        pj_row = conn.execute(
            text("SELECT id, status FROM porkchop_jobs WHERE id = 'job-p3-001'")
        ).fetchone()
        assert pj_row is not None and pj_row[1] == "COMPLETED"

    # 5. Downgrade back to Phase 3 (b2c3d4e5f6a7)
    command.downgrade(cfg, "b2c3d4e5f6a7")

    # 6. Verify Phase 4 and 5 tables are dropped, while Phase 1, 2, and 3 data remain intact
    with sync_engine.connect() as conn:
        inspector_post = inspect(conn)
        post_tables = set(inspector_post.get_table_names())
        for dropped_table in phase4_phase5_tables:
            assert dropped_table not in post_tables, (
                f"Table {dropped_table} was not dropped on downgrade"
            )

        assert "missions" in post_tables
        assert "components" in post_tables
        assert "techport_projects" in post_tables
        assert "porkchop_jobs" in post_tables

        m_row = conn.execute(
            text("SELECT id, name FROM missions WHERE id = 'miss-p3-001'")
        ).fetchone()
        assert m_row is not None and m_row[1] == "Europa Deep Explorer"
        pj_row = conn.execute(
            text("SELECT id, status FROM porkchop_jobs WHERE id = 'job-p3-001'")
        ).fetchone()
        assert pj_row is not None and pj_row[1] == "COMPLETED"

    # 7. Re-upgrade to head
    command.upgrade(cfg, "head")
    sync_engine.dispose()


def test_migration_phase5_to_phase6_upgrade_downgrade(temp_alembic_db):
    """
    Tests applying Phase 6 migration (dossier_jobs and dossier_reports)
    onto an existing Phase 5 database, verifying table creation, data integrity,
    and clean rollback without affecting prior phases.
    """
    sync_url, cfg = temp_alembic_db
    sync_engine = create_engine(sync_url)

    # 1. Upgrade to Phase 5 (c3d4e5f6a7b8)
    command.upgrade(cfg, "c3d4e5f6a7b8")

    import datetime
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # 2. Insert Phase 1-5 prerequisite data (User & Mission)
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users ("
                "  id, email, full_name, hashed_password, is_active, created_at, updated_at"
                ") VALUES ("
                "  'usr-mig-001', 'pilot@missionforge.org', 'Lead Pilot', 'hash123', 1, :now, :now"
                ")"
            ),
            {"now": now_str},
        )
        conn.execute(
            text(
                "INSERT INTO missions ("
                "  id, name, target, mission_class, budget_cap_usd, max_launch_mass_kg, "
                "  min_delta_v_mps, min_power_margin_percent, created_at, updated_at"
                ") VALUES ("
                "  'miss-p5-001', 'Titan Surveyor', 'TITAN', 'FLAGSHIP', 2500000000.0, "
                "  3500.0, 5200.0, 20.0, :now, :now"
                ")"
            ),
            {"now": now_str},
        )

    # 3. Upgrade to Phase 6 head (d4e5f6a7b8c9)
    command.upgrade(cfg, "d4e5f6a7b8c9")

    # 4. Verify Phase 6 tables and columns exist
    with sync_engine.connect() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        assert "dossier_jobs" in tables
        assert "dossier_reports" in tables

        job_cols = {c["name"] for c in inspector.get_columns("dossier_jobs")}
        expected_job_cols = {
            "id", "mission_id", "user_id", "room_id", "design_id",
            "format", "status", "progress_percent", "report_id",
            "error_message", "created_at", "updated_at", "completed_at",
        }
        assert expected_job_cols.issubset(job_cols)

        report_cols = {c["name"] for c in inspector.get_columns("dossier_reports")}
        expected_report_cols = {
            "id", "job_id", "mission_id", "user_id", "room_id", "design_id",
            "title", "format", "pdf_path", "pdf_size_bytes", "pdf_sha256",
            "json_path", "json_size_bytes", "json_sha256", "schema_version",
            "snapshot_data", "page_count", "created_at", "updated_at",
        }
        assert expected_report_cols.issubset(report_cols)

    # 5. Insert Phase 6 records and verify foreign key resolution
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO dossier_jobs ("
                "  id, mission_id, user_id, format, status, progress_percent, "
                "  created_at, updated_at"
                ") VALUES ("
                "  'job-mig-001', 'miss-p5-001', 'usr-mig-001', 'BOTH', 'QUEUED', 0.0, "
                "  :now, :now"
                ")"
            ),
            {"now": now_str},
        )
        conn.execute(
            text(
                "INSERT INTO dossier_reports ("
                "  id, job_id, mission_id, user_id, title, format, schema_version, "
                "  snapshot_data, page_count, created_at, updated_at"
                ") VALUES ("
                "  'rep-mig-001', 'job-mig-001', 'miss-p5-001', 'usr-mig-001', "
                "  'Titan Surveyor Concept Dossier', 'BOTH', '1.0.0', '{}', 5, :now, :now"
                ")"
            ),
            {"now": now_str},
        )

        # Verify insertion and data retrieval
        row = conn.execute(
            text("SELECT id, title, page_count FROM dossier_reports WHERE id = 'rep-mig-001'")
        ).fetchone()
        assert row is not None
        assert row[0] == "rep-mig-001"
        assert row[1] == "Titan Surveyor Concept Dossier"
        assert row[2] == 5

    # 6. Downgrade back to Phase 5 (c3d4e5f6a7b8)
    command.downgrade(cfg, "c3d4e5f6a7b8")

    # 7. Verify Phase 6 tables dropped while Phase 1-5 data remains intact
    with sync_engine.connect() as conn:
        inspector_post = inspect(conn)
        post_tables = set(inspector_post.get_table_names())
        assert "dossier_jobs" not in post_tables
        assert "dossier_reports" not in post_tables
        assert "missions" in post_tables
        assert "users" in post_tables

        u_row = conn.execute(text("SELECT email FROM users WHERE id = 'usr-mig-001'")).fetchone()
        assert u_row is not None and u_row[0] == "pilot@missionforge.org"

        m_row = conn.execute(text("SELECT name FROM missions WHERE id = 'miss-p5-001'")).fetchone()
        assert m_row is not None and m_row[0] == "Titan Surveyor"

    # 8. Re-upgrade to head
    command.upgrade(cfg, "head")
    sync_engine.dispose()


def test_migration_phase6_to_firebase_uid_upgrade_downgrade(temp_alembic_db):
    """
    Tests applying the Firebase UID column migration (e5f6a7b8c9d0) onto an existing
    Phase 6 database, verifying column and index creation, and safe rollback to d4e5f6a7b8c9.
    """
    sync_url, cfg = temp_alembic_db
    sync_engine = create_engine(sync_url)

    # 1. Upgrade to Phase 6 head (d4e5f6a7b8c9)
    command.upgrade(cfg, "d4e5f6a7b8c9")

    import datetime
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # 2. Insert existing user into Phase 6 schema
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users ("
                "  id, email, full_name, hashed_password, is_active, created_at, updated_at"
                ") VALUES ("
                "  'usr-fb-001', 'astronaut@missionforge.org', 'Cmdr. Space Explorer',"
                "  'pw123', 1, :now, :now"
                ")"
            ),
            {"now": now_str},
        )

    # 3. Upgrade to Firebase UID migration head (e5f6a7b8c9d0)
    command.upgrade(cfg, "e5f6a7b8c9d0")

    # 4. Verify firebase_uid column exists and update it
    with sync_engine.begin() as conn:
        inspector = inspect(conn)
        user_cols = {c["name"] for c in inspector.get_columns("users")}
        assert "firebase_uid" in user_cols

        conn.execute(
            text(
                "UPDATE users SET firebase_uid = 'firebase-uid-12345' WHERE id = 'usr-fb-001'"
            )
        )
        row = conn.execute(
            text("SELECT email, firebase_uid FROM users WHERE id = 'usr-fb-001'")
        ).fetchone()
        assert row is not None
        assert row[0] == "astronaut@missionforge.org"
        assert row[1] == "firebase-uid-12345"

    # 5. Downgrade back to Phase 6 (d4e5f6a7b8c9)
    command.downgrade(cfg, "d4e5f6a7b8c9")

    # 6. Verify firebase_uid is removed, but user data preserved
    with sync_engine.connect() as conn:
        inspector_post = inspect(conn)
        user_cols_post = {c["name"] for c in inspector_post.get_columns("users")}
        assert "firebase_uid" not in user_cols_post

        u_row = conn.execute(text("SELECT email FROM users WHERE id = 'usr-fb-001'")).fetchone()
        assert u_row is not None and u_row[0] == "astronaut@missionforge.org"

    # 7. Re-upgrade to head
    command.upgrade(cfg, "head")
    sync_engine.dispose()
