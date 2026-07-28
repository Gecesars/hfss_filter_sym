from __future__ import annotations

from typing import Any

import numpy as np

from .models import ComponentDefinition, ComponentKind, ParameterDefinition, StudyKind


def component_study_plan(payload: dict[str, Any]) -> dict[str, Any]:
    component_value = payload.get("component")
    if not isinstance(component_value, dict):
        raise TypeError("component must be an FD3D component definition")
    component = ComponentDefinition.from_dict(component_value)
    study_kind = StudyKind(str(payload.get("study_kind") or component.metadata.get("study")))
    parameter_name = str(payload.get("parameter_name") or _default_parameter(component, study_kind).name)
    parameter = _find_parameter(component, parameter_name)
    sample_values = payload.get("sample_values")
    if sample_values is None:
        values = np.linspace(parameter.minimum, parameter.maximum, parameter.samples)
    else:
        values = np.asarray(sample_values, dtype=float)
    if values.ndim != 1 or values.size < 2:
        raise ValueError("sample_values must contain at least two values")
    if np.any(values < parameter.minimum) or np.any(values > parameter.maximum):
        raise ValueError("sample_values exceed the parameter characterization bounds")
    if np.unique(values).size != values.size:
        raise ValueError("sample_values must be unique")

    geometry = dict(payload.get("geometry") or {})
    if component.recipe == "combline_resonator_eigenmode":
        plan = _combline_resonator_plan(component, geometry)
    elif component.recipe == "combline_pair_eigenmode":
        plan = _combline_pair_plan(component, geometry)
    else:
        raise ValueError(f"component recipe {component.recipe!r} has no Eigenmode plan")

    center_ghz = _positive(payload, "center_frequency_ghz", 1.0)
    frequency_margin = _positive(payload, "frequency_margin", 0.35)
    plan.update(
        {
            "schema": "hfss-filter-studio/fd3d-component-plan/v1",
            "analysis_kind": "eigenmode",
            "solution_type": "Eigenmode",
            "component_id": component.component_id,
            "component_version": component.version,
            "study": {
                "kind": study_kind.value,
                "parameter_name": parameter.name,
                "parameter_unit": parameter.unit,
                "sample_values": [float(item) for item in np.sort(values)],
                "tracking": {
                    "initial": "frequency-order",
                    "successive": "minimum-frequency-displacement",
                    "field_correlation_required": True,
                },
            },
            "setup": {
                "name": str(payload.get("setup_name") or "FD3D_Eigenmode"),
                "minimum_frequency_ghz": max(center_ghz * (1.0 - frequency_margin), 1e-6),
                "maximum_frequency_ghz": center_ghz * (1.0 + frequency_margin),
                "num_modes": _bounded_int(payload.get("num_modes", 4), 1, 40, "num_modes"),
                "maximum_passes": _bounded_int(
                    payload.get("maximum_passes", 15),
                    1,
                    100,
                    "maximum_passes",
                ),
                "max_delta_frequency_percent": _positive(
                    payload,
                    "max_delta_frequency_percent",
                    0.1,
                ),
                "minimum_converged_passes": _bounded_int(
                    payload.get("minimum_converged_passes", 2),
                    1,
                    20,
                    "minimum_converged_passes",
                ),
            },
            "observables": {
                "eigenfrequencies_hz": True,
                "quality_factors": True,
                "mode_fields": True,
                "field_energy_by_object": True,
                "parity_review": study_kind is StudyKind.COUPLING,
            },
            "ports": [],
            "assign_ports": False,
            "dry_run": bool(payload.get("dry_run", True)),
            "overwrite": bool(payload.get("overwrite", True)),
        }
    )
    return plan


def _combline_resonator_plan(
    component: ComponentDefinition,
    geometry: dict[str, Any],
) -> dict[str, Any]:
    prefix = str(geometry.get("name") or component.component_id).replace("-", "_")
    length = _geometry_value(geometry, "cavity_length_mm", 72.0)
    width = _geometry_value(geometry, "cavity_width_mm", 48.0)
    height = _geometry_value(geometry, "cavity_height_mm", 75.0)
    wall = _geometry_value(geometry, "wall_mm", 2.5)
    radius = _parameter_nominal(component, "resonator_radius_mm", geometry, 4.0)
    rod_height = _parameter_nominal(component, "resonator_height_mm", geometry, 62.0)
    if wall * 2 >= min(length, width, height):
        raise ValueError("wall_mm is too large for the resonator enclosure")
    if rod_height >= height - wall:
        raise ValueError("resonator_height_mm must leave a capacitive top gap")
    shell = f"{prefix}_shell"
    air = f"{prefix}_air"
    rod = f"{prefix}_rod"
    return {
        "name": prefix,
        "recipe": component.recipe,
        "units": "mm",
        "variables": {
            "cavity_length_mm": length,
            "cavity_width_mm": width,
            "cavity_height_mm": height,
            "wall_mm": wall,
            "resonator_radius_mm": radius,
            "resonator_height_mm": rod_height,
            "top_gap_mm": height - wall - rod_height,
        },
        "objects": [
            _box(shell, [0.0, 0.0, 0.0], [length, width, height], "copper"),
            _box(
                air,
                [wall, wall, wall],
                [length - 2 * wall, width - 2 * wall, height - 2 * wall],
                "air",
            ),
            _cylinder(
                rod,
                "Z",
                [length / 2.0, width / 2.0, wall],
                radius,
                rod_height,
                "copper",
            ),
        ],
        "operations": [
            {
                "operation": "subtract",
                "blank": shell,
                "tools": [air],
                "keep_originals": True,
            }
        ],
        "groups": {
            "metal": [shell, rod],
            "dielectric_regions": [air],
            "tracking_regions": {"resonator": [rod], "cavity": [air]},
        },
        "boundaries": [
            {"type": "perfect_e", "objects": [shell, rod], "name": f"{prefix}_PEC"}
        ],
        "geometry_contract": {
            "resonator_axis": "Z",
            "reference_plane": "cavity_base",
            "parameterized_objects": {
                "resonator_height_mm": [rod],
                "resonator_radius_mm": [rod],
            },
        },
    }


def _combline_pair_plan(
    component: ComponentDefinition,
    geometry: dict[str, Any],
) -> dict[str, Any]:
    prefix = str(geometry.get("name") or component.component_id).replace("-", "_")
    cavity_length = _geometry_value(geometry, "cavity_length_mm", 72.0)
    width = _geometry_value(geometry, "cavity_width_mm", 48.0)
    height = _geometry_value(geometry, "cavity_height_mm", 75.0)
    wall = _geometry_value(geometry, "wall_mm", 2.5)
    shared_wall = _geometry_value(geometry, "shared_wall_mm", wall)
    radius = _geometry_value(geometry, "resonator_radius_mm", 4.0)
    rod_height = _geometry_value(geometry, "resonator_height_mm", 62.0)
    iris_width = _parameter_nominal(component, "iris_width_mm", geometry, 18.0)
    iris_height = _geometry_value(geometry, "iris_height_mm", height * 0.60)
    total_length = 2.0 * cavity_length + shared_wall
    if iris_width >= width - 2.0 * wall:
        raise ValueError("iris_width_mm must fit inside the cavity width")
    if iris_height >= height - 2.0 * wall:
        raise ValueError("iris_height_mm must fit inside the cavity height")
    shell = f"{prefix}_shell"
    left_air = f"{prefix}_air_left"
    right_air = f"{prefix}_air_right"
    aperture = f"{prefix}_iris_cut"
    left_rod = f"{prefix}_rod_left"
    right_rod = f"{prefix}_rod_right"
    left_center = wall + (cavity_length - 2.0 * wall) / 2.0
    right_start = cavity_length + shared_wall
    right_center = right_start + wall + (cavity_length - 2.0 * wall) / 2.0
    aperture_x = cavity_length
    return {
        "name": prefix,
        "recipe": component.recipe,
        "units": "mm",
        "variables": {
            "cavity_length_mm": cavity_length,
            "cavity_width_mm": width,
            "cavity_height_mm": height,
            "wall_mm": wall,
            "shared_wall_mm": shared_wall,
            "resonator_radius_mm": radius,
            "resonator_height_mm": rod_height,
            "iris_width_mm": iris_width,
            "iris_height_mm": iris_height,
        },
        "objects": [
            _box(shell, [0.0, 0.0, 0.0], [total_length, width, height], "copper"),
            _box(
                left_air,
                [wall, wall, wall],
                [cavity_length - 2.0 * wall, width - 2.0 * wall, height - 2.0 * wall],
                "air",
            ),
            _box(
                right_air,
                [right_start + wall, wall, wall],
                [cavity_length - 2.0 * wall, width - 2.0 * wall, height - 2.0 * wall],
                "air",
            ),
            _box(
                aperture,
                [
                    aperture_x,
                    (width - iris_width) / 2.0,
                    wall + (height - 2.0 * wall - iris_height) / 2.0,
                ],
                [shared_wall, iris_width, iris_height],
                "air",
            ),
            _cylinder(
                left_rod,
                "Z",
                [left_center, width / 2.0, wall],
                radius,
                rod_height,
                "copper",
            ),
            _cylinder(
                right_rod,
                "Z",
                [right_center, width / 2.0, wall],
                radius,
                rod_height,
                "copper",
            ),
        ],
        "operations": [
            {
                "operation": "subtract",
                "blank": shell,
                "tools": [left_air, right_air, aperture],
                "keep_originals": True,
            }
        ],
        "groups": {
            "metal": [shell, left_rod, right_rod],
            "dielectric_regions": [left_air, right_air, aperture],
            "tracking_regions": {
                "left_resonator": [left_rod, left_air],
                "right_resonator": [right_rod, right_air],
                "coupling_aperture": [aperture],
            },
        },
        "boundaries": [
            {
                "type": "perfect_e",
                "objects": [shell, left_rod, right_rod],
                "name": f"{prefix}_PEC",
            }
        ],
        "geometry_contract": {
            "pair_symmetry_plane": "shared_wall_center",
            "parameterized_objects": {"iris_width_mm": [aperture]},
            "coupling_sign": {
                "source": "topology-or-field-parity",
                "review_required": True,
            },
        },
    }


def _default_parameter(
    component: ComponentDefinition,
    study_kind: StudyKind,
) -> ParameterDefinition:
    expected_role = {
        StudyKind.RESONANCE: "resonator_height_mm",
        StudyKind.COUPLING: "iris_width_mm",
        StudyKind.EXTERNAL_Q: "probe_depth_mm",
    }.get(study_kind)
    if expected_role:
        for parameter in component.parameters:
            if parameter.name == expected_role:
                return parameter
    if not component.parameters:
        raise ValueError(f"component {component.component_id!r} has no parameters")
    return component.parameters[0]


def _find_parameter(component: ComponentDefinition, name: str) -> ParameterDefinition:
    for parameter in component.parameters:
        if parameter.name == name:
            return parameter
    raise ValueError(f"component {component.component_id!r} has no parameter {name!r}")


def _parameter_nominal(
    component: ComponentDefinition,
    name: str,
    geometry: dict[str, Any],
    default: float,
) -> float:
    if name in geometry:
        return _geometry_value(geometry, name, default)
    try:
        return float(_find_parameter(component, name).nominal)
    except ValueError:
        return float(default)


def _geometry_value(geometry: dict[str, Any], name: str, default: float) -> float:
    value = float(geometry.get(name, default))
    if value <= 0.0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _box(
    name: str,
    origin: list[float],
    sizes: list[float],
    material: str,
) -> dict[str, Any]:
    return {
        "primitive": "box",
        "name": name,
        "origin": origin,
        "sizes": sizes,
        "material": material,
    }


def _cylinder(
    name: str,
    orientation: str,
    origin: list[float],
    radius: float,
    height: float,
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


def _positive(payload: dict[str, Any], name: str, default: float) -> float:
    value = float(payload.get(name, default))
    if value <= 0.0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _bounded_int(value: Any, minimum: int, maximum: int, name: str) -> int:
    result = int(value)
    if not minimum <= result <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return result
