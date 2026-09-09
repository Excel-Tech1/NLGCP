"""Tests for Phase 8 handoff, provenance, subjects, and determinism.

SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS.
"""

from __future__ import annotations

from pathlib import Path

from nlgcp_rtcm_replay import ENGINE_VERSION, PARSER_VERSION, fixtures
from nlgcp_rtcm_replay.admission import source_fingerprint
from nlgcp_rtcm_replay.framing import parse_stream
from nlgcp_rtcm_replay.handoff import handoff_from_dict, resolve_handoff
from nlgcp_rtcm_replay.models import (
    SELECTED_CORRECTION_SOURCE_UNAVAILABLE,
    CorrectionFrame,
    ReplayConfig,
)
from nlgcp_rtcm_replay.provenance import (
    build_provenance,
    config_fingerprint,
    sha256_canonical,
)
from nlgcp_rtcm_replay.subjects import envelope, ordering_key, replay_subject
from phase9_fixtures import make_valid_source, synthetic_source, write_source_file


def _handoff(mode: str, reference: str | None = None) -> dict[str, object]:
    return {
        "mode": mode,
        "source": reference or "NO_CORRECTION",
        "reference_station": reference,
        "virtual_station": None,
        "status": "OK" if mode != "NO_CORRECTION" else "BLOCKED",
        "provenance": {"decision_fingerprint": "phase8-test-fp"},
    }


def test_single_base_handoff_binds_matching_source(tmp_path: Path) -> None:
    _, source, _ = make_valid_source(tmp_path, station_id="SYN00TST")
    decision = handoff_from_dict(_handoff("SINGLE_BASE", "SYN00TST"))
    outcome = resolve_handoff(decision, [source])
    assert outcome.admitted
    assert outcome.selected_source_id == source.source_id
    assert "transport success != positioning success" in outcome.reason


def test_single_base_incompatible_source_blocked(tmp_path: Path) -> None:
    # Scenario E: Phase 8 selects EKAK but no EKAK recording exists.
    _, source, _ = make_valid_source(tmp_path, station_id="SYN00TST")
    decision = handoff_from_dict(_handoff("SINGLE_BASE", "EKAK00NGA"))
    outcome = resolve_handoff(decision, [source])
    assert not outcome.admitted
    assert SELECTED_CORRECTION_SOURCE_UNAVAILABLE in outcome.reason


def test_no_correction_emits_nothing(tmp_path: Path) -> None:
    _, source, _ = make_valid_source(tmp_path)
    decision = handoff_from_dict(_handoff("NO_CORRECTION"))
    outcome = resolve_handoff(decision, [source])
    assert outcome.admitted
    assert outcome.selected_source_id is None


def test_vrs_without_artifact_blocked(tmp_path: Path) -> None:
    _, source, _ = make_valid_source(tmp_path)
    payload = _handoff("VRS")
    payload["virtual_station"] = "VRS00SYN"
    decision = handoff_from_dict(payload)
    outcome = resolve_handoff(decision, [source])
    assert not outcome.admitted
    assert "VRS_CORRECTION_ARTIFACT_UNAVAILABLE" in outcome.reason


def test_unknown_mode_blocked(tmp_path: Path) -> None:
    _, source, _ = make_valid_source(tmp_path)
    decision = handoff_from_dict(_handoff("SOMETHING_ELSE"))
    outcome = resolve_handoff(decision, [source])
    assert not outcome.admitted


def test_malformed_handoff_fails_closed() -> None:
    try:
        handoff_from_dict({})
    except ValueError as exc:
        assert "malformed Phase 8 handoff" in str(exc)
    else:
        raise AssertionError("malformed handoff must fail closed")


def test_no_silent_station_substitution(tmp_path: Path) -> None:
    stream, _ = fixtures.valid_fixture_stream()
    path = write_source_file(tmp_path, "other.rtcm3", stream)
    other = synthetic_source(path, source_id="syn-other", station_id="SYN99OTH")
    decision = handoff_from_dict(_handoff("SINGLE_BASE", "SYN00TST"))
    outcome = resolve_handoff(decision, [other])
    assert not outcome.admitted


def test_provenance_record_complete(tmp_path: Path) -> None:
    _, source, _ = make_valid_source(tmp_path)
    config = ReplayConfig(speed=0.0)
    provenance = build_provenance(
        source_sha256=source.sha256,
        source_metadata=source.as_dict(),
        frame_inventory_fingerprint="inv-fp",
        phase8_decision_fingerprint="phase8-test-fp",
        selected_correction_source=source.source_id,
        replay_config_fingerprint=config_fingerprint(config),
        execution_timestamp="2026-09-09T00:00:00Z",
        git_commit="test-commit",
        working_tree_clean=True,
    )
    for key in (
        "source_sha256",
        "frame_inventory_fingerprint",
        "phase8_decision_fingerprint",
        "selected_correction_source",
        "replay_config_fingerprint",
        "software_version",
        "git_commit",
        "execution_timestamp",
    ):
        assert key in provenance
    assert provenance["software_version"] == ENGINE_VERSION


def test_config_fingerprint_invalidates_on_change() -> None:
    base = ReplayConfig(speed=0.0)
    changed = ReplayConfig(speed=1.0)
    assert config_fingerprint(base) != config_fingerprint(changed)
    filtered = ReplayConfig(speed=0.0, message_filter=(1077,))
    assert config_fingerprint(base) != config_fingerprint(filtered)


def test_source_fingerprint_changes_with_bytes(tmp_path: Path) -> None:
    _, source, _ = make_valid_source(tmp_path)
    assert source_fingerprint(source, source.sha256) != source_fingerprint(
        source, "0" * 64
    )


def test_canonical_hash_deterministic() -> None:
    assert sha256_canonical({"b": 1, "a": 2}) == sha256_canonical({"a": 2, "b": 1})


def test_parser_version_recorded() -> None:
    assert PARSER_VERSION == "1.0"


def test_replay_subject_follows_correction_family() -> None:
    assert replay_subject("SYN00TST") == "correction.replay.SYN00TST"
    try:
        replay_subject("bad station!")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe station must be rejected")


def test_ordering_key_and_envelope() -> None:
    frame = CorrectionFrame(
        sequence=3,
        cycle=1,
        source_id="s",
        station_id="SYN00TST",
        mountpoint="SYNTHETIC",
        message_number=1077,
        raw_bytes=b"\xd3\x00",
        source_timestamp="3000",
        replay_timestamp="3",
        provenance={},
    )
    assert ordering_key(frame) == ("s", 1, 3)
    env = envelope(frame)
    assert env["subject"] == "correction.replay.SYN00TST"
    assert env["ordering_key"] == ["s", 1, 3]


def test_timeline_inventory_crosscheck(tmp_path: Path) -> None:
    # Inventory fingerprint covers every discovered frame hash; timeline
    # replays exactly the CRC-valid subset — provenance links both.
    from nlgcp_rtcm_replay import PARSER_VERSION as PV
    from nlgcp_rtcm_replay.inventory import build_inventory
    from nlgcp_rtcm_replay.timing import build_timeline

    stream, _ = fixtures.corrupt_fixture_stream()
    result = parse_stream(stream)
    inventory = build_inventory(result, parser_version=PV)
    schedule = fixtures.synthetic_schedule(len(result.frames))
    events, _ = build_timeline(result.frames, arrival_ms=schedule)
    assert inventory.frames_valid == len(events) == 7
    assert inventory.inventory_fingerprint
