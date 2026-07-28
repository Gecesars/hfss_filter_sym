from __future__ import annotations

import pytest

from hfss_vna_bridge.fd3d.approval import (
    approve_characterization_curve,
    revoke_characterization_curve,
)
from hfss_vna_bridge.fd3d.characterization import build_characterization_curve


def _samples() -> list[dict]:
    return [
        {
            "parameter_value": value,
            "frequencies_hz": [frequency, frequency * 1.75],
            "quality_factors": [7200.0, 4100.0],
            "mode_labels": ["Mode1", "Mode2"],
            "metadata": {
                "backend": "pyaedt-hfss-eigenmode",
                "approved": False,
                "tracking_ambiguous": False,
            },
        }
        for value, frequency in ((50.0, 1.08e9), (55.0, 1.00e9), (60.0, 0.93e9))
    ]


def _resonance_curve() -> dict:
    return build_characterization_curve(
        {
            "study_kind": "RESONANCE",
            "parameter_name": "resonator_height_mm",
            "parameter_unit": "mm",
            "samples": _samples(),
            "metadata": {
                "backend": "pyaedt-hfss-eigenmode",
                "solver": "HFSS Eigenmode",
                "component_id": "combline-resonator-v1",
            },
        }
    ).to_dict()


def _review() -> dict:
    return {
        "reviewer": "RF Engineer",
        "evidence": ["field_plot_mode1.png", "eigenmode_report.csv"],
        "mode_identity_reviewed": True,
        "field_distribution_reviewed": True,
        "mode_crossing_reviewed": True,
        "minimum_q": 4000.0,
        "notes": "Fundamental combline mode and continuity confirmed across the sweep.",
    }


def test_real_hfss_curve_requires_explicit_review_and_gets_digest() -> None:
    approved = approve_characterization_curve(_resonance_curve(), _review())

    assert approved.approved is True
    approval = approved.metadata["approval"]
    assert approval["schema"].endswith("characterization-approval/v1")
    assert approval["reviewer"] == "RF Engineer"
    assert approval["mode_crossing_reviewed"] is True
    assert len(approval["curve_digest_sha256"]) == 64
    assert approval["quality_factor_review"]["accepted"] is True


def test_non_hfss_curve_cannot_be_approved() -> None:
    curve = _resonance_curve()
    curve["metadata"]["backend"] = "simulated-eigenmode"

    with pytest.raises(ValueError, match="real HFSS Eigenmode"):
        approve_characterization_curve(curve, _review())


def test_coupling_sign_must_match_field_parity_review() -> None:
    curve = build_characterization_curve(
        {
            "study_kind": "COUPLING",
            "parameter_name": "iris_width_mm",
            "parameter_unit": "mm",
            "samples": _samples(),
            "sign": 1.0,
            "metadata": {
                "backend": "pyaedt-hfss-eigenmode",
                "solver": "HFSS Eigenmode",
                "component_id": "combline-iris-v1",
            },
        }
    ).to_dict()
    review = {
        **_review(),
        "field_parity_reviewed": True,
        "coupling_sign": -1,
        "segmented_monotonic_branch": True,
    }

    with pytest.raises(ValueError, match="does not match"):
        approve_characterization_curve(curve, review)


def test_approved_curve_can_be_revoked_with_traceability() -> None:
    approved = approve_characterization_curve(_resonance_curve(), _review())
    revoked = revoke_characterization_curve(
        approved,
        reviewer="RF Lead",
        reason="Mode crossing found in the field audit.",
    )

    assert revoked.approved is False
    assert "approval" not in revoked.metadata
    assert revoked.metadata["revocation"]["reviewer"] == "RF Lead"
    assert revoked.metadata["revocation"]["previous_approval"]["reviewer"] == "RF Engineer"
