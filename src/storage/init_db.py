from __future__ import annotations

import argparse
from pathlib import Path

from .sqlite import SQLiteDatabase, initialize_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize a SwarmOS SQLite database.")
    parser.add_argument(
        "--db-path",
        required=True,
        help="Path to the SQLite database file.",
    )
    parser.add_argument(
        "--migration-dir",
        default=None,
        help="Optional directory containing SQL migrations.",
    )
    args = parser.parse_args()

    db = SQLiteDatabase(Path(args.db_path))
    initialize_database(db, args.migration_dir)
    db.close()
    print(f"Initialized database at {args.db_path}")


if __name__ == "__main__":
    main()
