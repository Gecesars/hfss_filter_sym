from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest

from hfss_vna_bridge.fd3d.external_q import (
    external_q_study_plan,
    fit_external_q,
    one_port_resonator_s11,
    run_hfss_external_q_study,
)
from hfss_vna_bridge.services.fd3d import create_project_blueprint


def _probe_component() -> dict[str, Any]:
    project = create_project_blueprint(
        {
            "name": "External Q test",
            "technology": "combline",
            "specification": {
                "filter_type": "BPF",
                "response_family": "chebyshev",
                "order": 3,
                "return_loss_db": 20.0,
                "f0_ghz": 1.0,
                "bandwidth_ghz": 0.05,
                "start_ghz": 0.90,
                "stop_ghz": 1.10,
                "points": 201,
            },
        }
    )["project"]
    return next(item for item in project["components"] if item["kind"] == "EXTERNAL_COUPLING")


def test_complex_fit_recovers_external_q_and_delay() -> None:
    frequency = np.linspace(0.985e9, 1.015e9, 1201)
    loaded_q = 740.0
    external_q = 1850.0
    depth = 2.0 * loaded_q / external_q
    exact = one_port_resonator_s11(
        frequency,
        resonance_frequency_hz=1.0012e9,
        loaded_q=loaded_q,
        resonant_depth=depth,
        phase_rad=0.37,
        delay_s=1.8e-9,
    )
    rng = np.random.default_rng(2026)
    noisy = exact + 8e-4 * (rng.normal(size=exact.size) + 1j * rng.normal(size=exact.size))

    fit = fit_external_q(frequency, noisy)

    assert fit.success is True
    assert fit.resonance_frequency_hz == pytest.approx(1.0012e9, rel=2e-5)
    assert fit.loaded_q == pytest.approx(loaded_q, rel=0.03)
    assert fit.external_q == pytest.approx(external_q, rel=0.04)
    assert fit.delay_s == pytest.approx(1.8e-9, rel=0.08)
    assert fit.rms_complex_error < 0.005


def test_external_q_plan_is_one_port_driven_modal_and_parameterized() -> None:
    plan = external_q_study_plan(
        {
            "component": _probe_component(),
            "center_frequency_ghz": 1.0,
            "sample_values": [8.0, 12.0, 16.0],
            "dry_run": False,
        }
    )

    assert plan["analysis_kind"] == "driven_external_q"
    assert plan["solution_type"] == "Modal"
    assert len(plan["ports"]) == 1
    assert plan["study"]["parameter_name"] == "probe_depth_mm"
    probe = next(item for item in plan["objects"] if item["name"].endswith("_probe"))
    assert probe["height"] == "2*wall_mm+probe_depth_mm"
    assert plan["setup"]["points"] == 1001


@dataclass
class _State:
    connected: bool = True
    backend: str = "pyaedt"


class _SolutionData:
    primary_sweep_units = "Hz"

    def __init__(self, depth: float) -> None:
        self.primary_sweep_values = np.linspace(0.985e9, 1.015e9, 401).tolist()
        self.expression = ""
        loaded_q = 600.0 + depth * 5.0
        external_q = 2500.0 / max(depth / 10.0, 0.2)
        self.values = one_port_resonator_s11(
            self.primary_sweep_values,
            resonance_frequency_hz=1.0e9,
            loaded_q=loaded_q,
            resonant_depth=2.0 * loaded_q / external_q,
            phase_rad=0.2,
            delay_s=0.8e-9,
        )

    def data_real(self, expression: str) -> list[float]:
        self.expression = expression
        return self.values.real.tolist()

    def data_imag(self, expression: str) -> list[float]:
        self.expression = expression
        return self.values.imag.tolist()


class _Post:
    def get_solution_data(self, **kwargs: Any) -> _SolutionData:
        variation = next(iter(kwargs["variations"].values()))[0]
        depth = float(str(variation).replace("mm", ""))
        return _SolutionData(depth)


class _Hfss:
    def __init__(self) -> None:
        self.design_name = "Original"
        self.solution_type = "Modal"
        self.project_name = "ExternalQ"
        self.project_file = "D:/fd3d/external_q.aedt"
        self.post = _Post()
        self.variables: dict[str, str] = {}
        self.analyzed: list[str] = []

    def insert_design(self, *, name: str, solution_type: str) -> str:
        self.design_name = name
        self.solution_type = solution_type
        return name

    def __setitem__(self, key: str, value: str) -> None:
        self.variables[key] = value

    def analyze_setup(self, setup_name: str, **kwargs: Any) -> bool:
        assert kwargs["blocking"] is True
        self.analyzed.append(setup_name)
        return True

    def save_project(self) -> bool:
        return True

    def set_active_design(self, name: str) -> None:
        self.design_name = name


class _Adapter:
    state = _State()

    def __init__(self) -> None:
        self.hfss = _Hfss()

    def _require_hfss(self) -> _Hfss:
        return self.hfss

    def build_model(self, plan: dict[str, Any]) -> dict[str, Any]:
        assert plan["dry_run"] is False
        return {"built": True, "ports": [plan["ports"][0]["name"]]}


def test_real_hfss_external_q_runner_solves_every_probe_depth() -> None:
    adapter = _Adapter()
    plan = external_q_study_plan(
        {
            "component": _probe_component(),
            "center_frequency_ghz": 1.0,
            "sample_values": [8.0, 12.0, 16.0],
            "dry_run": False,
        }
    )

    result = run_hfss_external_q_study(adapter, plan, cores=4)

    assert result["solver"] == "HFSS Driven Modal"
    assert result["eligible_for_approval"] is True
    assert result["approved"] is False
    assert len(result["samples"]) == 3
    assert len(adapter.hfss.analyzed) == 3
    assert result["curve"]["study_kind"] == "EXTERNAL_Q"
    assert all(item["fit"]["external_q"] > 0.0 for item in result["samples"])


def test_external_q_runner_rejects_simulated_backend() -> None:
    adapter = _Adapter()
    adapter.state = _State(connected=True, backend="simulated")
    plan = external_q_study_plan(
        {
            "component": _probe_component(),
            "center_frequency_ghz": 1.0,
            "sample_values": [8.0, 12.0],
            "dry_run": False,
        }
    )

    with pytest.raises(RuntimeError, match="real PyAEDT/HFSS"):
        run_hfss_external_q_study(adapter, plan)
