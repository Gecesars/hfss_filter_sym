from __future__ import annotations

import numpy as np
import pytest

from hfss_vna_bridge.engines.filter_engine import coupling_matrix_response
from hfss_vna_bridge.fd3d.matrix_extraction import extract_coupling_matrix


def _matrix() -> np.ndarray:
    matrix = np.zeros((5, 5), dtype=float)
    matrix[0, 1] = matrix[1, 0] = 0.92
    matrix[1, 2] = matrix[2, 1] = 0.71
    matrix[2, 3] = matrix[3, 2] = 0.68
    matrix[3, 4] = matrix[4, 3] = 0.90
    matrix[1, 1] = -0.08
    matrix[2, 2] = 0.03
    matrix[3, 3] = 0.07
    return matrix


def _payload(
    measured_matrix: np.ndarray,
    initial_matrix: np.ndarray,
    *,
    phase_s11: float = 0.0,
    delay_s11: float = 0.0,
    phase_s21: float = 0.0,
    delay_s21: float = 0.0,
    fit_reference_planes: bool = False,
) -> dict:
    frequency = np.linspace(0.94e9, 1.06e9, 301)
    s11, s21, _ = coupling_matrix_response(
        measured_matrix,
        frequency,
        filter_type="BPF",
        f0_hz=1.0e9,
        bandwidth_hz=50.0e6,
        unloaded_q=8000.0,
    )
    offset = frequency - 1.0e9
    s11 *= np.exp(1j * (phase_s11 + 2.0 * np.pi * offset * delay_s11))
    s21 *= np.exp(1j * (phase_s21 + 2.0 * np.pi * offset * delay_s21))
    return {
        "frequency_hz": frequency.tolist(),
        "s11_real": s11.real.tolist(),
        "s11_imag": s11.imag.tolist(),
        "s21_real": s21.real.tolist(),
        "s21_imag": s21.imag.tolist(),
        "initial_matrix": {
            "labels": ["S", "1", "2", "3", "L"],
            "values": initial_matrix.tolist(),
        },
        "specification": {
            "filter_type": "BPF",
            "f0_hz": 1.0e9,
            "bandwidth_hz": 50.0e6,
            "unloaded_q": 8000.0,
        },
        "optimize_f0": False,
        "optimize_bandwidth": False,
        "optimize_unloaded_q": False,
        "fit_reference_planes": fit_reference_planes,
        "regularization": 1e-10,
        "maximum_rms_s11": 1e-4,
        "maximum_rms_s21": 1e-4,
        "maximum_condition_number": 1e16,
        "max_nfev": 3000,
    }


def test_complex_fit_recovers_matrix_entries_from_fullwave_network() -> None:
    actual = _matrix()
    initial = np.array(actual, copy=True)
    initial[0, 1] = initial[1, 0] = 0.86
    initial[1, 2] = initial[2, 1] = 0.76
    initial[2, 2] = -0.02
    initial[3, 4] = initial[4, 3] = 0.84

    result = extract_coupling_matrix(_payload(actual, initial))
    extracted = np.asarray(result["extracted_matrix"])

    assert result["ok"] is True
    assert result["method"] == "complex-topology-constrained-coupling-matrix-fit"
    assert result["fit"]["rms_s11_complex"] < 1e-5
    assert result["fit"]["rms_s21_complex"] < 1e-5
    assert extracted == pytest.approx(actual, abs=2e-3)


def test_reference_plane_phase_and_delay_are_not_absorbed_by_matrix() -> None:
    actual = _matrix()
    result = extract_coupling_matrix(
        _payload(
            actual,
            actual,
            phase_s11=0.34,
            delay_s11=1.2e-9,
            phase_s21=-0.22,
            delay_s21=0.8e-9,
            fit_reference_planes=True,
        )
    )

    assert result["ok"] is True
    assert result["settings"]["phase_s11_rad"] == pytest.approx(0.34, abs=2e-3)
    assert result["settings"]["delay_s11_s"] == pytest.approx(1.2e-9, rel=0.02)
    assert result["settings"]["phase_s21_rad"] == pytest.approx(-0.22, abs=2e-3)
    assert result["settings"]["delay_s21_s"] == pytest.approx(0.8e-9, rel=0.02)


def test_extraction_rejects_asymmetric_initial_matrix() -> None:
    actual = _matrix()
    initial = np.array(actual, copy=True)
    initial[0, 1] = 0.4

    with pytest.raises(ValueError, match="symmetric"):
        extract_coupling_matrix(_payload(actual, initial))
