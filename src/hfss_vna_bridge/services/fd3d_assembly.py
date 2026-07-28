from __future__ import annotations

from typing import Any
from uuid import uuid4

from hfss_vna_bridge.fd3d.assembly import build_combline_assembly_plan


def create_filter_assembly_plan(payload: dict[str, Any]) -> dict[str, Any]:
    project = payload.get("project")
    if not isinstance(project, dict):
        raise TypeError("project is required")
    mapping = payload.get("mapping")
    if mapping is not None and not isinstance(mapping, dict):
        raise TypeError("mapping must be an object")
    plan = build_combline_assembly_plan(
        project,
        mapping,
        name=payload.get("name"),
        require_approved_curves=bool(payload.get("require_approved_curves", True)),
        allow_seed_external_q=bool(payload.get("allow_seed_external_q", True)),
        allow_seed_resonance=bool(payload.get("allow_seed_resonance", False)),
        allow_seed_coupling=bool(payload.get("allow_seed_coupling", False)),
        include_tuning_screws=bool(payload.get("include_tuning_screws", True)),
    )
    return {
        "status": 0,
        "ok": bool(plan["ready_for_hfss"]),
        "plan": plan,
        "validation": plan["validation"],
    }


def build_filter_assembly_in_hfss(
    adapter: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Create the complete filter in a real HFSS Driven Modal design."""

    state = getattr(adapter, "state", None)
    if state is None or not getattr(state, "connected", False):
        raise RuntimeError("AEDT adapter is not connected")
    if str(getattr(state, "backend", "")).lower() != "pyaedt":
        raise RuntimeError("FD3D filter assembly requires the real PyAEDT/HFSS backend")

    result = create_filter_assembly_plan(payload)
    plan = dict(result["plan"])
    if not plan["ready_for_hfss"]:
        blockers = "; ".join(plan["validation"]["blockers"])
        raise RuntimeError(f"FD3D assembly is not ready for HFSS: {blockers}")

    hfss = _require_hfss(adapter)
    original_design = str(getattr(hfss, "design_name", "") or "")
    design_name = _insert_driven_design(hfss, str(plan["name"]))
    try:
        plan["dry_run"] = False
        plan["overwrite"] = bool(payload.get("overwrite", True))
        model = adapter.build_model(plan)
        validation = adapter.validate_design(expected_ports=2)
        if not bool(validation.get("valid", False)):
            raise RuntimeError(
                "HFSS created the componentized filter but design validation failed: "
                + "; ".join(str(item) for item in validation.get("messages", []))
            )
        saved_project = None
        if bool(payload.get("save_project", True)):
            saved_project = adapter.save_project(
                file_name=payload.get("output_project"),
                overwrite=bool(payload.get("overwrite", True)),
            )
        return {
            "status": 0,
            "ok": True,
            "backend": "pyaedt-hfss-driven-modal",
            "solver": "HFSS Driven Modal",
            "design": design_name,
            "project_file": saved_project,
            "model": model,
            "validation": validation,
            "plan": plan,
            "traceability": {
                "project_id": plan["project_id"],
                "part_count": len(plan["parts"]),
                "parameter_sources": plan["parameter_sources"],
            },
        }
    except Exception:
        _restore_design(hfss, original_design)
        raise


def _require_hfss(adapter: Any) -> Any:
    getter = getattr(adapter, "_require_hfss", None)
    if not callable(getter):
        raise TypeError("adapter does not expose an active PyAEDT HFSS application")
    return getter()


def _insert_driven_design(hfss: Any, plan_name: str) -> str:
    safe = "".join(character if character.isalnum() or character == "_" else "_" for character in plan_name)
    requested = f"FD3D_{safe[:40]}_{uuid4().hex[:8]}"[:64]
    inserted = hfss.insert_design(name=requested, solution_type="Modal")
    if not inserted:
        raise RuntimeError("AEDT failed to insert an HFSS Driven Modal design")
    if str(getattr(hfss, "solution_type", "")).lower() not in {"modal", "drivenmodal"}:
        try:
            hfss.solution_type = "Modal"
        except (AttributeError, RuntimeError, TypeError):
            pass
    if str(getattr(hfss, "solution_type", "")).lower() not in {"modal", "drivenmodal"}:
        raise RuntimeError("the active HFSS design is not configured as Driven Modal")
    return str(inserted)


def _restore_design(hfss: Any, design_name: str) -> None:
    if not design_name:
        return
    try:
        hfss.set_active_design(design_name)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        pass
