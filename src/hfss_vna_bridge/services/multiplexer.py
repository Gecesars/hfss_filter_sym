from __future__ import annotations

from typing import Any

import numpy as np

from hfss_vna_bridge.services.synthesis import synthesize_filter


def synthesize_multiplexer(payload: dict[str, Any]) -> dict[str, Any]:
    channels = payload.get("channels")
    if not isinstance(channels, list) or len(channels) < 2:
        raise ValueError("channels must contain at least two filter specifications")
    if len(channels) > 16:
        raise ValueError("A maximum of 16 multiplexer channels is supported")
    start_ghz = float(payload.get("start_ghz", min(float(item["f0_ghz"]) for item in channels) * 0.8))
    stop_ghz = float(payload.get("stop_ghz", max(float(item["f0_ghz"]) for item in channels) * 1.2))
    points = int(payload.get("points", 801))
    if not 101 <= points <= 4001:
        raise ValueError("points must be between 101 and 4001")
    if stop_ghz <= start_ghz:
        raise ValueError("stop_ghz must be greater than start_ghz")

    results = []
    complex_transmissions = []
    for index, channel in enumerate(channels, start=1):
        if not isinstance(channel, dict):
            raise TypeError("each channel must be an object")
        specification = {
            "filter_type": "BPF",
            "response_family": "chebyshev",
            "order": 4,
            "return_loss_db": 22,
            "bandwidth_ghz": 0.05,
            **channel,
            "start_ghz": start_ghz,
            "stop_ghz": stop_ghz,
            "points": points,
        }
        result = synthesize_filter(specification)
        s21_magnitude = 10.0 ** (np.asarray(result["series"]["s21_db"]) / 20.0)
        phase = np.zeros(points)
        complex_transmissions.append(s21_magnitude * np.exp(1j * phase))
        results.append(
            {
                "id": str(channel.get("id") or f"CH{index}"),
                "name": str(channel.get("name") or f"Channel {index}"),
                "specification": result["specification"],
                "summary": result["summary"],
                "series": result["series"],
                "matrix": result["matrix"],
            }
        )

    transmission_power = np.sum(
        [np.abs(response) ** 2 for response in complex_transmissions],
        axis=0,
    )
    aggregate_s21 = np.sqrt(np.minimum(transmission_power, 1.0))
    aggregate_s11 = np.sqrt(np.maximum(1.0 - np.minimum(transmission_power, 1.0), 1e-15))
    frequencies = results[0]["series"]["frequencies_ghz"]
    topology_nodes = [{"id": "J", "label": "J", "kind": "junction", "x": 0.12, "y": 0.5}]
    topology_edges = []
    for index, channel in enumerate(results):
        y = (index + 1) / (len(results) + 1)
        topology_nodes.append(
            {"id": channel["id"], "label": channel["id"], "kind": "channel", "x": 0.72, "y": y}
        )
        topology_edges.append({"source": "J", "target": channel["id"], "kind": "branch"})
    return {
        "status": 0,
        "ok": True,
        "engine": {"name": "multi-channel-composite", "simulated": False},
        "specification": {
            "filter_type": "MULTI",
            "channels": len(results),
            "start_ghz": start_ghz,
            "stop_ghz": stop_ghz,
            "points": points,
        },
        "channels": results,
        "series": {
            "frequencies_ghz": frequencies,
            "s11_db": _db(aggregate_s11),
            "s21_db": _db(aggregate_s21),
            "s22_db": _db(aggregate_s11),
        },
        "topology": {"nodes": topology_nodes, "edges": topology_edges},
        "junction": {
            "model": "lossless-power-combiner-initial-design",
            "channel_isolation_note": (
                "Final manifold or star-junction isolation must be verified in HFSS."
            ),
        },
    }


def _db(values: np.ndarray) -> list[float]:
    return [round(float(value), 6) for value in 20.0 * np.log10(np.maximum(values, 1e-15))]
