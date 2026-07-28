from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import numpy as np

from .models import CharacterizationCurve, StudyKind


APPROVAL_SCHEMA = "hfss-filter-studio/fd3d-characterization-approval/v1"


def approve_characterization_curve(
    curve_value: CharacterizationCurve | dict[str, Any],
    review: dict[str, Any],
) -> CharacterizationCurve:
    """Approve a characterization only after explicit engineering review."""

    curve = (
        curve_value
        if isinstance(curve_value, CharacterizationCurve)
        else CharacterizationCurve.from_dict(curve_value)
    )
    reviewer = str(review.get("reviewer") or "").strip()
    if not reviewer:
        raise ValueError("reviewer is required")
    evidence = review.get("evidence") or []
    if not isinstance(evidence, list) or not evidence or any(not str(item).strip() for item in evidence):
        raise ValueError("at least one non-empty evidence reference is required")

    backend, solver = _require_real_hfss_source(curve, review)
    minimum_samples = int(review.get("minimum_samples", 3))
    if len(curve.source_samples) < minimum_samples:
        raise ValueError(
            f"characterization requires at least {minimum_samples} solved HFSS samples for approval"
        )
    if curve.monotonic_direction == "non_monotonic" and not bool(
        review.get("segmented_monotonic_branch", False)
    ):
        raise ValueError("non-monotonic characterization must be segmented before approval")

    modal_review = _modal_review(curve, review)
    driven_review = _driven_review(curve, review)
    sign = _coupling_sign_review(curve, review)
    q_review = _quality_review(curve, review)
    approval = {
        "schema": APPROVAL_SCHEMA,
        "reviewer": reviewer,
        "reviewed_at": datetime.now(UTC).isoformat(),
        "evidence": [str(item).strip() for item in evidence],
        "notes": str(review.get("notes") or "").strip(),
        "backend": backend,
        "solver": solver,
        "modal_review": modal_review,
        "driven_review": driven_review,
        "field_parity_reviewed": bool(review.get("field_parity_reviewed", False)),
        "mode_crossing_reviewed": bool(review.get("mode_crossing_reviewed", False)),
        "segmented_monotonic_branch": bool(review.get("segmented_monotonic_branch", False)),
        "coupling_sign": sign,
        "quality_factor_review": q_review,
        "curve_digest_sha256": _curve_digest(curve),
    }
    return CharacterizationCurve(
        curve_id=curve.curve_id,
        study_kind=curve.study_kind,
        parameter_name=curve.parameter_name,
        parameter_unit=curve.parameter_unit,
        x_values=curve.x_values,
        response_name=curve.response_name,
        response_unit=curve.response_unit,
        y_values=curve.y_values,
        monotonic_direction=curve.monotonic_direction,
        source_samples=curve.source_samples,
        approved=True,
        metadata={
            **curve.metadata,
            "approval": approval,
            "approved_backend": backend,
        },
    )


def revoke_characterization_curve(
    curve_value: CharacterizationCurve | dict[str, Any],
    *,
    reviewer: str,
    reason: str,
) -> CharacterizationCurve:
    curve = (
        curve_value
        if isinstance(curve_value, CharacterizationCurve)
        else CharacterizationCurve.from_dict(curve_value)
    )
    reviewer_value = str(reviewer).strip()
    reason_value = str(reason).strip()
    if not reviewer_value or not reason_value:
        raise ValueError("reviewer and reason are required to revoke a curve")
    revocation = {
        "reviewer": reviewer_value,
        "reason": reason_value,
        "revoked_at": datetime.now(UTC).isoformat(),
        "previous_approval": dict(curve.metadata.get("approval") or {}),
    }
    metadata = dict(curve.metadata)
    metadata.pop("approval", None)
    metadata["revocation"] = revocation
    return CharacterizationCurve(
        curve_id=curve.curve_id,
        study_kind=curve.study_kind,
        parameter_name=curve.parameter_name,
        parameter_unit=curve.parameter_unit,
        x_values=curve.x_values,
        response_name=curve.response_name,
        response_unit=curve.response_unit,
        y_values=curve.y_values,
        monotonic_direction=curve.monotonic_direction,
        source_samples=curve.source_samples,
        approved=False,
        metadata=metadata,
    )


def _require_real_hfss_source(
    curve: CharacterizationCurve,
    review: dict[str, Any],
) -> tuple[str, str]:
    if curve.study_kind is StudyKind.EXTERNAL_Q:
        backend = "pyaedt-hfss-driven-modal"
        solver = "HFSS Driven Modal"
    else:
        backend = "pyaedt-hfss-eigenmode"
        solver = "HFSS Eigenmode"
    actual_backend = str(curve.metadata.get("backend") or "")
    actual_solver = str(curve.metadata.get("solver") or "")
    if actual_backend != backend or actual_solver != solver:
        raise ValueError(f"only real {solver} characterizations can be approved for {curve.study_kind.value}")
    maximum_fit_rms = float(review.get("maximum_fit_rms", 0.05))
    for index, sample in enumerate(curve.source_samples):
        sample_backend = str(sample.metadata.get("backend") or "")
        if sample_backend != backend:
            raise ValueError(f"sample {index + 1} was not produced by the real {solver} backend")
        if bool(sample.metadata.get("approved", False)):
            raise ValueError("raw HFSS samples must not carry independent approval state")
        if curve.study_kind is StudyKind.EXTERNAL_Q:
            external_q = float(sample.metadata.get("external_q", 0.0))
            fit_rms = float(sample.metadata.get("rms_complex_error", np.inf))
            if external_q <= 0.0:
                raise ValueError(f"external-Q sample {index + 1} does not contain a positive Qe")
            if not np.isfinite(fit_rms) or fit_rms > maximum_fit_rms:
                raise ValueError(
                    f"external-Q sample {index + 1} fit RMS {fit_rms:g} exceeds {maximum_fit_rms:g}"
                )
    return backend, solver


def _modal_review(curve: CharacterizationCurve, review: dict[str, Any]) -> dict[str, Any]:
    if curve.study_kind is StudyKind.EXTERNAL_Q:
        return {"required": False}
    if not bool(review.get("mode_identity_reviewed", False)):
        raise ValueError("mode identity must be reviewed before approval")
    if not bool(review.get("field_distribution_reviewed", False)):
        raise ValueError("field distribution must be reviewed before approval")
    ambiguous = bool(curve.metadata.get("contains_ambiguous_tracking")) or any(
        bool(sample.metadata.get("tracking_ambiguous")) for sample in curve.source_samples
    )
    if ambiguous and not bool(review.get("mode_crossing_reviewed", False)):
        raise ValueError("ambiguous mode tracking requires explicit mode-crossing review")
    return {
        "required": True,
        "mode_identity_reviewed": True,
        "field_distribution_reviewed": True,
        "mode_crossing_reviewed": bool(review.get("mode_crossing_reviewed", False)),
        "ambiguous_tracking_present": ambiguous,
    }


def _driven_review(curve: CharacterizationCurve, review: dict[str, Any]) -> dict[str, Any]:
    if curve.study_kind is not StudyKind.EXTERNAL_Q:
        return {"required": False}
    required = {
        "complex_fit_reviewed": "complex S11 fit must be reviewed before Qe approval",
        "port_reference_reviewed": "port reference plane must be reviewed before Qe approval",
        "sweep_coverage_reviewed": "frequency sweep coverage must be reviewed before Qe approval",
    }
    for name, message in required.items():
        if not bool(review.get(name, False)):
            raise ValueError(message)
    return {
        "required": True,
        "complex_fit_reviewed": True,
        "port_reference_reviewed": True,
        "sweep_coverage_reviewed": True,
        "maximum_fit_rms": float(review.get("maximum_fit_rms", 0.05)),
    }


def _coupling_sign_review(curve: CharacterizationCurve, review: dict[str, Any]) -> int | None:
    if curve.study_kind is not StudyKind.COUPLING:
        return None
    if not bool(review.get("field_parity_reviewed", False)):
        raise ValueError("coupling curves require even/odd field parity review")
    sign = int(review.get("coupling_sign", 0))
    if sign not in {-1, 1}:
        raise ValueError("coupling_sign must be -1 or +1")
    values = np.asarray(curve.y_values, dtype=float)
    nonzero = values[np.abs(values) > 1e-15]
    if nonzero.size and np.any(np.sign(nonzero) != sign):
        raise ValueError("reviewed coupling sign does not match the characterized curve")
    return sign


def _quality_review(curve: CharacterizationCurve, review: dict[str, Any]) -> dict[str, Any]:
    values = [
        float(value)
        for sample in curve.source_samples
        for value in sample.quality_factors
        if value is not None
    ]
    if not values:
        return {"available": False, "accepted": bool(review.get("allow_missing_q", False))}
    minimum_q = float(review.get("minimum_q", 0.0))
    observed_minimum = min(values)
    if observed_minimum < minimum_q:
        raise ValueError(
            f"minimum observed Q {observed_minimum:g} is below review limit {minimum_q:g}"
        )
    return {
        "available": True,
        "minimum_observed": observed_minimum,
        "maximum_observed": max(values),
        "minimum_required": minimum_q,
        "accepted": True,
    }


def _curve_digest(curve: CharacterizationCurve) -> str:
    payload = curve.to_dict()
    payload["approved"] = False
    payload["metadata"] = {
        key: value for key, value in payload.get("metadata", {}).items() if key not in {"approval", "revocation"}
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()
