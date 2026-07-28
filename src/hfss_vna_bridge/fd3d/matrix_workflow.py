from __future__ import annotations

from typing import Any

import numpy as np

from hfss_vna_bridge.engines.filter_engine import coupling_matrix_response
from hfss_vna_bridge.fd3d.matrix_extraction import extract_coupling_matrix


def estimate_reference_plane(
    frequencies_hz: np.ndarray | list[float],
    measured: np.ndarray | list[complex],
    reference: np.ndarray | list[complex],
    *,
    center_frequency_hz: float,
    minimum_relative_magnitude: float = 0.03,
) -> dict[str, Any]:
    """Estimate constant phase and electrical delay from a complex response ratio.

    The estimate is intentionally separate from matrix fitting. Samples close to
    zeros are rejected because their phase is ill-defined. The remaining phase
    ratio is unwrapped and fitted by weighted least squares.
    """

    frequency = np.asarray(frequencies_hz, dtype=float)
    measured_values = np.asarray(measured, dtype=np.complex128)
    reference_values = np.asarray(reference, dtype=np.complex128)
    if frequency.ndim != 1 or measured_values.ndim != 1 or reference_values.ndim != 1:
        raise ValueError("frequency, measured and reference must be one-dimensional")
    if not (frequency.size == measured_values.size == reference_values.size):
        raise ValueError("frequency, measured and reference arrays must have equal length")
    if frequency.size < 5:
        raise ValueError("reference-plane estimation requires at least five samples")
    if np.any(np.diff(frequency) <= 0.0):
        raise ValueError("frequency samples must be strictly increasing")

    reference_magnitude = np.abs(reference_values)
    measured_magnitude = np.abs(measured_values)
    reference_limit = max(float(np.max(reference_magnitude)) * minimum_relative_magnitude, 1e-12)
    measured_limit = max(float(np.max(measured_magnitude)) * minimum_relative_magnitude, 1e-12)
    mask = (
        np.isfinite(frequency)
        & np.isfinite(measured_values.real)
        & np.isfinite(measured_values.imag)
        & np.isfinite(reference_values.real)
        & np.isfinite(reference_values.imag)
        & (reference_magnitude >= reference_limit)
        & (measured_magnitude >= measured_limit)
    )
    if np.count_nonzero(mask) < 5:
        raise ValueError("too few reliable complex samples remain for reference-plane estimation")

    frequency_fit = frequency[mask]
    offset = frequency_fit - float(center_frequency_hz)
    ratio = measured_values[mask] / reference_values[mask]
    phase = np.unwrap(np.angle(ratio))
    weight = np.sqrt(reference_magnitude[mask] * measured_magnitude[mask])
    weight /= max(float(np.max(weight)), 1e-15)
    design = np.column_stack([np.ones(offset.size), 2.0 * np.pi * offset])
    weighted_design = design * weight[:, np.newaxis]
    weighted_phase = phase * weight
    coefficients, _, rank, singular_values = np.linalg.lstsq(
        weighted_design,
        weighted_phase,
        rcond=None,
    )
    if rank < 2:
        raise ValueError("reference-plane phase fit is rank deficient")
    phase_rad = float(_principal_phase(coefficients[0]))
    delay_s = float(coefficients[1])
    predicted_phase = coefficients[0] + 2.0 * np.pi * offset * delay_s
    residual_phase = phase - predicted_phase
    rms_phase = float(np.sqrt(np.average(residual_phase**2, weights=np.maximum(weight, 1e-12))))
    corrected = measured_values * np.exp(
        -1j
        * (
            phase_rad
            + 2.0 * np.pi * (frequency - float(center_frequency_hz)) * delay_s
        )
    )
    return {
        "phase_rad": phase_rad,
        "delay_s": delay_s,
        "rms_phase_rad": rms_phase,
        "sample_count": int(np.count_nonzero(mask)),
        "rejected_sample_count": int(mask.size - np.count_nonzero(mask)),
        "rank": int(rank),
        "singular_values": [float(item) for item in singular_values],
        "corrected_real": corrected.real.tolist(),
        "corrected_imag": corrected.imag.tolist(),
    }


def extract_coupling_matrix_staged(payload: dict[str, Any]) -> dict[str, Any]:
    """De-embed reference planes first, then fit the coupling matrix.

    This staged workflow is the default engineering path. Joint fitting remains
    available in ``matrix_extraction.extract_coupling_matrix`` for experiments,
    but is more correlated and may be ill-conditioned.
    """

    frequency, measured_s11, measured_s21 = _network_arrays(payload)
    initial_matrix, labels = _initial_matrix(payload)
    specification = dict(payload.get("specification") or {})
    filter_type = str(specification.get("filter_type") or "BPF").upper()
    f0_hz = float(
        specification.get("f0_hz")
        or float(specification.get("f0_ghz", 1.0)) * 1e9
    )
    bandwidth_hz = float(
        specification.get("bandwidth_hz")
        or float(specification.get("bandwidth_ghz", 0.05)) * 1e9
    )
    unloaded_q_value = specification.get("unloaded_q")
    unloaded_q = (
        None
        if unloaded_q_value in {None, "", "Infinity", "infinity"}
        else float(unloaded_q_value)
    )
    ideal_s11, ideal_s21, _ = coupling_matrix_response(
        initial_matrix,
        frequency,
        filter_type=filter_type,
        f0_hz=f0_hz,
        bandwidth_hz=bandwidth_hz,
        unloaded_q=unloaded_q,
    )
    minimum_magnitude = float(payload.get("reference_minimum_relative_magnitude", 0.03))
    reference_s11 = estimate_reference_plane(
        frequency,
        measured_s11,
        ideal_s11,
        center_frequency_hz=f0_hz,
        minimum_relative_magnitude=minimum_magnitude,
    )
    reference_s21 = estimate_reference_plane(
        frequency,
        measured_s21,
        ideal_s21,
        center_frequency_hz=f0_hz,
        minimum_relative_magnitude=minimum_magnitude,
    )

    inner_payload = dict(payload)
    inner_payload.pop("points", None)
    inner_payload["frequency_hz"] = frequency.tolist()
    inner_payload["s11_real"] = reference_s11["corrected_real"]
    inner_payload["s11_imag"] = reference_s11["corrected_imag"]
    inner_payload["s21_real"] = reference_s21["corrected_real"]
    inner_payload["s21_imag"] = reference_s21["corrected_imag"]
    inner_payload["fit_reference_planes"] = False
    result = extract_coupling_matrix(inner_payload)

    fitted_s11 = np.asarray(result["series"]["fitted_s11_real"], dtype=float) + 1j * np.asarray(
        result["series"]["fitted_s11_imag"], dtype=float
    )
    fitted_s21 = np.asarray(result["series"]["fitted_s21_real"], dtype=float) + 1j * np.asarray(
        result["series"]["fitted_s21_imag"], dtype=float
    )
    reembedded_s11 = fitted_s11 * np.exp(
        1j
        * (
            float(reference_s11["phase_rad"])
            + 2.0
            * np.pi
            * (frequency - f0_hz)
            * float(reference_s11["delay_s"])
        )
    )
    reembedded_s21 = fitted_s21 * np.exp(
        1j
        * (
            float(reference_s21["phase_rad"])
            + 2.0
            * np.pi
            * (frequency - f0_hz)
            * float(reference_s21["delay_s"])
        )
    )
    rms_s11 = float(np.sqrt(np.mean(np.abs(reembedded_s11 - measured_s11) ** 2)))
    rms_s21 = float(np.sqrt(np.mean(np.abs(reembedded_s21 - measured_s21) ** 2)))
    accepted = bool(
        result["fit"]["optimizer_success"]
        and rms_s11 < float(payload.get("maximum_rms_s11", 0.20))
        and rms_s21 < float(payload.get("maximum_rms_s21", 0.20))
    )
    result["status"] = 0 if accepted else -400
    result["ok"] = accepted
    result["method"] = "staged-reference-plane-and-topology-constrained-matrix-fit"
    result["settings"].update(
        {
            "phase_s11_rad": float(reference_s11["phase_rad"]),
            "delay_s11_s": float(reference_s11["delay_s"]),
            "phase_s21_rad": float(reference_s21["phase_rad"]),
            "delay_s21_s": float(reference_s21["delay_s"]),
        }
    )
    result["fit"].update(
        {
            "success": accepted,
            "rms_s11_complex_deembedded": result["fit"]["rms_s11_complex"],
            "rms_s21_complex_deembedded": result["fit"]["rms_s21_complex"],
            "rms_s11_complex": rms_s11,
            "rms_s21_complex": rms_s21,
        }
    )
    result["series"].update(
        {
            "measured_s11_real": measured_s11.real.tolist(),
            "measured_s11_imag": measured_s11.imag.tolist(),
            "measured_s21_real": measured_s21.real.tolist(),
            "measured_s21_imag": measured_s21.imag.tolist(),
            "fitted_s11_real": reembedded_s11.real.tolist(),
            "fitted_s11_imag": reembedded_s11.imag.tolist(),
            "fitted_s21_real": reembedded_s21.real.tolist(),
            "fitted_s21_imag": reembedded_s21.imag.tolist(),
        }
    )
    result["reference_planes"] = {
        "s11": {key: value for key, value in reference_s11.items() if not key.startswith("corrected_")},
        "s21": {key: value for key, value in reference_s21.items() if not key.startswith("corrected_")},
    }
    result["traceability"].update(
        {
            "reference_plane_strategy": "prefit-weighted-linear-phase",
            "joint_reference_plane_fit": False,
            "matrix_labels": labels,
        }
    )
    return result


def _network_arrays(payload: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points = payload.get("points")
    if isinstance(points, list) and points:
        frequency = np.asarray([float(item["freq_hz"]) for item in points], dtype=float)
        s11 = np.asarray([_point_complex(item, "s11") for item in points], dtype=np.complex128)
        s21 = np.asarray([_point_complex(item, "s21") for item in points], dtype=np.complex128)
    else:
        frequency_value = payload.get("frequency_hz") or payload.get("frequencies_hz")
        frequency = np.asarray(frequency_value, dtype=float)
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
    return frequency, s11, s21


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
    labels_value = labels or ["S", *[str(index) for index in range(1, matrix.shape[0] - 1)], "L"]
    return matrix, [str(item) for item in labels_value]


def _complex_array(payload: dict[str, Any], prefix: str) -> np.ndarray:
    real = payload.get(f"{prefix}_real")
    imaginary = payload.get(f"{prefix}_imag")
    if not isinstance(real, list) or not isinstance(imaginary, list):
        raise TypeError(f"{prefix}_real and {prefix}_imag arrays are required")
    return np.asarray(real, dtype=float) + 1j * np.asarray(imaginary, dtype=float)


def _point_complex(point: dict[str, Any], prefix: str) -> complex:
    return complex(
        float(point.get(f"{prefix}_real", 0.0)),
        float(point.get(f"{prefix}_imag", 0.0)),
    )


def _principal_phase(value: float) -> float:
    return float((value + np.pi) % (2.0 * np.pi) - np.pi)
