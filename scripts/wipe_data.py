"""IRB-compliant data scrub: wipe all athlete data.

Per Gemini's recommendation #3 — "since there is no cloud backup, a single
'Wipe All Athlete Data' command must exist that performs a secure deletion
of the SQLite file and the /data/ directory."

This is destructive and irreversible. The script requires the user to type
the literal string DELETE EVERYTHING to proceed.

Removes:
  - The SQLite DB (data/alion.db)
  - data/processed/  (parquet pose files)
  - data/raw/        (uploaded videos, HRV CSVs)
  - data/photos/     (profile photos)

Re-creates the DB schema after wipe so the API still starts.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from common import get_settings
from store import create_db_and_tables

CONFIRM_PHRASE = "DELETE EVERYTHING"


def _resolve_paths() -> tuple[Path, list[Path]]:
    settings = get_settings()
    # settings.database_url is e.g. "sqlite:///data/alion.db"
    db_url = str(settings.database_url)
    if db_url.startswith("sqlite:///"):
        db_path = Path(db_url.removeprefix("sqlite:///"))
    elif db_url.startswith("sqlite://"):
        db_path = Path(db_url.removeprefix("sqlite://"))
    else:
        # Non-sqlite — refuse to guess what file holds the data.
        print(
            f"refusing to wipe: non-sqlite database_url ({db_url}). "
            "This script only handles the local sqlite setup.",
            file=sys.stderr,
        )
        sys.exit(2)

    data_dirs = [
        Path("data/processed"),
        Path("data/raw"),
        Path("data/photos"),
    ]
    return db_path, data_dirs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--yes",
        action="store_true",
        help="non-interactive — skip the typed-confirmation prompt",
    )
    ap.add_argument(
        "--keep-photos",
        action="store_true",
        help="preserve profile photos (keeps data/photos/)",
    )
    args = ap.parse_args()

    db_path, data_dirs = _resolve_paths()
    if args.keep_photos:
        data_dirs = [d for d in data_dirs if d.name != "photos"]

    print("This will permanently delete:")
    print(f"  - {db_path} (sqlite database)")
    for d in data_dirs:
        print(f"  - {d}/ (recursive)")
    print("\nThis cannot be undone. There is no backup.\n")

    if not args.yes:
        typed = input(f"Type {CONFIRM_PHRASE!r} to proceed (or anything else to abort): ")
        if typed != CONFIRM_PHRASE:
            print("Aborted.")
            return 1

    # Delete db
    if db_path.exists():
        try:
            db_path.unlink()
            print(f"removed {db_path}")
        except OSError as e:
            print(f"failed to remove {db_path}: {e}", file=sys.stderr)
            return 3
    else:
        print(f"(skipped, not found: {db_path})")

    # Delete data dirs
    for d in data_dirs:
        if d.exists():
            try:
                shutil.rmtree(d)
                print(f"removed {d}/")
            except OSError as e:
                print(f"failed to remove {d}: {e}", file=sys.stderr)
                return 3
        else:
            print(f"(skipped, not found: {d}/)")

    # Re-create schema so the API still starts (empty DB).
    create_db_and_tables()
    print("\nFresh empty database initialised. Wipe complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
