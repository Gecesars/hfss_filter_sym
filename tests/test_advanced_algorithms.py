import math

import numpy as np
import pytest

from hfss_vna_bridge.services.advanced_algorithms import (
    run_algorithm,
    supported_algorithms,
)
from hfss_vna_bridge.web.app import create_app


def _complex_points() -> list[dict[str, float]]:
    frequencies = np.linspace(0.9e9, 1.1e9, 101)
    delay = 3.5e-9
    magnitude = np.exp(-((frequencies - 1e9) / 45e6) ** 4)
    values = magnitude * np.exp(-1j * 2 * np.pi * frequencies * delay)
    return [
        {
            "freq_hz": float(frequency),
            "s21_real": float(value.real),
            "s21_imag": float(value.imag),
            "s11_real": float(0.1 * value.real),
            "s11_imag": float(0.1 * value.imag),
        }
        for frequency, value in zip(frequencies, values, strict=True)
    ]


def test_algorithm_inventory_and_signal_processing() -> None:
    inventory = supported_algorithms()
    smooth = run_algorithm(
        "SmoothCurve_Fun",
        {"values": [0, 1, 0.2, 1.1, 0.1, 1.0, 0], "window": 5},
    )
    phase = run_algorithm("PhaseRemove", {"points": _complex_points()})
    transformed = run_algorithm(
        "TimeDomain",
        {"points": _complex_points(), "window": "hann", "velocity_factor": 0.8},
    )
    peaks = run_algorithm(
        "findmaxima",
        {"frequency": [1, 2, 3, 4, 5], "values": [0, 2, 0, 3, 0]},
    )

    assert len(inventory) >= 60
    assert smooth["residual_rms"] >= 0
    assert phase["removed_delay_s"] == pytest.approx(3.5e-9, rel=0.02)
    assert transformed["nfft"] >= 202
    assert transformed["peak"]["distance_m"] >= 0
    assert [peak["index"] for peak in peaks["peaks"]] == [3, 1]


def test_matrix_extraction_dispersion_and_transformations() -> None:
    extracted = run_algorithm(
        "BPFExtractMatrix",
        {
            "points": _complex_points(),
            "order": 4,
            "specification": {"filter_type": "BPF", "order": 4},
        },
    )
    matrix = extracted["extractedMatrix"]
    dispersed = run_algorithm(
        "Dispersion2",
        {
            "matrix": matrix,
            "start_ghz": 0.9,
            "stop_ghz": 1.1,
            "points": 5,
            "slope_per_ghz": 0.2,
        },
    )
    signed = run_algorithm("signChange", {"matrix": matrix, "index": 1})
    shifted = run_algorithm("CM2S_fineTune", {"matrix": matrix, "shift": 0.1})

    assert len(matrix) == 6
    assert len(dispersed["matrices"]) == 5
    assert signed["matrix"][0][1] == -matrix[0][1]
    assert shifted["matrix"][1][1] == pytest.approx(matrix[1][1] + 0.1)


def test_sensitivity_linear_tuning_space_mapping_and_perturbation() -> None:
    samples = [
        {"dimensions": {"d1": 0.0, "d2": 0.0}, "couplings": {"k1": 1.0, "k2": 2.0}},
        {"dimensions": {"d1": 1.0, "d2": 0.0}, "couplings": {"k1": 3.0, "k2": 1.0}},
        {"dimensions": {"d1": 0.0, "d2": 1.0}, "couplings": {"k1": 4.0, "k2": 6.0}},
        {"dimensions": {"d1": 1.0, "d2": 1.0}, "couplings": {"k1": 6.0, "k2": 5.0}},
    ]
    sensitivity = run_algorithm("Dimension2CouplingAnalysis", {"samples": samples})
    tuning_payload = {
        "dimensions": {"d1": 0.0, "d2": 0.0},
        "current": {"k1": 1.0, "k2": 2.0},
        "target": {"k1": 6.0, "k2": 5.0},
        "jacobian": sensitivity["jacobian"],
    }
    tuned = run_algorithm("LinearTuning", tuning_payload)
    mapped = run_algorithm("OSM", {**tuning_payload, "damping": 0.5})
    perturbations = run_algorithm(
        "Perturbation",
        {"dimensions": {"d1": 10.0, "d2": 5.0}, "relative_step": 0.01},
    )

    assert sensitivity["residual_rms"] < 1e-10
    assert tuned["remaining_error_norm"] < 1e-5
    assert mapped["dimensions"]["d1"] == pytest.approx(tuned["dimensions"]["d1"] / 2)
    assert perturbations["run_count"] == 5


def test_power_thermal_guided_wave_and_lpf_algorithms() -> None:
    specification = {
        "filter_type": "BPF",
        "order": 3,
        "f0_ghz": 1,
        "bandwidth_ghz": 0.08,
        "start_ghz": 0.85,
        "stop_ghz": 1.15,
        "points": 101,
        "input_power_w": 1,
    }
    voltage = run_algorithm(
        "CalculateVoltageDistribution",
        {"specification": specification},
    )
    power = run_algorithm(
        "PowerHandling",
        {"specification": specification, "gap_mm": 1, "input_power_w": 1},
    )
    thermal = run_algorithm(
        "ThermalShift",
        {"f0_ghz": 1, "delta_temperature_c": 40, "expansion_ppm_per_c": 17},
    )
    coax = run_algorithm(
        "q_coaxial",
        {"inner_radius_mm": 1, "outer_radius_mm": 3, "frequency_ghz": 1},
    )
    circular = run_algorithm(
        "waveguidecircle",
        {"radius_mm": 10, "frequency_ghz": 12},
    )
    iris = run_algorithm(
        "RectangularWGCoupling2IrisWidth",
        {"a_mm": 22.86, "coupling": 0.1, "thickness_mm": 1},
    )
    lpf = run_algorithm(
        "LPFSynthesis",
        {"order": 5, "cutoff_ghz": 1, "points": 101},
    )

    assert len(voltage["energy"]) == 101
    assert power["breakdown_power_w"] > 0
    assert thermal["shift_hz"] < 0
    assert coax["q"] > 0
    assert circular["cutoff_hz"]["TE11"] < circular["cutoff_hz"]["TM01"]
    assert 0 < iris["iris_width_mm"] < 22.86
    assert len(lpf["dimensions"]["sections"]) == 5


def test_algorithm_http_compatibility_routes() -> None:
    client = create_app().test_client()

    inventory = client.get("/api/algorithms")
    smooth = client.post(
        "/SmoothCurve_Fun",
        json={"values": [0, 1, 0, 1, 0], "window": 3},
    )
    thermal = client.post(
        "/api/v1/algorithm/general/ThermalShift",
        json={"f0_ghz": 1, "delta_temperature_c": 20},
    )

    assert inventory.status_code == 200
    assert len(inventory.get_json()["algorithms"]) >= 60
    assert smooth.status_code == 200
    assert smooth.get_json()["algorithm"] == "SmoothCurve_Fun"
    assert thermal.status_code == 200
    assert math.isfinite(thermal.get_json()["shift_hz"])
