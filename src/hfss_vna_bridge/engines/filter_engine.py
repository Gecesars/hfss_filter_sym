from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import signal


@dataclass(frozen=True)
class FilterEngineResult:
    frequencies_hz: np.ndarray
    s11: np.ndarray
    s21: np.ndarray
    s22: np.ndarray
    group_delay_s: np.ndarray
    delivered_power_w: np.ndarray
    prototype: dict[str, Any]
    coupling: dict[str, Any]
    elements: list[dict[str, Any]]


def coupling_matrix_response(
    matrix: np.ndarray,
    frequencies_hz: np.ndarray,
    *,
    filter_type: str,
    f0_hz: float,
    bandwidth_hz: float,
    unloaded_q: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    values = np.asarray(matrix, dtype=float)
    if values.ndim != 2 or values.shape[0] != values.shape[1]:
        raise ValueError("coupling matrix must be square")
    if values.shape[0] < 3:
        raise ValueError("coupling matrix must contain source, resonator and load nodes")
    if not np.allclose(values, values.T, rtol=0.0, atol=1e-9):
        raise ValueError("coupling matrix must be symmetric")
    frequencies = np.asarray(frequencies_hz, dtype=float)
    if np.any(frequencies <= 0):
        raise ValueError("frequencies must be greater than zero")

    size = values.shape[0]
    resonator_identity = np.diag([0.0, *([1.0] * (size - 2)), 0.0])
    terminations = np.diag([1.0, *([0.0] * (size - 2)), 1.0])
    normalized = _normalized_frequency(
        filter_type,
        frequencies,
        f0_hz,
        bandwidth_hz,
    )
    normalized_loss = (
        0.0
        if unloaded_q is None
        else f0_hz / max(bandwidth_hz * unloaded_q, 1e-30)
    )
    s11 = np.empty(len(frequencies), dtype=np.complex128)
    s21 = np.empty(len(frequencies), dtype=np.complex128)
    s22 = np.empty(len(frequencies), dtype=np.complex128)
    identity = np.eye(size, dtype=np.complex128)
    for index, omega in enumerate(normalized):
        system = (
            values
            - omega * resonator_identity
            - 1j * terminations
            - 1j * normalized_loss * resonator_identity
        ).astype(np.complex128)
        try:
            inverse = np.linalg.solve(system, identity)
        except np.linalg.LinAlgError:
            inverse = np.linalg.pinv(system)
        s11[index] = 1.0 + 2j * inverse[0, 0]
        s21[index] = -2j * inverse[-1, 0]
        s22[index] = 1.0 + 2j * inverse[-1, -1]
    return s11, s21, s22


def design_filter_network(
    *,
    filter_type: str,
    order: int,
    family: str,
    return_loss_db: float,
    f0_hz: float,
    bandwidth_hz: float,
    frequencies_hz: np.ndarray,
    unloaded_q: float | None,
    impedance_ohm: float,
    input_power_w: float,
    transmission_zeros: list[dict[str, float]],
    stopband_attenuation_db: float = 60.0,
) -> FilterEngineResult:
    family_key = family.strip().lower()
    ripple_db = return_loss_to_ripple_db(return_loss_db)
    prototype_zeros, prototype_poles, prototype_gain = _analog_prototype(
        order,
        family_key,
        ripple_db,
        stopband_attenuation_db,
    )
    response_zeros, response_poles, response_gain = _frequency_transform(
        filter_type,
        prototype_zeros,
        prototype_poles,
        prototype_gain,
        f0_hz,
        bandwidth_hz,
    )
    angular_frequencies = 2.0 * math.pi * frequencies_hz
    _, ideal_s21 = signal.freqs_zpk(
        response_zeros,
        response_poles,
        response_gain,
        worN=angular_frequencies,
    )

    if filter_type == "MULTI":
        ideal_s21 = _multiband_response(
            order=order,
            family=family_key,
            ripple_db=ripple_db,
            stopband_attenuation_db=stopband_attenuation_db,
            f0_hz=f0_hz,
            bandwidth_hz=bandwidth_hz,
            angular_frequencies=angular_frequencies,
        )

    g_values = lowpass_prototype_values(order, family_key, ripple_db)
    notch_response = _finite_zero_response(
        angular_frequencies,
        transmission_zeros,
    )
    ideal_s21 = ideal_s21 * notch_response
    ideal_s21 = _enforce_passivity(ideal_s21)

    loss_db = _dissipative_loss_db(
        g_values,
        f0_hz,
        bandwidth_hz,
        unloaded_q,
    )
    loss_amplitude = 10.0 ** (-loss_db / 20.0)
    s21 = ideal_s21 * loss_amplitude

    ideal_transmitted_power = np.minimum(np.abs(ideal_s21) ** 2, 1.0)
    reflection_magnitude = np.sqrt(np.maximum(1.0 - ideal_transmitted_power, 1e-18))
    s21_phase = np.unwrap(np.angle(ideal_s21))
    s11 = reflection_magnitude * np.exp(1j * (s21_phase + math.pi / 2.0))
    s22 = reflection_magnitude * np.exp(1j * (s21_phase - math.pi / 2.0))

    group_delay = -np.gradient(np.unwrap(np.angle(s21)), angular_frequencies)
    delivered_power = input_power_w * np.abs(s21) ** 2
    coupling = coupling_network(
        g_values,
        f0_hz=f0_hz,
        bandwidth_hz=bandwidth_hz,
        transmission_zeros=transmission_zeros,
    )
    elements = scaled_lumped_elements(
        g_values,
        filter_type=filter_type,
        f0_hz=f0_hz,
        bandwidth_hz=bandwidth_hz,
        impedance_ohm=impedance_ohm,
    )

    return FilterEngineResult(
        frequencies_hz=frequencies_hz,
        s11=s11,
        s21=s21,
        s22=s22,
        group_delay_s=group_delay,
        delivered_power_w=delivered_power,
        prototype={
            "family": family_key,
            "order": order,
            "return_loss_db": return_loss_db,
            "passband_ripple_db": ripple_db,
            "stopband_attenuation_db": stopband_attenuation_db,
            "normalized_zeros": [_complex_json(value) for value in prototype_zeros],
            "normalized_poles": [_complex_json(value) for value in prototype_poles],
            "normalized_gain": float(prototype_gain),
            "g_values": [float(value) for value in g_values],
            "loss_db": float(loss_db),
            "model": "scipy-analog-zpk",
        },
        coupling=coupling,
        elements=elements,
    )


def return_loss_to_ripple_db(return_loss_db: float) -> float:
    epsilon_squared = 1.0 / (10.0 ** (return_loss_db / 10.0) - 1.0)
    return 10.0 * math.log10(1.0 + epsilon_squared)


def lowpass_prototype_values(
    order: int,
    family: str,
    ripple_db: float,
) -> list[float]:
    if family == "butterworth":
        return [
            1.0,
            *[
                2.0 * math.sin((2 * index - 1) * math.pi / (2 * order))
                for index in range(1, order + 1)
            ],
            1.0,
        ]
    if family != "chebyshev":
        return _prototype_values_from_poles(order, family, ripple_db)

    beta = math.log(1.0 / math.tanh(ripple_db / 17.371779276130074))
    gamma = math.sinh(beta / (2.0 * order))
    a = [
        math.sin((2 * index - 1) * math.pi / (2 * order))
        for index in range(1, order + 1)
    ]
    b = [
        gamma**2 + math.sin(index * math.pi / order) ** 2
        for index in range(1, order + 1)
    ]
    values = [1.0, 2.0 * a[0] / gamma]
    for index in range(1, order):
        values.append(
            4.0
            * a[index - 1]
            * a[index]
            / (b[index - 1] * values[index])
        )
    termination = 1.0 if order % 2 else 1.0 / math.tanh(beta / 4.0) ** 2
    values.append(termination)
    return values


def coupling_network(
    g_values: list[float],
    *,
    f0_hz: float,
    bandwidth_hz: float,
    transmission_zeros: list[dict[str, float]],
) -> dict[str, Any]:
    order = len(g_values) - 2
    labels = ["S", *[str(index) for index in range(1, order + 1)], "L"]
    size = order + 2
    matrix = [[0.0 for _ in range(size)] for _ in range(size)]
    for index in range(size - 1):
        coupling = 1.0 / math.sqrt(g_values[index] * g_values[index + 1])
        matrix[index][index + 1] = coupling
        matrix[index + 1][index] = coupling

    estimated_cross_couplings = []
    for index, zero in enumerate(transmission_zeros[: max(order - 2, 0)]):
        row = 1 + index
        column = min(order, row + 2)
        normalized_zero = _bandpass_normalized_frequency(
            zero["frequency_hz"],
            f0_hz,
            bandwidth_hz,
        )
        if abs(normalized_zero) < 1e-12:
            continue
        estimate = -matrix[row][row + 1] * matrix[row + 1][column] / normalized_zero
        matrix[row][column] = estimate
        matrix[column][row] = estimate
        estimated_cross_couplings.append(
            {
                "source": labels[row],
                "target": labels[column],
                "value": estimate,
                "target_frequency_hz": zero["frequency_hz"],
                "method": "triplet-initial-estimate",
            }
        )

    fractional_bandwidth = bandwidth_hz / f0_hz
    physical = {
        "fractional_bandwidth": fractional_bandwidth,
        "input_external_q": g_values[0] * g_values[1] / fractional_bandwidth,
        "output_external_q": g_values[-2] * g_values[-1] / fractional_bandwidth,
        "inter_resonator": [
            {
                "source": str(index),
                "target": str(index + 1),
                "coefficient": fractional_bandwidth
                / math.sqrt(g_values[index] * g_values[index + 1]),
            }
            for index in range(1, order)
        ],
    }
    return {
        "labels": labels,
        "values": matrix,
        "unit": "normalized",
        "physical": physical,
        "cross_couplings": estimated_cross_couplings,
        "synthesis": (
            "inline-prototype"
            if not estimated_cross_couplings
            else "inline-prototype-with-triplet-initial-estimates"
        ),
    }


def scaled_lumped_elements(
    g_values: list[float],
    *,
    filter_type: str,
    f0_hz: float,
    bandwidth_hz: float,
    impedance_ohm: float,
) -> list[dict[str, Any]]:
    if filter_type == "MULTI":
        return []
    angular_center = 2.0 * math.pi * f0_hz
    angular_bandwidth = 2.0 * math.pi * bandwidth_hz
    elements: list[dict[str, Any]] = []
    for index, g_value in enumerate(g_values[1:-1], start=1):
        series = index % 2 == 1
        if filter_type == "LPF":
            if series:
                elements.append(
                    _element(index, "series", "L", impedance_ohm * g_value / angular_center)
                )
            else:
                elements.append(
                    _element(index, "shunt", "C", g_value / (impedance_ohm * angular_center))
                )
            continue
        if filter_type == "BPF":
            if series:
                inductance = impedance_ohm * g_value / angular_bandwidth
                capacitance = angular_bandwidth / (
                    impedance_ohm * g_value * angular_center**2
                )
                elements.extend(
                    [
                        _element(index, "series", "L", inductance),
                        _element(index, "series", "C", capacitance),
                    ]
                )
            else:
                capacitance = g_value / (impedance_ohm * angular_bandwidth)
                inductance = impedance_ohm * angular_bandwidth / (
                    g_value * angular_center**2
                )
                elements.extend(
                    [
                        _element(index, "shunt", "L", inductance),
                        _element(index, "shunt", "C", capacitance),
                    ]
                )
            continue
        if filter_type == "BSF":
            if series:
                inductance = impedance_ohm * g_value * angular_bandwidth / angular_center**2
                capacitance = 1.0 / (impedance_ohm * g_value * angular_bandwidth)
                elements.extend(
                    [
                        _element(index, "series-parallel", "L", inductance),
                        _element(index, "series-parallel", "C", capacitance),
                    ]
                )
            else:
                capacitance = g_value * angular_bandwidth / (
                    impedance_ohm * angular_center**2
                )
                inductance = impedance_ohm / (g_value * angular_bandwidth)
                elements.extend(
                    [
                        _element(index, "shunt-series", "L", inductance),
                        _element(index, "shunt-series", "C", capacitance),
                    ]
                )
    return elements


def _analog_prototype(
    order: int,
    family: str,
    ripple_db: float,
    stopband_attenuation_db: float,
) -> tuple[np.ndarray, np.ndarray, float]:
    if family == "chebyshev":
        return signal.cheb1ap(order, ripple_db)
    if family == "butterworth":
        return signal.buttap(order)
    if family == "bessel":
        return signal.besselap(order, norm="mag")
    if family == "elliptic":
        return signal.ellipap(order, ripple_db, stopband_attenuation_db)
    raise ValueError("response_family must be chebyshev, butterworth, bessel, or elliptic")


def _frequency_transform(
    filter_type: str,
    zeros: np.ndarray,
    poles: np.ndarray,
    gain: float,
    f0_hz: float,
    bandwidth_hz: float,
) -> tuple[np.ndarray, np.ndarray, float]:
    angular_center = 2.0 * math.pi * f0_hz
    angular_bandwidth = 2.0 * math.pi * bandwidth_hz
    if filter_type == "BPF" or filter_type == "MULTI":
        return signal.lp2bp_zpk(
            zeros,
            poles,
            gain,
            wo=angular_center,
            bw=angular_bandwidth,
        )
    if filter_type == "BSF":
        return signal.lp2bs_zpk(
            zeros,
            poles,
            gain,
            wo=angular_center,
            bw=angular_bandwidth,
        )
    if filter_type == "LPF":
        return signal.lp2lp_zpk(zeros, poles, gain, wo=angular_center)
    raise ValueError("filter_type must be BPF, BSF, LPF, or MULTI")


def _multiband_response(
    *,
    order: int,
    family: str,
    ripple_db: float,
    stopband_attenuation_db: float,
    f0_hz: float,
    bandwidth_hz: float,
    angular_frequencies: np.ndarray,
) -> np.ndarray:
    zeros, poles, gain = _analog_prototype(
        order,
        family,
        ripple_db,
        stopband_attenuation_db,
    )
    channel_offset_hz = bandwidth_hz * 0.9
    responses = []
    for center_hz in (f0_hz - channel_offset_hz, f0_hz + channel_offset_hz):
        transformed = signal.lp2bp_zpk(
            zeros,
            poles,
            gain,
            wo=2.0 * math.pi * center_hz,
            bw=2.0 * math.pi * bandwidth_hz,
        )
        responses.append(signal.freqs_zpk(*transformed, worN=angular_frequencies)[1])
    combined = responses[0] + responses[1]
    peak = np.max(np.abs(combined))
    return combined / peak if peak > 1.0 else combined


def _finite_zero_response(
    angular_frequencies: np.ndarray,
    transmission_zeros: list[dict[str, float]],
) -> np.ndarray:
    response = np.ones_like(angular_frequencies, dtype=np.complex128)
    s = 1j * angular_frequencies
    for zero in transmission_zeros:
        angular_zero = 2.0 * math.pi * zero["frequency_hz"]
        pole_q = max(zero.get("q", 30.0), 0.5)
        depth_db = min(max(zero.get("depth_db", 80.0), 1.0), 180.0)
        zero_q = pole_q * 10.0 ** (depth_db / 20.0)
        numerator = s**2 + angular_zero / zero_q * s + angular_zero**2
        denominator = s**2 + angular_zero / pole_q * s + angular_zero**2
        response *= numerator / denominator
    return response


def _dissipative_loss_db(
    g_values: list[float],
    f0_hz: float,
    bandwidth_hz: float,
    unloaded_q: float | None,
) -> float:
    if unloaded_q is None:
        return 0.0
    fractional_bandwidth = bandwidth_hz / f0_hz
    return 4.343 * sum(g_values[1:-1]) / (unloaded_q * fractional_bandwidth)


def _enforce_passivity(response: np.ndarray) -> np.ndarray:
    magnitude = np.abs(response)
    scale = np.where(magnitude > 1.0, magnitude, 1.0)
    return response / scale


def _prototype_values_from_poles(
    order: int,
    family: str,
    ripple_db: float,
) -> list[float]:
    if family == "bessel":
        return [
            1.0,
            *[
                2.0 * math.sin((2 * index - 1) * math.pi / (2 * order))
                for index in range(1, order + 1)
            ],
            1.0,
        ]
    if family == "elliptic":
        return lowpass_prototype_values(order, "chebyshev", ripple_db)
    raise ValueError(f"unsupported prototype family: {family}")


def _bandpass_normalized_frequency(
    frequency_hz: float,
    f0_hz: float,
    bandwidth_hz: float,
) -> float:
    ratio = frequency_hz / f0_hz
    return (ratio - 1.0 / ratio) / (bandwidth_hz / f0_hz)


def _normalized_frequency(
    filter_type: str,
    frequencies_hz: np.ndarray,
    f0_hz: float,
    bandwidth_hz: float,
) -> np.ndarray:
    key = filter_type.strip().upper()
    if key in {"BPF", "MULTI"}:
        ratio = frequencies_hz / f0_hz
        return (ratio - 1.0 / ratio) / (bandwidth_hz / f0_hz)
    if key == "BSF":
        ratio = frequencies_hz / f0_hz
        denominator = ratio - 1.0 / ratio
        return np.divide(
            bandwidth_hz / f0_hz,
            denominator,
            out=np.full_like(denominator, np.inf),
            where=np.abs(denominator) > 1e-15,
        )
    if key == "LPF":
        return frequencies_hz / f0_hz
    raise ValueError("filter_type must be BPF, BSF, LPF, or MULTI")


def _element(index: int, connection: str, kind: str, value: float) -> dict[str, Any]:
    unit = "H" if kind == "L" else "F"
    return {
        "resonator": index,
        "connection": connection,
        "kind": kind,
        "value_si": value,
        "unit": unit,
    }


def _complex_json(value: complex) -> dict[str, float]:
    return {"real": float(np.real(value)), "imag": float(np.imag(value))}
