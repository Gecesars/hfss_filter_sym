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
    """Approve a characterization only after explicit engineering review.

    Approval is intentionally stricter than curve generation. Curves must originate
    from real HFSS solves, have reviewed mode identity and field evidence, avoid
    unreviewed mode crossings and remain invertible for physical dimension mapping.
    """

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
    if not bool(review.get("mode_identity_reviewed", False)):
        raise ValueError("mode identity must be reviewed before approval")
    if not bool(review.get("field_distribution_reviewed", False)):
        raise ValueError("field distribution must be reviewed before approval")

    _require_real_hfss_source(curve)
    minimum_samples = int(review.get("minimum_samples", 3))
    if len(curve.source_samples) < minimum_samples:
        raise ValueError(
            f"characterization requires at least {minimum_samples} solved HFSS samples for approval"
        )
    if curve.monotonic_direction == "non_monotonic" and not bool(
        review.get("segmented_monotonic_branch", False)
    ):
        raise ValueError("non-monotonic characterization must be segmented before approval")
    if bool(curve.metadata.get("contains_ambiguous_tracking")) and not bool(
        review.get("mode_crossing_reviewed", False)
    ):
        raise ValueError("ambiguous mode tracking requires explicit mode-crossing review")
    if any(bool(sample.metadata.get("tracking_ambiguous")) for sample in curve.source_samples) and not bool(
        review.get("mode_crossing_reviewed", False)
    ):
        raise ValueError("one or more samples contain an unreviewed tracking ambiguity")

    sign = None
    if curve.study_kind is StudyKind.COUPLING:
        if not bool(review.get("field_parity_reviewed", False)):
            raise ValueError("coupling curves require even/odd field parity review")
        sign = int(review.get("coupling_sign", 0))
        if sign not in {-1, 1}:
            raise ValueError("coupling_sign must be -1 or +1")
        values = np.asarray(curve.y_values, dtype=float)
        nonzero = values[np.abs(values) > 1e-15]
        if nonzero.size and np.any(np.sign(nonzero) != sign):
            raise ValueError("reviewed coupling sign does not match the characterized curve")

    q_review = _quality_review(curve, review)
    approval = {
        "schema": APPROVAL_SCHEMA,
        "reviewer": reviewer,
        "reviewed_at": datetime.now(UTC).isoformat(),
        "evidence": [str(item).strip() for item in evidence],
        "notes": str(review.get("notes") or "").strip(),
        "mode_identity_reviewed": True,
        "field_distribution_reviewed": True,
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
            "approved_backend": "pyaedt-hfss-eigenmode",
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


def _require_real_hfss_source(curve: CharacterizationCurve) -> None:
    backend = str(curve.metadata.get("backend") or "")
    solver = str(curve.metadata.get("solver") or "")
    if backend != "pyaedt-hfss-eigenmode" or solver != "HFSS Eigenmode":
        raise ValueError("only real HFSS Eigenmode characterizations can be approved")
    for index, sample in enumerate(curve.source_samples):
        sample_backend = str(sample.metadata.get("backend") or "")
        if sample_backend != "pyaedt-hfss-eigenmode":
            raise ValueError(f"sample {index + 1} was not produced by the real HFSS Eigenmode backend")
        if bool(sample.metadata.get("approved", False)):
            raise ValueError("raw HFSS samples must not carry independent approval state")


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
            f"minimum observed eigenmode Q {observed_minimum:g} is below review limit {minimum_q:g}"
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
