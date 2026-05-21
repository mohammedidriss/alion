"""Migrate local SQLite → Railway PostgreSQL.

Usage:
    uv run python scripts/migrate_sqlite_to_pg.py

Reads from data/alion.db, writes to the Railway PG URL.
Safe to re-run: uses INSERT ... ON CONFLICT DO NOTHING so existing rows
are silently skipped.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "store"))
# NOTE: do NOT add packages/common — it contains logging.py which shadows stdlib

import sqlite3  # noqa: E402

import sqlalchemy as sa  # noqa: E402

# Import all models so SQLModel.metadata knows every table
from models import (  # noqa: E402, F401
    Allergy,
    CheckIn,
    Coach,
    CoachAdviceCacheRow,
    CoachAssignment,
    CoachNote,
    ConsensusEventRow,
    Fighter,
    FighterSponsor,
    FighterTitle,
    Gym,
    GymManager,
    GymMembership,
    HRSampleRow,
    IMUSampleRow,
    MedicalCondition,
    MedicalRecord,
    Medication,
    PunchEventRow,
    RaterScoreRow,
    Referee,
    RoundPlanRow,
    SessionAttachment,
    User,
    WeighIn,
)
from sqlmodel import SQLModel, create_engine  # noqa: E402

SQLITE_PATH = ROOT / "data" / "alion.db"
PG_URL = (
    "postgresql+psycopg2://postgres:aqbvpSUvysBGrBchtlxzEcYsupBPHpbC"
    "@caboose.proxy.rlwy.net:21524/railway"
)

# Tables in FK-dependency order (parents first)
TABLES = [
    "user",
    "gym",
    "gym_manager",
    "fighter",
    "coach",
    "referee",
    "session",
    "gym_membership",
    "check_in",
    "weigh_in",
    "medical_record",
    "allergy",
    "medication",
    "medical_condition",
    "fighter_title",
    "fighter_sponsor",
    "coach_assignment",
    "coach_note",
    "punch_event",
    "hr_sample",
    "imu_sample",
    "consensus_event",
    "coach_advice_cache",
    "rq1_rating",
    "round_plan",
    "session_attachment",
]


def migrate() -> None:
    print(f"Source : {SQLITE_PATH}")
    print(f"Target : {PG_URL[:55]}…\n")

    if not SQLITE_PATH.exists():
        sys.exit(f"ERROR: SQLite file not found at {SQLITE_PATH}")

    src = sqlite3.connect(str(SQLITE_PATH))
    src.row_factory = sqlite3.Row

    pg_engine = create_engine(PG_URL, echo=False, pool_pre_ping=True)

    print("Creating tables in PostgreSQL (if not exist)…")
    SQLModel.metadata.create_all(pg_engine)
    print("  done.\n")

    # Disable FK constraint checks for the duration of the bulk load
    # (SQLite didn't enforce them, so some dangling FKs may exist in the source)
    with pg_engine.begin() as conn:
        conn.execute(sa.text("SET session_replication_role = replica"))

    total_in = 0

    for table_name in TABLES:
        exists = src.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        if not exists:
            continue

        rows = src.execute(f"SELECT * FROM '{table_name}'").fetchall()
        if not rows:
            print(f"  [{table_name:30s}]  0 rows")
            continue

        cols = [d[0] for d in src.execute(
            f"SELECT * FROM '{table_name}' LIMIT 0"
        ).description]

        tbl = SQLModel.metadata.tables[table_name]

        # Build list of dicts, sanitising empty strings → None for nullable cols
        records = []
        for row in rows:
            d = dict(zip(cols, tuple(row), strict=False))
            for k, v in d.items():
                col = tbl.c.get(k)
                if col is not None and v == "" and col.nullable:
                    d[k] = None
            records.append(d)

        # INSERT … ON CONFLICT DO NOTHING — whole table in one transaction
        stmt = sa.dialects.postgresql.insert(tbl).on_conflict_do_nothing()
        with pg_engine.begin() as conn:
            conn.execute(stmt, records)

        # Count what actually landed by querying PG
        with pg_engine.connect() as conn:
            pg_count = conn.execute(sa.select(sa.func.count()).select_from(tbl)).scalar()

        print(f"  [{table_name:30s}]  {len(records):5d} src rows  →  {pg_count:5d} in PG")
        total_in += len(records)

    # Re-enable FK checks
    with pg_engine.begin() as conn:
        conn.execute(sa.text("SET session_replication_role = DEFAULT"))

    src.close()
    print(f"\n✓ Done — {total_in} source rows processed across {len(TABLES)} tables.")


if __name__ == "__main__":
    migrate()
