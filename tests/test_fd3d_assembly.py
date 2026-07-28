from __future__ import annotations

from copy import deepcopy
from typing import Any

from hfss_vna_bridge.fd3d.assembly import build_combline_assembly_plan
from hfss_vna_bridge.services.fd3d import create_project_blueprint


def _project(order: int = 4) -> dict[str, Any]:
    return create_project_blueprint(
        {
            "name": "Componentized combline",
            "technology": "combline",
            "specification": {
                "filter_type": "BPF",
                "response_family": "chebyshev",
                "order": order,
                "return_loss_db": 20.0,
                "f0_ghz": 1.0,
                "bandwidth_ghz": 0.05,
                "start_ghz": 0.90,
                "stop_ghz": 1.10,
                "points": 201,
            },
        }
    )["project"]


def _mapped(project: dict[str, Any], *, extrapolated: bool = False) -> dict[str, Any]:
    seed = project["metadata"]["geometry_seed"]
    rows = []
    for node in project["assembly"]["nodes"]:
        if node["role"] != "resonator":
            continue
        rows.append(
            {
                "target_id": node["instance_id"],
                "target_type": "resonance_frequency",
                "curve_id": "resonance-curve",
                "parameter_name": "resonator_height_mm",
                "parameter_value": seed["resonator_height_mm"] * 0.98,
                "parameter_unit": "mm",
                "target_response": 1.0e9,
                "predicted_response": 1.0e9,
                "sensitivity": -8.0e6,
                "extrapolated": extrapolated,
            }
        )
    for edge in project["assembly"]["edges"]:
        if edge["target_type"] != "coupling" or edge["kind"] != "main":
            continue
        rows.append(
            {
                "target_id": edge["edge_id"],
                "target_type": "coupling",
                "curve_id": "coupling-curve",
                "parameter_name": "iris_width_mm",
                "parameter_value": seed["iris_width_mm"] * 1.03,
                "parameter_unit": "mm",
                "target_response": edge["target_value"],
                "predicted_response": edge["target_value"],
                "sensitivity": 0.002,
                "extrapolated": extrapolated,
            }
        )
    return {
        "valid": True,
        "mappings": rows,
        "missing_characterizations": [],
        "errors": [],
        "summary": {"mapped_count": len(rows)},
    }


def test_componentized_assembly_builds_separate_parts() -> None:
    project = _project()
    plan = build_combline_assembly_plan(
        project,
        _mapped(project),
        require_approved_curves=False,
        allow_seed_external_q=True,
    )

    assert plan["ready_for_hfss"] is True
    assert plan["solution_type"] == "Modal"
    assert len(plan["groups"]["resonators"]) == 4
    assert len(plan["groups"]["air_regions"]) == 4
    assert len(plan["groups"]["coupling_apertures"]) == 3
    assert len(plan["groups"]["tuning_features"]) == 4
    assert len(plan["groups"]["probes"]) == 2
    assert len(plan["ports"]) == 2
    assert plan["operations"][0]["blank"] == plan["groups"]["housing"][0]
    assert len(plan["operations"][0]["tools"]) == 7
    assert plan["validation"]["uses_seed_external_q"] is True
    assert all(part["object_name"] for part in plan["parts"])


def test_missing_characterized_dimensions_block_hfss_build() -> None:
    project = _project()
    plan = build_combline_assembly_plan(
        project,
        {"valid": False, "mappings": [], "summary": {}},
        require_approved_curves=False,
        allow_seed_external_q=True,
        allow_seed_resonance=False,
        allow_seed_coupling=False,
    )

    assert plan["ready_for_hfss"] is False
    assert any("missing mapped resonator_height_mm" in item for item in plan["validation"]["blockers"])
    assert any("missing mapped iris_width_mm" in item for item in plan["validation"]["blockers"])


def test_cross_coupling_requires_explicit_physical_realization() -> None:
    project = deepcopy(_project())
    project["assembly"]["edges"].append(
        {
            "edge_id": "edge-1-4-cross",
            "source_instance": "resonator-1",
            "target_instance": "resonator-4",
            "component_id": "combline-iris-v1",
            "kind": "cross",
            "target_type": "coupling",
            "target_value": -0.01,
            "target_coupling": -0.01,
            "sign": -1,
            "sign_reviewed": False,
        }
    )

    plan = build_combline_assembly_plan(
        project,
        _mapped(project),
        require_approved_curves=False,
        allow_seed_external_q=True,
    )

    assert plan["ready_for_hfss"] is False
    assert plan["validation"]["unrealized_cross_coupling_count"] == 1
    assert plan["unrealized_edges"][0]["edge_id"] == "edge-1-4-cross"
    assert any("explicit physical realization" in item for item in plan["validation"]["blockers"])


def test_extrapolated_component_mapping_is_never_build_ready() -> None:
    project = _project()
    plan = build_combline_assembly_plan(
        project,
        _mapped(project, extrapolated=True),
        require_approved_curves=False,
        allow_seed_external_q=True,
    )

    assert plan["ready_for_hfss"] is False
    assert any("extrapolated" in item for item in plan["validation"]["blockers"])
