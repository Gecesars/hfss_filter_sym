from __future__ import annotations

import math
import re
from uuid import uuid4

import numpy as np

from .models import (
    ComponentDefinition,
    ComponentKind,
    FD3D_PROJECT_SCHEMA,
    Fd3dProject,
    ParameterDefinition,
    ProjectStage,
)

_C0 = 299_792_458.0


def create_fd3d_blueprint(
    *,
    name: str,
    specification: dict,
    synthesis: dict,
    technology: str = "combline",
    description: str = "",
) -> Fd3dProject:
    project_name = str(name).strip()
    if not project_name:
        raise ValueError("project name is required")
    technology_key = str(technology).strip().lower()
    if technology_key != "combline":
        raise ValueError("the initial FD3D blueprint supports technology='combline'")
    order = int(specification.get("order", 0))
    if order < 1:
        raise ValueError("filter order must be greater than zero")
    matrix = dict(synthesis.get("matrix") or {})
    labels = [str(item) for item in matrix.get("labels", [])]
    values = np.asarray(matrix.get("values", []), dtype=float)
    expected = order + 2
    if labels != ["S", *[str(index) for index in range(1, order + 1)], "L"]:
        raise ValueError("synthesis matrix labels do not match filter order")
    if values.shape != (expected, expected):
        raise ValueError(f"synthesis matrix must be {expected}x{expected}")
    if not np.allclose(values, values.T, rtol=0.0, atol=1e-9):
        raise ValueError("synthesis matrix must be symmetric")

    effective_f0_ghz = float(
        synthesis.get("specification", {}).get(
            "effective_f0_ghz",
            specification.get("f0_ghz", 1.0),
        )
    )
    seed = _combline_seed(effective_f0_ghz)
    components = _combline_components(seed)
    nodes = _assembly_nodes(order)
    edges = _assembly_edges(labels, values, matrix)
    project_id = f"{_slug(project_name)}-{uuid4().hex[:8]}"
    return Fd3dProject(
        project_id=project_id,
        name=project_name[:120],
        stage=ProjectStage.SYNTHESIS,
        specification=dict(specification),
        synthesis={
            "engine": dict(synthesis.get("engine") or {}),
            "matrix": matrix,
            "topology": dict(synthesis.get("topology") or {}),
            "prototype": dict(synthesis.get("prototype") or {}),
            "summary": dict(synthesis.get("summary") or {}),
        },
        components=components,
        assembly={
            "technology": technology_key,
            "status": "blueprint",
            "nodes": nodes,
            "edges": edges,
            "interfaces": [],
            "parameter_mapping": [],
            "validation": {
                "valid": True,
                "warnings": [
                    "Physical dimensions are uncharacterized seed values.",
                    "Coupling signs must be confirmed by topology or field parity.",
                ],
            },
        },
        metadata={
            "description": description[:2000],
            "foundation": "fd3d-project-platform-phase-0",
            "geometry_seed": seed,
            "geometry_seed_status": "heuristic-not-aedt-validated",
        },
    )


def validate_fd3d_project(value: Fd3dProject | dict) -> dict:
    project = value if isinstance(value, Fd3dProject) else Fd3dProject.from_dict(value)
    errors: list[str] = []
    warnings: list[str] = []
    component_ids = [item.component_id for item in project.components]
    if len(component_ids) != len(set(component_ids)):
        errors.append("duplicate component definitions")
    matrix = dict(project.synthesis.get("matrix") or {})
    labels = [str(item) for item in matrix.get("labels", [])]
    values = np.asarray(matrix.get("values", []), dtype=float)
    if values.ndim != 2 or values.shape[0] != values.shape[1]:
        errors.append("target coupling matrix must be square")
    elif labels and values.shape[0] != len(labels):
        errors.append("target matrix labels and dimensions differ")
    elif not np.allclose(values, values.T, rtol=0.0, atol=1e-9):
        errors.append("target coupling matrix must be symmetric")

    nodes = list(project.assembly.get("nodes") or [])
    edges = list(project.assembly.get("edges") or [])
    node_ids = [str(item.get("instance_id")) for item in nodes]
    if len(node_ids) != len(set(node_ids)):
        errors.append("assembly contains duplicate instance ids")
    node_set = set(node_ids)
    for edge in edges:
        source = str(edge.get("source_instance"))
        target = str(edge.get("target_instance"))
        if source not in node_set or target not in node_set:
            errors.append(f"assembly edge {edge.get('edge_id')} references an unknown node")
        if source == target:
            errors.append(f"assembly edge {edge.get('edge_id')} is self-referential")
        if float(edge.get("target_coupling", 0.0)) == 0.0:
            warnings.append(f"assembly edge {edge.get('edge_id')} has zero target coupling")
        if edge.get("sign_reviewed") is not True:
            warnings.append(f"coupling sign for {edge.get('edge_id')} is not field-reviewed")

    characterized_ids = {
        str(item.metadata.get("component_id"))
        for item in project.characterizations
        if item.metadata.get("component_id")
    }
    required_ids = {
        str(item.get("component_id"))
        for item in nodes
        if item.get("role") == "resonator"
    }
    if project.stage not in {ProjectStage.SPECIFICATION, ProjectStage.SYNTHESIS}:
        missing = sorted(required_ids - characterized_ids)
        if missing:
            warnings.append("resonator components without approved characterization: " + ", ".join(missing))
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": sorted(set(warnings)),
        "schema": FD3D_PROJECT_SCHEMA,
        "stage": project.stage.value,
        "component_count": len(project.components),
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def _combline_seed(frequency_ghz: float) -> dict[str, float]:
    if frequency_ghz <= 0.0:
        raise ValueError("center frequency must be greater than zero")
    wavelength_mm = _C0 / (frequency_ghz * 1e9) * 1e3
    return {
        "wavelength_mm": wavelength_mm,
        "cavity_length_mm": 0.24 * wavelength_mm,
        "cavity_width_mm": 0.16 * wavelength_mm,
        "cavity_height_mm": 0.25 * wavelength_mm,
        "wall_mm": max(2.0, 0.008 * wavelength_mm),
        "resonator_radius_mm": max(2.0, 0.012 * wavelength_mm),
        "resonator_height_mm": 0.21 * wavelength_mm,
        "cavity_pitch_mm": 0.14 * wavelength_mm,
        "iris_width_mm": 0.055 * wavelength_mm,
        "probe_depth_mm": 0.07 * wavelength_mm,
    }


def _combline_components(seed: dict[str, float]) -> tuple[ComponentDefinition, ...]:
    resonator_height = seed["resonator_height_mm"]
    iris_width = seed["iris_width_mm"]
    probe_depth = seed["probe_depth_mm"]
    return (
        ComponentDefinition(
            component_id="combline-resonator-v1",
            name="Combline resonator",
            version=1,
            technology="combline",
            kind=ComponentKind.RESONATOR,
            recipe="combline_resonator_eigenmode",
            parameters=(
                ParameterDefinition(
                    "resonator_height_mm",
                    "mm",
                    resonator_height,
                    resonator_height * 0.75,
                    resonator_height * 1.20,
                    samples=9,
                    role="tuning",
                    description="Primary resonance tuning dimension.",
                ),
                ParameterDefinition(
                    "resonator_radius_mm",
                    "mm",
                    seed["resonator_radius_mm"],
                    seed["resonator_radius_mm"] * 0.70,
                    seed["resonator_radius_mm"] * 1.40,
                    samples=5,
                    role="manufacturing",
                ),
            ),
            interfaces=(
                {"name": "left", "kind": "cavity-wall", "normal": [-1, 0, 0]},
                {"name": "right", "kind": "cavity-wall", "normal": [1, 0, 0]},
                {"name": "base", "kind": "ground", "normal": [0, 0, -1]},
            ),
            metadata={"study": "RESONANCE", "seed_status": "heuristic"},
        ),
        ComponentDefinition(
            component_id="combline-iris-v1",
            name="Combline internal coupling iris",
            version=1,
            technology="combline",
            kind=ComponentKind.INTERNAL_COUPLING,
            recipe="combline_pair_eigenmode",
            parameters=(
                ParameterDefinition(
                    "iris_width_mm",
                    "mm",
                    iris_width,
                    max(seed["wall_mm"] * 1.5, iris_width * 0.30),
                    iris_width * 2.20,
                    samples=11,
                    role="tuning",
                    description="Coupling aperture width between identical resonators.",
                ),
            ),
            interfaces=(
                {"name": "left", "kind": "cavity-wall", "normal": [-1, 0, 0]},
                {"name": "right", "kind": "cavity-wall", "normal": [1, 0, 0]},
            ),
            metadata={"study": "COUPLING", "sign_requires_review": True},
        ),
        ComponentDefinition(
            component_id="combline-probe-v1",
            name="Combline coaxial probe",
            version=1,
            technology="combline",
            kind=ComponentKind.EXTERNAL_COUPLING,
            recipe="combline_probe_driven",
            parameters=(
                ParameterDefinition(
                    "probe_depth_mm",
                    "mm",
                    probe_depth,
                    probe_depth * 0.30,
                    probe_depth * 1.80,
                    samples=9,
                    role="tuning",
                    description="External-Q control dimension.",
                ),
            ),
            interfaces=(
                {"name": "port", "kind": "coaxial-port", "normal": [-1, 0, 0]},
                {"name": "cavity", "kind": "electric-coupling", "normal": [1, 0, 0]},
            ),
            metadata={"study": "EXTERNAL_Q", "requires_driven_model": True},
        ),
        ComponentDefinition(
            component_id="combline-housing-v1",
            name="Linear combline housing",
            version=1,
            technology="combline",
            kind=ComponentKind.HOUSING,
            recipe="combline_housing",
            parameters=(
                ParameterDefinition(
                    "cavity_pitch_mm",
                    "mm",
                    seed["cavity_pitch_mm"],
                    seed["cavity_pitch_mm"] * 0.70,
                    seed["cavity_pitch_mm"] * 1.40,
                    samples=5,
                    role="assembly",
                ),
            ),
            metadata={"seed_status": "heuristic"},
        ),
    )


def _assembly_nodes(order: int) -> list[dict]:
    nodes = [
        {
            "instance_id": "source",
            "component_id": "combline-probe-v1",
            "role": "source",
            "matrix_label": "S",
            "transform": {"translation_mm": [0.0, 0.0, 0.0], "rotation_deg": [0, 0, 0]},
        }
    ]
    nodes.extend(
        {
            "instance_id": f"resonator-{index}",
            "component_id": "combline-resonator-v1",
            "role": "resonator",
            "matrix_label": str(index),
            "transform": {"translation_mm": [0.0, 0.0, 0.0], "rotation_deg": [0, 0, 0]},
        }
        for index in range(1, order + 1)
    )
    nodes.append(
        {
            "instance_id": "load",
            "component_id": "combline-probe-v1",
            "role": "load",
            "matrix_label": "L",
            "transform": {"translation_mm": [0.0, 0.0, 0.0], "rotation_deg": [0, 0, 180]},
        }
    )
    return nodes


def _assembly_edges(labels: list[str], values: np.ndarray, matrix: dict) -> list[dict]:
    physical = dict(matrix.get("physical") or {})
    physical_pairs = {
        (str(item["source"]), str(item["target"])): float(item["coefficient"])
        for item in physical.get("inter_resonator", [])
    }
    instance_by_label = {
        "S": "source",
        "L": "load",
        **{label: f"resonator-{label}" for label in labels if label not in {"S", "L"}},
    }
    edges: list[dict] = []
    for row in range(len(labels)):
        for column in range(row + 1, len(labels)):
            normalized = float(values[row, column])
            if abs(normalized) <= 1e-12:
                continue
            source_label = labels[row]
            target_label = labels[column]
            pair = (source_label, target_label)
            physical_target = physical_pairs.get(pair)
            if source_label == "S" and target_label == "1":
                physical_target = None
                target_type = "external_q"
                target_value = float(physical.get("input_external_q", math.nan))
                component_id = "combline-probe-v1"
            elif source_label == labels[-2] and target_label == "L":
                physical_target = None
                target_type = "external_q"
                target_value = float(physical.get("output_external_q", math.nan))
                component_id = "combline-probe-v1"
            else:
                target_type = "coupling"
                target_value = normalized if physical_target is None else physical_target
                component_id = "combline-iris-v1"
            edges.append(
                {
                    "edge_id": f"edge-{source_label}-{target_label}",
                    "source_instance": instance_by_label[source_label],
                    "target_instance": instance_by_label[target_label],
                    "component_id": component_id,
                    "kind": "cross" if column - row > 1 else "main",
                    "target_type": target_type,
                    "target_value": target_value,
                    "target_coupling": normalized,
                    "normalized_matrix_value": normalized,
                    "sign": 1 if normalized >= 0.0 else -1,
                    "sign_reviewed": False,
                    "physical_parameter": None,
                    "characterization_curve_id": None,
                }
            )
    return edges


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:56]
    return text or "fd3d-project"
