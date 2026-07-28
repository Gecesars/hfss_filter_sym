from __future__ import annotations

import math
from typing import Any

from .models import CharacterizationSample, StudyKind


def simulate_eigenmode_study(plan: dict[str, Any]) -> tuple[CharacterizationSample, ...]:
    """Generate deterministic offline samples for UI and workflow development.

    The output is explicitly marked simulated and must never be promoted to an
    approved component characterization without a real AEDT run.
    """

    if str(plan.get("analysis_kind")) != "eigenmode":
        raise ValueError("plan must be an eigenmode component study")
    study = dict(plan.get("study") or {})
    setup = dict(plan.get("setup") or {})
    kind = StudyKind(str(study.get("kind")))
    values = [float(item) for item in study.get("sample_values", [])]
    if len(values) < 2:
        raise ValueError("study plan requires at least two sample values")
    center_hz = (
        float(setup.get("minimum_frequency_ghz", 0.65))
        + float(setup.get("maximum_frequency_ghz", 1.35))
    ) * 0.5e9
    nominal = _nominal_parameter(plan, study["parameter_name"])
    samples: list[CharacterizationSample] = []
    for index, value in enumerate(values):
        if kind is StudyKind.RESONANCE:
            frequency = center_hz * nominal / value
            spurious = frequency * (1.72 + 0.015 * index)
            frequencies = (frequency, spurious)
            labels = ("target-resonance", "first-spurious")
            quality = (7_500.0 + 25.0 * index, 5_000.0 + 10.0 * index)
        elif kind is StudyKind.COUPLING:
            ratio = max(value / nominal, 0.05)
            coupling = min(0.22, 0.018 * ratio**1.35)
            lower = center_hz * math.sqrt(1.0 - coupling)
            upper = center_hz * math.sqrt(1.0 + coupling)
            frequencies = (lower, upper, center_hz * 1.85)
            labels = ("even", "odd", "first-spurious")
            quality = (7_200.0, 7_150.0, 4_600.0)
        else:
            raise ValueError(f"offline Eigenmode simulation does not support {kind.value}")
        samples.append(
            CharacterizationSample(
                parameter_value=value,
                frequencies_hz=tuple(float(item) for item in frequencies),
                quality_factors=tuple(float(item) for item in quality),
                mode_labels=labels,
                metadata={
                    "backend": "simulated-eigenmode",
                    "approved": False,
                    "sample_index": index,
                    "component_id": plan.get("component_id"),
                },
            )
        )
    return tuple(samples)


def _nominal_parameter(plan: dict[str, Any], parameter_name: str) -> float:
    variables = dict(plan.get("variables") or {})
    if parameter_name not in variables:
        study_values = [float(item) for item in plan["study"]["sample_values"]]
        return float(study_values[len(study_values) // 2])
    value = float(variables[parameter_name])
    if value <= 0.0:
        raise ValueError(f"nominal parameter {parameter_name!r} must be greater than zero")
    return value
