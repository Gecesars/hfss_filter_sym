from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .models import Fd3dProject


ASSEMBLY_PLAN_SCHEMA = "hfss-filter-studio/fd3d-assembly-plan/v1"


def build_combline_assembly_plan(
    project_value: Fd3dProject | dict[str, Any],
    mapping_result: dict[str, Any] | None = None,
    *,
    name: str | None = None,
    require_approved_curves: bool = True,
    allow_seed_external_q: bool = True,
    allow_seed_resonance: bool = False,
    allow_seed_coupling: bool = False,
    include_tuning_screws: bool = True,
) -> dict[str, Any]:
    """Create a part-by-part driven HFSS plan for a linear combline filter.

    The plan is deliberately independent from PyAEDT. It consumes the electrical
    target-to-dimension mapping produced from characterized component curves and
    emits deterministic solids, boolean operations, ports, groups and traceable
    part metadata. Cross couplings are never silently approximated by an inline
    iris; they are reported as unresolved physical realizations.
    """

    project = (
        project_value
        if isinstance(project_value, Fd3dProject)
        else Fd3dProject.from_dict(project_value)
    )
    technology = str(project.assembly.get("technology") or "").lower()
    if technology != "combline":
        raise ValueError("the initial assembly planner supports combline projects only")

    seed = {str(key): float(value) for key, value in project.metadata.get("geometry_seed", {}).items()}
    required_seed = {
        "cavity_length_mm",
        "cavity_width_mm",
        "cavity_height_mm",
        "wall_mm",
        "resonator_radius_mm",
        "resonator_height_mm",
        "iris_width_mm",
        "probe_depth_mm",
    }
    missing_seed = sorted(required_seed - set(seed))
    if missing_seed:
        raise ValueError("project geometry seed is incomplete: " + ", ".join(missing_seed))

    nodes = list(project.assembly.get("nodes") or [])
    edges = list(project.assembly.get("edges") or [])
    resonators = sorted(
        (node for node in nodes if node.get("role") == "resonator"),
        key=lambda item: int(str(item.get("matrix_label") or "0")),
    )
    if not resonators:
        raise ValueError("assembly contains no resonator instances")

    mapping = dict(mapping_result or {})
    mapping_rows = list(mapping.get("mappings") or [])
    by_target = {str(item.get("target_id")): dict(item) for item in mapping_rows}
    approved_curve_ids = {
        item.curve_id for item in project.characterizations if item.approved
    }

    warnings: list[str] = []
    blockers: list[str] = []
    parameter_sources: list[dict[str, Any]] = []

    cavity_length = seed["cavity_length_mm"]
    cavity_width = seed["cavity_width_mm"]
    cavity_height = seed["cavity_height_mm"]
    wall = seed["wall_mm"]
    shared_wall = wall
    radius = seed["resonator_radius_mm"]
    iris_height = 0.60 * cavity_height
    order = len(resonators)
    total_length = order * cavity_length + (order - 1) * shared_wall
    if wall * 2.0 >= min(cavity_length, cavity_width, cavity_height):
        raise ValueError("wall thickness is incompatible with the seeded cavity dimensions")

    prefix = _prefix(name or project.name)
    shell = f"{prefix}_housing"
    objects: list[dict[str, Any]] = [
        _box(shell, [0.0, 0.0, 0.0], [total_length, cavity_width, cavity_height], "copper")
    ]
    subtraction_tools: list[str] = []
    parts: list[dict[str, Any]] = [
        _part(shell, "housing", "combline-housing-v1", parameters={
            "length_mm": total_length,
            "width_mm": cavity_width,
            "height_mm": cavity_height,
            "wall_mm": wall,
        })
    ]
    rods: list[str] = []
    air_regions: list[str] = []
    tuning_screws: list[str] = []

    for index, node in enumerate(resonators, start=1):
        instance_id = str(node["instance_id"])
        height, source = _dimension_for_target(
            instance_id,
            "resonator_height_mm",
            by_target,
            seed["resonator_height_mm"],
            allow_seed=allow_seed_resonance,
            require_approved=require_approved_curves,
            approved_curve_ids=approved_curve_ids,
            blockers=blockers,
            warnings=warnings,
        )
        top_gap = cavity_height - wall - height
        if top_gap <= 0.0:
            blockers.append(f"{instance_id}: resonator height leaves no capacitive top gap")
        cell_start = (index - 1) * (cavity_length + shared_wall)
        center_x = cell_start + wall + (cavity_length - 2.0 * wall) / 2.0

        air_name = f"{prefix}_air_{index:02d}"
        rod_name = f"{prefix}_resonator_{index:02d}"
        air_regions.append(air_name)
        rods.append(rod_name)
        subtraction_tools.append(air_name)
        objects.extend(
            [
                _box(
                    air_name,
                    [cell_start + wall, wall, wall],
                    [cavity_length - 2.0 * wall, cavity_width - 2.0 * wall, cavity_height - 2.0 * wall],
                    "air",
                ),
                _cylinder(
                    rod_name,
                    "Z",
                    [center_x, cavity_width / 2.0, wall],
                    radius,
                    height,
                    "copper",
                ),
            ]
        )
        parts.extend(
            [
                _part(air_name, "cavity-region", "combline-housing-v1", instance_id=instance_id),
                _part(
                    rod_name,
                    "resonator",
                    str(node.get("component_id") or "combline-resonator-v1"),
                    instance_id=instance_id,
                    parameters={
                        "resonator_height_mm": height,
                        "resonator_radius_mm": radius,
                        "top_gap_mm": top_gap,
                    },
                    source=source,
                ),
            ]
        )
        parameter_sources.append({"target_id": instance_id, "parameter_name": "resonator_height_mm", **source})

        if include_tuning_screws:
            screw_name = f"{prefix}_tuning_screw_{index:02d}"
            screw_radius = max(0.5, radius * 0.35)
            screw_depth = max(0.25, min(top_gap * 0.35, cavity_height * 0.08))
            tuning_screws.append(screw_name)
            objects.append(
                _cylinder(
                    screw_name,
                    "Z",
                    [center_x, cavity_width / 2.0, cavity_height],
                    screw_radius,
                    -screw_depth,
                    "copper",
                )
            )
            parts.append(
                _part(
                    screw_name,
                    "tuning-feature",
                    "combline-tuning-screw-v1",
                    instance_id=f"tuning-{instance_id}",
                    parameters={"depth_mm": screw_depth, "radius_mm": screw_radius},
                    source={"source": "seed", "status": "uncharacterized-tuning-feature"},
                )
            )

    irises: list[str] = []
    main_resonator_edges = []
    unrealized_edges: list[dict[str, Any]] = []
    resonator_order = {str(node["instance_id"]): index for index, node in enumerate(resonators, start=1)}
    for edge in edges:
        source_id = str(edge.get("source_instance"))
        target_id = str(edge.get("target_instance"))
        if source_id in resonator_order and target_id in resonator_order:
            separation = abs(resonator_order[source_id] - resonator_order[target_id])
            if separation == 1 and str(edge.get("kind") or "main") == "main":
                main_resonator_edges.append(edge)
            else:
                unrealized_edges.append(dict(edge))

    main_resonator_edges.sort(
        key=lambda edge: min(resonator_order[str(edge["source_instance"])], resonator_order[str(edge["target_instance"])])
    )
    for edge in main_resonator_edges:
        left_index = min(
            resonator_order[str(edge["source_instance"])],
            resonator_order[str(edge["target_instance"])],
        )
        edge_id = str(edge["edge_id"])
        iris_width, source = _dimension_for_target(
            edge_id,
            "iris_width_mm",
            by_target,
            seed["iris_width_mm"],
            allow_seed=allow_seed_coupling,
            require_approved=require_approved_curves,
            approved_curve_ids=approved_curve_ids,
            blockers=blockers,
            warnings=warnings,
        )
        if iris_width >= cavity_width - 2.0 * wall:
            blockers.append(f"{edge_id}: iris width does not fit inside the cavity")
        aperture_x = left_index * cavity_length + (left_index - 1) * shared_wall
        aperture = f"{prefix}_iris_{left_index:02d}_{left_index + 1:02d}"
        irises.append(aperture)
        subtraction_tools.append(aperture)
        objects.append(
            _box(
                aperture,
                [
                    aperture_x,
                    (cavity_width - iris_width) / 2.0,
                    wall + (cavity_height - 2.0 * wall - iris_height) / 2.0,
                ],
                [shared_wall, iris_width, iris_height],
                "air",
            )
        )
        parts.append(
            _part(
                aperture,
                "internal-coupling-aperture",
                str(edge.get("component_id") or "combline-iris-v1"),
                instance_id=edge_id,
                parameters={"iris_width_mm": iris_width, "iris_height_mm": iris_height},
                source=source,
            )
        )
        parameter_sources.append({"target_id": edge_id, "parameter_name": "iris_width_mm", **source})

    if unrealized_edges:
        blockers.append(
            "cross couplings require an explicit physical realization; no inline-iris approximation was created"
        )

    source_edge = _find_external_edge(edges, "source")
    load_edge = _find_external_edge(edges, "load")
    input_depth, input_source = _external_dimension(
        source_edge,
        by_target,
        seed["probe_depth_mm"],
        allow_seed=allow_seed_external_q,
        require_approved=require_approved_curves,
        approved_curve_ids=approved_curve_ids,
        blockers=blockers,
        warnings=warnings,
    )
    output_depth, output_source = _external_dimension(
        load_edge,
        by_target,
        seed["probe_depth_mm"],
        allow_seed=allow_seed_external_q,
        require_approved=require_approved_curves,
        approved_curve_ids=approved_curve_ids,
        blockers=blockers,
        warnings=warnings,
    )
    probe_radius = max(0.5, radius * 0.35)
    probe_z = wall + min(seed["resonator_height_mm"] * 0.55, cavity_height * 0.55)
    input_pin = f"{prefix}_input_probe"
    output_pin = f"{prefix}_output_probe"
    objects.extend(
        [
            _cylinder(input_pin, "X", [0.0, cavity_width / 2.0, probe_z], probe_radius, wall + input_depth, "copper"),
            _cylinder(output_pin, "X", [total_length, cavity_width / 2.0, probe_z], probe_radius, -(wall + output_depth), "copper"),
        ]
    )
    parts.extend(
        [
            _part(input_pin, "external-coupling-probe", "combline-probe-v1", instance_id="source", parameters={"probe_depth_mm": input_depth}, source=input_source),
            _part(output_pin, "external-coupling-probe", "combline-probe-v1", instance_id="load", parameters={"probe_depth_mm": output_depth}, source=output_source),
        ]
    )

    spec = dict(project.specification)
    f0_ghz = float(spec.get("effective_f0_ghz", spec.get("f0_ghz", 1.0)))
    bandwidth_ghz = float(spec.get("effective_bandwidth_ghz", spec.get("bandwidth_ghz", 0.05)))
    start_ghz = float(spec.get("start_ghz", max(f0_ghz - 2.5 * bandwidth_ghz, 1e-6)))
    stop_ghz = float(spec.get("stop_ghz", f0_ghz + 2.5 * bandwidth_ghz))

    operations = [
        {
            "operation": "subtract",
            "blank": shell,
            "tools": subtraction_tools,
            "keep_originals": True,
        }
    ]
    ready = not blockers
    return {
        "schema": ASSEMBLY_PLAN_SCHEMA,
        "name": prefix,
        "project_id": project.project_id,
        "technology": "combline",
        "solution_type": "Modal",
        "units": "mm",
        "ready_for_hfss": ready,
        "objects": objects,
        "operations": operations,
        "ports": [
            {"name": f"{prefix}_Port1", "signal": input_pin, "reference": shell, "impedance": 50.0},
            {"name": f"{prefix}_Port2", "signal": output_pin, "reference": shell, "impedance": 50.0},
        ],
        "groups": {
            "housing": [shell],
            "air_regions": air_regions,
            "resonators": rods,
            "coupling_apertures": irises,
            "tuning_features": tuning_screws,
            "probes": [input_pin, output_pin],
        },
        "parts": parts,
        "parameter_sources": parameter_sources,
        "unrealized_edges": unrealized_edges,
        "setup": {
            "name": "FD3D_FilterSetup",
            "sweep_name": "FD3D_FilterSweep",
            "center_frequency_ghz": f0_ghz,
            "start_frequency_ghz": start_ghz,
            "stop_frequency_ghz": stop_ghz,
            "points": int(spec.get("points", 401)),
            "maximum_passes": 15,
            "max_delta_s": 0.01,
            "sweep_type": "Interpolating",
        },
        "validation": {
            "valid": ready,
            "blockers": sorted(set(blockers)),
            "warnings": sorted(set(warnings)),
            "unrealized_cross_coupling_count": len(unrealized_edges),
            "uses_seed_external_q": any(
                item.get("source") == "seed" for item in (input_source, output_source)
            ),
        },
        "traceability": {
            "target_matrix": dict(project.synthesis.get("matrix") or {}),
            "mapping_summary": dict(mapping.get("summary") or {}),
            "require_approved_curves": require_approved_curves,
        },
        "dry_run": True,
        "overwrite": True,
        "assign_ports": True,
    }


def _dimension_for_target(
    target_id: str,
    expected_parameter: str,
    by_target: dict[str, dict[str, Any]],
    seed_value: float,
    *,
    allow_seed: bool,
    require_approved: bool,
    approved_curve_ids: set[str],
    blockers: list[str],
    warnings: list[str],
) -> tuple[float, dict[str, Any]]:
    row = by_target.get(target_id)
    if row is None:
        if allow_seed:
            warnings.append(f"{target_id}: using uncharacterized seed for {expected_parameter}")
            return float(seed_value), {"source": "seed", "status": "uncharacterized"}
        blockers.append(f"{target_id}: missing mapped {expected_parameter}")
        return float(seed_value), {"source": "seed", "status": "blocked-missing-mapping"}
    parameter = str(row.get("parameter_name") or "")
    if parameter != expected_parameter:
        blockers.append(
            f"{target_id}: mapping uses {parameter or 'unknown parameter'} instead of {expected_parameter}"
        )
    curve_id = str(row.get("curve_id") or "")
    if require_approved and curve_id not in approved_curve_ids:
        blockers.append(f"{target_id}: characterization curve {curve_id or '<none>'} is not approved")
    if bool(row.get("extrapolated", False)):
        blockers.append(f"{target_id}: mapped dimension is extrapolated")
    value = float(row.get("parameter_value", seed_value))
    if value <= 0.0:
        blockers.append(f"{target_id}: mapped {expected_parameter} must be positive")
        value = float(seed_value)
    return value, {
        "source": "characterization",
        "curve_id": curve_id,
        "status": "approved" if curve_id in approved_curve_ids else "pending-approval",
        "target_response": row.get("target_response"),
        "predicted_response": row.get("predicted_response"),
        "sensitivity": row.get("sensitivity"),
    }


def _external_dimension(
    edge: dict[str, Any] | None,
    by_target: dict[str, dict[str, Any]],
    seed_value: float,
    **kwargs: Any,
) -> tuple[float, dict[str, Any]]:
    target_id = str(edge.get("edge_id")) if edge else "missing-external-edge"
    return _dimension_for_target(
        target_id,
        "probe_depth_mm",
        by_target,
        seed_value,
        **kwargs,
    )


def _find_external_edge(edges: Iterable[dict[str, Any]], terminal: str) -> dict[str, Any] | None:
    for edge in edges:
        if str(edge.get("target_type")) != "external_q":
            continue
        if terminal in {str(edge.get("source_instance")), str(edge.get("target_instance"))}:
            return edge
    return None


def _part(
    object_name: str,
    role: str,
    component_id: str,
    *,
    instance_id: str | None = None,
    parameters: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "object_name": object_name,
        "role": role,
        "component_id": component_id,
        "instance_id": instance_id,
        "parameters": dict(parameters or {}),
        "dimension_source": dict(source or {}),
    }


def _box(name: str, origin: list[Any], sizes: list[Any], material: str) -> dict[str, Any]:
    return {"primitive": "box", "name": name, "origin": origin, "sizes": sizes, "material": material}


def _cylinder(
    name: str,
    orientation: str,
    origin: list[Any],
    radius: Any,
    height: Any,
    material: str,
) -> dict[str, Any]:
    return {
        "primitive": "cylinder",
        "name": name,
        "orientation": orientation,
        "origin": origin,
        "radius": radius,
        "height": height,
        "material": material,
    }


def _prefix(value: str) -> str:
    text = "".join(character if character.isalnum() or character == "_" else "_" for character in str(value))
    text = text.strip("_") or "FD3D_Filter"
    return text[:48]
