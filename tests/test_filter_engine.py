import math

import pytest

from hfss_vna_bridge.services.synthesis import (
    evaluate_coupling_matrix,
    synthesize_filter,
)


def test_chebyshev_engine_meets_return_loss_and_builds_physical_network() -> None:
    result = synthesize_filter(
        {
            "filter_type": "BPF",
            "response_family": "chebyshev",
            "order": 4,
            "return_loss_db": 25,
            "f0_ghz": 1,
            "bandwidth_ghz": 0.05,
            "start_ghz": 0.9,
            "stop_ghz": 1.1,
            "points": 801,
        }
    )

    assert result["engine"]["simulated"] is False
    assert result["prototype"]["model"] == "scipy-analog-zpk"
    assert result["summary"]["achieved_return_loss_db"] == pytest.approx(25, abs=0.1)
    assert result["matrix"]["values"][0][1] == pytest.approx(1.1522, abs=0.005)
    assert len(result["prototype"]["g_values"]) == 6
    assert len(result["elements"]) == 8
    assert result["summary"]["input_external_q"] > 1
    assert result["matrix"]["physical"]["inter_resonator"]

    for s11_db, s21_db in zip(
        result["series"]["s11_db"],
        result["series"]["s21_db"],
        strict=True,
    ):
        total_power = 10 ** (s11_db / 10) + 10 ** (s21_db / 10)
        assert total_power == pytest.approx(1, abs=2e-5)


def test_finite_unloaded_q_adds_real_insertion_loss() -> None:
    ideal = synthesize_filter(
        {
            "filter_type": "BPF",
            "order": 4,
            "f0_ghz": 1,
            "bandwidth_ghz": 0.05,
            "start_ghz": 0.95,
            "stop_ghz": 1.05,
        }
    )
    lossy = synthesize_filter(
        {
            "filter_type": "BPF",
            "order": 4,
            "f0_ghz": 1,
            "bandwidth_ghz": 0.05,
            "start_ghz": 0.95,
            "stop_ghz": 1.05,
            "unloaded_q": 1000,
        }
    )

    assert ideal["prototype"]["loss_db"] == 0
    assert lossy["prototype"]["loss_db"] > 0
    assert lossy["summary"]["center_insertion_loss_db"] > ideal["summary"][
        "center_insertion_loss_db"
    ]


@pytest.mark.parametrize("filter_type", ["BPF", "BSF", "LPF", "MULTI"])
def test_real_engine_supports_all_filter_modes(filter_type: str) -> None:
    result = synthesize_filter(
        {
            "filter_type": filter_type,
            "response_family": "butterworth",
            "order": 3,
            "f0_ghz": 1,
            "bandwidth_ghz": 0.08,
            "start_ghz": 0.7,
            "stop_ghz": 1.3,
            "points": 301,
        }
    )

    assert len(result["series"]["s21_db"]) == 301
    assert all(math.isfinite(value) for value in result["series"]["s21_db"])
    assert result["prototype"]["family"] == "butterworth"


def test_finite_transmission_zero_creates_requested_notch() -> None:
    result = synthesize_filter(
        {
            "filter_type": "BPF",
            "order": 4,
            "f0_ghz": 1,
            "bandwidth_ghz": 0.05,
            "start_ghz": 1.02,
            "stop_ghz": 1.12,
            "points": 1001,
            "zeros": [{"frequency_ghz": 1.08, "depth_db": 80, "q": 30}],
        }
    )
    frequencies = result["series"]["frequencies_ghz"]
    index = min(range(len(frequencies)), key=lambda item: abs(frequencies[item] - 1.08))

    assert result["series"]["s21_db"][index] < -75
    assert result["matrix"]["cross_couplings"]


def test_edited_coupling_matrix_recalculates_a_passive_response() -> None:
    specification = {
        "filter_type": "BPF",
        "response_family": "chebyshev",
        "order": 4,
        "return_loss_db": 25,
        "f0_ghz": 1,
        "bandwidth_ghz": 0.05,
        "start_ghz": 0.9,
        "stop_ghz": 1.1,
        "points": 401,
    }
    synthesized = synthesize_filter(specification)
    evaluated = evaluate_coupling_matrix(
        {"specification": specification, "matrix": synthesized["matrix"]}
    )

    center = 200
    assert evaluated["series"]["s11_db"][center] == pytest.approx(-25, abs=0.1)
    for s11_db, s21_db in zip(
        evaluated["series"]["s11_db"],
        evaluated["series"]["s21_db"],
        strict=True,
    ):
        assert 10 ** (s11_db / 10) + 10 ** (s21_db / 10) == pytest.approx(
            1,
            abs=2e-5,
        )


def test_coupling_matrix_response_rejects_asymmetric_matrix() -> None:
    synthesized = synthesize_filter({"order": 2, "points": 101})
    matrix = synthesized["matrix"]
    matrix["values"][0][1] += 0.1

    with pytest.raises(ValueError, match="symmetric"):
        evaluate_coupling_matrix(
            {
                "specification": {"order": 2, "points": 101},
                "matrix": matrix,
            }
        )
