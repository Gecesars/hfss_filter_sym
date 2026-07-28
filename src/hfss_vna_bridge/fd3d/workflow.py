from __future__ import annotations

from dataclasses import replace
from typing import Any

from .models import CharacterizationCurve, Fd3dProject, ProjectStage, StudyKind
from .project_factory import validate_fd3d_project


_STAGE_ORDER = list(ProjectStage)


def attach_characterization(
    project_value: Fd3dProject | dict[str, Any],
    curve_value: CharacterizationCurve | dict[str, Any],
    *,
    replace_curve_id: bool = True,
) -> Fd3dProject:
    project = _project(project_value)
    curve = _curve(curve_value)
    component_id = str(curve.metadata.get("component_id") or "")
    component_ids = {item.component_id for item in project.components}
    if not component_id or component_id not in component_ids:
        raise ValueError("characterization does not reference a component in this project")
    values = list(project.characterizations)
    matching = [index for index, item in enumerate(values) if item.curve_id == curve.curve_id]
    if matching:
        if not replace_curve_id:
            raise ValueError(f"curve {curve.curve_id!r} already exists in the project")
        values[matching[0]] = curve
    else:
        values.append(curve)
    stage = _at_least(project.stage, ProjectStage.CHARACTERIZATION)
    return replace(
        project,
        stage=stage,
        characterizations=tuple(values),
        metadata={
            **project.metadata,
            "last_characterization_curve_id": curve.curve_id,
            "workflow_status": "characterization-pending-approval",
        },
    )


def attach_mapping(
    project_value: Fd3dProject | dict[str, Any],
    mapping: dict[str, Any],
) -> Fd3dProject:
    project = _project(project_value)
    if not isinstance(mapping, dict):
        raise TypeError("mapping must be an object")
    if not bool(mapping.get("valid", False)):
        raise ValueError("invalid target-to-dimension mapping cannot be attached")
    mapped_count = int(mapping.get("summary", {}).get("mapped_count", 0))
    if mapped_count <= 0:
        raise ValueError("mapping contains no mapped dimensions")
    assembly = {
        **project.assembly,
        "parameter_mapping": [dict(item) for item in mapping.get("mappings", [])],
        "mapping_summary": dict(mapping.get("summary") or {}),
        "status": "mapped",
    }
    return replace(
        project,
        stage=_at_least(project.stage, ProjectStage.ASSEMBLY),
        assembly=assembly,
        metadata={
            **project.metadata,
            "workflow_status": "dimensions-mapped",
        },
    )


def attach_assembly_plan(
    project_value: Fd3dProject | dict[str, Any],
    plan: dict[str, Any],
) -> Fd3dProject:
    project = _project(project_value)
    if not isinstance(plan, dict):
        raise TypeError("assembly plan must be an object")
    if str(plan.get("project_id")) != project.project_id:
        raise ValueError("assembly plan belongs to a different FD3D project")
    if not bool(plan.get("ready_for_hfss", False)):
        blockers = "; ".join(str(item) for item in plan.get("validation", {}).get("blockers", []))
        raise ValueError(f"blocked assembly plan cannot be attached: {blockers}")
    assembly = {
        **project.assembly,
        "status": "ready-for-hfss",
        "plan": dict(plan),
        "validation": dict(plan.get("validation") or {}),
    }
    return replace(
        project,
        stage=_at_least(project.stage, ProjectStage.ASSEMBLY),
        assembly=assembly,
        metadata={
            **project.metadata,
            "workflow_status": "assembly-ready-for-hfss",
        },
    )


def attach_fullwave_analysis(
    project_value: Fd3dProject | dict[str, Any],
    analysis: dict[str, Any],
) -> Fd3dProject:
    project = _project(project_value)
    if not isinstance(analysis, dict) or not bool(analysis.get("ok", False)):
        raise ValueError("a successful full-wave analysis result is required")
    if str(analysis.get("backend")) != "pyaedt-hfss-driven-modal":
        raise ValueError("full-wave project analysis must originate from real HFSS Driven Modal")
    design = str(analysis.get("design") or "")
    if not design:
        raise ValueError("analysis does not identify its HFSS design")
    analyses = [*project.analyses, dict(analysis)]
    return replace(
        project,
        stage=_at_least(project.stage, ProjectStage.FULLWAVE_ANALYSIS),
        analyses=tuple(analyses),
        metadata={
            **project.metadata,
            "workflow_status": "fullwave-analysis-complete",
            "last_fullwave_design": design,
        },
    )


def project_gate_status(project_value: Fd3dProject | dict[str, Any]) -> dict[str, Any]:
    project = _project(project_value)
    required = _required_characterizations(project)
    approved = {
        (str(item.metadata.get("component_id")), item.study_kind)
        for item in project.characterizations
        if item.approved
    }
    missing = [
        {"component_id": component_id, "study_kind": kind.value}
        for component_id, kind in sorted(required, key=lambda item: (item[0], item[1].value))
        if (component_id, kind) not in approved
    ]
    mapping = list(project.assembly.get("parameter_mapping") or [])
    assembly_plan = project.assembly.get("plan")
    fullwave = [
        item
        for item in project.analyses
        if item.get("backend") == "pyaedt-hfss-driven-modal" and item.get("ok") is True
    ]
    validation = validate_fd3d_project(project)
    return {
        "valid_project": bool(validation["valid"]),
        "stage": project.stage.value,
        "required_characterizations": [
            {"component_id": component_id, "study_kind": kind.value}
            for component_id, kind in sorted(required, key=lambda item: (item[0], item[1].value))
        ],
        "missing_approved_characterizations": missing,
        "characterization_gate": not missing,
        "mapping_gate": bool(mapping),
        "assembly_gate": bool(
            isinstance(assembly_plan, dict) and assembly_plan.get("ready_for_hfss") is True
        ),
        "fullwave_gate": bool(fullwave),
        "release_gate": bool(
            validation["valid"]
            and not missing
            and mapping
            and isinstance(assembly_plan, dict)
            and assembly_plan.get("ready_for_hfss") is True
            and fullwave
        ),
        "warnings": validation["warnings"],
        "errors": validation["errors"],
    }


def advance_stage(
    project_value: Fd3dProject | dict[str, Any],
    target_stage: ProjectStage | str,
) -> Fd3dProject:
    project = _project(project_value)
    target = target_stage if isinstance(target_stage, ProjectStage) else ProjectStage(str(target_stage))
    if _STAGE_ORDER.index(target) < _STAGE_ORDER.index(project.stage):
        raise ValueError("workflow stage cannot be moved backwards; restore a project revision instead")
    gates = project_gate_status(project)
    if _STAGE_ORDER.index(target) >= _STAGE_ORDER.index(ProjectStage.ASSEMBLY) and not gates[
        "characterization_gate"
    ]:
        raise ValueError("approved component characterizations are required before assembly")
    if _STAGE_ORDER.index(target) >= _STAGE_ORDER.index(ProjectStage.FULLWAVE_ANALYSIS) and not gates[
        "assembly_gate"
    ]:
        raise ValueError("a valid HFSS-ready assembly is required before full-wave analysis")
    if target is ProjectStage.RELEASED and not gates["release_gate"]:
        raise ValueError("project does not satisfy the release gate")
    return replace(
        project,
        stage=target,
        metadata={
            **project.metadata,
            "workflow_status": f"stage-{target.value.lower()}",
        },
    )


def _required_characterizations(project: Fd3dProject) -> set[tuple[str, StudyKind]]:
    required: set[tuple[str, StudyKind]] = set()
    for node in project.assembly.get("nodes", []):
        role = str(node.get("role") or "")
        component_id = str(node.get("component_id") or "")
        if role == "resonator":
            required.add((component_id, StudyKind.RESONANCE))
    for edge in project.assembly.get("edges", []):
        component_id = str(edge.get("component_id") or "")
        if str(edge.get("target_type")) == "external_q":
            required.add((component_id, StudyKind.EXTERNAL_Q))
        elif str(edge.get("target_type")) == "coupling":
            required.add((component_id, StudyKind.COUPLING))
    return required


def _project(value: Fd3dProject | dict[str, Any]) -> Fd3dProject:
    return value if isinstance(value, Fd3dProject) else Fd3dProject.from_dict(value)


def _curve(value: CharacterizationCurve | dict[str, Any]) -> CharacterizationCurve:
    return value if isinstance(value, CharacterizationCurve) else CharacterizationCurve.from_dict(value)


def _at_least(current: ProjectStage, requested: ProjectStage) -> ProjectStage:
    return requested if _STAGE_ORDER.index(requested) > _STAGE_ORDER.index(current) else current
