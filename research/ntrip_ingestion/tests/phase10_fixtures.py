"""Shared synthetic helpers for Phase 10 tests.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"),
)

from nlgcp_ntrip_ingest.models import NtripConfig  # noqa: E402
from nlgcp_ntrip_ingest.testserver import NtripTestServer  # noqa: E402
from nlgcp_rtcm_replay import fixtures as replay_fixtures  # noqa: E402

SYNTHETIC_MESSAGES = [1005, 1077, 1087, 1005, 1230, 1077, 1006, 1087]


def synthetic_stream() -> tuple[bytes, list[int]]:
    return replay_fixtures.build_stream(SYNTHETIC_MESSAGES), SYNTHETIC_MESSAGES


def single_pass_bytes() -> int:
    """Exact byte budget for one synthetic stream pass (stops before re-stream)."""
    stream, _ = synthetic_stream()
    return len(stream)


def base_config(**overrides: object) -> NtripConfig:
    fields: dict[str, object] = {
        "host": "127.0.0.1",
        "port": 2101,
        "mountpoint": "TEST00SYN",
        "dial_timeout_s": 5.0,
        "tls_timeout_s": 5.0,
        "handshake_timeout_s": 5.0,
        "read_timeout_s": 2.0,
        "idle_timeout_s": 5.0,
        "max_reconnects": 2,
        "reconnect_base_delay_s": 0.01,
        "reconnect_max_delay_s": 0.05,
        "buffer_capacity": 16,
    }
    fields.update(overrides)
    return NtripConfig(**fields)  # type: ignore[arg-type]


def start_server(scenario: str, **kwargs: object) -> NtripTestServer:
    stream, _ = synthetic_stream()
    server = NtripTestServer(scenario, stream_bytes=stream, **kwargs)  # type: ignore[arg-type]
    server.start()
    return server
