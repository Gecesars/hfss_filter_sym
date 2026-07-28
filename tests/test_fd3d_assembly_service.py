from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from hfss_vna_bridge.services.fd3d import create_project_blueprint
from hfss_vna_bridge.services.fd3d_assembly import build_filter_assembly_in_hfss


@dataclass
class _State:
    connected: bool = True
    backend: str = "pyaedt"


class _Hfss:
    def __init__(self) -> None:
        self.design_name = "OriginalDesign"
        self.solution_type = "Modal"
        self.inserted: list[tuple[str, str]] = []
        self.restored: list[str] = []

    def insert_design(self, *, name: str, solution_type: str) -> str:
        self.inserted.append((name, solution_type))
        self.design_name = name
        self.solution_type = solution_type
        return name

    def set_active_design(self, name: str) -> None:
        self.restored.append(name)
        self.design_name = name


class _Adapter:
    state = _State()

    def __init__(self) -> None:
        self.hfss = _Hfss()
        self.plan: dict[str, Any] | None = None

    def _require_hfss(self) -> _Hfss:
        return self.hfss

    def build_model(self, plan: dict[str, Any]) -> dict[str, Any]:
        self.plan = dict(plan)
        return {
            "built": True,
            "object_count": len(plan["objects"]),
            "ports": [item["name"] for item in plan["ports"]],
        }

    def validate_design(self, expected_ports: int | None = None) -> dict[str, Any]:
        return {"valid": expected_ports == 2, "messages": [], "expected_ports": expected_ports}

    def save_project(self, file_name: str | None = None, *, overwrite: bool = True) -> str:
        assert overwrite is True
        return file_name or "D:/fd3d/componentized_filter.aedt"


def _project_and_mapping() -> tuple[dict[str, Any], dict[str, Any]]:
    project = create_project_blueprint(
        {
            "name": "Assembly service",
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
    seed = project["metadata"]["geometry_seed"]
    rows = []
    for node in project["assembly"]["nodes"]:
        if node["role"] == "resonator":
            rows.append(
                {
                    "target_id": node["instance_id"],
                    "curve_id": "r",
                    "parameter_name": "resonator_height_mm",
                    "parameter_value": seed["resonator_height_mm"],
                    "extrapolated": False,
                }
            )
    for edge in project["assembly"]["edges"]:
        if edge["target_type"] == "coupling" and edge["kind"] == "main":
            rows.append(
                {
                    "target_id": edge["edge_id"],
                    "curve_id": "k",
                    "parameter_name": "iris_width_mm",
                    "parameter_value": seed["iris_width_mm"],
                    "extrapolated": False,
                }
            )
    return project, {"valid": True, "mappings": rows, "summary": {"mapped_count": len(rows)}}


def test_componentized_filter_build_runs_in_real_driven_modal_design() -> None:
    project, mapping = _project_and_mapping()
    adapter = _Adapter()
    result = build_filter_assembly_in_hfss(
        adapter,
        {
            "project": project,
            "mapping": mapping,
            "require_approved_curves": False,
            "allow_seed_external_q": True,
            "save_project": True,
        },
    )

    assert result["solver"] == "HFSS Driven Modal"
    assert result["validation"]["valid"] is True
    assert adapter.hfss.inserted[0][1] == "Modal"
    assert adapter.plan is not None
    assert adapter.plan["dry_run"] is False
    assert len(adapter.plan["ports"]) == 2
    assert result["traceability"]["part_count"] > 3


def test_componentized_filter_build_rejects_simulated_backend() -> None:
    project, mapping = _project_and_mapping()
    adapter = _Adapter()
    adapter.state = _State(connected=True, backend="simulated")

    with pytest.raises(RuntimeError, match="real PyAEDT/HFSS"):
        build_filter_assembly_in_hfss(
            adapter,
            {
                "project": project,
                "mapping": mapping,
                "require_approved_curves": False,
            },
        )


def test_unready_assembly_is_not_sent_to_hfss() -> None:
    project, _ = _project_and_mapping()
    adapter = _Adapter()

    with pytest.raises(RuntimeError, match="not ready for HFSS"):
        build_filter_assembly_in_hfss(
            adapter,
            {
                "project": project,
                "mapping": {"valid": False, "mappings": [], "summary": {}},
                "require_approved_curves": False,
                "allow_seed_external_q": True,
            },
        )
    assert adapter.plan is None
