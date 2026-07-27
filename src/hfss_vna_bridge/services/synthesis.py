from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class FilterSpecification:
    filter_type: str = "BPF"
    order: int = 4
    return_loss_db: float = 25.0
    f0_ghz: float = 1.0
    bandwidth_ghz: float = 0.05
    start_ghz: float = 0.875
    stop_ghz: float = 1.125
    shift_mhz: float = 0.0
    delta_bandwidth_mhz: float = 0.0
    unloaded_q: float | None = None
    points: int = 401

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> FilterSpecification:
        filter_type = str(payload.get("filter_type", "BPF")).upper()
        if filter_type not in {"BPF", "BSF", "LPF", "MULTI"}:
            raise ValueError("filter_type must be BPF, BSF, LPF, or MULTI")

        order = _bounded_int(payload.get("order", 4), 1, 12, "order")
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
            order=order,
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
            points=_bounded_int(payload.get("points", 401), 101, 2001, "points"),
        )


def synthesize_filter(payload: dict[str, Any]) -> dict[str, Any]:
    specification = FilterSpecification.from_payload(payload)
    zeros = _normalize_zeros(payload.get("zeros", []))
    dispersion = str(payload.get("dispersion", "symmetric"))
    effective_f0 = specification.f0_ghz + specification.shift_mhz / 1_000.0
    effective_bw = max(
        specification.bandwidth_ghz + specification.delta_bandwidth_mhz / 1_000.0,
        1e-6,
    )

    frequencies = _linspace(
        specification.start_ghz,
        specification.stop_ghz,
        specification.points,
    )
    s11_db: list[float] = []
    s21_db: list[float] = []
    s22_db: list[float] = []
    group_delay_ns: list[float] = []
    power_w: list[float] = []

    for frequency in frequencies:
        transmission = _transmission_power(
            specification.filter_type,
            specification.order,
            frequency,
            effective_f0,
            effective_bw,
        )
        transmission = _apply_transmission_zeros(
            transmission,
            frequency,
            zeros,
            effective_bw,
        )
        insertion_loss = _insertion_loss(specification, frequency, effective_f0)
        s21 = max(-70.0, 10.0 * math.log10(max(transmission, 1e-12)) - insertion_loss)

        reflection_power = max(1.0 - transmission * 0.998, 1e-9)
        base_reflection = 10.0 * math.log10(reflection_power)
        ripple = _return_loss_ripple(
            frequency,
            effective_f0,
            effective_bw,
            specification.order,
            transmission,
        )
        s11 = max(-70.0, min(0.0, base_reflection - ripple))
        s22 = max(-70.0, min(0.0, s11 + 0.6 * math.sin(frequency * 151.0)))
        delay = _group_delay(
            frequency,
            effective_f0,
            effective_bw,
            specification.order,
            transmission,
        )

        s11_db.append(round(s11, 5))
        s21_db.append(round(s21, 5))
        s22_db.append(round(s22, 5))
        group_delay_ns.append(round(delay, 5))
        power_w.append(round(max(0.0, transmission * 0.1), 7))

    matrix = _coupling_matrix(specification.order, zeros, dispersion)
    topology = _topology(specification.order, zeros)
    center_index = min(
        range(len(frequencies)),
        key=lambda index: abs(frequencies[index] - effective_f0),
    )

    return {
        "status": 0,
        "ok": True,
        "specification": {
            **asdict(specification),
            "effective_f0_ghz": effective_f0,
            "effective_bandwidth_ghz": effective_bw,
        },
        "series": {
            "frequencies_ghz": [round(value, 9) for value in frequencies],
            "s11_db": s11_db,
            "s21_db": s21_db,
            "s22_db": s22_db,
            "group_delay_ns": group_delay_ns,
            "power_w": power_w,
        },
        "matrix": matrix,
        "topology": topology,
        "dispersion": {
            "mode": dispersion,
            "input_group_delay_ns": group_delay_ns[center_index],
            "output_group_delay_ns": group_delay_ns[center_index],
        },
        "summary": {
            "center_insertion_loss_db": abs(s21_db[center_index]),
            "minimum_s11_db": min(s11_db),
            "minimum_s22_db": min(s22_db),
            "frequency_points": len(frequencies),
        },
    }


def _transmission_power(
    filter_type: str,
    order: int,
    frequency: float,
    f0_ghz: float,
    bandwidth_ghz: float,
) -> float:
    half_bandwidth = max(bandwidth_ghz / 2.0, 1e-9)
    normalized = (frequency - f0_ghz) / half_bandwidth
    bandpass = 1.0 / (1.0 + abs(normalized) ** (2 * order))

    if filter_type == "BPF":
        return bandpass
    if filter_type == "BSF":
        return max(1e-12, 1.0 - bandpass)
    if filter_type == "LPF":
        cutoff = max(f0_ghz, 1e-9)
        return 1.0 / (1.0 + abs(frequency / cutoff) ** (2 * order))

    offset = bandwidth_ghz * 0.82
    left = 1.0 / (
        1.0 + abs((frequency - (f0_ghz - offset)) / half_bandwidth) ** (2 * order)
    )
    right = 1.0 / (
        1.0 + abs((frequency - (f0_ghz + offset)) / half_bandwidth) ** (2 * order)
    )
    return min(1.0, left + right)


def _apply_transmission_zeros(
    transmission: float,
    frequency: float,
    zeros: list[dict[str, float]],
    bandwidth_ghz: float,
) -> float:
    result = transmission
    width = max(bandwidth_ghz * 0.035, 1e-6)
    for zero in zeros:
        distance = (frequency - zero["frequency_ghz"]) / width
        depth = min(max(zero["depth_db"], 1.0), 120.0)
        attenuation = 10 ** (-(depth * math.exp(-(distance**2))) / 10.0)
        result *= attenuation
    return max(result, 1e-12)


def _return_loss_ripple(
    frequency: float,
    f0_ghz: float,
    bandwidth_ghz: float,
    order: int,
    transmission: float,
) -> float:
    normalized = (frequency - f0_ghz) / max(bandwidth_ghz / 2.0, 1e-9)
    ripple = 0.0
    width = 0.10 + 0.025 / max(order, 1)
    for index in range(order):
        position = -0.76 + (1.52 * (index + 0.5) / order)
        ripple += 45.0 * math.exp(-((normalized - position) / width) ** 2)
    return ripple * transmission


def _group_delay(
    frequency: float,
    f0_ghz: float,
    bandwidth_ghz: float,
    order: int,
    transmission: float,
) -> float:
    normalized = (frequency - f0_ghz) / max(bandwidth_ghz / 2.0, 1e-9)
    center = 3.1 * order / max(bandwidth_ghz * 1_000.0, 1.0)
    edge = 2.6 * math.exp(-((abs(normalized) - 0.82) / 0.18) ** 2)
    return 0.15 + transmission * (center + edge)


def _insertion_loss(
    specification: FilterSpecification,
    frequency: float,
    f0_ghz: float,
) -> float:
    if specification.unloaded_q is None:
        return 0.025
    normalized_offset = abs(frequency - f0_ghz) / max(f0_ghz, 1e-9)
    return (
        4.343
        * specification.order
        * (1.0 + normalized_offset)
        / specification.unloaded_q
    )


def _coupling_matrix(
    order: int,
    zeros: list[dict[str, float]],
    dispersion: str,
) -> dict[str, Any]:
    labels = ["S", *[str(index) for index in range(1, order + 1)], "L"]
    size = len(labels)
    values = [[0.0 for _ in range(size)] for _ in range(size)]
    for index in range(size - 1):
        edge_distance = min(index, size - 2 - index)
        value = 1.1522 - 0.1234 * min(edge_distance, 2)
        if order % 2 == 0 and edge_distance >= order // 2:
            value *= 0.75
        values[index][index + 1] = round(value, 4)
        values[index + 1][index] = round(value, 4)

    for index, zero in enumerate(zeros[: max(0, order - 1)]):
        row = 1 + index
        column = min(order, row + 2)
        direction = -1.0 if zero["frequency_ghz"] < 1.0 else 1.0
        cross_value = round(direction * min(0.35, zero["depth_db"] / 240.0), 4)
        values[row][column] = cross_value
        values[column][row] = cross_value

    if dispersion in {"input", "both"} and order:
        values[1][1] = -0.05
    if dispersion in {"output", "both"} and order:
        values[-2][-2] = 0.05

    return {"labels": labels, "values": values, "unit": "normalized"}


def _topology(order: int, zeros: list[dict[str, float]]) -> dict[str, Any]:
    labels = ["S", *[str(index) for index in range(1, order + 1)], "L"]
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
        {"source": labels[index], "target": labels[index + 1], "kind": "main"}
        for index in range(len(labels) - 1)
    ]
    for index, zero in enumerate(zeros[: max(0, order - 1)]):
        source_index = 1 + index
        target_index = min(order, source_index + 2)
        edges.append(
            {
                "source": labels[source_index],
                "target": labels[target_index],
                "kind": "cross",
                "frequency_ghz": zero["frequency_ghz"],
            }
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
        normalized.append(
            {
                "frequency_ghz": _positive_float(frequency, "zero.frequency_ghz"),
                "depth_db": _positive_float(item.get("depth_db", 60.0), "zero.depth_db"),
            }
        )
    return normalized


def _linspace(start: float, stop: float, points: int) -> list[float]:
    step = (stop - start) / (points - 1)
    return [start + index * step for index in range(points)]


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
