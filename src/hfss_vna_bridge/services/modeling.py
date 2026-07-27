from __future__ import annotations

import re
from typing import Any

HFSS_RECIPE_MAP = {
    "makelpfmodel": "lpf_step",
    "iosimulation": "io",
    "full3dsimulation": "cavity",
    "lumpportsimulation": "planar",
    "planarsimulation": "planar",
    "planarupdatemodel": "planar",
    "ccsinglemodeling": "combline",
    "ccupdatelumpport": "combline",
    "ccthermalmodeling": "combline",
    "ccpowerhandling": "combline",
    "cccouplingmodeling": "combline",
    "cciomodeling": "combline",
    "wgrsinglemodeling": "waveguide",
    "wgrcouplingmodeling": "waveguide",
    "wgriomodeling": "waveguide",
    "wgcsinglemodeling": "waveguide",
    "wgccouplingmodeling": "waveguide",
    "wgciomodeling": "waveguide",
    "siwsinglemodeling": "siw",
    "siwcouplingmodeling": "siw",
    "siwiomodeling": "siw",
    "siwfull3d": "siw",
    "buildcavityfull3d": "cavity",
    "updatecavityfull3d": "cavity",
    "lpfstepmodeling": "lpf_step",
    "lpfopenstubmodeling": "lpf_open_stub",
    "lpfellipticmodeling": "lpf_elliptic",
    "lpfcustommodeling": "lpf_custom",
}


def model_plan(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = method.replace("-", "").replace("_", "").lower()
    recipe = str(payload.get("recipe") or HFSS_RECIPE_MAP.get(normalized) or normalized).lower()
    if recipe in {"cavity", "combline", "waveguide"}:
        plan = _cavity_plan(recipe, payload)
    elif recipe in {"planar", "siw", "lpf_step", "lpf_open_stub", "lpf_elliptic", "lpf_custom", "io"}:
        plan = _planar_plan(recipe, payload)
    else:
        raise ValueError(f"Unsupported HFSS model recipe: {recipe}")
    plan["method"] = method
    plan["recipe"] = recipe
    plan["dry_run"] = _boolean(payload.get("dry_run", False))
    plan["overwrite"] = _boolean(payload.get("overwrite", True))
    plan["assign_ports"] = _boolean(payload.get("assign_ports", True))
    plan["setup"] = {
        "name": str(payload.get("setup_name") or payload.get("setup") or "FilterSetup"),
        "sweep_name": str(payload.get("sweep_name") or payload.get("sweep") or "FilterSweep"),
        "center_frequency_ghz": _positive(payload, "f0_ghz", 1.0),
        "start_frequency_ghz": _positive(payload, "start_ghz", 0.8),
        "stop_frequency_ghz": _positive(payload, "stop_ghz", 1.2),
        "points": _bounded_int(payload.get("points", 401), 2, 10_001, "points"),
        "maximum_passes": _bounded_int(payload.get("maximum_passes", 12), 1, 100, "maximum_passes"),
        "max_delta_s": _positive(payload, "max_delta_s", 0.02),
        "sweep_type": str(payload.get("sweep_type") or "Interpolating"),
    }
    if plan["setup"]["stop_frequency_ghz"] <= plan["setup"]["start_frequency_ghz"]:
        raise ValueError("stop_ghz must be greater than start_ghz")
    return plan


def _cavity_plan(recipe: str, payload: dict[str, Any]) -> dict[str, Any]:
    prefix = _prefix(payload.get("name") or recipe)
    order = _bounded_int(payload.get("order", 4), 1, 24, "order")
    length = _positive(payload, "length_mm", 120.0)
    width = _positive(payload, "width_mm", 50.0)
    height = _positive(payload, "height_mm", 25.0)
    wall = _positive(payload, "wall_mm", 2.0)
    if wall * 2 >= min(length, width, height):
        raise ValueError("wall_mm is too large for the selected enclosure")
    radius = _positive(payload, "resonator_radius_mm", 3.0)
    resonator_height = _positive(payload, "resonator_height_mm", height - wall * 2)
    material = str(payload.get("metal_material") or "copper")
    objects = [
        _box(f"{prefix}_shell", [0, 0, 0], [length, width, height], material),
        _box(
            f"{prefix}_air",
            [wall, wall, wall],
            [length - 2 * wall, width - 2 * wall, height - 2 * wall],
            "air",
        ),
    ]
    operations = [
        {
            "operation": "subtract",
            "blank": f"{prefix}_shell",
            "tools": [f"{prefix}_air"],
            "keep_originals": True,
        }
    ]
    pitch = (length - 2 * wall) / (order + 1)
    resonators = []
    for index in range(order):
        name = f"{prefix}_res_{index + 1}"
        resonators.append(name)
        objects.append(
            _cylinder(
                name,
                "Z",
                [wall + pitch * (index + 1), width / 2, wall],
                radius,
                min(resonator_height, height - 2 * wall),
                material,
            )
        )
    if recipe == "waveguide":
        for index in range(1, order):
            objects.append(
                _box(
                    f"{prefix}_iris_{index}",
                    [wall + pitch * (index + 0.5), wall, wall],
                    [wall, width - 2 * wall, height - 2 * wall],
                    material,
                )
            )
    port_radius = max(radius * 0.35, 0.5)
    objects.extend(
        [
            _cylinder(
                f"{prefix}_input_pin",
                "Z",
                [wall + pitch * 0.45, width / 2, wall],
                port_radius,
                min(resonator_height * 0.7, height - 2 * wall),
                material,
            ),
            _cylinder(
                f"{prefix}_output_pin",
                "Z",
                [length - wall - pitch * 0.45, width / 2, wall],
                port_radius,
                min(resonator_height * 0.7, height - 2 * wall),
                material,
            ),
        ]
    )
    return {
        "name": prefix,
        "units": "mm",
        "solution_type": "Modal",
        "objects": objects,
        "operations": operations,
        "ports": [
            {
                "name": f"{prefix}_Port1",
                "signal": f"{prefix}_input_pin",
                "reference": f"{prefix}_shell",
                "impedance": 50.0,
            },
            {
                "name": f"{prefix}_Port2",
                "signal": f"{prefix}_output_pin",
                "reference": f"{prefix}_shell",
                "impedance": 50.0,
            },
        ],
        "groups": {"resonators": resonators},
        "parameters": {
            "order": order,
            "length_mm": length,
            "width_mm": width,
            "height_mm": height,
            "wall_mm": wall,
        },
    }


def _planar_plan(recipe: str, payload: dict[str, Any]) -> dict[str, Any]:
    prefix = _prefix(payload.get("name") or recipe)
    order = _bounded_int(payload.get("order", 4), 1, 24, "order")
    length = _positive(payload, "length_mm", 100.0)
    width = _positive(payload, "board_width_mm", 40.0)
    substrate_height = _positive(payload, "substrate_height_mm", 1.524)
    copper = _positive(payload, "copper_thickness_mm", 0.035)
    line_width = _positive(payload, "line_width_mm", 2.8)
    substrate = str(payload.get("substrate_material") or "Rogers RO4003C (tm)")
    metal = str(payload.get("metal_material") or "copper")
    objects = [
        _box(
            f"{prefix}_substrate",
            [0, -width / 2, 0],
            [length, width, substrate_height],
            substrate,
        ),
        _box(
            f"{prefix}_ground",
            [0, -width / 2, -copper],
            [length, width, copper],
            metal,
        ),
    ]
    section_length = length / (order + 2)
    traces = []
    for index in range(order + 2):
        section_width = line_width
        if recipe in {"lpf_step", "lpf_elliptic", "lpf_custom"}:
            custom_widths = payload.get("section_widths_mm")
            if isinstance(custom_widths, list) and index < len(custom_widths):
                section_width = _number(custom_widths[index], "section_widths_mm")
            else:
                section_width *= 1.8 if index % 2 else 0.7
        trace_name = f"{prefix}_trace_{index + 1}"
        traces.append(trace_name)
        objects.append(
            _box(
                trace_name,
                [index * section_length, -section_width / 2, substrate_height],
                [section_length, section_width, copper],
                metal,
            )
        )
        if recipe in {"lpf_open_stub", "lpf_elliptic"} and 0 < index < order + 1:
            stub_length = _positive(payload, "stub_length_mm", section_length * 0.7)
            objects.append(
                _box(
                    f"{prefix}_stub_{index}",
                    [
                        index * section_length + section_length / 2 - line_width / 2,
                        section_width / 2,
                        substrate_height,
                    ],
                    [line_width, stub_length, copper],
                    metal,
                )
            )
    operations: list[dict[str, Any]] = []
    vias = []
    if recipe == "siw":
        via_radius = _positive(payload, "via_diameter_mm", 0.8) / 2.0
        via_pitch = _positive(payload, "via_pitch_mm", 1.5)
        via_count = max(2, int(length / via_pitch) + 1)
        for row, y in enumerate((-width * 0.32, width * 0.32), start=1):
            for index in range(via_count):
                name = f"{prefix}_via_{row}_{index + 1}"
                vias.append(name)
                objects.append(
                    _cylinder(
                        name,
                        "Z",
                        [min(index * via_pitch, length), y, -copper],
                        via_radius,
                        substrate_height + 2 * copper,
                        metal,
                    )
                )
    return {
        "name": prefix,
        "units": "mm",
        "solution_type": "Modal",
        "objects": objects,
        "operations": operations,
        "ports": [
            {
                "name": f"{prefix}_Port1",
                "signal": traces[0],
                "reference": f"{prefix}_ground",
                "impedance": 50.0,
            },
            {
                "name": f"{prefix}_Port2",
                "signal": traces[-1],
                "reference": f"{prefix}_ground",
                "impedance": 50.0,
            },
        ],
        "groups": {"traces": traces, "vias": vias},
        "parameters": {
            "order": order,
            "length_mm": length,
            "board_width_mm": width,
            "substrate_height_mm": substrate_height,
            "line_width_mm": line_width,
        },
    }


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


def _prefix(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_]+", "_", str(value)).strip("_")
    return (text or "FilterModel")[:48]


def _positive(payload: dict[str, Any], name: str, default: float) -> float:
    value = float(payload.get(name, default))
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _number(value: Any, name: str) -> float:
    number = float(value)
    if number <= 0:
        raise ValueError(f"{name} values must be greater than zero")
    return number


def _bounded_int(value: Any, minimum: int, maximum: int, name: str) -> int:
    result = int(value)
    if result < minimum or result > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return result


def _boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
