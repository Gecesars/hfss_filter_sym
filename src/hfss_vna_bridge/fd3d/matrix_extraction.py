from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import least_squares

from hfss_vna_bridge.engines.filter_engine import coupling_matrix_response


@dataclass(frozen=True)
class MatrixExtractionVariable:
    row: int
    column: int
    label: str
    kind: str
    initial: float
    lower: float
    upper: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "row": self.row,
            "column": self.column,
            "label": self.label,
            "kind": self.kind,
            "initial": self.initial,
            "lower": self.lower,
            "upper": self.upper,
        }


def extract_coupling_matrix(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Fit a real symmetric coupling matrix to complex two-port data.

    The topology is defined by the initial matrix or an explicit boolean mask.
    Only selected matrix entries are optimized. Reference-plane phase and delay
    are fitted as nuisance parameters so that electrical delay is not absorbed by
    resonator detuning or coupling coefficients.
    """

    frequency, measured_s11, measured_s21 = _network_arrays(payload)
    initial, labels = _initial_matrix(payload)
    size = initial.shape[0]
    order = size - 2
    specification = dict(payload.get("specification") or {})
    filter_type = str(specification.get("filter_type") or "BPF").upper()
    f0_initial = float(specification.get("f0_hz") or float(specification.get("f0_ghz", 1.0)) * 1e9)
    bandwidth_initial = float(
        specification.get("bandwidth_hz")
        or float(specification.get("bandwidth_ghz", 0.05)) * 1e9
    )
    if f0_initial <= 0.0 or bandwidth_initial <= 0.0:
        raise ValueError("positive f0 and bandwidth are required")
    unloaded_q_value = specification.get("unloaded_q")
    unloaded_q = None if unloaded_q_value in {None, "", "Infinity", "infinity"} else float(unloaded_q_value)
    if unloaded_q is not None and unloaded_q <= 0.0:
        raise ValueError("unloaded_q must be positive")

    variables = _matrix_variables(initial, labels, payload)
    optimize_f0 = bool(payload.get("optimize_f0", True))
    optimize_bandwidth = bool(payload.get("optimize_bandwidth", True))
    optimize_unloaded_q = bool(payload.get("optimize_unloaded_q", False))
    fit_reference_planes = bool(payload.get("fit_reference_planes", True))
    regularization = max(float(payload.get("regularization", 1e-5)), 0.0)
    passband_weight = max(float(payload.get("passband_weight", 2.0)), 0.0)
    reflection_weight = max(float(payload.get("reflection_weight", 1.0)), 0.0)
    transmission_weight = max(float(payload.get("transmission_weight", 1.0)), 0.0)

    vector = [item.initial for item in variables]
    lower = [item.lower for item in variables]
    upper = [item.upper for item in variables]
    nuisance_names: list[str] = []
    if optimize_f0:
        vector.append(f0_initial)
        lower.append(max(float(frequency[0]), f0_initial * 0.80))
        upper.append(min(float(frequency[-1]), f0_initial * 1.20))
        nuisance_names.append("f0_hz")
    if optimize_bandwidth:
        vector.append(np.log(bandwidth_initial))
        lower.append(np.log(max(bandwidth_initial * 0.25, 1.0)))
        upper.append(np.log(bandwidth_initial * 4.0))
        nuisance_names.append("log_bandwidth_hz")
    if optimize_unloaded_q:
        q_seed = unloaded_q or 5000.0
        vector.append(np.log(q_seed))
        lower.append(np.log(10.0))
        upper.append(np.log(1.0e8))
        nuisance_names.append("log_unloaded_q")
    if fit_reference_planes:
        frequency_step = max(float(np.median(np.diff(frequency))), 1.0)
        delay_bound = min(1.0 / frequency_step, 1.0e-6)
        for name in ("phase_s11", "delay_s11", "phase_s21", "delay_s21"):
            nuisance_names.append(name)
            vector.append(0.0)
            if name.startswith("phase"):
                lower.append(-4.0 * np.pi)
                upper.append(4.0 * np.pi)
            else:
                lower.append(-delay_bound)
                upper.append(delay_bound)

    initial_vector = np.asarray(vector, dtype=float)
    lower_bounds = np.asarray(lower, dtype=float)
    upper_bounds = np.asarray(upper, dtype=float)
    passband = np.abs(frequency - f0_initial) <= bandwidth_initial * 0.75
    point_weight = np.ones(frequency.size, dtype=float)
    point_weight[passband] = passband_weight
    scale11 = max(float(np.sqrt(np.mean(np.abs(measured_s11) ** 2))), 1e-6)
    scale21 = max(float(np.sqrt(np.mean(np.abs(measured_s21) ** 2))), 1e-6)

    def decode(candidate: np.ndarray) -> tuple[np.ndarray, dict[str, float]]:
        matrix = np.array(initial, copy=True)
        for value, item in zip(candidate[: len(variables)], variables, strict=True):
            matrix[item.row, item.column] = float(value)
            matrix[item.column, item.row] = float(value)
        cursor = len(variables)
        settings = {
            "f0_hz": f0_initial,
            "bandwidth_hz": bandwidth_initial,
            "unloaded_q": unloaded_q,
            "phase_s11": 0.0,
            "delay_s11": 0.0,
            "phase_s21": 0.0,
            "delay_s21": 0.0,
        }
        for name in nuisance_names:
            value = float(candidate[cursor])
            cursor += 1
            if name == "log_bandwidth_hz":
                settings["bandwidth_hz"] = float(np.exp(value))
            elif name == "log_unloaded_q":
                settings["unloaded_q"] = float(np.exp(value))
            else:
                settings[name] = value
        return matrix, settings

    def predict(candidate: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, float]]:
        matrix, settings = decode(candidate)
        s11, s21, _ = coupling_matrix_response(
            matrix,
            frequency,
            filter_type=filter_type,
            f0_hz=float(settings["f0_hz"]),
            bandwidth_hz=float(settings["bandwidth_hz"]),
            unloaded_q=settings["unloaded_q"],
        )
        if fit_reference_planes:
            offset = frequency - float(settings["f0_hz"])
            s11 = s11 * np.exp(
                1j * (float(settings["phase_s11"]) + 2.0 * np.pi * offset * float(settings["delay_s11"]))
            )
            s21 = s21 * np.exp(
                1j * (float(settings["phase_s21"]) + 2.0 * np.pi * offset * float(settings["delay_s21"]))
            )
        return matrix, s11, s21, settings

    def residual(candidate: np.ndarray) -> np.ndarray:
        _, predicted_s11, predicted_s21, _ = predict(candidate)
        difference11 = reflection_weight * point_weight * (predicted_s11 - measured_s11) / scale11
        difference21 = transmission_weight * point_weight * (predicted_s21 - measured_s21) / scale21
        values = [difference11.real, difference11.imag, difference21.real, difference21.imag]
        if regularization > 0.0 and variables:
            matrix_delta = candidate[: len(variables)] - initial_vector[: len(variables)]
            values.append(np.sqrt(regularization) * matrix_delta)
        return np.concatenate(values)

    result = least_squares(
        residual,
        initial_vector,
        bounds=(lower_bounds, upper_bounds),
        loss=str(payload.get("loss") or "soft_l1"),
        f_scale=float(payload.get("f_scale", 0.05)),
        max_nfev=int(payload.get("max_nfev", 5000)),
        x_scale="jac",
        verbose=0,
    )
    extracted, predicted_s11, predicted_s21, settings = predict(result.x)
    raw_residual11 = predicted_s11 - measured_s11
    raw_residual21 = predicted_s21 - measured_s21
    rms11 = float(np.sqrt(np.mean(np.abs(raw_residual11) ** 2)))
    rms21 = float(np.sqrt(np.mean(np.abs(raw_residual21) ** 2)))
    condition = _jacobian_condition(result.jac)
    covariance = _covariance_diagonal(result.jac, residual(result.x))
    matrix_uncertainty = []
    for index, item in enumerate(variables):
        standard = None if covariance is None else float(np.sqrt(max(covariance[index], 0.0)))
        matrix_uncertainty.append({**item.to_dict(), "value": float(result.x[index]), "standard_error": standard})

    success = bool(result.success and rms11 < float(payload.get("maximum_rms_s11", 0.20)) and rms21 < float(payload.get("maximum_rms_s21", 0.20)))
    messages = [str(result.message)]
    if condition is not None and condition > float(payload.get("maximum_condition_number", 1e12)):
        messages.append(f"Jacobian is ill-conditioned ({condition:.4g})")
        success = False
    return {
        "status": 0 if success else -400,
        "ok": success,
        "method": "complex-topology-constrained-coupling-matrix-fit",
        "filter_type": filter_type,
        "order": order,
        "labels": labels,
        "initial_matrix": initial.tolist(),
        "extracted_matrix": extracted.tolist(),
        "deviation_matrix": (extracted - initial).tolist(),
        "variables": matrix_uncertainty,
        "settings": {
            "f0_hz": float(settings["f0_hz"]),
            "bandwidth_hz": float(settings["bandwidth_hz"]),
            "unloaded_q": settings["unloaded_q"],
            "phase_s11_rad": float(settings["phase_s11"]),
            "delay_s11_s": float(settings["delay_s11"]),
            "phase_s21_rad": float(settings["phase_s21"]),
            "delay_s21_s": float(settings["delay_s21"]),
        },
        "fit": {
            "success": success,
            "optimizer_success": bool(result.success),
            "message": "; ".join(messages),
            "cost": float(result.cost),
            "optimality": float(result.optimality),
            "evaluations": int(result.nfev),
            "rms_s11_complex": rms11,
            "rms_s21_complex": rms21,
            "jacobian_condition_number": condition,
        },
        "series": {
            "frequency_hz": frequency.tolist(),
            "measured_s11_real": measured_s11.real.tolist(),
            "measured_s11_imag": measured_s11.imag.tolist(),
            "measured_s21_real": measured_s21.real.tolist(),
            "measured_s21_imag": measured_s21.imag.tolist(),
            "fitted_s11_real": predicted_s11.real.tolist(),
            "fitted_s11_imag": predicted_s11.imag.tolist(),
            "fitted_s21_real": predicted_s21.real.tolist(),
            "fitted_s21_imag": predicted_s21.imag.tolist(),
        },
        "traceability": {
            "topology_source": "explicit-mask" if payload.get("topology_mask") is not None else "initial-matrix",
            "regularization": regularization,
            "fit_reference_planes": fit_reference_planes,
            "reflection_weight": reflection_weight,
            "transmission_weight": transmission_weight,
            "passband_weight": passband_weight,
        },
    }


def _network_arrays(payload: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points = payload.get("points")
    if isinstance(points, list) and points:
        frequency = np.asarray([float(item["freq_hz"]) for item in points], dtype=float)
        s11 = np.asarray([_point_complex(item, "s11") for item in points], dtype=np.complex128)
        s21 = np.asarray([_point_complex(item, "s21") for item in points], dtype=np.complex128)
    else:
        frequency = np.asarray(payload.get("frequency_hz") or payload.get("frequencies_hz"), dtype=float)
        s11 = _complex_array(payload, "s11")
        s21 = _complex_array(payload, "s21")
    if frequency.ndim != 1 or s11.ndim != 1 or s21.ndim != 1:
        raise ValueError("frequency, S11 and S21 must be one-dimensional")
    if not (frequency.size == s11.size == s21.size) or frequency.size < 21:
        raise ValueError("frequency, S11 and S21 must have the same length of at least 21")
    order = np.argsort(frequency)
    frequency = frequency[order]
    s11 = s11[order]
    s21 = s21[order]
    if np.any(np.diff(frequency) <= 0.0):
        raise ValueError("frequency samples must be strictly increasing")
    if np.any(~np.isfinite(frequency)) or np.any(~np.isfinite(s11.real)) or np.any(~np.isfinite(s21.real)):
        raise ValueError("network samples must be finite")
    return frequency, s11, s21


def _complex_array(payload: dict[str, Any], prefix: str) -> np.ndarray:
    real = payload.get(f"{prefix}_real")
    imaginary = payload.get(f"{prefix}_imag")
    if not isinstance(real, list) or not isinstance(imaginary, list):
        raise TypeError(f"{prefix}_real and {prefix}_imag arrays are required")
    return np.asarray(real, dtype=float) + 1j * np.asarray(imaginary, dtype=float)


def _point_complex(point: dict[str, Any], prefix: str) -> complex:
    return complex(float(point.get(f"{prefix}_real", 0.0)), float(point.get(f"{prefix}_imag", 0.0)))


def _initial_matrix(payload: dict[str, Any]) -> tuple[np.ndarray, list[str]]:
    matrix_value = payload.get("initial_matrix") or payload.get("matrix")
    if isinstance(matrix_value, dict):
        values = matrix_value.get("values")
        labels = matrix_value.get("labels")
    else:
        values = matrix_value
        labels = None
    matrix = np.asarray(values, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or matrix.shape[0] < 3:
        raise ValueError("initial matrix must be a square source-resonator-load matrix")
    if not np.allclose(matrix, matrix.T, atol=1e-10, rtol=0.0):
        raise ValueError("initial matrix must be symmetric")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("initial matrix values must be finite")
    labels_value = labels or ["S", *[str(index) for index in range(1, matrix.shape[0] - 1)], "L"]
    if len(labels_value) != matrix.shape[0]:
        raise ValueError("matrix labels do not match matrix size")
    return matrix, [str(item) for item in labels_value]


def _matrix_variables(
    initial: np.ndarray,
    labels: list[str],
    payload: dict[str, Any],
) -> list[MatrixExtractionVariable]:
    size = initial.shape[0]
    mask_value = payload.get("topology_mask")
    if mask_value is None:
        mask = np.abs(initial) > float(payload.get("topology_threshold", 1e-12))
        for index in range(1, size - 1):
            mask[index, index] = True
    else:
        mask = np.asarray(mask_value, dtype=bool)
        if mask.shape != initial.shape:
            raise ValueError("topology_mask must have the same shape as initial_matrix")
        if not np.array_equal(mask, mask.T):
            raise ValueError("topology_mask must be symmetric")
    variables = []
    default_bound = abs(float(payload.get("matrix_bound", 3.0)))
    diagonal_bound = abs(float(payload.get("diagonal_bound", default_bound)))
    per_entry_bounds = dict(payload.get("entry_bounds") or {})
    frozen = {str(item) for item in payload.get("frozen_entries", [])}
    for row in range(size):
        for column in range(row, size):
            if not mask[row, column]:
                continue
            if row == column and row in {0, size - 1}:
                continue
            label = f"M[{labels[row]},{labels[column]}]"
            if label in frozen:
                continue
            kind = "detuning" if row == column else "coupling"
            bound = diagonal_bound if kind == "detuning" else default_bound
            entry = per_entry_bounds.get(label)
            if isinstance(entry, list) and len(entry) == 2:
                lower, upper = float(entry[0]), float(entry[1])
            else:
                lower, upper = -bound, bound
            if upper <= lower:
                raise ValueError(f"invalid bounds for {label}")
            variables.append(
                MatrixExtractionVariable(
                    row=row,
                    column=column,
                    label=label,
                    kind=kind,
                    initial=float(initial[row, column]),
                    lower=lower,
                    upper=upper,
                )
            )
    if not variables:
        raise ValueError("topology mask does not contain any optimizable matrix entries")
    return variables


def _jacobian_condition(jacobian: np.ndarray) -> float | None:
    if jacobian.size == 0:
        return None
    singular = np.linalg.svd(jacobian, compute_uv=False)
    if not singular.size or singular[-1] <= np.finfo(float).eps:
        return np.inf
    return float(singular[0] / singular[-1])


def _covariance_diagonal(jacobian: np.ndarray, residual: np.ndarray) -> np.ndarray | None:
    if jacobian.ndim != 2 or jacobian.shape[0] <= jacobian.shape[1]:
        return None
    try:
        inverse = np.linalg.pinv(jacobian.T @ jacobian)
    except np.linalg.LinAlgError:
        return None
    degrees = max(jacobian.shape[0] - jacobian.shape[1], 1)
    variance = float(np.dot(residual, residual) / degrees)
    return np.diag(inverse * variance)
