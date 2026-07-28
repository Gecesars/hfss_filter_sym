from __future__ import annotations

import pytest

from hfss_vna_bridge.fd3d.approval import approve_characterization_curve
from hfss_vna_bridge.fd3d.characterization import build_characterization_curve


def _external_q_curve() -> dict:
    samples = []
    for depth, qe, fit_rms in ((8.0, 3100.0, 0.012), (12.0, 2100.0, 0.009), (16.0, 1450.0, 0.011)):
        samples.append(
            {
                "parameter_value": depth,
                "frequencies_hz": [1.0e9],
                "quality_factors": [720.0],
                "mode_labels": ["driven-resonance"],
                "metadata": {
                    "backend": "pyaedt-hfss-driven-modal",
                    "approved": False,
                    "external_q": qe,
                    "internal_q": 5200.0,
                    "coupling_beta": 5200.0 / qe,
                    "rms_complex_error": fit_rms,
                },
            }
        )
    return build_characterization_curve(
        {
            "study_kind": "EXTERNAL_Q",
            "parameter_name": "probe_depth_mm",
            "parameter_unit": "mm",
            "samples": samples,
            "metadata_key": "external_q",
            "metadata": {
                "backend": "pyaedt-hfss-driven-modal",
                "solver": "HFSS Driven Modal",
                "component_id": "combline-probe-v1",
            },
        }
    ).to_dict()


def _review() -> dict:
    return {
        "reviewer": "RF Engineer",
        "evidence": ["s11_complex_fit.csv", "probe_geometry.png"],
        "complex_fit_reviewed": True,
        "port_reference_reviewed": True,
        "sweep_coverage_reviewed": True,
        "maximum_fit_rms": 0.02,
        "minimum_q": 500.0,
    }


def test_driven_external_q_curve_can_be_approved_without_modal_fields() -> None:
    approved = approve_characterization_curve(_external_q_curve(), _review())

    assert approved.approved is True
    assert approved.metadata["approved_backend"] == "pyaedt-hfss-driven-modal"
    assert approved.metadata["approval"]["driven_review"]["required"] is True
    assert approved.metadata["approval"]["modal_review"]["required"] is False


def test_driven_external_q_requires_port_reference_review() -> None:
    review = _review()
    review["port_reference_reviewed"] = False

    with pytest.raises(ValueError, match="port reference plane"):
        approve_characterization_curve(_external_q_curve(), review)


def test_driven_external_q_rejects_poor_complex_fit() -> None:
    curve = _external_q_curve()
    curve["source_samples"][1]["metadata"]["rms_complex_error"] = 0.08

    with pytest.raises(ValueError, match="fit RMS"):
        approve_characterization_curve(curve, _review())
