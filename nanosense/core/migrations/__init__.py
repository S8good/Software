# nanosense/core/migrations/__init__.py
"""
Registry for database migrations.

Each migration module should expose a callable `apply(conn: sqlite3.Connection)`
and register itself by appending `(migration_id, apply)` to `MIGRATIONS`.
`migration_id` must be unique and sortable (e.g. zero-padded numeric prefixes).
"""

from typing import Callable, List, Tuple
import sqlite3

from . import migration_0001_prepare_phase1_schema
from . import migration_0002_snapshot_soft_delete
from . import migration_0003_database_p0

MigrationFunc = Callable[[sqlite3.Connection], None]
MigrationDescriptor = Tuple[str, MigrationFunc]

MIGRATIONS: List[MigrationDescriptor] = [
    (
        migration_0001_prepare_phase1_schema.MIGRATION_ID,
        migration_0001_prepare_phase1_schema.apply,
    ),
    (
        migration_0002_snapshot_soft_delete.MIGRATION_ID,
        migration_0002_snapshot_soft_delete.apply,
    ),
    (
        migration_0003_database_p0.MIGRATION_ID,
        migration_0003_database_p0.apply,
    ),
]

__all__ = ["MIGRATIONS", "MigrationFunc", "MigrationDescriptor"]
