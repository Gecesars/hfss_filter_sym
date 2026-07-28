from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import numpy as np
from scipy.optimize import least_squares

from .characterization import build_characterization_curve


EXTERNAL_Q_PLAN_SCHEMA = "hfss-filter-studio/fd3d-external-q-plan/v1"


@dataclass(frozen=True)
class ExternalQFit:
    resonance_frequency_hz: float
    loaded_q: float
    external_q: float
    internal_q: float | None
    coupling_beta: float
    resonant_depth: float
    phase_rad: float
    delay_s: float
    rms_complex_error: float
    success: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "resonance_frequency_hz": self.resonance_frequency_hz,
            "loaded_q": self.loaded_q,
            "external_q": self.external_q,
            "internal_q": self.internal_q,
            "coupling_beta": self.coupling_beta,
            "resonant_depth": self.resonant_depth,
            "phase_rad": self.phase_rad,
            "delay_s": self.delay_s,
            "rms_complex_error": self.rms_complex_error,
            "success": self.success,
            "message": self.message,
        }


def one_port_resonator_s11(
    frequencies_hz: np.ndarray | list[float],
    *,
    resonance_frequency_hz: float,
    loaded_q: float,
    resonant_depth: float,
    phase_rad: float = 0.0,
    delay_s: float = 0.0,
) -> np.ndarray:
    """Return the calibrated one-port resonator reflection model.

    ``resonant_depth`` is ``2*Ql/Qe`` and is constrained to ``0 < d < 2``.
    Therefore ``Qe = 2*Ql/d`` and ``1/Ql = 1/Qi + 1/Qe``.
    """

    frequency = np.asarray(frequencies_hz, dtype=float)
    f0 = float(resonance_frequency_hz)
    ql = float(loaded_q)
    depth = float(resonant_depth)
    if f0 <= 0.0 or ql <= 0.0:
        raise ValueError("resonance frequency and loaded Q must be positive")
    if not 0.0 < depth < 2.0:
        raise ValueError("resonant_depth must be in the open interval (0, 2)")
    normalized = (frequency - f0) / f0
    resonator = 1.0 - depth / (1.0 + 2j * ql * normalized)
    reference = np.exp(1j * (float(phase_rad) + 2.0 * np.pi * (frequency - f0) * float(delay_s)))
    return reference * resonator


def fit_external_q(
    frequencies_hz: np.ndarray | list[float],
    s11: np.ndarray | list[complex],
) -> ExternalQFit:
    """Fit a complex one-port resonator and extract Ql, Qe, Qi and beta."""

    frequency = np.asarray(frequencies_hz, dtype=float)
    reflection = np.asarray(s11, dtype=np.complex128)
    if frequency.ndim != 1 or reflection.ndim != 1 or frequency.size != reflection.size:
        raise ValueError("frequency and S11 must be one-dimensional arrays with equal length")
    if frequency.size < 21:
        raise ValueError("external-Q fitting requires at least 21 frequency samples")
    if np.any(~np.isfinite(frequency)) or np.any(~np.isfinite(reflection.real)) or np.any(~np.isfinite(reflection.imag)):
        raise ValueError("frequency and S11 samples must be finite")
    order = np.argsort(frequency)
    frequency = frequency[order]
    reflection = reflection[order]
    if np.any(np.diff(frequency) <= 0.0):
        raise ValueError("frequency samples must be strictly increasing")

    minimum_index = int(np.argmin(np.abs(reflection)))
    f0_seed = float(frequency[minimum_index])
    phase_seed = float(np.angle(np.mean(np.r_[reflection[:3], reflection[-3:]])))
    corrected_at_resonance = reflection[minimum_index] * np.exp(-1j * phase_seed)
    depth_seed = float(np.clip(1.0 - corrected_at_resonance.real, 0.05, 1.95))
    span = float(frequency[-1] - frequency[0])
    q_from_span = max(f0_seed / max(span * 0.15, 1.0), 10.0)

    def unpack(vector: np.ndarray) -> tuple[float, float, float, float, float]:
        f0 = float(vector[0])
        ql = float(np.exp(vector[1]))
        depth = float(2.0 / (1.0 + np.exp(-vector[2])))
        return f0, ql, depth, float(vector[3]), float(vector[4])

    scale = max(float(np.sqrt(np.mean(np.abs(reflection) ** 2))), 1e-9)

    def residual(vector: np.ndarray) -> np.ndarray:
        f0, ql, depth, phase, delay = unpack(vector)
        predicted = one_port_resonator_s11(
            frequency,
            resonance_frequency_hz=f0,
            loaded_q=ql,
            resonant_depth=depth,
            phase_rad=phase,
            delay_s=delay,
        )
        difference = (predicted - reflection) / scale
        return np.r_[difference.real, difference.imag]

    q_seeds = sorted(
        {
            max(10.0, q_from_span),
            50.0,
            150.0,
            500.0,
            1500.0,
            5000.0,
            15000.0,
        }
    )
    depth_seeds = sorted({depth_seed, 0.2, 0.6, 1.0, 1.5, 1.85})
    frequency_step = float(np.median(np.diff(frequency)))
    lower = np.asarray(
        [frequency[0], np.log(2.0), -8.0, -8.0 * np.pi, -2.0 / max(frequency_step, 1.0)],
        dtype=float,
    )
    upper = np.asarray(
        [frequency[-1], np.log(1.0e7), 8.0, 8.0 * np.pi, 2.0 / max(frequency_step, 1.0)],
        dtype=float,
    )
    best = None
    for q_seed in q_seeds:
        for depth_value in depth_seeds:
            logit = np.log(depth_value / (2.0 - depth_value))
            initial = np.asarray([f0_seed, np.log(q_seed), logit, phase_seed, 0.0], dtype=float)
            candidate = least_squares(
                residual,
                initial,
                bounds=(lower, upper),
                loss="soft_l1",
                f_scale=0.05,
                max_nfev=5000,
                x_scale="jac",
            )
            cost = float(np.mean(residual(candidate.x) ** 2))
            if best is None or cost < best[0]:
                best = (cost, candidate)
    if best is None:
        raise RuntimeError("external-Q optimizer did not produce a candidate")

    _, solution = best
    f0, ql, depth, phase, delay = unpack(solution.x)
    external_q = 2.0 * ql / depth
    inverse_internal = 1.0 / ql - 1.0 / external_q
    internal_q = None if inverse_internal <= 0.0 else 1.0 / inverse_internal
    beta = np.inf if internal_q is None else internal_q / external_q
    predicted = one_port_resonator_s11(
        frequency,
        resonance_frequency_hz=f0,
        loaded_q=ql,
        resonant_depth=depth,
        phase_rad=phase,
        delay_s=delay,
    )
    rms = float(np.sqrt(np.mean(np.abs(predicted - reflection) ** 2)))
    success = bool(solution.success and frequency[0] < f0 < frequency[-1] and rms < 0.15)
    message = str(solution.message)
    if not frequency[0] < f0 < frequency[-1]:
        message = "fitted resonance lies outside the solved frequency sweep"
    elif rms >= 0.15:
        message = f"complex fit residual is too large ({rms:.4g})"
    return ExternalQFit(
        resonance_frequency_hz=f0,
        loaded_q=ql,
        external_q=external_q,
        internal_q=internal_q,
        coupling_beta=float(beta),
        resonant_depth=depth,
        phase_rad=phase,
        delay_s=delay,
        rms_complex_error=rms,
        success=success,
        message=message,
    )


def external_q_study_plan(payload: dict[str, Any]) -> dict[str, Any]:
    component = payload.get("component")
    if not isinstance(component, dict):
        raise TypeError("component is required")
    if str(component.get("recipe")) != "combline_probe_driven":
        raise ValueError("external-Q study requires a combline_probe_driven component")
    parameters = {str(item["name"]): dict(item) for item in component.get("parameters", [])}
    probe = parameters.get("probe_depth_mm")
    if probe is None:
        raise ValueError("component does not define probe_depth_mm")
    samples_value = payload.get("sample_values")
    if samples_value is None:
        samples = np.linspace(
            float(probe["minimum"]),
            float(probe["maximum"]),
            int(probe.get("samples", 9)),
        )
    else:
        samples = np.asarray(samples_value, dtype=float)
    if samples.ndim != 1 or samples.size < 2 or np.unique(samples).size != samples.size:
        raise ValueError("sample_values must contain at least two unique values")
    if np.any(samples < float(probe["minimum"])) or np.any(samples > float(probe["maximum"])):
        raise ValueError("probe-depth samples exceed component bounds")

    geometry = dict(payload.get("geometry") or {})
    cavity_length = _positive(geometry, "cavity_length_mm", 72.0)
    cavity_width = _positive(geometry, "cavity_width_mm", 48.0)
    cavity_height = _positive(geometry, "cavity_height_mm", 75.0)
    wall = _positive(geometry, "wall_mm", 2.5)
    resonator_radius = _positive(geometry, "resonator_radius_mm", 4.0)
    resonator_height = _positive(geometry, "resonator_height_mm", 62.0)
    probe_radius = _positive(geometry, "probe_radius_mm", max(0.5, resonator_radius * 0.35))
    coax_dielectric_radius = _positive(
        geometry,
        "coax_dielectric_radius_mm",
        max(probe_radius * 2.0, probe_radius + 0.5),
    )
    feed_z = _positive(
        geometry,
        "feed_height_mm",
        wall + min(resonator_height * 0.55, cavity_height * 0.55),
    )
    center_ghz = _positive(payload, "center_frequency_ghz", 1.0)
    span_fraction = _positive(payload, "sweep_span_fraction", 0.12)
    start_ghz = center_ghz * (1.0 - span_fraction / 2.0)
    stop_ghz = center_ghz * (1.0 + span_fraction / 2.0)
    prefix = str(payload.get("name") or component.get("component_id") or "external_q").replace("-", "_")
    shell = f"{prefix}_shell"
    air = f"{prefix}_air"
    rod = f"{prefix}_rod"
    feed_hole = f"{prefix}_feed_hole"
    dielectric = f"{prefix}_coax_dielectric"
    pin = f"{prefix}_probe"
    nominal_depth = float(probe["nominal"])

    return {
        "schema": EXTERNAL_Q_PLAN_SCHEMA,
        "name": prefix,
        "analysis_kind": "driven_external_q",
        "solution_type": "Modal",
        "component_id": str(component["component_id"]),
        "component_version": int(component.get("version", 1)),
        "units": "mm",
        "study": {
            "kind": "EXTERNAL_Q",
            "parameter_name": "probe_depth_mm",
            "parameter_unit": "mm",
            "sample_values": [float(item) for item in np.sort(samples)],
        },
        "variables": {
            "cavity_length_mm": cavity_length,
            "cavity_width_mm": cavity_width,
            "cavity_height_mm": cavity_height,
            "wall_mm": wall,
            "resonator_radius_mm": resonator_radius,
            "resonator_height_mm": resonator_height,
            "probe_radius_mm": probe_radius,
            "coax_dielectric_radius_mm": coax_dielectric_radius,
            "feed_height_mm": feed_z,
            "probe_depth_mm": nominal_depth,
        },
        "objects": [
            _box(shell, [0.0, 0.0, 0.0], [cavity_length, cavity_width, cavity_height], "copper"),
            _box(
                air,
                [wall, wall, wall],
                [cavity_length - 2.0 * wall, cavity_width - 2.0 * wall, cavity_height - 2.0 * wall],
                "air",
            ),
            _cylinder(
                rod,
                "Z",
                [cavity_length / 2.0, cavity_width / 2.0, wall],
                resonator_radius,
                resonator_height,
                "copper",
            ),
            _cylinder(
                feed_hole,
                "X",
                [0.0, cavity_width / 2.0, feed_z],
                coax_dielectric_radius,
                wall + nominal_depth,
                "air",
            ),
            _cylinder(
                dielectric,
                "X",
                [-wall, cavity_width / 2.0, feed_z],
                coax_dielectric_radius,
                f"2*wall_mm+probe_depth_mm",
                str(geometry.get("coax_dielectric_material") or "Teflon (tm)"),
            ),
            _cylinder(
                pin,
                "X",
                [-wall, cavity_width / 2.0, feed_z],
                probe_radius,
                "2*wall_mm+probe_depth_mm",
                "copper",
            ),
        ],
        "operations": [
            {
                "operation": "subtract",
                "blank": shell,
                "tools": [air, feed_hole],
                "keep_originals": True,
            }
        ],
        "ports": [
            {
                "name": f"{prefix}_Port1",
                "signal": pin,
                "reference": shell,
                "impedance": 50.0,
            }
        ],
        "groups": {
            "metal": [shell, rod, pin],
            "dielectric_regions": [air, dielectric, feed_hole],
            "resonator": [rod, air],
            "feed": [pin, dielectric, feed_hole],
        },
        "setup": {
            "name": "FD3D_ExternalQ_Setup",
            "sweep_name": "FD3D_ExternalQ_Sweep",
            "center_frequency_ghz": center_ghz,
            "start_frequency_ghz": start_ghz,
            "stop_frequency_ghz": stop_ghz,
            "points": int(payload.get("points", 1001)),
            "maximum_passes": int(payload.get("maximum_passes", 15)),
            "max_delta_s": float(payload.get("max_delta_s", 0.01)),
            "sweep_type": str(payload.get("sweep_type") or "Discrete"),
        },
        "dry_run": bool(payload.get("dry_run", True)),
        "overwrite": True,
        "assign_ports": True,
    }


def run_hfss_external_q_study(
    adapter: Any,
    plan: dict[str, Any],
    *,
    cores: int | None = None,
    tasks: int | None = None,
    gpus: int | None = None,
    save_project: bool = True,
) -> dict[str, Any]:
    state = getattr(adapter, "state", None)
    if state is None or not getattr(state, "connected", False):
        raise RuntimeError("AEDT adapter is not connected")
    if str(getattr(state, "backend", "")).lower() != "pyaedt":
        raise RuntimeError("external-Q characterization requires the real PyAEDT/HFSS backend")
    if str(plan.get("analysis_kind")) != "driven_external_q":
        raise ValueError("plan must be an FD3D driven external-Q study")
    if bool(plan.get("dry_run", False)):
        raise ValueError("dry_run plans cannot be solved in HFSS")

    hfss = _require_hfss(adapter)
    original_design = str(getattr(hfss, "design_name", "") or "")
    design_name = _insert_driven_design(hfss, plan)
    try:
        _set_variables(hfss, plan)
        build_plan = dict(plan)
        build_plan["dry_run"] = False
        build_plan["overwrite"] = False
        model = adapter.build_model(build_plan)
        setup_name = str(plan["setup"]["name"])
        sweep_name = str(plan["setup"]["sweep_name"])
        port_name = str(plan["ports"][0]["name"])
        study = dict(plan["study"])
        parameter_name = str(study["parameter_name"])
        parameter_unit = str(study["parameter_unit"])
        rows = []
        curve_samples = []
        for index, parameter_value in enumerate(study["sample_values"]):
            hfss[parameter_name] = _quantity(float(parameter_value), parameter_unit)
            solved = hfss.analyze_setup(
                setup_name,
                cores=cores,
                tasks=tasks,
                gpus=gpus,
                blocking=True,
            )
            if solved is False:
                raise RuntimeError(
                    f"HFSS external-Q solve failed for {parameter_name}={parameter_value:g}{parameter_unit}"
                )
            frequencies, s11 = _extract_s11(hfss, setup_name, sweep_name, port_name, parameter_name, parameter_value, parameter_unit)
            fit = fit_external_q(frequencies, s11)
            if not fit.success:
                raise RuntimeError(
                    f"external-Q fit failed for {parameter_name}={parameter_value:g}{parameter_unit}: {fit.message}"
                )
            row = {
                "parameter_value": float(parameter_value),
                "fit": fit.to_dict(),
                "frequency_hz": [float(item) for item in frequencies],
                "s11_real": [float(item) for item in s11.real],
                "s11_imag": [float(item) for item in s11.imag],
                "metadata": {
                    "backend": "pyaedt-hfss-driven-modal",
                    "solver": "HFSS Driven Modal",
                    "design_name": design_name,
                    "setup_name": setup_name,
                    "sweep_name": sweep_name,
                    "sample_index": index,
                    "approved": False,
                },
            }
            rows.append(row)
            curve_samples.append(
                {
                    "parameter_value": float(parameter_value),
                    "frequencies_hz": [fit.resonance_frequency_hz],
                    "quality_factors": [fit.loaded_q],
                    "mode_labels": ["driven-resonance"],
                    "metadata": {
                        **row["metadata"],
                        "external_q": fit.external_q,
                        "internal_q": fit.internal_q,
                        "coupling_beta": fit.coupling_beta,
                        "rms_complex_error": fit.rms_complex_error,
                    },
                }
            )
        curve = build_characterization_curve(
            {
                "study_kind": "EXTERNAL_Q",
                "parameter_name": parameter_name,
                "parameter_unit": parameter_unit,
                "samples": curve_samples,
                "metadata_key": "external_q",
                "approved": False,
                "metadata": {
                    "backend": "pyaedt-hfss-driven-modal",
                    "solver": "HFSS Driven Modal",
                    "component_id": plan.get("component_id"),
                    "component_version": plan.get("component_version"),
                    "design": design_name,
                    "setup": setup_name,
                    "sweep": sweep_name,
                },
            }
        )
        saved = None
        if save_project:
            saved_value = hfss.save_project()
            if saved_value is False:
                raise RuntimeError("HFSS solved external-Q study but failed to save the project")
            saved = getattr(hfss, "project_file", None)
        return {
            "backend": "pyaedt-hfss-driven-modal",
            "solver": "HFSS Driven Modal",
            "eligible_for_approval": True,
            "approved": False,
            "project": getattr(hfss, "project_name", None),
            "project_file": saved or getattr(hfss, "project_file", None),
            "design": design_name,
            "setup": setup_name,
            "sweep": sweep_name,
            "component_id": plan.get("component_id"),
            "component_version": plan.get("component_version"),
            "parameter_name": parameter_name,
            "parameter_unit": parameter_unit,
            "samples": rows,
            "curve": curve.to_dict(),
            "model": model,
        }
    except Exception:
        _restore_design(hfss, original_design)
        raise


def _extract_s11(
    hfss: Any,
    setup_name: str,
    sweep_name: str,
    port_name: str,
    parameter_name: str,
    parameter_value: float,
    parameter_unit: str,
) -> tuple[np.ndarray, np.ndarray]:
    expression = f"S({port_name},{port_name})"
    solution_name = f"{setup_name} : {sweep_name}"
    variations = {parameter_name: [_quantity(parameter_value, parameter_unit)]}
    data = hfss.post.get_solution_data(
        expressions=expression,
        setup_sweep_name=solution_name,
        variations=variations,
        primary_sweep_variable="Freq",
        report_category="Modal Solution Data",
    )
    if data is False or data is None:
        raise RuntimeError("HFSS returned no complex S11 data for external-Q extraction")
    frequency = np.asarray([float(item) for item in data.primary_sweep_values], dtype=float)
    unit = str(getattr(data, "primary_sweep_units", "Hz") or "Hz").lower()
    scale = {"hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9}.get(unit)
    if scale is None:
        raise RuntimeError(f"unsupported HFSS frequency unit: {unit}")
    frequency *= scale
    real = np.asarray(data.data_real(expression), dtype=float)
    imaginary = np.asarray(data.data_imag(expression), dtype=float)
    if frequency.size != real.size or real.size != imaginary.size:
        raise RuntimeError("HFSS S11 frequency, real and imaginary arrays have different lengths")
    return frequency, real + 1j * imaginary


def _require_hfss(adapter: Any) -> Any:
    getter = getattr(adapter, "_require_hfss", None)
    if not callable(getter):
        raise TypeError("adapter does not expose an active PyAEDT HFSS application")
    return getter()


def _insert_driven_design(hfss: Any, plan: dict[str, Any]) -> str:
    component = str(plan.get("component_id") or "external_q").replace("-", "_")
    requested = f"FD3D_Qe_{component}_{uuid4().hex[:8]}"[:64]
    inserted = hfss.insert_design(name=requested, solution_type="Modal")
    if not inserted:
        raise RuntimeError("AEDT failed to insert the HFSS external-Q design")
    return str(inserted)


def _set_variables(hfss: Any, plan: dict[str, Any]) -> None:
    for name, value in dict(plan.get("variables") or {}).items():
        unit = "mm" if str(name).endswith("_mm") else ""
        hfss[str(name)] = _quantity(float(value), unit)


def _restore_design(hfss: Any, design_name: str) -> None:
    if not design_name:
        return
    try:
        hfss.set_active_design(design_name)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        pass


def _positive(payload: dict[str, Any], name: str, default: float) -> float:
    value = float(payload.get(name, default))
    if value <= 0.0:
        raise ValueError(f"{name} must be greater than zero")
    return value


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


def _quantity(value: float, unit: str) -> str:
    return f"{float(value):.15g}{unit}"
