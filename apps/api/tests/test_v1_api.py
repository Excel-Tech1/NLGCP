"""Tests for Milestone B-08 Read-Only /api/v1 Control-Plane Endpoints & Migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from nlgcp_api.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_all_ten_v1_control_plane_endpoints_read_only_and_fail_closed() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Existing /health remains byte-identical
        r0 = await client.get("/health")
        assert r0.status_code == 200
        assert r0.json() == {"status": "ok", "service": "nlgcp-api"}

        # 1. Health summary separates process health from scientific validity
        r1 = await client.get("/api/v1/health/summary")
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["process_health"] == "OK"
        assert d1["scientific_validity"] == "NOT_ASSESSED"
        assert d1["operational_approved"] is False

        # 2. Stations catalogue (read-only B-04 provenance)
        r2 = await client.get("/api/v1/stations")
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["count"] >= 9
        assert d2["live_cors_ingestion_status"] == "BLOCKED_NO_AUTHORIZED_LIVE_CREDENTIALS"

        r2_osgf = await client.get("/api/v1/stations/OSGF")
        assert r2_osgf.status_code == 200
        assert r2_osgf.json()["station_id"] == "OSGF"
        assert r2_osgf.json()["live_stream_connected"] is False

        r2_miss = await client.get("/api/v1/stations/NONEXISTENT99")
        assert r2_miss.status_code == 404

        # 3. Correction engine status
        r3 = await client.get("/api/v1/correction/engine/status")
        assert r3.status_code == 200
        d3 = r3.json()
        assert d3["phase6_operational_spatial_default"] == "ZERO"
        assert d3["phase7_operational_vrs_mode"] == "VRS_GEOMETRY_ONLY"
        assert d3["operational_approved"] is False
        assert d3["operational_classification_policy"] == "FORBIDDEN"

        # 4. RTCM stats
        r4 = await client.get("/api/v1/correction/rtcm/stats")
        assert r4.status_code == 200
        d4 = r4.json()
        assert d4["operational_approved"] is False
        families = {row["family_id"]: row["status"] for row in d4["message_families"]}
        assert families["REFERENCE_STATION_1005"] == "SYNTHETICALLY_VALIDATED"
        assert "OPERATIONALLY_APPROVED" not in families.values()

        # 5-7. Caster status, clients, mountpoints
        r5 = await client.get("/api/v1/caster/status")
        assert r5.status_code == 200
        assert r5.json()["network_boundary"] == "127.0.0.1_LOOPBACK_ONLY"

        r6 = await client.get("/api/v1/caster/clients")
        assert r6.status_code == 200
        assert "sessions" in r6.json()

        r7 = await client.get("/api/v1/caster/mountpoints")
        assert r7.status_code == 200
        assert "mountpoints" in r7.json()

        # 8-9. Diagnostics & errors
        r8 = await client.get("/api/v1/diagnostics")
        assert r8.status_code == 200
        assert "SCIENTIFIC_READINESS" in r8.json()["caster_health"]

        r9 = await client.get("/api/v1/diagnostics/errors?limit=10")
        assert r9.status_code == 200
        assert r9.json()["limit"] == 10

        # 10. Scientific readiness gate ledger
        r10 = await client.get("/api/v1/readiness/scientific")
        assert r10.status_code == 200
        d10 = r10.json()
        assert d10["operational_approved"] is False
        assert d10["operational_classification"] == "FORBIDDEN"
        assert d10["gates"]["phase6_operational_spatial_model"] == "ZERO"


def test_b08_alembic_migration_chains_cleanly_off_phase2_head() -> None:
    mig = (
        Path(__file__).resolve().parents[3]
        / "database/alembic/versions/9c4a7e2f1b08_add_b08_runtime_control_plane_tables.py"
    )
    assert mig.is_file()
    spec = importlib.util.spec_from_file_location("b08_mig", mig)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "9c4a7e2f1b08"
    assert mod.down_revision == "5d50ff0e583d"
    assert callable(mod.upgrade) and callable(mod.downgrade)
