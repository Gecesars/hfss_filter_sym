from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import optimize

from hfss_vna_bridge.services.synthesis import synthesize_filter


def optimize_filter_specification(payload: dict[str, Any]) -> dict[str, Any]:
    base = dict(payload.get("specification") or {})
    if not base:
        raise ValueError("specification is required")
    targets = {
        "center_ghz": float(base.get("f0_ghz", 1.0)),
        "bandwidth_ghz": float(base.get("bandwidth_ghz", 0.05)),
        "return_loss_db": float(base.get("return_loss_db", 25.0)),
        "maximum_insertion_loss_db": 1.0,
        **(payload.get("targets") or {}),
    }
    requested = payload.get("variables") or {
        "f0_ghz": [
            float(base.get("f0_ghz", 1.0)) * 0.95,
            float(base.get("f0_ghz", 1.0)) * 1.05,
        ],
        "bandwidth_ghz": [
            float(base.get("bandwidth_ghz", 0.05)) * 0.7,
            float(base.get("bandwidth_ghz", 0.05)) * 1.3,
        ],
        "return_loss_db": [
            max(1.0, float(base.get("return_loss_db", 25.0)) - 8.0),
            float(base.get("return_loss_db", 25.0)) + 8.0,
        ],
    }
    if not isinstance(requested, dict) or not requested:
        raise ValueError("variables must be a non-empty object of [minimum, maximum] bounds")
    names: list[str] = []
    bounds: list[tuple[float, float]] = []
    for name, value in requested.items():
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError(f"Variable {name!r} must contain [minimum, maximum]")
        minimum, maximum = float(value[0]), float(value[1])
        if maximum <= minimum:
            raise ValueError(f"Variable {name!r} maximum must exceed minimum")
        names.append(str(name))
        bounds.append((minimum, maximum))

    max_iterations = _bounded_int(payload.get("max_iterations", 20), 1, 200, "max_iterations")
    seed = int(payload.get("seed", 2026))
    history: list[dict[str, float]] = []
    evaluations = 0

    def objective(vector: np.ndarray) -> float:
        nonlocal evaluations
        evaluations += 1
        candidate = {**base, **dict(zip(names, vector, strict=True)), "points": 201}
        result = synthesize_filter(candidate)
        summary = result["summary"]
        spec = result["specification"]
        center_error = (
            (spec["effective_f0_ghz"] - float(targets["center_ghz"]))
            / max(float(targets["bandwidth_ghz"]), 1e-9)
        )
        bandwidth_error = (
            (spec["effective_bandwidth_ghz"] - float(targets["bandwidth_ghz"]))
            / max(float(targets["bandwidth_ghz"]), 1e-9)
        )
        return_error = (
            summary["achieved_return_loss_db"] - float(targets["return_loss_db"])
        ) / max(float(targets["return_loss_db"]), 1.0)
        insertion_excess = max(
            0.0,
            summary["center_insertion_loss_db"]
            - float(targets["maximum_insertion_loss_db"]),
        )
        return float(
            center_error**2
            + bandwidth_error**2
            + return_error**2
            + insertion_excess**2
        )

    def callback(vector: np.ndarray, convergence: float) -> bool:
        history.append(
            {
                "iteration": float(len(history) + 1),
                "objective": objective(vector),
                "convergence": float(convergence),
            }
        )
        return False

    result = optimize.differential_evolution(
        objective,
        bounds,
        maxiter=max_iterations,
        popsize=_bounded_int(payload.get("population", 8), 4, 30, "population"),
        seed=seed,
        polish=True,
        updating="immediate",
        workers=1,
        callback=callback,
    )
    optimized = {**base, **dict(zip(names, result.x, strict=True))}
    synthesis = synthesize_filter(optimized)
    return {
        "status": 0,
        "ok": True,
        "success": bool(result.success),
        "message": str(result.message),
        "objective": float(result.fun),
        "evaluations": evaluations,
        "iterations": int(result.nit),
        "variables": {name: float(value) for name, value in zip(names, result.x, strict=True)},
        "specification": optimized,
        "summary": synthesis["summary"],
        "targets": targets,
        "history": history,
    }


def tuning_recommendations(
    target: dict[str, Any],
    measured: dict[str, Any],
    *,
    sensitivities: dict[str, float] | None = None,
) -> dict[str, Any]:
    target_center = _required_metric(target, "center_hz")
    measured_center = _required_metric(measured, "center_hz")
    target_bandwidth = _required_metric(target, "bandwidth_3db_hz")
    measured_bandwidth = _required_metric(measured, "bandwidth_3db_hz")
    target_return = abs(_required_metric(target, "minimum_s11_db"))
    measured_return = abs(_required_metric(measured, "minimum_s11_db"))
    mapping = {
        "frequency_hz_per_turn": 2.0e6,
        "bandwidth_hz_per_turn": 1.0e6,
        "return_loss_db_per_turn": 1.0,
        **(sensitivities or {}),
    }

    center_error = target_center - measured_center
    bandwidth_error = target_bandwidth - measured_bandwidth
    return_error = target_return - measured_return
    actions = [
        _tuning_action(
            "resonators",
            center_error / mapping["frequency_hz_per_turn"],
            "turns",
            center_error,
            "Move all resonators together to align center frequency.",
        ),
        _tuning_action(
            "inter_resonator_couplings",
            bandwidth_error / mapping["bandwidth_hz_per_turn"],
            "turns",
            bandwidth_error,
            "Adjust inter-resonator coupling to align the 3 dB bandwidth.",
        ),
        _tuning_action(
            "input_output_couplings",
            return_error / mapping["return_loss_db_per_turn"],
            "turns",
            return_error,
            "Balance source/load coupling to recover in-band return loss.",
        ),
    ]
    actions.sort(key=lambda item: abs(float(item["normalized_priority"])), reverse=True)
    return {
        "status": 0,
        "ok": True,
        "errors": {
            "center_hz": center_error,
            "bandwidth_hz": bandwidth_error,
            "return_loss_db": return_error,
        },
        "actions": actions,
        "sensitivities": mapping,
        "converged": (
            abs(center_error) <= abs(target_bandwidth) * 0.01
            and abs(bandwidth_error) <= abs(target_bandwidth) * 0.02
            and abs(return_error) <= 0.5
        ),
    }


def monte_carlo_filter(payload: dict[str, Any]) -> dict[str, Any]:
    base = dict(payload.get("specification") or payload)
    samples = _bounded_int(payload.get("samples", 250), 10, 10_000, "samples")
    seed = int(payload.get("seed", 2026))
    tolerances = {
        "f0_relative": 0.002,
        "bandwidth_relative": 0.03,
        "return_loss_db": 0.5,
        "unloaded_q_relative": 0.05,
        **(payload.get("tolerances") or {}),
    }
    limits = {
        "minimum_return_loss_db": float(base.get("return_loss_db", 25.0)) - 3.0,
        "maximum_insertion_loss_db": 1.5,
        **(payload.get("limits") or {}),
    }
    base["points"] = min(int(base.get("points", 201)), 401)
    rng = np.random.default_rng(seed)
    rows = []
    passed = 0
    for index in range(samples):
        candidate = dict(base)
        candidate["f0_ghz"] = float(base.get("f0_ghz", 1.0)) * (
            1.0 + rng.normal(0.0, float(tolerances["f0_relative"]))
        )
        candidate["bandwidth_ghz"] = float(base.get("bandwidth_ghz", 0.05)) * (
            1.0 + rng.normal(0.0, float(tolerances["bandwidth_relative"]))
        )
        candidate["return_loss_db"] = max(
            1.0,
            float(base.get("return_loss_db", 25.0))
            + rng.normal(0.0, float(tolerances["return_loss_db"])),
        )
        if base.get("unloaded_q") not in {None, "", "Infinity", "infinity"}:
            candidate["unloaded_q"] = max(
                1.0,
                float(base["unloaded_q"])
                * (1.0 + rng.normal(0.0, float(tolerances["unloaded_q_relative"]))),
            )
        result = synthesize_filter(candidate)
        summary = result["summary"]
        accepted = (
            summary["achieved_return_loss_db"] >= limits["minimum_return_loss_db"]
            and summary["center_insertion_loss_db"] <= limits["maximum_insertion_loss_db"]
        )
        passed += int(accepted)
        rows.append(
            {
                "sample": index + 1,
                "passed": accepted,
                "f0_ghz": candidate["f0_ghz"],
                "bandwidth_ghz": candidate["bandwidth_ghz"],
                "return_loss_db": summary["achieved_return_loss_db"],
                "insertion_loss_db": summary["center_insertion_loss_db"],
            }
        )
    return {
        "status": 0,
        "ok": True,
        "samples": samples,
        "seed": seed,
        "passed": passed,
        "failed": samples - passed,
        "yield_percent": 100.0 * passed / samples,
        "statistics": {
            "return_loss_db": _statistics(row["return_loss_db"] for row in rows),
            "insertion_loss_db": _statistics(row["insertion_loss_db"] for row in rows),
            "f0_ghz": _statistics(row["f0_ghz"] for row in rows),
            "bandwidth_ghz": _statistics(row["bandwidth_ghz"] for row in rows),
        },
        "limits": limits,
        "tolerances": tolerances,
        "samples_preview": rows[: min(100, len(rows))],
    }


def transmission_line(payload: dict[str, Any]) -> dict[str, Any]:
    kind = str(payload.get("kind") or "microstrip").lower()
    if kind == "microstrip":
        return _microstrip(payload)
    if kind == "stripline":
        return _stripline(payload)
    if kind == "rectangular_waveguide":
        return _rectangular_waveguide(payload)
    if kind == "siw":
        return _siw(payload)
    raise ValueError("kind must be microstrip, stripline, rectangular_waveguide, or siw")


def _microstrip(payload: dict[str, Any]) -> dict[str, Any]:
    width = _positive(payload, "width_mm", 2.9) * 1e-3
    height = _positive(payload, "height_mm", 1.6) * 1e-3
    epsilon_r = _positive(payload, "epsilon_r", 4.4)
    frequency = _positive(payload, "frequency_ghz", 1.0) * 1e9
    ratio = width / height
    epsilon_eff = (epsilon_r + 1.0) / 2.0 + (epsilon_r - 1.0) / 2.0 / math.sqrt(
        1.0 + 12.0 / ratio
    )
    if ratio <= 1.0:
        impedance = 60.0 / math.sqrt(epsilon_eff) * math.log(
            8.0 / ratio + ratio / 4.0
        )
    else:
        impedance = 120.0 * math.pi / (
            math.sqrt(epsilon_eff)
            * (ratio + 1.393 + 0.667 * math.log(ratio + 1.444))
        )
    wavelength = 299_792_458.0 / (frequency * math.sqrt(epsilon_eff))
    return _line_result(
        "microstrip",
        impedance,
        epsilon_eff,
        wavelength,
        {"width_mm": width * 1e3, "height_mm": height * 1e3, "epsilon_r": epsilon_r},
    )


def _stripline(payload: dict[str, Any]) -> dict[str, Any]:
    width = _positive(payload, "width_mm", 1.0) * 1e-3
    spacing = _positive(payload, "spacing_mm", 1.6) * 1e-3
    thickness = _positive(payload, "thickness_mm", 0.035) * 1e-3
    epsilon_r = _positive(payload, "epsilon_r", 4.4)
    frequency = _positive(payload, "frequency_ghz", 1.0) * 1e9
    effective_width = width + thickness / math.pi * (
        1.0 + math.log(max(2.0 * spacing / max(thickness, 1e-12), 1.0))
    )
    impedance = 30.0 * math.pi / math.sqrt(epsilon_r) / (
        effective_width / spacing + 0.441
    )
    wavelength = 299_792_458.0 / (frequency * math.sqrt(epsilon_r))
    return _line_result(
        "stripline",
        impedance,
        epsilon_r,
        wavelength,
        {
            "width_mm": width * 1e3,
            "spacing_mm": spacing * 1e3,
            "thickness_mm": thickness * 1e3,
            "epsilon_r": epsilon_r,
        },
    )


def _rectangular_waveguide(payload: dict[str, Any]) -> dict[str, Any]:
    broad_wall = _positive(payload, "a_mm", 22.86) * 1e-3
    narrow_wall = _positive(payload, "b_mm", 10.16) * 1e-3
    frequency = _positive(payload, "frequency_ghz", 10.0) * 1e9
    cutoff_te10 = 299_792_458.0 / (2.0 * broad_wall)
    cutoff_te20 = 299_792_458.0 / broad_wall
    cutoff_te01 = 299_792_458.0 / (2.0 * narrow_wall)
    if frequency <= cutoff_te10:
        guide_wavelength = None
        impedance = None
    else:
        ratio = cutoff_te10 / frequency
        guide_wavelength = 299_792_458.0 / frequency / math.sqrt(1.0 - ratio**2)
        impedance = 376.730313668 / math.sqrt(1.0 - ratio**2)
    return {
        "status": 0,
        "ok": True,
        "kind": "rectangular_waveguide",
        "cutoff_hz": {"TE10": cutoff_te10, "TE20": cutoff_te20, "TE01": cutoff_te01},
        "single_mode_upper_hz": min(cutoff_te20, cutoff_te01),
        "operating_above_cutoff": frequency > cutoff_te10,
        "guide_wavelength_mm": guide_wavelength * 1e3 if guide_wavelength else None,
        "wave_impedance_ohm": impedance,
    }


def _siw(payload: dict[str, Any]) -> dict[str, Any]:
    width = _positive(payload, "width_mm", 15.0)
    diameter = _positive(payload, "via_diameter_mm", 0.8)
    pitch = _positive(payload, "via_pitch_mm", 1.5)
    epsilon_r = _positive(payload, "epsilon_r", 3.55)
    effective_width_mm = width - diameter**2 / (0.95 * pitch)
    if effective_width_mm <= 0:
        raise ValueError("SIW effective width must be positive")
    cutoff = 299_792_458.0 / (
        2.0 * effective_width_mm * 1e-3 * math.sqrt(epsilon_r)
    )
    return {
        "status": 0,
        "ok": True,
        "kind": "siw",
        "effective_width_mm": effective_width_mm,
        "cutoff_te10_hz": cutoff,
        "recommended": {
            "via_pitch_max_mm": 2.0 * diameter,
            "pitch_to_diameter": pitch / diameter,
            "passes_leakage_rule": pitch <= 2.0 * diameter,
        },
    }


def _line_result(
    kind: str,
    impedance: float,
    epsilon_eff: float,
    wavelength_m: float,
    inputs: dict[str, float],
) -> dict[str, Any]:
    return {
        "status": 0,
        "ok": True,
        "kind": kind,
        "inputs": inputs,
        "impedance_ohm": impedance,
        "effective_permittivity": epsilon_eff,
        "guided_wavelength_mm": wavelength_m * 1e3,
        "quarter_wave_mm": wavelength_m * 250.0,
        "half_wave_mm": wavelength_m * 500.0,
    }


def _tuning_action(
    control: str,
    value: float,
    unit: str,
    raw_error: float,
    rationale: str,
) -> dict[str, Any]:
    return {
        "control": control,
        "direction": "increase" if value > 0 else "decrease",
        "adjustment": value,
        "unit": unit,
        "raw_error": raw_error,
        "normalized_priority": value,
        "rationale": rationale,
    }


def _required_metric(metrics: dict[str, Any], name: str) -> float:
    value = metrics.get(name)
    if value is None:
        raise ValueError(f"Metric {name!r} is required for tuning")
    return float(value)


def _statistics(values: Any) -> dict[str, float]:
    array = np.asarray(list(values), dtype=float)
    return {
        "mean": float(np.mean(array)),
        "std": float(np.std(array)),
        "minimum": float(np.min(array)),
        "maximum": float(np.max(array)),
        "p05": float(np.percentile(array, 5)),
        "p50": float(np.percentile(array, 50)),
        "p95": float(np.percentile(array, 95)),
    }


def _positive(payload: dict[str, Any], name: str, default: float) -> float:
    value = float(payload.get(name, default))
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _bounded_int(value: Any, minimum: int, maximum: int, name: str) -> int:
    result = int(value)
    if result < minimum or result > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return result
