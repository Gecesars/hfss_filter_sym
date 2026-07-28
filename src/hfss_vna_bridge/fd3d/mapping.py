from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np

from .characterization import invert_curve
from .models import CharacterizationCurve, Fd3dProject, StudyKind


def map_targets_to_dimensions(
    project_value: Fd3dProject | dict[str, Any],
    curves: Iterable[CharacterizationCurve | dict[str, Any]] | None = None,
    *,
    allow_extrapolation: bool = False,
) -> dict[str, Any]:
    project = (
        project_value
        if isinstance(project_value, Fd3dProject)
        else Fd3dProject.from_dict(project_value)
    )
    curve_values = tuple(
        item if isinstance(item, CharacterizationCurve) else CharacterizationCurve.from_dict(item)
        for item in (curves if curves is not None else project.characterizations)
    )
    by_component_kind: dict[tuple[str, StudyKind], list[CharacterizationCurve]] = {}
    for curve in curve_values:
        component_id = str(curve.metadata.get("component_id") or "")
        if component_id:
            by_component_kind.setdefault((component_id, curve.study_kind), []).append(curve)

    mappings: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    center_hz = _center_frequency_hz(project)

    for node in project.assembly.get("nodes", []):
        if node.get("role") != "resonator":
            continue
        component_id = str(node.get("component_id"))
        curve = _select_curve(by_component_kind, component_id, StudyKind.RESONANCE)
        target = center_hz
        if curve is None:
            missing.append(
                {
                    "target_id": str(node.get("instance_id")),
                    "component_id": component_id,
                    "study_kind": StudyKind.RESONANCE.value,
                    "target_response": target,
                }
            )
            continue
        _append_mapping(
            mappings,
            errors,
            curve,
            target_id=str(node.get("instance_id")),
            target_response=target,
            target_type="resonance_frequency",
            allow_extrapolation=allow_extrapolation,
        )

    for edge in project.assembly.get("edges", []):
        target_type = str(edge.get("target_type"))
        study_kind = (
            StudyKind.EXTERNAL_Q if target_type == "external_q" else StudyKind.COUPLING
        )
        component_id = str(edge.get("component_id"))
        curve = _select_curve(by_component_kind, component_id, study_kind)
        target = float(edge.get("target_value"))
        if not np.isfinite(target):
            errors.append(
                {
                    "target_id": str(edge.get("edge_id")),
                    "message": "electrical target is not finite",
                }
            )
            continue
        if curve is None:
            missing.append(
                {
                    "target_id": str(edge.get("edge_id")),
                    "component_id": component_id,
                    "study_kind": study_kind.value,
                    "target_response": target,
                }
            )
            continue
        sign_transform_required = False
        curve_values_array = np.asarray(curve.y_values, dtype=float)
        mapped_target = target
        if study_kind is StudyKind.COUPLING and target < 0.0 and np.all(curve_values_array >= 0.0):
            mapped_target = abs(target)
            sign_transform_required = True
        _append_mapping(
            mappings,
            errors,
            curve,
            target_id=str(edge.get("edge_id")),
            target_response=mapped_target,
            target_type=target_type,
            allow_extrapolation=allow_extrapolation,
            extra={
                "electrical_sign": -1 if target < 0.0 else 1,
                "sign_transform_required": sign_transform_required,
                "requested_signed_target": target,
            },
        )

    return {
        "valid": not errors and not missing,
        "mappings": mappings,
        "missing_characterizations": missing,
        "errors": errors,
        "summary": {
            "target_count": len(mappings) + len(missing) + len(errors),
            "mapped_count": len(mappings),
            "missing_count": len(missing),
            "error_count": len(errors),
            "extrapolation_allowed": allow_extrapolation,
        },
    }


def _append_mapping(
    mappings: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    curve: CharacterizationCurve,
    *,
    target_id: str,
    target_response: float,
    target_type: str,
    allow_extrapolation: bool,
    extra: dict[str, Any] | None = None,
) -> None:
    try:
        mapping = invert_curve(
            curve,
            target_response,
            allow_extrapolation=allow_extrapolation,
        )
    except ValueError as exc:
        errors.append(
            {
                "target_id": target_id,
                "curve_id": curve.curve_id,
                "message": str(exc),
            }
        )
        return
    mappings.append(
        {
            "target_id": target_id,
            "target_type": target_type,
            "curve_id": curve.curve_id,
            "component_id": curve.metadata.get("component_id"),
            **mapping,
            **(extra or {}),
        }
    )


def _select_curve(
    curves: dict[tuple[str, StudyKind], list[CharacterizationCurve]],
    component_id: str,
    study_kind: StudyKind,
) -> CharacterizationCurve | None:
    candidates = curves.get((component_id, study_kind), [])
    if not candidates:
        return None
    approved = [item for item in candidates if item.approved]
    values = approved or candidates
    return sorted(
        values,
        key=lambda item: (
            bool(item.approved),
            len(item.x_values),
            item.curve_id,
        ),
        reverse=True,
    )[0]


def _center_frequency_hz(project: Fd3dProject) -> float:
    synthesis_spec = dict(project.synthesis.get("specification") or {})
    specification = project.specification
    frequency_ghz = float(
        synthesis_spec.get(
            "effective_f0_ghz",
            specification.get("effective_f0_ghz", specification.get("f0_ghz", 0.0)),
        )
    )
    if frequency_ghz <= 0.0:
        raise ValueError("project center frequency is unavailable")
    return frequency_ghz * 1e9
