"""SYNTHETIC TEST DATA — NOT VALID FOR SCIENTIFIC RESULTS."""

from __future__ import annotations

from dataclasses import replace

import pytest
from nlgcp_rtcm_generation import ENCODER_VERSION
from nlgcp_rtcm_generation.admission import admit_request
from nlgcp_rtcm_generation.bitstream import BitReader, BitWriter
from nlgcp_rtcm_generation.fields import FieldSpec
from nlgcp_rtcm_generation.generator import CorrectionGenerator
from nlgcp_rtcm_generation.lab import LocalLabConsumer, to_phase9_frame
from nlgcp_rtcm_generation.models import (
    CoordinateProvenance,
    CorrectionGenerationRequest,
    EpochContract,
    GenerationMode,
    GenerationStatus,
    OutputClassification,
    ReasonCode,
    VerificationState,
)
from nlgcp_rtcm_generation.provenance import fingerprint
from nlgcp_rtcm_generation.registry import MessageFamilyRegistry
from nlgcp_rtcm_generation.validation import validate_frame


def synthetic_request(
    *, mode: GenerationMode = GenerationMode.SINGLE_BASE, family: str = "SYNTHETIC_TEST_FRAME"
) -> CorrectionGenerationRequest:
    coordinate = CoordinateProvenance(
        station_id="SYNA00SYN",
        ecef_xyz_m=(1.0, 2.0, 3.0),
        reference_frame="SYNTHETIC_FRAME",
        coordinate_epoch="2026-01-01T00:00:00Z",
        source="SYNTHETIC TEST DATA",
        fingerprint="synthetic-coordinate-fp",
        verification_state=VerificationState.SYNTHETIC_TEST_ONLY,
    )
    return CorrectionGenerationRequest(
        request_id="request-syn-001",
        decision_id="decision-syn-001",
        decision_fingerprint="decision-fp",
        decision_status="OK",
        mode=mode,
        reference_station_id="SYNA00SYN",
        virtual_station_id=None,
        coordinate=coordinate,
        epoch=EpochContract("2026-01-01T00:00:00Z", "2026-01-01T00:00:00.100Z"),
        gnss_systems=("GPS",),
        input_source_fingerprint="synthetic-input-fp",
        input_source_admitted=True,
        station_identity_verified=True,
        coordinate_verified=True,
        correction_model_fingerprint="synthetic-model-fp",
        correction_model_approved=True,
        output_message_family=family,
        encoder_version=ENCODER_VERSION,
        scientific_status="SYNTHETIC_TEST_ONLY",
        classification=OutputClassification.SYNTHETIC_TEST_ONLY,
        synthetic_fixture=True,
    )


def test_no_correction_generates_no_frames() -> None:
    request = synthetic_request(mode=GenerationMode.NO_CORRECTION)
    result = CorrectionGenerator().generate(request)
    assert result.status == GenerationStatus.NO_CORRECTION
    assert result.frames == ()
    assert result.reason_codes == (ReasonCode.NO_CORRECTION_REQUESTED,)


def test_current_vrs_path_is_blocked() -> None:
    request = synthetic_request(mode=GenerationMode.VRS)
    result = CorrectionGenerator().generate(request)
    assert result.status == GenerationStatus.BLOCKED
    assert ReasonCode.VRS_OPERATIONAL_NOT_APPROVED in result.reason_codes
    assert ReasonCode.CORRECTION_MODEL_NOT_APPROVED in result.reason_codes


def test_single_base_without_authentic_input_is_blocked() -> None:
    request = replace(synthetic_request(), input_source_admitted=False)
    result = CorrectionGenerator().generate(request)
    assert result.status == GenerationStatus.BLOCKED
    assert ReasonCode.INPUT_SOURCE_UNVERIFIED in result.reason_codes


def test_unverified_coordinates_and_missing_epoch_are_blocked() -> None:
    request = replace(
        synthetic_request(),
        coordinate_verified=False,
        epoch=EpochContract(None),
    )
    admission = admit_request(request)
    assert not admission.admissible
    assert ReasonCode.COORDINATE_UNVERIFIED in admission.reason_codes
    assert ReasonCode.GNSS_EPOCH_UNAVAILABLE in admission.reason_codes


def test_operational_classification_can_never_be_emitted() -> None:
    request = replace(
        synthetic_request(),
        classification=OutputClassification.OPERATIONAL_APPROVED,
    )
    result = CorrectionGenerator().generate(request)
    assert result.status == GenerationStatus.BLOCKED
    assert ReasonCode.OPERATIONAL_CLASSIFICATION_FORBIDDEN in result.reason_codes


def test_scaffolded_real_message_family_has_no_encoder() -> None:
    request = replace(synthetic_request(), output_message_family="REFERENCE_STATION_1005")
    result = CorrectionGenerator().generate(request)
    assert result.status == GenerationStatus.BLOCKED
    assert ReasonCode.UNSUPPORTED_MESSAGE_TYPE in result.reason_codes


def test_synthetic_frame_is_deterministic_and_phase9_compatible() -> None:
    generator = CorrectionGenerator()
    request = synthetic_request()
    first = generator.generate(request, fields={"value": 7})
    second = generator.generate(request, fields={"value": 7})
    assert first.status == GenerationStatus.ENCODED
    assert first.frames[0].raw_bytes == second.frames[0].raw_bytes
    assert first.frames[0].frame_sha256 == second.frames[0].frame_sha256
    validation = validate_frame(first.frames[0])
    assert validation.framing_valid
    assert validation.phase9_compatible
    assert validation.semantic_validation == "NOT_PERFORMED_SYNTHETIC_PAYLOAD"


def test_synthetic_fixture_is_explicitly_labelled() -> None:
    result = CorrectionGenerator().generate(synthetic_request())
    assert "SYNTHETIC" in result.frames[0].raw_bytes.decode("latin1")
    assert result.frames[0].classification == OutputClassification.SYNTHETIC_TEST_ONLY


def test_bit_writer_boundaries_and_round_trip() -> None:
    writer = BitWriter(max_bits=32)
    writer.write_unsigned(0b101, 3)
    writer.write_signed(-2, 4)
    encoded = writer.to_bytes()
    reader = BitReader(encoded)
    assert reader.read_unsigned(3) == 0b101
    assert reader.read_signed(4) == -2


def test_bit_writer_rejects_overflow_and_underflow() -> None:
    writer = BitWriter()
    with pytest.raises(ValueError):
        writer.write_unsigned(8, 3)
    with pytest.raises(ValueError):
        BitReader(b"\x00").read_unsigned(9)


def test_field_spec_rejects_nan_and_range_overflow() -> None:
    spec = FieldSpec("range", 8, False, "m", 0.1, 0.0, 25.5)
    assert spec.validate(float("nan"))
    assert spec.validate(26.0)
    assert spec.encode_integer(1.2) == 12


def test_request_fingerprint_changes_with_input() -> None:
    first = synthetic_request()
    second = replace(first, input_source_fingerprint="different")
    assert fingerprint(first.as_dict()) != fingerprint(second.as_dict())


def test_registry_does_not_claim_operational_support() -> None:
    registry = MessageFamilyRegistry()
    statuses = {row["family_id"]: row["status"] for row in registry.as_dict()}
    assert statuses["REFERENCE_STATION_1005"] == "SCAFFOLDED"
    assert statuses["MSM4_GPS_1074"] == "SCAFFOLDED"
    assert "OPERATIONALLY_APPROVED" not in statuses.values()


def test_local_lab_adapter_preserves_phase9_contract() -> None:
    result = CorrectionGenerator().generate(synthetic_request())
    consumer = LocalLabConsumer()
    phase9_frame = to_phase9_frame(result.frames[0])
    consumer.consume(phase9_frame)
    assert len(consumer.frames) == 1
    assert consumer.frames[0].message_number == 4095
    assert consumer.frames[0].provenance["classification"] == "SYNTHETIC_TEST_ONLY"
