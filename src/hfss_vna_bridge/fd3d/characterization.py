from __future__ import annotations

from collections.abc import Iterable
from uuid import uuid4

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import linear_sum_assignment

from .models import CharacterizationCurve, CharacterizationSample, StudyKind


def coupling_from_split_modes(
    lower_frequency_hz: float,
    upper_frequency_hz: float,
    *,
    sign: float = 1.0,
) -> float:
    """Return coupling from the split eigenfrequencies of an identical resonator pair.

    Frequency splitting determines only the magnitude. The caller must provide the
    physical sign from topology, parity or a reviewed field classification.
    """

    lower = float(lower_frequency_hz)
    upper = float(upper_frequency_hz)
    if lower <= 0.0 or upper <= 0.0:
        raise ValueError("split-mode frequencies must be greater than zero")
    if upper <= lower:
        raise ValueError("upper_frequency_hz must exceed lower_frequency_hz")
    polarity = 1.0 if float(sign) >= 0.0 else -1.0
    return polarity * (upper**2 - lower**2) / (upper**2 + lower**2)


def track_modes_by_frequency(
    samples: Iterable[CharacterizationSample],
) -> tuple[CharacterizationSample, ...]:
    """Track modes using minimum frequency displacement between adjacent samples.

    This is the first deterministic tracking layer. Field correlation and parity
    classification will be added by the AEDT phase. Ambiguous changes are exposed
    in metadata instead of silently reordering a crossing.
    """

    ordered = sorted(samples, key=lambda item: item.parameter_value)
    if not ordered:
        return ()
    first = _sorted_sample(ordered[0])
    tracked = [first]
    previous = np.asarray(first.frequencies_hz, dtype=float)
    for sample in ordered[1:]:
        current = np.asarray(sample.frequencies_hz, dtype=float)
        if current.size != previous.size:
            raise ValueError("all samples must contain the same number of modes")
        scale = max(float(np.median(previous)), 1.0)
        cost = np.abs(previous[:, np.newaxis] - current[np.newaxis, :]) / scale
        rows, columns = linear_sum_assignment(cost)
        order = columns[np.argsort(rows)]
        frequencies = tuple(float(current[index]) for index in order)
        quality = (
            tuple(sample.quality_factors[index] for index in order)
            if sample.quality_factors
            else ()
        )
        labels = (
            tuple(sample.mode_labels[index] for index in order)
            if sample.mode_labels
            else tuple(f"mode-{index + 1}" for index in range(current.size))
        )
        normalized_cost = float(np.max(cost[rows, columns])) if rows.size else 0.0
        metadata = {
            **sample.metadata,
            "tracking_method": "minimum-frequency-displacement",
            "tracking_max_relative_jump": normalized_cost,
            "tracking_ambiguous": bool(normalized_cost > 0.08),
        }
        tracked_sample = CharacterizationSample(
            parameter_value=sample.parameter_value,
            frequencies_hz=frequencies,
            quality_factors=quality,
            mode_labels=labels,
            metadata=metadata,
        )
        tracked.append(tracked_sample)
        previous = np.asarray(frequencies, dtype=float)
    return tuple(tracked)


def build_characterization_curve(payload: dict) -> CharacterizationCurve:
    kind = StudyKind(str(payload.get("study_kind") or payload.get("kind") or "RESONANCE"))
    samples = tuple(
        item
        if isinstance(item, CharacterizationSample)
        else CharacterizationSample.from_dict(item)
        for item in payload.get("samples", [])
    )
    if len(samples) < 2:
        raise ValueError("at least two characterization samples are required")
    tracked = track_modes_by_frequency(samples)
    parameter_name = str(payload.get("parameter_name") or "parameter")
    parameter_unit = str(payload.get("parameter_unit") or "")
    mode_index = int(payload.get("mode_index", 0))
    x_values = np.asarray([item.parameter_value for item in tracked], dtype=float)

    if kind is StudyKind.RESONANCE:
        y_values = np.asarray(
            [_mode_frequency(item, mode_index) for item in tracked],
            dtype=float,
        )
        response_name = str(payload.get("response_name") or "resonance_frequency")
        response_unit = str(payload.get("response_unit") or "Hz")
    elif kind is StudyKind.COUPLING:
        low_index = int(payload.get("lower_mode_index", 0))
        high_index = int(payload.get("upper_mode_index", 1))
        sign = float(payload.get("sign", 1.0))
        y_values = np.asarray(
            [
                coupling_from_split_modes(
                    _mode_frequency(item, low_index),
                    _mode_frequency(item, high_index),
                    sign=sign,
                )
                for item in tracked
            ],
            dtype=float,
        )
        response_name = str(payload.get("response_name") or "coupling_coefficient")
        response_unit = str(payload.get("response_unit") or "")
    elif kind is StudyKind.EXTERNAL_Q:
        metadata_key = str(payload.get("metadata_key") or "external_q")
        try:
            y_values = np.asarray(
                [float(item.metadata[metadata_key]) for item in tracked],
                dtype=float,
            )
        except KeyError as exc:
            raise ValueError(
                f"EXTERNAL_Q samples require metadata key {metadata_key!r}"
            ) from exc
        if np.any(y_values <= 0.0):
            raise ValueError("external Q values must be greater than zero")
        response_name = str(payload.get("response_name") or "external_q")
        response_unit = str(payload.get("response_unit") or "")
    else:
        raise ValueError(f"curve generation is not implemented for {kind.value}")

    order = np.argsort(x_values)
    x_values = x_values[order]
    y_values = y_values[order]
    if np.any(np.diff(x_values) <= 0.0):
        raise ValueError("parameter samples must be unique")
    direction = _monotonic_direction(y_values)
    curve_id = str(payload.get("curve_id") or f"curve-{uuid4().hex[:12]}")
    approved = bool(payload.get("approved", False))
    metadata = {
        **dict(payload.get("metadata") or {}),
        "mode_tracking": "minimum-frequency-displacement",
        "sample_count": int(x_values.size),
        "x_min": float(x_values[0]),
        "x_max": float(x_values[-1]),
        "y_min": float(np.min(y_values)),
        "y_max": float(np.max(y_values)),
        "monotonic_fraction": _monotonic_fraction(y_values),
        "contains_ambiguous_tracking": any(
            bool(item.metadata.get("tracking_ambiguous")) for item in tracked
        ),
    }
    return CharacterizationCurve(
        curve_id=curve_id,
        study_kind=kind,
        parameter_name=parameter_name,
        parameter_unit=parameter_unit,
        x_values=tuple(float(item) for item in x_values),
        response_name=response_name,
        response_unit=response_unit,
        y_values=tuple(float(item) for item in y_values),
        monotonic_direction=direction,
        source_samples=tracked,
        approved=approved,
        metadata=metadata,
    )


def evaluate_curve(
    curve: CharacterizationCurve | dict,
    parameter_value: float,
    *,
    allow_extrapolation: bool = False,
) -> dict[str, float | bool | str]:
    item = curve if isinstance(curve, CharacterizationCurve) else CharacterizationCurve.from_dict(curve)
    x = np.asarray(item.x_values, dtype=float)
    y = np.asarray(item.y_values, dtype=float)
    value = float(parameter_value)
    extrapolated = value < x[0] or value > x[-1]
    if extrapolated and not allow_extrapolation:
        raise ValueError(
            f"parameter target {value:g} is outside characterized range {x[0]:g}..{x[-1]:g}"
        )
    interpolator = PchipInterpolator(x, y, extrapolate=allow_extrapolation)
    response = float(interpolator(value))
    sensitivity = float(interpolator.derivative()(value))
    return {
        "parameter_name": item.parameter_name,
        "parameter_value": value,
        "response_name": item.response_name,
        "predicted_response": response,
        "sensitivity": sensitivity,
        "extrapolated": extrapolated,
    }


def invert_curve(
    curve: CharacterizationCurve | dict,
    target_response: float,
    *,
    allow_extrapolation: bool = False,
) -> dict[str, float | bool | str]:
    item = curve if isinstance(curve, CharacterizationCurve) else CharacterizationCurve.from_dict(curve)
    if item.monotonic_direction == "non_monotonic":
        raise ValueError("non-monotonic curves must be segmented before inversion")
    x = np.asarray(item.x_values, dtype=float)
    y = np.asarray(item.y_values, dtype=float)
    if item.monotonic_direction == "decreasing":
        x = x[::-1]
        y = y[::-1]
    unique_y, unique_indices = np.unique(y, return_index=True)
    if unique_y.size < 2:
        raise ValueError("curve response is not invertible")
    inverse_x = x[unique_indices]
    target = float(target_response)
    extrapolated = target < unique_y[0] or target > unique_y[-1]
    if extrapolated and not allow_extrapolation:
        raise ValueError(
            f"response target {target:g} is outside characterized range "
            f"{unique_y[0]:g}..{unique_y[-1]:g}"
        )
    inverse = PchipInterpolator(unique_y, inverse_x, extrapolate=allow_extrapolation)
    parameter = float(inverse(target))
    forward = evaluate_curve(item, parameter, allow_extrapolation=allow_extrapolation)
    return {
        "curve_id": item.curve_id,
        "parameter_name": item.parameter_name,
        "parameter_value": parameter,
        "parameter_unit": item.parameter_unit,
        "target_response": target,
        "predicted_response": float(forward["predicted_response"]),
        "response_error": float(forward["predicted_response"]) - target,
        "sensitivity": float(forward["sensitivity"]),
        "extrapolated": extrapolated,
    }


def _mode_frequency(sample: CharacterizationSample, index: int) -> float:
    try:
        return float(sample.frequencies_hz[index])
    except IndexError as exc:
        raise ValueError(
            f"mode index {index} is unavailable for sample at {sample.parameter_value:g}"
        ) from exc


def _sorted_sample(sample: CharacterizationSample) -> CharacterizationSample:
    order = np.argsort(np.asarray(sample.frequencies_hz, dtype=float))
    frequencies = tuple(float(sample.frequencies_hz[index]) for index in order)
    quality = (
        tuple(sample.quality_factors[index] for index in order)
        if sample.quality_factors
        else ()
    )
    labels = (
        tuple(sample.mode_labels[index] for index in order)
        if sample.mode_labels
        else tuple(f"mode-{index + 1}" for index in range(len(order)))
    )
    return CharacterizationSample(
        parameter_value=sample.parameter_value,
        frequencies_hz=frequencies,
        quality_factors=quality,
        mode_labels=labels,
        metadata={
            **sample.metadata,
            "tracking_method": "initial-frequency-order",
            "tracking_ambiguous": False,
        },
    )


def _monotonic_direction(values: np.ndarray) -> str:
    differences = np.diff(values)
    tolerance = max(float(np.max(np.abs(values))) * 1e-10, 1e-15)
    if np.all(differences >= -tolerance) and np.any(differences > tolerance):
        return "increasing"
    if np.all(differences <= tolerance) and np.any(differences < -tolerance):
        return "decreasing"
    return "non_monotonic"


def _monotonic_fraction(values: np.ndarray) -> float:
    differences = np.diff(values)
    if differences.size == 0:
        return 1.0
    positive = float(np.count_nonzero(differences >= 0.0)) / differences.size
    negative = float(np.count_nonzero(differences <= 0.0)) / differences.size
    return max(positive, negative)
