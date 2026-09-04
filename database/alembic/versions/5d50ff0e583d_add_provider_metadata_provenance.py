"""Add provider metadata provenance.

Revision ID: 5d50ff0e583d
Revises: 45cf4a80f5ae
Create Date: 2026-08-24

Providers must retain provenance just like stations, coordinates, and
equipment. Source records also retain the vault-relative path used by the
provenance-controlled importer so repeated imports can resolve the same
source deterministically.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "5d50ff0e583d"
down_revision: str | None = "45cf4a80f5ae"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    """Add provenance reference to providers."""

    op.add_column(
        "metadata_sources",
        sa.Column(
            "source_path",
            sa.Text(),
            nullable=True,
        ),
    )

    op.create_unique_constraint(
        "uq_metadata_sources_identity",
        "metadata_sources",
        [
            "source_type",
            "source_reference",
            "source_path",
            "sha256",
        ],
    )

    op.add_column(
        "providers",
        sa.Column(
            "metadata_source_id",
            sa.BigInteger(),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_providers_metadata_source_id",
        "providers",
        "metadata_sources",
        ["metadata_source_id"],
        ["metadata_source_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Remove provider provenance reference."""

    op.drop_constraint(
        "fk_providers_metadata_source_id",
        "providers",
        type_="foreignkey",
    )

    op.drop_column(
        "providers",
        "metadata_source_id",
    )

    op.drop_constraint(
        "uq_metadata_sources_identity",
        "metadata_sources",
        type_="unique",
    )

    op.drop_column(
        "metadata_sources",
        "source_path",
    )
