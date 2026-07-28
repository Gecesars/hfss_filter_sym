from __future__ import annotations

from dataclasses import replace

import pytest

from hfss_vna_bridge.fd3d.models import CharacterizationCurve, CharacterizationSample, StudyKind
from hfss_vna_bridge.fd3d.workflow import (
    advance_stage,
    attach_characterization,
    attach_mapping,
    project_gate_status,
)
from hfss_vna_bridge.services.fd3d import create_project_blueprint


def _project() -> dict:
    return create_project_blueprint(
        {
            "name": "Workflow project",
            "technology": "combline",
            "specification": {
                "filter_type": "BPF",
                "response_family": "chebyshev",
                "order": 3,
                "return_loss_db": 20.0,
                "f0_ghz": 1.0,
                "bandwidth_ghz": 0.05,
                "start_ghz": 0.9,
                "stop_ghz": 1.1,
                "points": 201,
            },
        }
    )["project"]


def _approved_curve(component_id: str, kind: StudyKind, curve_id: str) -> CharacterizationCurve:
    response_name = {
        StudyKind.RESONANCE: "resonance_frequency",
        StudyKind.COUPLING: "coupling_coefficient",
        StudyKind.EXTERNAL_Q: "external_q",
    }[kind]
    samples = (
        CharacterizationSample(
            parameter_value=1.0,
            frequencies_hz=(1.0e9,),
            quality_factors=(1000.0,),
            mode_labels=("mode",),
            metadata={"backend": "pyaedt-hfss-eigenmode", "approved": False},
        ),
        CharacterizationSample(
            parameter_value=2.0,
            frequencies_hz=(0.99e9,),
            quality_factors=(1000.0,),
            mode_labels=("mode",),
            metadata={"backend": "pyaedt-hfss-eigenmode", "approved": False},
        ),
    )
    return CharacterizationCurve(
        curve_id=curve_id,
        study_kind=kind,
        parameter_name="dimension_mm",
        parameter_unit="mm",
        x_values=(1.0, 2.0),
        response_name=response_name,
        response_unit="",
        y_values=(1.0, 2.0),
        monotonic_direction="increasing",
        source_samples=samples,
        approved=True,
        metadata={"component_id": component_id, "approval": {"reviewer": "RF"}},
    )


def test_project_gate_lists_all_required_component_characterizations() -> None:
    status = project_gate_status(_project())

    required = {(item["component_id"], item["study_kind"]) for item in status["required_characterizations"]}
    assert ("combline-resonator-v1", "RESONANCE") in required
    assert ("combline-iris-v1", "COUPLING") in required
    assert ("combline-probe-v1", "EXTERNAL_Q") in required
    assert status["characterization_gate"] is False


def test_approved_curves_open_characterization_gate() -> None:
    project = _project()
    project = attach_characterization(
        project,
        _approved_curve("combline-resonator-v1", StudyKind.RESONANCE, "fr"),
    )
    project = attach_characterization(
        project,
        _approved_curve("combline-iris-v1", StudyKind.COUPLING, "fk"),
    )
    project = attach_characterization(
        project,
        _approved_curve("combline-probe-v1", StudyKind.EXTERNAL_Q, "fqe"),
    )

    status = project_gate_status(project)
    assert status["characterization_gate"] is True
    assert status["missing_approved_characterizations"] == []


def test_invalid_mapping_cannot_advance_project() -> None:
    project = _project()
    with pytest.raises(ValueError, match="invalid"):
        attach_mapping(project, {"valid": False, "mappings": [], "summary": {}})


def test_stage_cannot_skip_required_characterization_gate() -> None:
    with pytest.raises(ValueError, match="approved component characterizations"):
        advance_stage(_project(), "ASSEMBLY")


def test_curve_with_foreign_component_is_rejected() -> None:
    curve = replace(
        _approved_curve("combline-resonator-v1", StudyKind.RESONANCE, "foreign"),
        metadata={"component_id": "foreign-component"},
    )
    with pytest.raises(ValueError, match="component in this project"):
        attach_characterization(_project(), curve)
