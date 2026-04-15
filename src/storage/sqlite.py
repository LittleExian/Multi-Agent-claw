from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any, Iterator, Sequence


class DatabaseInitializationError(RuntimeError):
    """Raised when database initialization cannot proceed safely."""


class SQLiteDatabase:
    """Small SQLite wrapper with row mapping and transaction support."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = RLock()
        self._transaction_depth = 0

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            self._conn = conn
        return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = self.connect()
            is_outermost = self._transaction_depth == 0
            try:
                if is_outermost:
                    conn.execute("BEGIN")
                self._transaction_depth += 1
                yield conn
                self._transaction_depth -= 1
                if is_outermost:
                    conn.commit()
            except Exception:
                self._transaction_depth = max(self._transaction_depth - 1, 0)
                if is_outermost:
                    conn.rollback()
                raise

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        with self.transaction() as conn:
            conn.execute(sql, tuple(params or ()))

    def executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> None:
        with self.transaction() as conn:
            conn.executemany(sql, rows)

    def fetchone(self, sql: str, params: Sequence[Any] | None = None) -> sqlite3.Row | None:
        with self._lock:
            conn = self.connect()
            cur = conn.execute(sql, tuple(params or ()))
            return cur.fetchone()

    def fetchall(self, sql: str, params: Sequence[Any] | None = None) -> list[sqlite3.Row]:
        with self._lock:
            conn = self.connect()
            cur = conn.execute(sql, tuple(params or ()))
            return list(cur.fetchall())

    def scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        row = self.fetchone(sql, params)
        if row is None:
            return None
        return row[0]

    def table_names(self) -> list[str]:
        rows = self.fetchall(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
        return [row["name"] for row in rows]


def _ensure_migrations_table(db: SQLiteDatabase) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
        """
    )


def initialize_database(
    db: SQLiteDatabase,
    migration_dir: str | Path | None = None,
) -> None:
    migration_root = Path(migration_dir) if migration_dir else Path(__file__).resolve().parents[2] / "sql"
    init_file = migration_root / "001_init.sql"
    if not init_file.exists():
        raise FileNotFoundError(f"Migration file not found: {init_file}")

    _ensure_migrations_table(db)
    already_applied = db.scalar(
        "SELECT 1 FROM schema_migrations WHERE version = ?",
        ("001_init",),
    )
    if already_applied:
        return

    existing_tables = set(db.table_names()) - {"schema_migrations"}
    if existing_tables:
        raise DatabaseInitializationError(
            "Database already contains tables but 001_init is not marked as applied. "
            "Refusing to run init migration automatically."
        )

    schema_sql = init_file.read_text(encoding="utf-8")
    with db.transaction() as conn:
        conn.executescript(schema_sql)
        conn.execute(
            "INSERT INTO schema_migrations(version) VALUES (?)",
            ("001_init",),
        )
