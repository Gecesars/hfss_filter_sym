from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from hfss_vna_bridge.adapters.aedt.eigenmode import run_hfss_eigenmode_study
from hfss_vna_bridge.services.fd3d import create_project_blueprint
from hfss_vna_bridge.fd3d.modeling import component_study_plan


@dataclass
class _State:
    connected: bool = True
    backend: str = "pyaedt"


class _CreatedObject:
    def __init__(self, name: str) -> None:
        self.name = name

    def subtract(self, tools: list[Any], keep_originals: bool = False) -> bool:
        assert tools
        assert keep_originals is True
        return True

    def unite(self, tools: list[Any]) -> bool:
        assert tools
        return True


class _Modeler:
    def __init__(self) -> None:
        self.model_units = "mm"
        self.created: list[dict[str, Any]] = []

    def create_box(self, **kwargs: Any) -> _CreatedObject:
        self.created.append({"kind": "box", **kwargs})
        return _CreatedObject(kwargs["name"])

    def create_cylinder(self, **kwargs: Any) -> _CreatedObject:
        self.created.append({"kind": "cylinder", **kwargs})
        return _CreatedObject(kwargs["name"])

    def fit_all(self) -> None:
        return None


class _Setup:
    def __init__(self, name: str) -> None:
        self.name = name
        self.props: dict[str, Any] = {}

    def update(self) -> bool:
        return True


class _Solution:
    def __init__(self, value: float) -> None:
        self.value = value

    def get_expression_data(self) -> tuple[None, list[float]]:
        return None, [self.value]


class _Post:
    def __init__(self, app: "_Hfss") -> None:
        self.app = app

    def available_report_quantities(
        self,
        *,
        quantities_category: str,
        solution: str | None = None,
    ) -> list[str]:
        assert solution is None or solution.endswith("LastAdaptive")
        if quantities_category == "Eigen Q":
            return ["Q1", "Q2"]
        if quantities_category == "Eigen Modes":
            return ["Mode1", "Mode2"]
        return []

    def get_solution_data(self, **kwargs: Any) -> _Solution:
        expression = kwargs["expressions"]
        assert kwargs["report_category"] == "Eigenmode"
        variation = next(iter(kwargs["variations"].values()))[0]
        value = float(str(variation).replace("mm", ""))
        if expression == "Mode1":
            return _Solution(1.1e9 * 50.0 / value)
        if expression == "Mode2":
            return _Solution(1.8e9 * 50.0 / value)
        if expression == "Q1":
            return _Solution(7100.0)
        if expression == "Q2":
            return _Solution(4300.0)
        raise AssertionError(expression)


class _Hfss:
    def __init__(self) -> None:
        self.design_name = "OriginalDriven"
        self.solution_type = "Modal"
        self.project_name = "FD3DProject"
        self.project_file = "D:/fd3d/FD3DProject.aedt"
        self.modeler = _Modeler()
        self.post = _Post(self)
        self.variables: dict[str, str] = {}
        self.inserted: list[tuple[str, str]] = []
        self.analyzed: list[str] = []
        self.active_designs: list[str] = []

    def insert_design(self, *, name: str, solution_type: str) -> str:
        self.inserted.append((name, solution_type))
        self.design_name = name
        self.solution_type = solution_type
        return name

    def __setitem__(self, key: str, value: str) -> None:
        self.variables[key] = value

    def create_setup(self, *, name: str, setup_type: str) -> _Setup:
        assert setup_type == "HFSSEigen"
        return _Setup(name)

    def analyze_setup(self, name: str, **kwargs: Any) -> bool:
        assert kwargs["blocking"] is True
        self.analyzed.append(name)
        return True

    def save_project(self) -> bool:
        return True

    def set_active_design(self, name: str) -> None:
        self.active_designs.append(name)
        self.design_name = name


class _Adapter:
    state = _State()

    def __init__(self) -> None:
        self.hfss = _Hfss()

    def _require_hfss(self) -> _Hfss:
        return self.hfss


def _resonator_plan() -> dict[str, Any]:
    project = create_project_blueprint(
        {
            "name": "HFSS Eigenmode contract",
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
    )["project"]
    component = next(item for item in project["components"] if item["kind"] == "RESONATOR")
    plan = component_study_plan(
        {
            "component": component,
            "study_kind": "RESONANCE",
            "center_frequency_ghz": 1.0,
            "sample_values": [50.0, 55.0, 60.0],
            "dry_run": False,
        }
    )
    return plan


def test_runner_requires_real_pyaedt_backend() -> None:
    adapter = _Adapter()
    adapter.state = _State(connected=True, backend="simulated")
    with pytest.raises(RuntimeError, match="real PyAEDT/HFSS"):
        run_hfss_eigenmode_study(adapter, _resonator_plan())


def test_runner_builds_and_solves_every_variation_in_hfss() -> None:
    adapter = _Adapter()
    result = run_hfss_eigenmode_study(adapter, _resonator_plan(), cores=4)
    assert result["solver"] == "HFSS Eigenmode"
    assert result["backend"] == "pyaedt-hfss-eigenmode"
    assert result["eligible_for_approval"] is True
    assert result["approved"] is False
    assert result["sample_count"] == 3
    assert len(adapter.hfss.analyzed) == 3
    assert adapter.hfss.inserted[0][1] == "Eigenmode"
    assert len(result["samples"][0]["frequencies_hz"]) == 2
    assert result["samples"][0]["quality_factors"] == pytest.approx([7100.0, 4300.0])
    rod = next(
        item
        for item in adapter.hfss.modeler.created
        if item["kind"] == "cylinder" and item["name"].endswith("_rod")
    )
    assert rod["height"] == "resonator_height_mm"


def test_dry_run_plan_cannot_be_solved() -> None:
    adapter = _Adapter()
    plan = _resonator_plan()
    plan["dry_run"] = True
    with pytest.raises(ValueError, match="dry_run"):
        run_hfss_eigenmode_study(adapter, plan)
