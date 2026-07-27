from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from hfss_vna_bridge.engines.filter_engine import (
    coupling_matrix_response,
    design_filter_network,
)


@dataclass(frozen=True)
class FilterSpecification:
    filter_type: str = "BPF"
    response_family: str = "chebyshev"
    order: int = 4
    return_loss_db: float = 25.0
    f0_ghz: float = 1.0
    bandwidth_ghz: float = 0.05
    start_ghz: float = 0.875
    stop_ghz: float = 1.125
    shift_mhz: float = 0.0
    delta_bandwidth_mhz: float = 0.0
    unloaded_q: float | None = None
    impedance_ohm: float = 50.0
    input_power_w: float = 0.1
    stopband_attenuation_db: float = 60.0
    dispersion: str = "symmetric"
    dispersion_value: float = 0.0
    points: int = 401

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> FilterSpecification:
        filter_type = str(payload.get("filter_type", "BPF")).upper()
        if filter_type not in {"BPF", "BSF", "LPF", "MULTI"}:
            raise ValueError("filter_type must be BPF, BSF, LPF, or MULTI")

        response_family = str(
            payload.get("response_family", payload.get("family", "chebyshev"))
        ).lower()
        if response_family not in {"chebyshev", "butterworth", "bessel", "elliptic"}:
            raise ValueError(
                "response_family must be chebyshev, butterworth, bessel, or elliptic"
            )

        dispersion = str(payload.get("dispersion", "symmetric")).lower()
        if dispersion not in {"symmetric", "input", "output", "both"}:
            raise ValueError("dispersion must be symmetric, input, output, or both")

        start_ghz = _positive_float(payload.get("start_ghz", 0.875), "start_ghz")
        stop_ghz = _positive_float(payload.get("stop_ghz", 1.125), "stop_ghz")
        if stop_ghz <= start_ghz:
            raise ValueError("stop_ghz must be greater than start_ghz")

        q_value = payload.get("unloaded_q")
        unloaded_q = None
        if q_value not in {None, "", "Infinity", "infinity"}:
            unloaded_q = _positive_float(q_value, "unloaded_q")

        return cls(
            filter_type=filter_type,
            response_family=response_family,
            order=_bounded_int(payload.get("order", 4), 1, 12, "order"),
            return_loss_db=_positive_float(
                payload.get("return_loss_db", payload.get("rl_db", 25.0)),
                "return_loss_db",
            ),
            f0_ghz=_positive_float(payload.get("f0_ghz", 1.0), "f0_ghz"),
            bandwidth_ghz=_positive_float(
                payload.get("bandwidth_ghz", payload.get("bw_ghz", 0.05)),
                "bandwidth_ghz",
            ),
            start_ghz=start_ghz,
            stop_ghz=stop_ghz,
            shift_mhz=float(payload.get("shift_mhz", 0.0)),
            delta_bandwidth_mhz=float(payload.get("delta_bandwidth_mhz", 0.0)),
            unloaded_q=unloaded_q,
            impedance_ohm=_positive_float(
                payload.get("impedance_ohm", 50.0),
                "impedance_ohm",
            ),
            input_power_w=_positive_float(
                payload.get("input_power_w", 0.1),
                "input_power_w",
            ),
            stopband_attenuation_db=_positive_float(
                payload.get("stopband_attenuation_db", 60.0),
                "stopband_attenuation_db",
            ),
            dispersion=dispersion,
            dispersion_value=float(payload.get("dispersion_value", 0.0)),
            points=_bounded_int(payload.get("points", 401), 101, 2001, "points"),
        )


def synthesize_filter(payload: dict[str, Any]) -> dict[str, Any]:
    specification = FilterSpecification.from_payload(payload)
    transmission_zeros = _normalize_zeros(payload.get("zeros", []))
    effective_f0_hz = (specification.f0_ghz + specification.shift_mhz / 1_000.0) * 1e9
    effective_bandwidth_hz = max(
        specification.bandwidth_ghz + specification.delta_bandwidth_mhz / 1_000.0,
        1e-9,
    ) * 1e9
    frequencies_hz = np.linspace(
        specification.start_ghz * 1e9,
        specification.stop_ghz * 1e9,
        specification.points,
    )

    result = design_filter_network(
        filter_type=specification.filter_type,
        order=specification.order,
        family=specification.response_family,
        return_loss_db=specification.return_loss_db,
        f0_hz=effective_f0_hz,
        bandwidth_hz=effective_bandwidth_hz,
        frequencies_hz=frequencies_hz,
        unloaded_q=specification.unloaded_q,
        impedance_ohm=specification.impedance_ohm,
        input_power_w=specification.input_power_w,
        transmission_zeros=transmission_zeros,
        stopband_attenuation_db=specification.stopband_attenuation_db,
    )

    matrix = _matrix_payload(result.coupling, specification)
    topology = _topology(matrix)
    s11_db = _to_db(result.s11)
    s21_db = _to_db(result.s21)
    s22_db = _to_db(result.s22)
    group_delay_ns = result.group_delay_s * 1e9
    center_index = int(np.argmin(np.abs(frequencies_hz - effective_f0_hz)))
    passband_mask = _passband_mask(
        specification.filter_type,
        frequencies_hz,
        effective_f0_hz,
        effective_bandwidth_hz,
    )
    passband_s11 = s11_db[passband_mask]
    passband_s21 = s21_db[passband_mask]

    return {
        "status": 0,
        "ok": True,
        "engine": {
            "name": "coupled-resonator-prototype",
            "version": 1,
            "numerics": "NumPy/SciPy analog ZPK",
            "simulated": False,
        },
        "specification": {
            **asdict(specification),
            "effective_f0_ghz": effective_f0_hz / 1e9,
            "effective_bandwidth_ghz": effective_bandwidth_hz / 1e9,
        },
        "series": {
            "frequencies_ghz": _rounded(frequencies_hz / 1e9, 9),
            "s11_db": _rounded(s11_db, 6),
            "s21_db": _rounded(s21_db, 6),
            "s22_db": _rounded(s22_db, 6),
            "group_delay_ns": _rounded(group_delay_ns, 6),
            "power_w": _rounded(result.delivered_power_w, 9),
        },
        "prototype": result.prototype,
        "elements": result.elements,
        "matrix": matrix,
        "topology": topology,
        "dispersion": {
            "mode": specification.dispersion,
            "value": specification.dispersion_value,
            "input_group_delay_ns": float(group_delay_ns[center_index]),
            "output_group_delay_ns": float(group_delay_ns[center_index]),
        },
        "summary": {
            "center_insertion_loss_db": float(abs(s21_db[center_index])),
            "minimum_s11_db": float(np.min(s11_db)),
            "minimum_s22_db": float(np.min(s22_db)),
            "achieved_return_loss_db": float(-np.max(passband_s11)),
            "passband_ripple_db": float(np.max(passband_s21) - np.min(passband_s21)),
            "frequency_points": len(frequencies_hz),
            "input_external_q": result.coupling["physical"]["input_external_q"],
            "output_external_q": result.coupling["physical"]["output_external_q"],
        },
    }


def evaluate_coupling_matrix(payload: dict[str, Any]) -> dict[str, Any]:
    specification = FilterSpecification.from_payload(payload.get("specification") or payload)
    matrix_payload = payload.get("matrix")
    if isinstance(matrix_payload, dict):
        values = matrix_payload.get("values")
        labels = matrix_payload.get("labels")
    else:
        values = matrix_payload
        labels = None
    if not isinstance(values, list):
        raise TypeError("matrix.values must be a two-dimensional array")
    matrix = np.asarray(values, dtype=float)
    expected_size = specification.order + 2
    if matrix.shape != (expected_size, expected_size):
        raise ValueError(
            f"matrix must have shape {expected_size}x{expected_size} for order {specification.order}"
        )
    if not np.all(np.isfinite(matrix)):
        raise ValueError("matrix values must be finite")
    if not np.allclose(matrix, matrix.T, rtol=0.0, atol=1e-9):
        raise ValueError("matrix must be symmetric")
    frequencies_hz = np.linspace(
        specification.start_ghz * 1e9,
        specification.stop_ghz * 1e9,
        specification.points,
    )
    effective_f0_hz = (specification.f0_ghz + specification.shift_mhz / 1_000.0) * 1e9
    effective_bandwidth_hz = max(
        specification.bandwidth_ghz + specification.delta_bandwidth_mhz / 1_000.0,
        1e-9,
    ) * 1e9
    s11, s21, s22 = coupling_matrix_response(
        matrix,
        frequencies_hz,
        filter_type=specification.filter_type,
        f0_hz=effective_f0_hz,
        bandwidth_hz=effective_bandwidth_hz,
        unloaded_q=specification.unloaded_q,
    )
    angular_frequencies = 2.0 * np.pi * frequencies_hz
    group_delay_ns = -np.gradient(np.unwrap(np.angle(s21)), angular_frequencies) * 1e9
    s11_db = _to_db(s11)
    s21_db = _to_db(s21)
    s22_db = _to_db(s22)
    center_index = int(np.argmin(np.abs(frequencies_hz - effective_f0_hz)))
    return {
        "status": 0,
        "ok": True,
        "engine": {
            "name": "normalized-coupling-matrix",
            "version": 1,
            "simulated": False,
        },
        "matrix": {
            "labels": labels or ["S", *[str(index) for index in range(1, specification.order + 1)], "L"],
            "values": matrix.tolist(),
        },
        "series": {
            "frequencies_ghz": _rounded(frequencies_hz / 1e9, 9),
            "s11_db": _rounded(s11_db, 6),
            "s21_db": _rounded(s21_db, 6),
            "s22_db": _rounded(s22_db, 6),
            "group_delay_ns": _rounded(group_delay_ns, 6),
            "power_w": _rounded(specification.input_power_w * np.abs(s21) ** 2, 9),
        },
        "summary": {
            "center_insertion_loss_db": float(abs(s21_db[center_index])),
            "minimum_s11_db": float(np.min(s11_db)),
            "minimum_s22_db": float(np.min(s22_db)),
            "frequency_points": len(frequencies_hz),
        },
    }


def _matrix_payload(
    coupling: dict[str, Any],
    specification: FilterSpecification,
) -> dict[str, Any]:
    matrix = [list(row) for row in coupling["values"]]
    dispersion = specification.dispersion
    value = specification.dispersion_value
    if len(matrix) > 2 and dispersion in {"input", "both"}:
        matrix[1][1] = -value
    if len(matrix) > 2 and dispersion in {"output", "both"}:
        matrix[-2][-2] = value
    return {
        **coupling,
        "values": [[round(float(value), 8) for value in row] for row in matrix],
    }


def _topology(matrix: dict[str, Any]) -> dict[str, Any]:
    labels = matrix["labels"]
    nodes = [
        {
            "id": label,
            "label": label,
            "x": round(index / max(len(labels) - 1, 1), 6),
            "y": 0.5,
            "kind": "port" if label in {"S", "L"} else "resonator",
        }
        for index, label in enumerate(labels)
    ]
    edges = [
        {
            "source": labels[index],
            "target": labels[index + 1],
            "kind": "main",
            "coupling": matrix["values"][index][index + 1],
        }
        for index in range(len(labels) - 1)
    ]
    edges.extend(
        {
            "source": coupling["source"],
            "target": coupling["target"],
            "kind": "cross",
            "coupling": coupling["value"],
            "frequency_ghz": coupling["target_frequency_hz"] / 1e9,
        }
        for coupling in matrix["cross_couplings"]
    )
    return {"nodes": nodes, "edges": edges}


def _normalize_zeros(value: Any) -> list[dict[str, float]]:
    if not isinstance(value, list):
        raise TypeError("zeros must be a list")
    normalized = []
    for item in value:
        if not isinstance(item, dict):
            raise TypeError("each transmission zero must be an object")
        frequency = item.get("frequency_ghz", item.get("frequency"))
        if frequency in {None, ""}:
            continue
        frequency_ghz = _positive_float(frequency, "zero.frequency_ghz")
        normalized.append(
            {
                "frequency_hz": frequency_ghz * 1e9,
                "depth_db": _positive_float(item.get("depth_db", 80.0), "zero.depth_db"),
                "q": _positive_float(item.get("q", 30.0), "zero.q"),
            }
        )
    return normalized


def _passband_mask(
    filter_type: str,
    frequencies_hz: np.ndarray,
    f0_hz: float,
    bandwidth_hz: float,
) -> np.ndarray:
    if filter_type == "BPF":
        ratio = frequencies_hz / f0_hz
        normalized = (ratio - 1.0 / ratio) / (bandwidth_hz / f0_hz)
        return np.abs(normalized) <= 1.0
    if filter_type == "BSF":
        return np.abs(frequencies_hz - f0_hz) >= bandwidth_hz
    if filter_type == "LPF":
        return frequencies_hz <= f0_hz
    channel_offset = bandwidth_hz * 0.9
    return (
        np.abs(frequencies_hz - (f0_hz - channel_offset)) <= bandwidth_hz / 2.0
    ) | (
        np.abs(frequencies_hz - (f0_hz + channel_offset)) <= bandwidth_hz / 2.0
    )


def _to_db(values: np.ndarray) -> np.ndarray:
    return 20.0 * np.log10(np.maximum(np.abs(values), 1e-12))


def _rounded(values: np.ndarray, digits: int) -> list[float]:
    return [round(float(value), digits) for value in values]


def _positive_float(value: Any, name: str) -> float:
    result = float(value)
    if result <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return result


def _bounded_int(value: Any, minimum: int, maximum: int, name: str) -> int:
    result = int(value)
    if result < minimum or result > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return result
