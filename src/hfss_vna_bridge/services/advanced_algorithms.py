from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np
from scipy import optimize, signal, special

from hfss_vna_bridge.engines.engineering import (
    monte_carlo_filter,
    optimize_filter_specification,
    transmission_line,
    tuning_recommendations,
)
from hfss_vna_bridge.services.multiplexer import synthesize_multiplexer
from hfss_vna_bridge.services.synthesis import (
    FilterSpecification,
    evaluate_coupling_matrix,
    synthesize_filter,
)

Algorithm = Callable[[dict[str, Any]], dict[str, Any]]


def run_algorithm(method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = _normalize(method)
    handler = _ALGORITHMS.get(normalized)
    if handler is None:
        raise KeyError(f"Algorithm not found: {method}")
    data = dict(payload or {})
    if normalized == _normalize("addSpecLines"):
        data.setdefault("operation", "add")
    elif normalized == _normalize("deleteAllSpec"):
        data.setdefault("operation", "delete_all")
    result = handler(data)
    return {"status": 0, "ok": True, "algorithm": method, **result}


def algorithm_exists(method: str) -> bool:
    return _normalize(method) in _ALGORITHMS


def supported_algorithms() -> list[dict[str, str]]:
    rows = {
        key: {
            "name": key,
            "category": _CATEGORY.get(handler, "engineering"),
        }
        for key, handler in _ALGORITHMS.items()
    }
    return [rows[key] for key in sorted(rows)]


def smooth_curve(payload: dict[str, Any]) -> dict[str, Any]:
    values = _real_values(payload)
    if len(values) < 3:
        raise ValueError("At least three values are required")
    requested = int(payload.get("window", payload.get("window_length", 11)))
    window = min(requested, len(values) if len(values) % 2 else len(values) - 1)
    window = max(window, 3)
    if window % 2 == 0:
        window -= 1
    order = min(int(payload.get("polynomial_order", 3)), window - 1)
    if order < 1:
        raise ValueError("polynomial_order must be greater than zero")
    smoothed = signal.savgol_filter(values, window, order, mode="interp")
    residual = values - smoothed
    return {
        "values": _float_list(smoothed),
        "window": window,
        "polynomial_order": order,
        "residual_rms": float(np.sqrt(np.mean(residual**2))),
    }


def find_maxima(payload: dict[str, Any]) -> dict[str, Any]:
    values = _real_values(payload)
    frequencies = _frequency_values(payload, len(values))
    distance = max(1, int(payload.get("distance", 1)))
    prominence = payload.get("prominence")
    kwargs = {"distance": distance}
    if prominence is not None:
        kwargs["prominence"] = float(prominence)
    indices, properties = signal.find_peaks(values, **kwargs)
    peaks = [
        {
            "index": int(index),
            "frequency_hz": float(frequencies[index]),
            "value": float(values[index]),
            "prominence": float(properties.get("prominences", np.zeros(len(indices)))[offset]),
        }
        for offset, index in enumerate(indices)
    ]
    peaks.sort(key=lambda item: item["value"], reverse=True)
    return {"peaks": peaks, "count": len(peaks)}


def remove_linear_phase(payload: dict[str, Any]) -> dict[str, Any]:
    frequencies, values = _complex_trace(payload)
    if len(values) < 3:
        raise ValueError("At least three complex samples are required")
    phase = np.unwrap(np.angle(values))
    mask = _frequency_mask(payload, frequencies)
    if np.count_nonzero(mask) < 2:
        raise ValueError("The selected phase-fit range contains fewer than two points")
    coefficients = np.polyfit(frequencies[mask], phase[mask], 1)
    fitted = np.polyval(coefficients, frequencies)
    corrected = values * np.exp(-1j * fitted)
    delay_s = -float(coefficients[0]) / (2.0 * math.pi)
    return {
        "frequency_hz": _float_list(frequencies),
        "real": _float_list(corrected.real),
        "imag": _float_list(corrected.imag),
        "magnitude_db": _db(corrected),
        "phase_deg": _float_list(np.degrees(np.unwrap(np.angle(corrected)))),
        "removed_delay_s": delay_s,
        "removed_phase_offset_deg": math.degrees(float(coefficients[1])),
    }


def time_domain(payload: dict[str, Any]) -> dict[str, Any]:
    frequencies, values = _complex_trace(payload)
    if len(values) < 3:
        raise ValueError("At least three complex samples are required")
    uniform_frequency = np.linspace(frequencies[0], frequencies[-1], len(frequencies))
    uniform_values = np.interp(uniform_frequency, frequencies, values.real) + 1j * np.interp(
        uniform_frequency,
        frequencies,
        values.imag,
    )
    window_name = str(payload.get("window") or "hann").lower()
    windows = {
        "none": np.ones(len(values)),
        "hann": signal.windows.hann(len(values), sym=False),
        "hamming": signal.windows.hamming(len(values), sym=False),
        "blackman": signal.windows.blackman(len(values), sym=False),
        "kaiser": signal.windows.kaiser(len(values), float(payload.get("beta", 6.0))),
    }
    if window_name not in windows:
        raise ValueError("window must be none, hann, hamming, blackman, or kaiser")
    minimum_fft = int(payload.get("nfft", 0))
    nfft = max(minimum_fft, 1 << math.ceil(math.log2(len(values) * 2)))
    response = np.fft.ifft(uniform_values * windows[window_name], n=nfft)
    spacing = float(uniform_frequency[1] - uniform_frequency[0])
    delay = np.arange(nfft, dtype=float) / (nfft * spacing)
    velocity_factor = float(payload.get("velocity_factor", 1.0))
    if not 0 < velocity_factor <= 1:
        raise ValueError("velocity_factor must be in the interval (0, 1]")
    distance = delay * 299_792_458.0 * velocity_factor / 2.0
    gate = payload.get("gate")
    if isinstance(gate, dict):
        start = float(gate.get("start_s", 0.0))
        stop = float(gate.get("stop_s", delay[-1]))
        response = np.where((delay >= start) & (delay <= stop), response, 0.0)
    magnitude = np.abs(response)
    peak = int(np.argmax(magnitude))
    return {
        "delay_s": _float_list(delay),
        "distance_m": _float_list(distance),
        "magnitude_db": _db(response),
        "real": _float_list(response.real),
        "imag": _float_list(response.imag),
        "window": window_name,
        "nfft": nfft,
        "peak": {
            "index": peak,
            "delay_s": float(delay[peak]),
            "distance_m": float(distance[peak]),
            "magnitude_db": float(_db_array(response)[peak]),
        },
    }


def extract_matrix(payload: dict[str, Any]) -> dict[str, Any]:
    specification = dict(payload.get("specification") or {})
    measured = payload.get("points")
    if isinstance(measured, list) and measured:
        frequencies = np.asarray([float(point["freq_hz"]) for point in measured], dtype=float)
        s21_db = np.asarray(
            [
                _point_db(point, "s21")
                for point in measured
            ],
            dtype=float,
        )
        s11_db = np.asarray([_point_db(point, "s11") for point in measured], dtype=float)
        peak = int(np.argmax(s21_db))
        threshold = float(s21_db[peak] - 3.0)
        passband = frequencies[s21_db >= threshold]
        specification.setdefault("f0_ghz", float(frequencies[peak] / 1e9))
        if len(passband) >= 2:
            specification.setdefault(
                "bandwidth_ghz",
                float((passband[-1] - passband[0]) / 1e9),
            )
        specification.setdefault("return_loss_db", max(1.0, float(-np.max(s11_db))))
        specification.setdefault("start_ghz", float(frequencies[0] / 1e9))
        specification.setdefault("stop_ghz", float(frequencies[-1] / 1e9))
        specification.setdefault("points", min(max(len(frequencies), 101), 2001))
    specification.setdefault("order", int(payload.get("order", 4)))
    result = synthesize_filter(specification)
    target = payload.get("target_matrix")
    deviation = None
    if isinstance(target, list):
        target_array = np.asarray(target, dtype=float)
        extracted = np.asarray(result["matrix"]["values"], dtype=float)
        if target_array.shape != extracted.shape:
            raise ValueError("target_matrix shape does not match the extracted matrix")
        deviation = _matrix_list(extracted - target_array)
    return {
        "extractedMatrix": result["matrix"]["values"],
        "extracted_matrix": result["matrix"],
        "deviateMatrix": deviation,
        "deviation_matrix": deviation,
        "q": result["specification"].get("unloaded_q"),
        "frequency": result["series"]["frequencies_ghz"],
        "fstart": result["specification"]["start_ghz"],
        "fstop": result["specification"]["stop_ghz"],
        "summary": result["summary"],
        "method": "response-feature-initialization",
    }


def dimension_coupling_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    samples = payload.get("samples")
    if not isinstance(samples, list) or len(samples) < 2:
        raise ValueError("samples must contain at least two dimension/coupling observations")
    dimension_names = _ordered_names(samples, "dimensions")
    coupling_names = _ordered_names(samples, "couplings")
    dimensions = np.asarray(
        [[float(sample["dimensions"][name]) for name in dimension_names] for sample in samples],
        dtype=float,
    )
    couplings = np.asarray(
        [[float(sample["couplings"][name]) for name in coupling_names] for sample in samples],
        dtype=float,
    )
    design = np.column_stack([np.ones(len(samples)), dimensions])
    coefficients, _, rank, singular = np.linalg.lstsq(design, couplings, rcond=None)
    predicted = design @ coefficients
    residual = couplings - predicted
    return {
        "dimension_names": dimension_names,
        "coupling_names": coupling_names,
        "intercept": {
            name: float(coefficients[0, index])
            for index, name in enumerate(coupling_names)
        },
        "jacobian": {
            coupling: {
                dimension: float(coefficients[row + 1, column])
                for row, dimension in enumerate(dimension_names)
            }
            for column, coupling in enumerate(coupling_names)
        },
        "rank": int(rank),
        "singular_values": _float_list(singular),
        "residual_rms": float(np.sqrt(np.mean(residual**2))),
    }


def linear_tuning(payload: dict[str, Any]) -> dict[str, Any]:
    dimensions = {str(key): float(value) for key, value in (payload.get("dimensions") or {}).items()}
    current = {str(key): float(value) for key, value in (payload.get("current") or {}).items()}
    target = {str(key): float(value) for key, value in (payload.get("target") or {}).items()}
    jacobian = payload.get("jacobian")
    if not dimensions or not current or set(current) != set(target) or not isinstance(jacobian, dict):
        raise ValueError("dimensions, matching current/target, and jacobian are required")
    dimension_names = list(dimensions)
    coupling_names = list(current)
    matrix = np.asarray(
        [
            [float(jacobian[coupling][dimension]) for dimension in dimension_names]
            for coupling in coupling_names
        ],
        dtype=float,
    )
    error = np.asarray([target[name] - current[name] for name in coupling_names], dtype=float)
    regularization = max(float(payload.get("regularization", 1e-6)), 0.0)
    system = matrix.T @ matrix + regularization * np.eye(len(dimension_names))
    delta = np.linalg.solve(system, matrix.T @ error)
    maximum_step = payload.get("maximum_step")
    if maximum_step is not None:
        delta = np.clip(delta, -abs(float(maximum_step)), abs(float(maximum_step)))
    updated = {
        name: dimensions[name] + float(delta[index])
        for index, name in enumerate(dimension_names)
    }
    predicted = np.asarray([current[name] for name in coupling_names]) + matrix @ delta
    return {
        "dimension": updated,
        "dimensions": updated,
        "adjustments": {
            name: float(delta[index])
            for index, name in enumerate(dimension_names)
        },
        "predicted": {
            name: float(predicted[index])
            for index, name in enumerate(coupling_names)
        },
        "remaining_error_norm": float(
            np.linalg.norm(np.asarray(list(target.values()), dtype=float) - predicted)
        ),
    }


def perturbation_plan(payload: dict[str, Any]) -> dict[str, Any]:
    dimensions = {str(key): float(value) for key, value in (payload.get("dimensions") or {}).items()}
    if not dimensions:
        raise ValueError("dimensions is required")
    relative_step = abs(float(payload.get("relative_step", 0.01)))
    absolute_step = abs(float(payload.get("absolute_step", 0.0)))
    runs = [{"id": "baseline", "dimensions": dimensions, "variable": None, "direction": 0}]
    for name, value in dimensions.items():
        step = max(abs(value) * relative_step, absolute_step, 1e-12)
        for direction in (-1, 1):
            varied = dict(dimensions)
            varied[name] = value + direction * step
            runs.append(
                {
                    "id": f"{name}_{'plus' if direction > 0 else 'minus'}",
                    "dimensions": varied,
                    "variable": name,
                    "direction": direction,
                    "step": step,
                }
            )
    return {
        "envVariables": list(dimensions),
        "runs": runs,
        "run_count": len(runs),
        "scheme": "central-finite-difference",
    }


def space_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    if "jacobian" not in data and isinstance(data.get("samples"), list):
        sensitivity = dimension_coupling_analysis(data)
        data["jacobian"] = sensitivity["jacobian"]
    result = linear_tuning(data)
    damping = float(payload.get("damping", 1.0))
    if not 0 < damping <= 1:
        raise ValueError("damping must be in the interval (0, 1]")
    original = {str(key): float(value) for key, value in payload["dimensions"].items()}
    damped = {
        name: original[name] + damping * (value - original[name])
        for name, value in result["dimensions"].items()
    }
    result["dimensions"] = damped
    result["dimension"] = damped
    result["damping"] = damping
    result["method"] = "regularized-output-space-mapping"
    return result


def dispersion(payload: dict[str, Any]) -> dict[str, Any]:
    matrix_value = payload.get("matrix")
    if isinstance(matrix_value, dict):
        matrix_value = matrix_value.get("values")
    matrix = np.asarray(matrix_value, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("matrix must be square")
    start = float(payload.get("start_ghz", 0.8))
    stop = float(payload.get("stop_ghz", 1.2))
    points = int(payload.get("points", 101))
    frequencies = np.linspace(start, stop, points)
    reference = float(payload.get("reference_ghz", (start + stop) / 2.0))
    slope = float(payload.get("slope_per_ghz", payload.get("dispersion", 0.0)))
    resonator_mask = np.zeros_like(matrix)
    resonator_mask[1:-1, 1:-1] = np.eye(max(matrix.shape[0] - 2, 0))
    matrices = [
        _matrix_list(matrix + resonator_mask * slope * (frequency - reference))
        for frequency in frequencies
    ]
    return {
        "freq": _float_list(frequencies),
        "matrices": matrices,
        "matrix": matrices[len(matrices) // 2],
        "bandwidth": stop - start,
        "center": reference,
    }


def sign_change(payload: dict[str, Any]) -> dict[str, Any]:
    matrix_value = payload.get("matrix", payload.get("M"))
    matrix = np.asarray(matrix_value, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("matrix must be square")
    signs = payload.get("signs")
    if isinstance(signs, list):
        vector = np.asarray(signs, dtype=float)
    else:
        index = int(payload.get("index", 1))
        vector = np.ones(matrix.shape[0])
        vector[index] = -1.0
    if vector.shape != (matrix.shape[0],):
        raise ValueError("signs must contain one value per matrix row")
    vector = np.where(vector < 0, -1.0, 1.0)
    transformed = np.diag(vector) @ matrix @ np.diag(vector)
    return {"Mout": _matrix_list(transformed), "matrix": _matrix_list(transformed)}


def shift_matrix(payload: dict[str, Any]) -> dict[str, Any]:
    matrix_value = payload.get("matrix", payload.get("M"))
    matrix = np.asarray(matrix_value, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("matrix must be square")
    shift = float(payload.get("shift", payload.get("frequency_shift", 0.0)))
    shifted = matrix.copy()
    for index in range(1, matrix.shape[0] - 1):
        shifted[index, index] += shift
    return {"M": _matrix_list(shifted), "matrix": _matrix_list(shifted)}


def voltage_distribution(payload: dict[str, Any]) -> dict[str, Any]:
    specification = FilterSpecification.from_payload(payload.get("specification") or payload)
    matrix_value = payload.get("matrix")
    if isinstance(matrix_value, dict):
        matrix_value = matrix_value.get("values")
    if matrix_value is None:
        matrix_value = synthesize_filter(payload.get("specification") or payload)["matrix"]["values"]
    matrix = np.asarray(matrix_value, dtype=float)
    frequencies = np.linspace(
        specification.start_ghz * 1e9,
        specification.stop_ghz * 1e9,
        min(specification.points, 801),
    )
    omega = _normalized_frequency(
        frequencies,
        specification.filter_type,
        specification.f0_ghz * 1e9,
        specification.bandwidth_ghz * 1e9,
    )
    size = matrix.shape[0]
    loading = np.zeros((size, size), dtype=complex)
    loading[0, 0] = 1.0
    loading[-1, -1] = 1.0
    resonator_identity = np.zeros((size, size))
    resonator_identity[1:-1, 1:-1] = np.eye(size - 2)
    energy = np.zeros((len(frequencies), size - 2))
    for row, normalized in enumerate(omega):
        system = matrix - normalized * resonator_identity - 1j * loading
        state = np.linalg.solve(system, np.eye(size, dtype=complex)[:, 0])
        energy[row] = np.abs(state[1:-1]) ** 2 * specification.input_power_w
    total = np.sum(energy, axis=1)
    voltage = np.sqrt(np.maximum(2.0 * energy * specification.impedance_ohm, 0.0))
    return {
        "freq": _float_list(frequencies / 1e9),
        "energy": [_float_list(row) for row in energy],
        "total_energy": _float_list(total),
        "voltage": [_float_list(row) for row in voltage],
        "peak_voltage_v": float(np.max(voltage)),
        "peak_resonator": int(np.unravel_index(np.argmax(voltage), voltage.shape)[1] + 1),
    }


def power_handling(payload: dict[str, Any]) -> dict[str, Any]:
    distribution = voltage_distribution(payload)
    gap_mm = _positive(payload, "gap_mm", 1.0)
    breakdown_field = _positive(payload, "breakdown_field_v_per_m", 3.0e6)
    current_power = _positive(
        payload,
        "input_power_w",
        float((payload.get("specification") or {}).get("input_power_w", 0.1)),
    )
    allowable_voltage = breakdown_field * gap_mm * 1e-3
    peak = max(float(distribution["peak_voltage_v"]), 1e-15)
    breakdown_power = current_power * (allowable_voltage / peak) ** 2
    return {
        "PowerBreakDown": breakdown_power,
        "breakdown_power_w": breakdown_power,
        "allowable_voltage_v": allowable_voltage,
        "peak_voltage_at_input_power_v": peak,
        "safety_factor": allowable_voltage / peak,
        "distribution": distribution,
    }


def thermal_shift(payload: dict[str, Any]) -> dict[str, Any]:
    f0_ghz = _positive(payload, "f0", float(payload.get("f0_ghz", 1.0)))
    delta_temperature = float(
        payload.get(
            "delta_temperature_c",
            float(payload.get("temperature_c", 45.0)) - float(payload.get("reference_c", 20.0)),
        )
    )
    expansion_ppm = float(payload.get("expansion_ppm_per_c", 17.0))
    dielectric_tc_ppm = float(payload.get("dielectric_tc_ppm_per_c", 0.0))
    total_fraction = -(expansion_ppm + dielectric_tc_ppm / 2.0) * 1e-6 * delta_temperature
    shift_ghz = f0_ghz * total_fraction
    return {
        "shift": shift_ghz,
        "shift_ghz": shift_ghz,
        "shift_hz": shift_ghz * 1e9,
        "resulting_frequency_ghz": f0_ghz + shift_ghz,
        "delta_temperature_c": delta_temperature,
    }


def coaxial_q(payload: dict[str, Any]) -> dict[str, Any]:
    inner = _positive(payload, "inner_radius_mm", 1.0) * 1e-3
    outer = _positive(payload, "outer_radius_mm", 3.0) * 1e-3
    if outer <= inner:
        raise ValueError("outer_radius_mm must exceed inner_radius_mm")
    frequency = _positive(payload, "frequency_ghz", 1.0) * 1e9
    epsilon_r = _positive(payload, "epsilon_r", 1.0)
    conductivity = _positive(payload, "conductivity_s_per_m", 5.8e7)
    loss_tangent = max(float(payload.get("loss_tangent", 0.0)), 0.0)
    permeability = 4.0e-7 * math.pi
    surface_resistance = math.sqrt(math.pi * frequency * permeability / conductivity)
    impedance = 60.0 / math.sqrt(epsilon_r) * math.log(outer / inner)
    attenuation_conductor = (
        surface_resistance
        / (2.0 * impedance)
        * (1.0 / inner + 1.0 / outer)
        / math.log(outer / inner)
    )
    beta = 2.0 * math.pi * frequency * math.sqrt(epsilon_r) / 299_792_458.0
    attenuation_dielectric = beta * loss_tangent / 2.0
    attenuation = attenuation_conductor + attenuation_dielectric
    q = beta / max(2.0 * attenuation, 1e-30)
    return {
        "q": q,
        "impedance_ohm": impedance,
        "surface_resistance_ohm": surface_resistance,
        "attenuation_np_per_m": attenuation,
        "conductor_q": beta / max(2.0 * attenuation_conductor, 1e-30),
        "dielectric_q": None if loss_tangent == 0 else 1.0 / loss_tangent,
    }


def circular_waveguide(payload: dict[str, Any]) -> dict[str, Any]:
    radius = _positive(payload, "radius_mm", float(payload.get("width_mm", 10.0))) * 1e-3
    epsilon_r = _positive(payload, "epsilon_r", 1.0)
    frequency = _positive(payload, "frequency_ghz", 10.0) * 1e9
    roots = {
        "TE11": float(special.jnp_zeros(1, 1)[0]),
        "TM01": float(special.jn_zeros(0, 1)[0]),
        "TE21": float(special.jnp_zeros(2, 1)[0]),
        "TE01": float(special.jnp_zeros(0, 1)[0]),
        "TM11": float(special.jn_zeros(1, 1)[0]),
    }
    cutoff = {
        mode: root * 299_792_458.0 / (2.0 * math.pi * radius * math.sqrt(epsilon_r))
        for mode, root in roots.items()
    }
    dominant = cutoff["TE11"]
    propagating = frequency > dominant
    guide_wavelength = (
        299_792_458.0
        / (frequency * math.sqrt(epsilon_r))
        / math.sqrt(1.0 - (dominant / frequency) ** 2)
        if propagating
        else None
    )
    return {
        "kind": "circular_waveguide",
        "cutoff_hz": cutoff,
        "dominant_mode": "TE11",
        "operating_above_cutoff": propagating,
        "guide_wavelength_mm": guide_wavelength * 1e3 if guide_wavelength else None,
    }


def iris_width(payload: dict[str, Any]) -> dict[str, Any]:
    coupling = abs(float(payload.get("coupling", payload.get("k", 0.05))))
    broad_wall = _positive(payload, "a_mm", 22.86)
    thickness = max(float(payload.get("thickness_mm", 1.0)), 0.0)
    if coupling >= 1:
        raise ValueError("coupling must be below one")
    width = broad_wall * (2.0 / math.pi) * math.asin(math.sqrt(coupling))
    corrected = min(width + 0.35 * thickness, broad_wall * 0.95)
    return {
        "iris_width_mm": corrected,
        "zero_thickness_width_mm": width,
        "coupling": coupling,
        "normalized_width": corrected / broad_wall,
        "model": "inductive-iris-initial-dimension",
    }


def lpf_synthesis(payload: dict[str, Any]) -> dict[str, Any]:
    specification = {
        "filter_type": "LPF",
        "response_family": str(payload.get("response_family", "chebyshev")),
        "order": int(payload.get("order", 5)),
        "return_loss_db": float(payload.get("return_loss_db", 20.0)),
        "f0_ghz": float(payload.get("cutoff_ghz", payload.get("f0_ghz", 1.0))),
        "bandwidth_ghz": float(payload.get("bandwidth_ghz", 0.1)),
        "start_ghz": float(payload.get("start_ghz", 0.01)),
        "stop_ghz": float(payload.get("stop_ghz", 2.0)),
        "points": int(payload.get("points", 401)),
    }
    result = synthesize_filter(specification)
    result["dimensions"] = lpf_dimensions(
        {
            **payload,
            "prototype": result["prototype"],
            "cutoff_ghz": specification["f0_ghz"],
        }
    )
    return result


def lpf_dimensions(payload: dict[str, Any]) -> dict[str, Any]:
    prototype = payload.get("prototype")
    if not isinstance(prototype, dict) or not isinstance(prototype.get("g_values"), list):
        result = synthesize_filter(
            {
                "filter_type": "LPF",
                "order": int(payload.get("order", 5)),
                "return_loss_db": float(payload.get("return_loss_db", 20.0)),
                "f0_ghz": float(payload.get("cutoff_ghz", 1.0)),
                "start_ghz": 0.01,
                "stop_ghz": float(payload.get("cutoff_ghz", 1.0)) * 2.0,
                "points": 201,
            }
        )
        prototype = result["prototype"]
    g_values = [float(value) for value in prototype["g_values"][1:-1]]
    cutoff = _positive(payload, "cutoff_ghz", 1.0)
    epsilon_eff = _positive(payload, "effective_permittivity", 2.8)
    guided = 299_792_458.0 / (cutoff * 1e9 * math.sqrt(epsilon_eff))
    high_z = _positive(payload, "high_impedance_ohm", 90.0)
    low_z = _positive(payload, "low_impedance_ohm", 25.0)
    reference = _positive(payload, "reference_impedance_ohm", 50.0)
    sections = []
    for index, g_value in enumerate(g_values, start=1):
        impedance = high_z if index % 2 else low_z
        electrical_length = min(
            math.pi / 3.0,
            abs(g_value) * reference / impedance if index % 2 else abs(g_value) * impedance / reference,
        )
        sections.append(
            {
                "section": index,
                "impedance_ohm": impedance,
                "electrical_length_deg": math.degrees(electrical_length),
                "length_mm": guided * electrical_length / (2.0 * math.pi) * 1e3,
                "prototype_g": g_value,
            }
        )
    return {"sections": sections, "guided_wavelength_mm": guided * 1e3}


def lpf_update(payload: dict[str, Any]) -> dict[str, Any]:
    dimensions = lpf_dimensions(payload)
    return {"updated": True, **dimensions}


def optimize_lpf(payload: dict[str, Any]) -> dict[str, Any]:
    specification = {
        "filter_type": "LPF",
        "f0_ghz": float(payload.get("cutoff_ghz", 1.0)),
        "bandwidth_ghz": float(payload.get("bandwidth_ghz", 0.1)),
        "start_ghz": float(payload.get("start_ghz", 0.01)),
        "stop_ghz": float(payload.get("stop_ghz", 2.0)),
        "order": int(payload.get("order", 5)),
        "return_loss_db": float(payload.get("return_loss_db", 20.0)),
        "points": 201,
    }
    return optimize_filter_specification(
        {
            "specification": specification,
            "targets": payload.get("targets") or {
                "center_ghz": specification["f0_ghz"],
                "bandwidth_ghz": specification["bandwidth_ghz"],
                "return_loss_db": specification["return_loss_db"],
                "maximum_insertion_loss_db": 1.0,
            },
            "variables": payload.get("variables")
            or {
                "f0_ghz": [specification["f0_ghz"] * 0.9, specification["f0_ghz"] * 1.1],
                "return_loss_db": [10.0, 35.0],
            },
            "max_iterations": int(payload.get("max_iterations", 12)),
            "population": int(payload.get("population", 8)),
        }
    )


def multiplexer_cm2s(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("channels"), list):
        return synthesize_multiplexer(payload)
    matrices = payload.get("matrices")
    specifications = payload.get("specifications")
    if not isinstance(matrices, list) or not isinstance(specifications, list):
        raise TypeError("channels or matching matrices/specifications are required")
    if len(matrices) != len(specifications):
        raise ValueError("matrices and specifications must have the same length")
    channels = []
    for index, (matrix, specification) in enumerate(zip(matrices, specifications, strict=True)):
        response = evaluate_coupling_matrix(
            {"matrix": matrix, "specification": specification}
        )
        channels.append({"id": f"CH{index + 1}", **response})
    power = np.sum(
        [10.0 ** (np.asarray(channel["series"]["s21_db"]) / 10.0) for channel in channels],
        axis=0,
    )
    aggregate = np.sqrt(np.minimum(power, 1.0))
    return {
        "channels": channels,
        "series": {
            "frequencies_ghz": channels[0]["series"]["frequencies_ghz"],
            "s21_db": _db(aggregate),
        },
    }


def multiplexer_optimize(payload: dict[str, Any]) -> dict[str, Any]:
    base = synthesize_multiplexer(payload)
    channels = payload["channels"]
    targets = [float(channel["f0_ghz"]) for channel in channels]
    initial = np.asarray(targets, dtype=float)
    bounds = [
        (
            center - float(channel["bandwidth_ghz"]) * 0.25,
            center + float(channel["bandwidth_ghz"]) * 0.25,
        )
        for center, channel in zip(targets, channels, strict=True)
    ]
    history: list[float] = []

    def objective(vector: np.ndarray) -> float:
        candidate = dict(payload)
        candidate["channels"] = [
            {**channel, "f0_ghz": float(value)}
            for channel, value in zip(channels, vector, strict=True)
        ]
        result = synthesize_multiplexer(candidate)
        response = np.asarray(result["series"]["s21_db"], dtype=float)
        frequency = np.asarray(result["series"]["frequencies_ghz"], dtype=float)
        score = 0.0
        for target in targets:
            index = int(np.argmin(np.abs(frequency - target)))
            score += float(response[index] ** 2)
        history.append(score)
        return score

    result = optimize.minimize(
        objective,
        initial,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": int(payload.get("max_iterations", 60))},
    )
    optimized_payload = {
        **payload,
        "channels": [
            {**channel, "f0_ghz": float(value)}
            for channel, value in zip(channels, result.x, strict=True)
        ],
    }
    optimized = synthesize_multiplexer(optimized_payload)
    return {
        "Mopt": [channel["matrix"]["values"] for channel in optimized["channels"]],
        "success": bool(result.success),
        "objective": float(result.fun),
        "centers_ghz": _float_list(result.x),
        "history": history,
        "initial": base,
        "optimized": optimized,
    }


def general_optimization(payload: dict[str, Any]) -> dict[str, Any]:
    result = optimize_filter_specification(payload)
    return {
        **result,
        "M_res": synthesize_filter(result["specification"])["matrix"]["values"],
        "aaa": result["objective"],
    }


def monte_carlo_compat(payload: dict[str, Any]) -> dict[str, Any]:
    result = monte_carlo_filter(payload)
    return {
        **result,
        "Mi": result["samples_preview"],
        "yield": result["yield_percent"],
    }


def tuning_compat(payload: dict[str, Any]) -> dict[str, Any]:
    if all(key in payload for key in ("dimensions", "current", "target", "jacobian")):
        result = linear_tuning(payload)
        target = payload["target"]
        predicted = result["predicted"]
        result["deviateMatrix"] = {
            name: float(target[name]) - float(predicted[name])
            for name in target
        }
        return result
    result = tuning_recommendations(
        payload.get("target") or {},
        payload.get("measured") or {},
        sensitivities=payload.get("sensitivities"),
    )
    result["dimension"] = {
        action["control"]: action["adjustment"]
        for action in result["actions"]
    }
    result["deviateMatrix"] = result["errors"]
    return result


def transmission_line_compat(payload: dict[str, Any]) -> dict[str, Any]:
    kind = str(payload.get("kind") or payload.get("type") or "microstrip").lower()
    if kind in {"circular_waveguide", "waveguidecircle", "circular"}:
        return circular_waveguide(payload)
    if kind in {"coax", "coaxial"}:
        return coaxial_q(payload)
    return transmission_line({**payload, "kind": kind})


def topology_library(payload: dict[str, Any]) -> dict[str, Any]:
    order = int(payload.get("order", 4))
    if not 1 <= order <= 24:
        raise ValueError("order must be between 1 and 24")
    nodes = ["S", *[str(index) for index in range(1, order + 1)], "L"]
    topologies = [
        {
            "id": "inline",
            "name": "Inline",
            "edges": [[nodes[index], nodes[index + 1]] for index in range(len(nodes) - 1)],
        },
        {
            "id": "folded",
            "name": "Folded",
            "edges": [
                *[[nodes[index], nodes[index + 1]] for index in range(len(nodes) - 1)],
                *(
                    [["1", str(order)]]
                    if order > 2
                    else []
                ),
            ],
        },
        {
            "id": "canonical",
            "name": "Canonical cross-coupled",
            "edges": [
                *[[nodes[index], nodes[index + 1]] for index in range(len(nodes) - 1)],
                *[
                    [str(index), str(order + 1 - index)]
                    for index in range(1, (order + 1) // 2)
                ],
            ],
        },
    ]
    return {"nodes": nodes, "topologies": topologies}


def specification_lines(payload: dict[str, Any]) -> dict[str, Any]:
    lines = payload.get("lines", payload.get("specLines", []))
    if not isinstance(lines, list):
        raise TypeError("lines must be a list")
    operation = str(payload.get("operation") or "update").lower()
    if operation == "delete_all":
        lines = []
    elif operation == "add":
        item = payload.get("line")
        if not isinstance(item, dict):
            raise TypeError("line must be an object")
        lines = [*lines, item]
    elif operation == "update":
        index = int(payload.get("index", -1))
        item = payload.get("line")
        if index >= 0:
            if not isinstance(item, dict) or index >= len(lines):
                raise ValueError("A valid index and line are required")
            lines = [*lines]
            lines[index] = item
    else:
        raise ValueError("operation must be add, update, or delete_all")
    return {"lines": lines, "count": len(lines)}


def _ordered_names(samples: list[dict[str, Any]], key: str) -> list[str]:
    first = samples[0].get(key)
    if not isinstance(first, dict) or not first:
        raise ValueError(f"Each sample must define non-empty {key}")
    names = [str(name) for name in first]
    for sample in samples:
        values = sample.get(key)
        if not isinstance(values, dict) or set(values) != set(names):
            raise ValueError(f"Every sample must define the same {key}")
    return names


def _real_values(payload: dict[str, Any]) -> np.ndarray:
    for key in ("values", "data", "magnitude_db", "s21_db", "y"):
        value = payload.get(key)
        if isinstance(value, list):
            return np.asarray(value, dtype=float)
    points = payload.get("points")
    if isinstance(points, list) and points:
        parameter = str(payload.get("parameter") or "s21").lower()
        return np.asarray([_point_db(point, parameter) for point in points], dtype=float)
    raise ValueError("values or points are required")


def _frequency_values(payload: dict[str, Any], count: int) -> np.ndarray:
    for key in ("frequencies_hz", "frequency_hz", "frequency"):
        value = payload.get(key)
        if isinstance(value, list):
            frequencies = np.asarray(value, dtype=float)
            if len(frequencies) != count:
                raise ValueError("frequency and value arrays must have the same length")
            unit = str(payload.get("frequency_unit") or "Hz").lower()
            scale = {"hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9}.get(unit)
            if scale is None:
                raise ValueError("Unsupported frequency_unit")
            return frequencies * scale
    points = payload.get("points")
    if isinstance(points, list) and len(points) == count:
        return np.asarray([float(point["freq_hz"]) for point in points], dtype=float)
    start = float(payload.get("start_hz", 0.0))
    stop = float(payload.get("stop_hz", max(count - 1, 1)))
    return np.linspace(start, stop, count)


def _complex_trace(payload: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    points = payload.get("points")
    parameter = str(payload.get("parameter") or "s21").lower()
    if isinstance(points, list) and points:
        frequencies = np.asarray([float(point["freq_hz"]) for point in points], dtype=float)
        values = np.asarray(
            [
                complex(
                    float(point.get(f"{parameter}_real", 0.0)),
                    float(point.get(f"{parameter}_imag", 0.0)),
                )
                for point in points
            ],
            dtype=complex,
        )
        return frequencies, values
    real = payload.get("real")
    imaginary = payload.get("imag", payload.get("imaginary"))
    if isinstance(real, list) and isinstance(imaginary, list):
        values = np.asarray(real, dtype=float) + 1j * np.asarray(imaginary, dtype=float)
        return _frequency_values(payload, len(values)), values
    magnitude_db = payload.get("magnitude_db", payload.get(f"{parameter}_db"))
    phase_deg = payload.get("phase_deg", payload.get(f"{parameter}_phase_deg"))
    if isinstance(magnitude_db, list) and isinstance(phase_deg, list):
        magnitude = 10.0 ** (np.asarray(magnitude_db, dtype=float) / 20.0)
        values = magnitude * np.exp(1j * np.radians(np.asarray(phase_deg, dtype=float)))
        return _frequency_values(payload, len(values)), values
    raise ValueError("Complex points, real/imag arrays, or magnitude/phase arrays are required")


def _frequency_mask(payload: dict[str, Any], frequencies: np.ndarray) -> np.ndarray:
    start = float(payload.get("fit_start_hz", frequencies[0]))
    stop = float(payload.get("fit_stop_hz", frequencies[-1]))
    return (frequencies >= start) & (frequencies <= stop)


def _point_db(point: dict[str, Any], parameter: str) -> float:
    direct = point.get(f"{parameter}_db")
    if direct is not None:
        return float(direct)
    value = complex(
        float(point.get(f"{parameter}_real", 0.0)),
        float(point.get(f"{parameter}_imag", 0.0)),
    )
    return 20.0 * math.log10(max(abs(value), 1e-15))


def _normalized_frequency(
    frequencies: np.ndarray,
    filter_type: str,
    f0_hz: float,
    bandwidth_hz: float,
) -> np.ndarray:
    if filter_type in {"BPF", "MULTI"}:
        ratio = frequencies / f0_hz
        return (ratio - 1.0 / ratio) / (bandwidth_hz / f0_hz)
    if filter_type == "BSF":
        ratio = frequencies / f0_hz
        denominator = ratio - 1.0 / ratio
        return (bandwidth_hz / f0_hz) / np.where(
            np.abs(denominator) < 1e-12,
            np.sign(denominator) * 1e-12 + 1e-12,
            denominator,
        )
    return frequencies / f0_hz


def _positive(payload: dict[str, Any], key: str, default: float) -> float:
    value = float(payload.get(key, default))
    if value <= 0:
        raise ValueError(f"{key} must be greater than zero")
    return value


def _db(values: np.ndarray) -> list[float]:
    return _float_list(_db_array(values))


def _db_array(values: np.ndarray) -> np.ndarray:
    return 20.0 * np.log10(np.maximum(np.abs(values), 1e-15))


def _float_list(values: Any) -> list[float]:
    return [float(value) for value in np.asarray(values).flat]


def _matrix_list(values: np.ndarray) -> list[list[float]]:
    return [[float(value) for value in row] for row in values]


def _normalize(value: str) -> str:
    return value.replace("-", "").replace("_", "").lower()


def _register(handler: Algorithm, *names: str) -> dict[str, Algorithm]:
    return {_normalize(name): handler for name in names}


_ALGORITHMS: dict[str, Algorithm] = {
    **_register(smooth_curve, "SmoothCurve", "SmoothCurve_Fun"),
    **_register(find_maxima, "findmaxima"),
    **_register(remove_linear_phase, "PhaseRemove"),
    **_register(time_domain, "TimeDomain"),
    **_register(
        extract_matrix,
        "ExtractAll",
        "ExtractMatrix",
        "ExtractMatrixTest",
        "BPFExtractMatrix",
        "BandStopExtractMatrix",
        "MultiportExtraction",
        "GetMultiport",
    ),
    **_register(dimension_coupling_analysis, "Dimension2CouplingAnalysis"),
    **_register(linear_tuning, "LinearTuning", "LinearSlopeWay"),
    **_register(
        tuning_compat,
        "AITuning",
        "AdvancedAI",
        "InvokePortTuning",
        "portTuning",
        "portTuningCache",
    ),
    **_register(
        space_mapping,
        "OSM",
        "SpaceMapping",
        "SpaceMappingTuning",
    ),
    **_register(perturbation_plan, "Perturbation"),
    **_register(dispersion, "Dispersion", "Dispersion2", "DispersionLite", "OldDispersion"),
    **_register(sign_change, "signChange"),
    **_register(shift_matrix, "ShiftMatrix", "CM2S_fineTune"),
    **_register(
        voltage_distribution,
        "StoreEnergy_final",
        "StoreEnergyMultiplexer",
        "CalculateVoltageDistribution",
        "CalculateVoltageDistributionNew",
    ),
    **_register(
        power_handling,
        "PowerHandling",
        "PowerHandlingCoefficent",
        "PeakPower",
    ),
    **_register(thermal_shift, "ThermalShift", "temperaturedrift"),
    **_register(coaxial_q, "q_coaxial"),
    **_register(circular_waveguide, "waveguidecircle", "waveguidecircle_temp"),
    **_register(transmission_line_compat, "transmissionlinetoolbox", "waveguiderect", "waveguiderect_temp", "waveguideSIW"),
    **_register(iris_width, "RectangularWGCoupling2IrisWidth"),
    **_register(lpf_synthesis, "LPFSynthesis", "lpf_stepimpedance", "lpf_openstubfirstelementseries", "lpf_openstubfirstelementshunt"),
    **_register(lpf_dimensions, "LPFGetDimension", "lpf_abcd_stepimpedance_cascade", "lpf_abcd_openstub_type1_cascade", "lpf_abcd_openstub_type2_cascade"),
    **_register(lpf_update, "LPFUpdate"),
    **_register(optimize_lpf, "LPFOptimize"),
    **_register(synthesize_filter, "SynthesisAll", "Synthesize", "BandStopSynthesizeMethod1", "MultibandSynthesis", "GetGoldenValue"),
    **_register(synthesize_multiplexer, "MultiplexerSynthesis", "DiplexerSynthesize"),
    **_register(multiplexer_cm2s, "MultiplexerCM2S", "DiplexerCM2S"),
    **_register(multiplexer_optimize, "MultiplexerOptimization", "MultiplexerOptimize"),
    **_register(general_optimization, "Optimization", "InvokeDeepOptimization"),
    **_register(monte_carlo_compat, "MC_Final", "PerformMonteCarloSimulation"),
    **_register(topology_library, "GenTopoLibrary"),
    **_register(specification_lines, "addSpecLines", "UpdateSpecLines", "deleteAllSpec"),
}

_CATEGORY = {
    smooth_curve: "signal-processing",
    find_maxima: "signal-processing",
    remove_linear_phase: "signal-processing",
    time_domain: "signal-processing",
    extract_matrix: "matrix-extraction",
    dimension_coupling_analysis: "sensitivity",
    linear_tuning: "tuning",
    tuning_compat: "tuning",
    space_mapping: "tuning",
    perturbation_plan: "sensitivity",
    dispersion: "coupling-matrix",
    sign_change: "coupling-matrix",
    shift_matrix: "coupling-matrix",
    voltage_distribution: "power",
    power_handling: "power",
    thermal_shift: "thermal",
    coaxial_q: "guided-wave",
    circular_waveguide: "guided-wave",
    transmission_line_compat: "guided-wave",
    iris_width: "guided-wave",
    lpf_synthesis: "lpf",
    lpf_dimensions: "lpf",
    lpf_update: "lpf",
    optimize_lpf: "lpf",
    synthesize_filter: "synthesis",
    synthesize_multiplexer: "multiplexer",
    multiplexer_cm2s: "multiplexer",
    multiplexer_optimize: "multiplexer",
    general_optimization: "optimization",
    monte_carlo_compat: "monte-carlo",
    topology_library: "topology",
    specification_lines: "specification",
}
