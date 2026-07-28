from __future__ import annotations

import math

import pytest

from hfss_vna_bridge.fd3d.characterization import (
    build_characterization_curve,
    coupling_from_split_modes,
    invert_curve,
    track_modes_by_frequency,
)
from hfss_vna_bridge.fd3d.models import CharacterizationSample


def test_coupling_from_split_modes_uses_squared_frequency_formula() -> None:
    lower = 950.0e6
    upper = 1_050.0e6
    expected = (upper**2 - lower**2) / (upper**2 + lower**2)
    assert coupling_from_split_modes(lower, upper) == pytest.approx(expected)
    assert coupling_from_split_modes(lower, upper, sign=-1) == pytest.approx(-expected)


def test_mode_tracking_recovers_swapped_solver_order() -> None:
    samples = (
        CharacterizationSample(1.0, (900.0e6, 1_100.0e6)),
        CharacterizationSample(2.0, (1_090.0e6, 910.0e6)),
        CharacterizationSample(3.0, (920.0e6, 1_080.0e6)),
    )
    tracked = track_modes_by_frequency(samples)
    assert tracked[1].frequencies_hz == pytest.approx((910.0e6, 1_090.0e6))
    assert tracked[2].frequencies_hz == pytest.approx((920.0e6, 1_080.0e6))


def test_resonance_curve_is_invertible_without_extrapolation() -> None:
    curve = build_characterization_curve(
        {
            "study_kind": "RESONANCE",
            "curve_id": "res-height",
            "parameter_name": "resonator_height_mm",
            "parameter_unit": "mm",
            "samples": [
                {"parameter_value": 50.0, "frequencies_hz": [1_100.0e6]},
                {"parameter_value": 55.0, "frequencies_hz": [1_000.0e6]},
                {"parameter_value": 60.0, "frequencies_hz": [900.0e6]},
            ],
        }
    )
    assert curve.monotonic_direction == "decreasing"
    mapping = invert_curve(curve, 1_000.0e6)
    assert mapping["parameter_value"] == pytest.approx(55.0)
    assert mapping["predicted_response"] == pytest.approx(1_000.0e6)
    with pytest.raises(ValueError, match="outside characterized range"):
        invert_curve(curve, 1_300.0e6)


def test_coupling_curve_uses_tracked_split_modes() -> None:
    curve = build_characterization_curve(
        {
            "study_kind": "COUPLING",
            "curve_id": "iris-k12",
            "parameter_name": "iris_width_mm",
            "parameter_unit": "mm",
            "samples": [
                {"parameter_value": 5.0, "frequencies_hz": [990.0e6, 1_010.0e6]},
                {"parameter_value": 10.0, "frequencies_hz": [980.0e6, 1_020.0e6]},
                {"parameter_value": 15.0, "frequencies_hz": [970.0e6, 1_030.0e6]},
            ],
        }
    )
    assert curve.monotonic_direction == "increasing"
    assert curve.y_values[0] < curve.y_values[-1]
    mapping = invert_curve(curve, curve.y_values[1])
    assert mapping["parameter_value"] == pytest.approx(10.0)


def test_non_monotonic_curve_requires_segmentation() -> None:
    curve = build_characterization_curve(
        {
            "study_kind": "RESONANCE",
            "parameter_name": "x",
            "samples": [
                {"parameter_value": 1.0, "frequencies_hz": [1.0e9]},
                {"parameter_value": 2.0, "frequencies_hz": [1.1e9]},
                {"parameter_value": 3.0, "frequencies_hz": [1.05e9]},
            ],
        }
    )
    assert curve.monotonic_direction == "non_monotonic"
    assert math.isclose(float(curve.metadata["monotonic_fraction"]), 0.5)
    with pytest.raises(ValueError, match="segmented"):
        invert_curve(curve, 1.075e9)
