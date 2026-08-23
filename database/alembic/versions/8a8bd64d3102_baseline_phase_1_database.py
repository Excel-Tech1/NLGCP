"""Baseline the existing Phase 1 database.

Revision ID: 8a8bd64d3102
Revises:
Create Date: 2026-08-23

This revision intentionally performs no schema changes.

The database already contains the Phase 1 bootstrap state:
- PostGIS
- schema_migrations
- 001_enable_postgis

Alembic adoption begins from this existing verified state.
"""

revision: str = "8a8bd64d3102"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    """Represent the already-existing Phase 1 schema."""
    pass


def downgrade() -> None:
    """No schema objects are owned by this baseline revision."""
    pass
