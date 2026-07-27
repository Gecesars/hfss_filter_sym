from __future__ import annotations

from copy import deepcopy
from typing import Any

_ENTRIES: tuple[dict[str, Any], ...] = (
    {
        "id": "bpf-chebyshev-4",
        "name": "4-pole Chebyshev Bandpass",
        "category": "synthesis",
        "description": "General-purpose inline coupled-resonator starting point.",
        "specification": {
            "filter_type": "BPF",
            "response_family": "chebyshev",
            "order": 4,
            "return_loss_db": 25,
            "f0_ghz": 1.0,
            "bandwidth_ghz": 0.05,
            "start_ghz": 0.875,
            "stop_ghz": 1.125,
            "points": 401,
        },
    },
    {
        "id": "combline-6",
        "name": "6-pole Combline Cavity",
        "category": "cavity",
        "description": "Parametric metallic cavity with six cylindrical resonators.",
        "model": {
            "recipe": "combline",
            "order": 6,
            "length_mm": 150,
            "width_mm": 55,
            "height_mm": 28,
            "wall_mm": 2,
            "resonator_radius_mm": 3.2,
        },
    },
    {
        "id": "siw-4",
        "name": "4-pole SIW Filter",
        "category": "planar",
        "description": "Substrate-integrated waveguide geometry with two via fences.",
        "model": {
            "recipe": "siw",
            "order": 4,
            "length_mm": 95,
            "board_width_mm": 32,
            "substrate_height_mm": 1.524,
            "via_diameter_mm": 0.8,
            "via_pitch_mm": 1.5,
        },
    },
    {
        "id": "lpf-stepped-7",
        "name": "7-section Stepped-Impedance LPF",
        "category": "planar",
        "description": "Alternating high/low impedance microstrip sections.",
        "model": {
            "recipe": "lpf_step",
            "order": 5,
            "length_mm": 84,
            "board_width_mm": 30,
            "line_width_mm": 2.8,
        },
    },
)


def list_library(category: str | None = None) -> list[dict[str, Any]]:
    entries = _ENTRIES
    if category:
        entries = tuple(item for item in entries if item["category"] == category)
    return [deepcopy(item) for item in entries]


def get_library_entry(entry_id: str) -> dict[str, Any]:
    for entry in _ENTRIES:
        if entry["id"] == entry_id:
            return deepcopy(entry)
    raise KeyError(f"Library entry not found: {entry_id}")
