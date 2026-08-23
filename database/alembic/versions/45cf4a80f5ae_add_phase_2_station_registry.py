"""Add the Phase 2 station registry.

Revision ID: 45cf4a80f5ae
Revises: 8a8bd64d3102
Create Date: 2026-08-23

This migration creates the authoritative structured foundation for
historical GNSS station metadata.

No real stations or scientific observations are inserted by this
migration.

Coordinate and equipment records are effective-dated so historical
observations can later be associated with the metadata valid at their
observation epoch.

Unknown scientific metadata remains nullable rather than being invented.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "45cf4a80f5ae"
down_revision: str | None = "8a8bd64d3102"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    """Create the Phase 2 station-registry tables."""

    op.create_table(
        "metadata_sources",
        sa.Column(
            "metadata_source_id",
            sa.BigInteger(),
            sa.Identity(),
            primary_key=True,
        ),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column(
            "retrieved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "sha256 IS NULL OR char_length(sha256) = 64",
            name="ck_metadata_sources_sha256_length",
        ),
    )

    op.create_table(
        "providers",
        sa.Column(
            "provider_id",
            sa.BigInteger(),
            sa.Identity(),
            primary_key=True,
        ),
        sa.Column("provider_code", sa.Text(), nullable=False),
        sa.Column("provider_name", sa.Text(), nullable=False),
        sa.Column("operator_name", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "provider_code",
            name="uq_providers_provider_code",
        ),
    )

    op.create_table(
        "stations",
        sa.Column(
            "station_id",
            sa.BigInteger(),
            sa.Identity(),
            primary_key=True,
        ),
        sa.Column(
            "provider_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "providers.provider_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("station_code", sa.Text(), nullable=False),
        sa.Column("station_name", sa.Text(), nullable=True),
        sa.Column("network", sa.Text(), nullable=True),
        sa.Column("operator_name", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column(
            "first_observation",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_observation",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "metadata_source_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "metadata_sources.metadata_source_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "provider_id",
            "station_code",
            name="uq_stations_provider_station_code",
        ),
        sa.CheckConstraint(
            """
            last_observation IS NULL
            OR first_observation IS NULL
            OR last_observation >= first_observation
            """,
            name="ck_stations_observation_interval",
        ),
    )

    op.create_index(
        "ix_stations_station_code",
        "stations",
        ["station_code"],
    )

    op.create_index(
        "ix_stations_network",
        "stations",
        ["network"],
    )

    op.create_table(
        "station_coordinates",
        sa.Column(
            "coordinate_id",
            sa.BigInteger(),
            sa.Identity(),
            primary_key=True,
        ),
        sa.Column(
            "station_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "stations.station_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "latitude_deg",
            sa.Numeric(precision=12, scale=9),
            nullable=True,
        ),
        sa.Column(
            "longitude_deg",
            sa.Numeric(precision=12, scale=9),
            nullable=True,
        ),
        sa.Column(
            "ellipsoidal_height_m",
            sa.Numeric(precision=14, scale=5),
            nullable=True,
        ),
        sa.Column(
            "ecef_x_m",
            sa.Numeric(precision=16, scale=5),
            nullable=True,
        ),
        sa.Column(
            "ecef_y_m",
            sa.Numeric(precision=16, scale=5),
            nullable=True,
        ),
        sa.Column(
            "ecef_z_m",
            sa.Numeric(precision=16, scale=5),
            nullable=True,
        ),
        sa.Column("reference_frame", sa.Text(), nullable=True),
        sa.Column(
            "coordinate_epoch",
            sa.Numeric(precision=9, scale=4),
            nullable=True,
        ),
        sa.Column("solution_method", sa.Text(), nullable=True),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "valid_to",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "metadata_source_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "metadata_sources.metadata_source_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            """
            latitude_deg IS NULL
            OR (latitude_deg >= -90 AND latitude_deg <= 90)
            """,
            name="ck_station_coordinates_latitude",
        ),
        sa.CheckConstraint(
            """
            longitude_deg IS NULL
            OR (longitude_deg >= -180 AND longitude_deg <= 180)
            """,
            name="ck_station_coordinates_longitude",
        ),
        sa.CheckConstraint(
            """
            (latitude_deg IS NULL AND longitude_deg IS NULL)
            OR
            (latitude_deg IS NOT NULL AND longitude_deg IS NOT NULL)
            """,
            name="ck_station_coordinates_geodetic_pair",
        ),
        sa.CheckConstraint(
            """
            (
                ecef_x_m IS NULL
                AND ecef_y_m IS NULL
                AND ecef_z_m IS NULL
            )
            OR
            (
                ecef_x_m IS NOT NULL
                AND ecef_y_m IS NOT NULL
                AND ecef_z_m IS NOT NULL
            )
            """,
            name="ck_station_coordinates_ecef_triplet",
        ),
        sa.CheckConstraint(
            """
            (latitude_deg IS NOT NULL AND longitude_deg IS NOT NULL)
            OR
            (
                ecef_x_m IS NOT NULL
                AND ecef_y_m IS NOT NULL
                AND ecef_z_m IS NOT NULL
            )
            """,
            name="ck_station_coordinates_has_coordinate",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_station_coordinates_valid_interval",
        ),
    )

    op.create_index(
        "ix_station_coordinates_station_validity",
        "station_coordinates",
        ["station_id", "valid_from", "valid_to"],
    )

    op.create_table(
        "station_equipment",
        sa.Column(
            "equipment_id",
            sa.BigInteger(),
            sa.Identity(),
            primary_key=True,
        ),
        sa.Column(
            "station_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "stations.station_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("receiver_model", sa.Text(), nullable=True),
        sa.Column("receiver_serial", sa.Text(), nullable=True),
        sa.Column("receiver_firmware", sa.Text(), nullable=True),
        sa.Column("antenna_model", sa.Text(), nullable=True),
        sa.Column("antenna_serial", sa.Text(), nullable=True),
        sa.Column("radome", sa.Text(), nullable=True),
        sa.Column(
            "antenna_height_m",
            sa.Numeric(precision=10, scale=5),
            nullable=True,
        ),
        sa.Column(
            "antenna_height_reference",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "valid_to",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "metadata_source_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "metadata_sources.metadata_source_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_station_equipment_valid_interval",
        ),
        sa.CheckConstraint(
            "antenna_height_m IS NULL OR antenna_height_m >= 0",
            name="ck_station_equipment_antenna_height",
        ),
    )

    op.create_index(
        "ix_station_equipment_station_validity",
        "station_equipment",
        ["station_id", "valid_from", "valid_to"],
    )


def downgrade() -> None:
    """Remove the Phase 2 station-registry tables."""

    op.drop_index(
        "ix_station_equipment_station_validity",
        table_name="station_equipment",
    )
    op.drop_table("station_equipment")

    op.drop_index(
        "ix_station_coordinates_station_validity",
        table_name="station_coordinates",
    )
    op.drop_table("station_coordinates")

    op.drop_index(
        "ix_stations_network",
        table_name="stations",
    )
    op.drop_index(
        "ix_stations_station_code",
        table_name="stations",
    )
    op.drop_table("stations")

    op.drop_table("providers")
    op.drop_table("metadata_sources")
