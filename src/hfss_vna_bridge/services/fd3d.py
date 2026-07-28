from __future__ import annotations

from typing import Any

from hfss_vna_bridge.fd3d.characterization import (
    build_characterization_curve,
    evaluate_curve,
    invert_curve,
)
from hfss_vna_bridge.fd3d.modeling import component_study_plan
from hfss_vna_bridge.fd3d.project_factory import (
    create_fd3d_blueprint,
    validate_fd3d_project,
)
from hfss_vna_bridge.services.synthesis import synthesize_filter


def create_project_blueprint(payload: dict[str, Any]) -> dict[str, Any]:
    specification = dict(payload.get("specification") or payload)
    name = str(payload.get("name") or "FD3D Filter Project")
    technology = str(payload.get("technology") or "combline")
    synthesis = synthesize_filter(specification)
    project = create_fd3d_blueprint(
        name=name,
        description=str(payload.get("description") or ""),
        specification=specification,
        synthesis=synthesis,
        technology=technology,
    )
    validation = validate_fd3d_project(project)
    return {
        "status": 0,
        "ok": True,
        "project": project.to_dict(),
        "validation": validation,
    }


def create_characterization_curve(payload: dict[str, Any]) -> dict[str, Any]:
    curve = build_characterization_curve(payload)
    return {
        "status": 0,
        "ok": True,
        "curve": curve.to_dict(),
        "quality": {
            "monotonic_direction": curve.monotonic_direction,
            "monotonic_fraction": curve.metadata.get("monotonic_fraction"),
            "contains_ambiguous_tracking": curve.metadata.get(
                "contains_ambiguous_tracking"
            ),
            "invertible": curve.monotonic_direction != "non_monotonic",
        },
    }


def evaluate_characterization_curve(payload: dict[str, Any]) -> dict[str, Any]:
    curve = payload.get("curve")
    if not isinstance(curve, dict):
        raise TypeError("curve is required")
    if "parameter_value" not in payload:
        raise ValueError("parameter_value is required")
    result = evaluate_curve(
        curve,
        float(payload["parameter_value"]),
        allow_extrapolation=bool(payload.get("allow_extrapolation", False)),
    )
    return {"status": 0, "ok": True, "evaluation": result}


def invert_characterization_curve(payload: dict[str, Any]) -> dict[str, Any]:
    curve = payload.get("curve")
    if not isinstance(curve, dict):
        raise TypeError("curve is required")
    if "target_response" not in payload:
        raise ValueError("target_response is required")
    result = invert_curve(
        curve,
        float(payload["target_response"]),
        allow_extrapolation=bool(payload.get("allow_extrapolation", False)),
    )
    return {"status": 0, "ok": True, "mapping": result}


def create_component_study_plan(payload: dict[str, Any]) -> dict[str, Any]:
    plan = component_study_plan(payload)
    return {
        "status": 0,
        "ok": True,
        "plan": plan,
        "summary": {
            "component_id": plan["component_id"],
            "analysis_kind": plan["analysis_kind"],
            "study_kind": plan["study"]["kind"],
            "parameter_name": plan["study"]["parameter_name"],
            "sample_count": len(plan["study"]["sample_values"]),
            "object_count": len(plan["objects"]),
            "num_modes": plan["setup"]["num_modes"],
        },
    }


def validate_project(payload: dict[str, Any]) -> dict[str, Any]:
    project = payload.get("project") if "project" in payload else payload
    if not isinstance(project, dict):
        raise TypeError("project must be an object")
    result = validate_fd3d_project(project)
    return {"status": 0, "ok": result["valid"], "validation": result}
