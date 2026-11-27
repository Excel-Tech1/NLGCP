"""Add B-08 runtime control-plane, provider, and audit tables.

Revision ID: 9c4a7e2f1b08
Revises: 5d50ff0e583d
Create Date: 2026-11-27

Creates structured PostgreSQL/PostGIS control-plane tables aligned with
ADR-001 (source-independent ingestion), ADR-006 (PostgreSQL/PostGIS
authoritative store), ADR-007 (separate control and correction planes),
and ADR-011 (fail-closed integrity).

No fabricated stations, credentials, live streams, or GNSS observation
payloads are inserted by this migration. Large GNSS data remains outside
PostgreSQL under ``NLGCP_DATA_ROOT``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9c4a7e2f1b08"
down_revision: str | None = "5d50ff0e583d"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    """Create B-08 control-plane provider, mountpoint, decision, and audit tables."""

    op.create_table(
        "cors_providers",
        sa.Column("cors_provider_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("provider_code", sa.Text(), nullable=False),
        sa.Column("provider_name", sa.Text(), nullable=False),
        sa.Column("operator_name", sa.Text(), nullable=True),
        sa.Column("access_tier", sa.Text(), nullable=False),
        sa.Column("authorization_status", sa.Text(), nullable=False),
        sa.Column("website_url", sa.Text(), nullable=True),
        sa.Column("ntrip_host", sa.Text(), nullable=True),
        sa.Column("ntrip_port", sa.Integer(), nullable=True),
        sa.Column("tls_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "metadata_source_id",
            sa.BigInteger(),
            sa.ForeignKey("metadata_sources.metadata_source_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("provider_code", name="uq_cors_providers_code"),
        sa.CheckConstraint(
            "ntrip_port IS NULL OR (ntrip_port >= 1 AND ntrip_port <= 65535)",
            name="ck_cors_providers_port_range",
        ),
    )

    op.create_table(
        "ntrip_mountpoints",
        sa.Column("mountpoint_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("mountpoint_name", sa.Text(), nullable=False),
        sa.Column(
            "cors_provider_id",
            sa.BigInteger(),
            sa.ForeignKey("cors_providers.cors_provider_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "station_id",
            sa.BigInteger(),
            sa.ForeignKey("stations.station_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("classification", sa.Text(), nullable=False),
        sa.Column("synthetic_only", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "operational_approved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("mountpoint_name", name="uq_ntrip_mountpoints_name"),
        sa.CheckConstraint(
            "operational_approved = false",
            name="ck_ntrip_mountpoints_no_operational_promotion",
        ),
    )

    op.create_table(
        "correction_decisions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("decision_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("selected_reference", sa.Text(), nullable=True),
        sa.Column("spatial_model_status", sa.Text(), nullable=False),
        sa.Column("vrs_status", sa.Text(), nullable=False),
        sa.Column("integrity_status", sa.Text(), nullable=False),
        sa.Column("provenance_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("decision_id", name="uq_correction_decisions_decision_id"),
    )

    op.create_table(
        "rtcm_generation_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("decision_id", sa.Text(), nullable=False),
        sa.Column("message_family", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("classification", sa.Text(), nullable=False),
        sa.Column("frame_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("stream_sha256", sa.String(length=64), nullable=True),
        sa.Column("reason_codes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "classification <> 'OPERATIONAL_APPROVED'",
            name="ck_rtcm_generation_no_operational_approved",
        ),
    )

    op.create_table(
        "ingestion_sessions",
        sa.Column("session_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("session_uuid", sa.Text(), nullable=False),
        sa.Column(
            "cors_provider_id",
            sa.BigInteger(),
            sa.ForeignKey("cors_providers.cors_provider_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("mountpoint_name", sa.Text(), nullable=False),
        sa.Column("ingestion_mode", sa.Text(), nullable=False),
        sa.Column("admission_status", sa.Text(), nullable=False),
        sa.Column("frames_valid", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("frames_crc_fail", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("capture_sha256", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_uuid", name="uq_ingestion_sessions_uuid"),
    )

    op.create_table(
        "control_plane_audit_events",
        sa.Column("audit_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("service_name", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    """Drop B-08 runtime control-plane tables cleanly."""

    op.drop_table("control_plane_audit_events")
    op.drop_table("ingestion_sessions")
    op.drop_table("rtcm_generation_runs")
    op.drop_table("correction_decisions")
    op.drop_table("ntrip_mountpoints")
    op.drop_table("cors_providers")
