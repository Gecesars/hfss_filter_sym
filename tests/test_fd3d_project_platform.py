from __future__ import annotations

from pathlib import Path

import pytest

from hfss_vna_bridge.fd3d.modeling import component_study_plan
from hfss_vna_bridge.services.fd3d import create_project_blueprint
from hfss_vna_bridge.services.project_store import ProjectStore


def _blueprint() -> dict:
    result = create_project_blueprint(
        {
            "name": "Combline 4 poles",
            "technology": "combline",
            "specification": {
                "filter_type": "BPF",
                "response_family": "chebyshev",
                "order": 4,
                "return_loss_db": 20.0,
                "f0_ghz": 1.0,
                "bandwidth_ghz": 0.05,
                "start_ghz": 0.90,
                "stop_ghz": 1.10,
                "points": 201,
            },
        }
    )
    assert result["ok"] is True
    return result["project"]


def test_blueprint_contains_matrix_components_and_assembly() -> None:
    project = _blueprint()
    assert project["schema"] == "hfss-filter-studio/fd3d-project/v1"
    assert project["stage"] == "SYNTHESIS"
    assert len(project["components"]) == 4
    assert len(project["assembly"]["nodes"]) == 6
    assert len(project["assembly"]["edges"]) >= 5
    resonators = [
        item for item in project["assembly"]["nodes"] if item["role"] == "resonator"
    ]
    assert len(resonators) == 4
    assert project["metadata"]["geometry_seed_status"] == "heuristic-not-aedt-validated"


def test_resonator_component_generates_portless_eigenmode_plan() -> None:
    project = _blueprint()
    component = next(
        item for item in project["components"] if item["kind"] == "RESONATOR"
    )
    plan = component_study_plan(
        {
            "component": component,
            "study_kind": "RESONANCE",
            "center_frequency_ghz": 1.0,
            "dry_run": True,
        }
    )
    assert plan["analysis_kind"] == "eigenmode"
    assert plan["solution_type"] == "Eigenmode"
    assert plan["ports"] == []
    assert plan["assign_ports"] is False
    assert len(plan["study"]["sample_values"]) == 9
    assert plan["setup"]["num_modes"] == 4
    assert {item["primitive"] for item in plan["objects"]} == {"box", "cylinder"}


def test_coupling_component_generates_pair_plan_with_parity_review() -> None:
    project = _blueprint()
    component = next(
        item for item in project["components"] if item["kind"] == "INTERNAL_COUPLING"
    )
    plan = component_study_plan(
        {
            "component": component,
            "study_kind": "COUPLING",
            "center_frequency_ghz": 1.0,
            "sample_values": [8.0, 12.0, 16.0],
        }
    )
    assert plan["study"]["kind"] == "COUPLING"
    assert plan["study"]["parameter_name"] == "iris_width_mm"
    assert plan["observables"]["parity_review"] is True
    assert plan["geometry_contract"]["coupling_sign"]["review_required"] is True
    assert len(plan["objects"]) == 6


def test_project_store_persists_fd3d_workflow(tmp_path: Path) -> None:
    fd3d_project = _blueprint()
    store = ProjectStore(tmp_path)
    saved = store.create(
        {
            "name": "FD3D Stored Project",
            "specification": fd3d_project["specification"],
            "matrix": fd3d_project["synthesis"]["matrix"],
            "workflow": {"stage": fd3d_project["stage"]},
            "fd3d": fd3d_project,
            "components": fd3d_project["components"],
            "assembly": fd3d_project["assembly"],
        }
    )
    loaded = store.get(saved["id"])
    assert loaded["version"] == 3
    assert loaded["fd3d"]["schema"] == fd3d_project["schema"]
    assert loaded["workflow"]["stage"] == "SYNTHESIS"
    summary = store.list_projects()[0]
    assert summary["workflow_stage"] == "SYNTHESIS"
    assert summary["fd3d_schema"] == fd3d_project["schema"]


def test_component_plan_rejects_samples_outside_bounds() -> None:
    project = _blueprint()
    component = next(
        item for item in project["components"] if item["kind"] == "RESONATOR"
    )
    with pytest.raises(ValueError, match="exceed"):
        component_study_plan(
            {
                "component": component,
                "study_kind": "RESONANCE",
                "sample_values": [1.0, 2.0],
            }
        )
