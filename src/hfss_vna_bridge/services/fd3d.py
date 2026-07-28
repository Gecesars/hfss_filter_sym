from __future__ import annotations

from typing import Any

from hfss_vna_bridge.adapters.aedt.eigenmode import run_hfss_eigenmode_study
from hfss_vna_bridge.fd3d.characterization import (
    build_characterization_curve,
    evaluate_curve,
    invert_curve,
)
from hfss_vna_bridge.fd3d.mapping import map_targets_to_dimensions
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
            "solver_required": "HFSS Eigenmode",
        },
    }


def execute_hfss_eigenmode_study(
    adapter: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    plan = payload.get("plan")
    if not isinstance(plan, dict):
        plan = component_study_plan(payload)
    plan = dict(plan)
    plan["dry_run"] = False
    result = run_hfss_eigenmode_study(
        adapter,
        plan,
        cores=_optional_int(payload.get("cores")),
        tasks=_optional_int(payload.get("tasks")),
        gpus=_optional_int(payload.get("gpus")),
        save_project=bool(payload.get("save_project", True)),
    )
    curve_payload: dict[str, Any] = {
        "study_kind": result["study_kind"],
        "parameter_name": result["parameter_name"],
        "parameter_unit": result["parameter_unit"],
        "samples": result["samples"],
        "approved": False,
        "metadata": {
            "backend": result["backend"],
            "solver": result["solver"],
            "project": result["project"],
            "project_file": result["project_file"],
            "design": result["design"],
            "setup": result["setup"],
            "component_id": result["component_id"],
            "component_version": result["component_version"],
            "eligible_for_approval": result["eligible_for_approval"],
        },
    }
    study_kind = str(result["study_kind"])
    if study_kind == "RESONANCE":
        curve_payload["mode_index"] = int(payload.get("mode_index", 0))
    elif study_kind == "COUPLING":
        curve_payload["lower_mode_index"] = int(payload.get("lower_mode_index", 0))
        curve_payload["upper_mode_index"] = int(payload.get("upper_mode_index", 1))
        curve_payload["sign"] = float(payload.get("sign", 1.0))
    curve = build_characterization_curve(curve_payload)
    return {
        "status": 0,
        "ok": True,
        "study": result,
        "curve": curve.to_dict(),
        "approval": {
            "eligible": True,
            "approved": False,
            "requires_mode_review": True,
            "requires_field_parity_review": study_kind == "COUPLING",
        },
    }


def map_project_targets(payload: dict[str, Any]) -> dict[str, Any]:
    project = payload.get("project")
    if not isinstance(project, dict):
        raise TypeError("project is required")
    curves = payload.get("curves")
    if curves is not None and not isinstance(curves, list):
        raise TypeError("curves must be a list")
    mapping = map_targets_to_dimensions(
        project,
        curves,
        allow_extrapolation=bool(payload.get("allow_extrapolation", False)),
    )
    return {"status": 0, "ok": mapping["valid"], "mapping": mapping}


def validate_project(payload: dict[str, Any]) -> dict[str, Any]:
    project = payload.get("project") if "project" in payload else payload
    if not isinstance(project, dict):
        raise TypeError("project must be an object")
    result = validate_fd3d_project(project)
    return {"status": 0, "ok": result["valid"], "validation": result}


def _optional_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)
