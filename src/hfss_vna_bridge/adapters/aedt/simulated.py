from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from hfss_vna_bridge.core.models import AdapterState, NetworkPoint
from hfss_vna_bridge.core.touchstone import write_s2p


class SimulatedAedtAdapter:
    """Deterministic AEDT stand-in used for tests and offline development."""

    def __init__(self) -> None:
        self._state = AdapterState(False, "simulated", "SIM::AEDT")
        self._project_path: Path | None = None
        self._design_name = "SimulatedHFSSDesign"
        self._variables: dict[str, str] = {
            "arm_scale_a": "1.0",
            "arm_scale_b": "1.0",
            "dist_refletor": "20mm",
            "comp_refletor": "80mm",
            "refl_lat": "16mm",
        }
        self._model_history: list[dict[str, Any]] = []
        self._analysis_config: dict[str, Any] = {}

    @property
    def state(self) -> AdapterState:
        return self._state

    def connect(
        self,
        project_path: str | Path | None = None,
        design_name: str | None = None,
        *,
        version: str | None = "2026.1",
        new_desktop: bool = False,
        non_graphical: bool = False,
        close_on_exit: bool = False,
        student_version: bool = False,
        machine: str | None = None,
        port: int | None = None,
        aedt_process_id: int | None = None,
        remove_lock: bool = False,
    ) -> AdapterState:
        del (
            new_desktop,
            non_graphical,
            close_on_exit,
            student_version,
            machine,
            port,
            aedt_process_id,
            remove_lock,
        )
        self._version = version or "2026.1"
        self._project_path = Path(project_path) if project_path else None
        if design_name:
            self._design_name = design_name
        resource = str(self._project_path) if self._project_path else "SIM::AEDT"
        self._state = AdapterState(True, "simulated", resource, self._design_name)
        return self._state

    def list_designs(self) -> list[str]:
        self._require_connected()
        return [self._design_name]

    def set_active_design(self, design_name: str) -> AdapterState:
        self._require_connected()
        self._design_name = design_name
        self._state = AdapterState(
            True,
            "simulated",
            self._state.resource,
            self._design_name,
        )
        return self._state

    def get_variables(self) -> dict[str, str]:
        self._require_connected()
        return dict(self._variables)

    def set_variables(self, variables: dict[str, str | float | int]) -> dict[str, str]:
        self._require_connected()
        for name, value in variables.items():
            self._variables[name] = str(value)
        return self.get_variables()

    def analyze(
        self,
        setup_name: str | None = None,
        sweep_name: str | None = None,
        output_touchstone: str | Path | None = None,
        *,
        cores: int | None = None,
        tasks: int | None = None,
        gpus: int | None = None,
        blocking: bool = True,
        revert_to_initial_mesh: bool = False,
    ) -> dict[str, Any]:
        del cores, tasks, gpus, revert_to_initial_mesh
        self._require_connected()
        output = None
        if output_touchstone:
            output = write_s2p(
                output_touchstone,
                self._synthetic_network(),
                comment=f"simulated AEDT setup={setup_name or 'default'} sweep={sweep_name or 'default'}",
            )
        return {
            "project": str(self._project_path) if self._project_path else None,
            "design": self._design_name,
            "setup": setup_name,
            "sweep": sweep_name,
            "touchstone": str(output) if output else None,
            "solved": True,
            "blocking": blocking,
            "session": self.session_info(),
        }

    def session_info(self) -> dict[str, Any]:
        self._require_connected()
        return {
            "connected": True,
            "version": getattr(self, "_version", "2026.1"),
            "version_full": "simulated",
            "process_id": None,
            "grpc_port": None,
            "grpc": False,
            "install_dir": None,
            "project_name": self._project_path.stem if self._project_path else "SimulatedProject",
            "project_file": str(self._project_path) if self._project_path else None,
            "design_name": self._design_name,
            "design_type": "HFSS",
            "solution_type": "Modal",
            "setups": ["SynMatrix"],
            "sweeps": {"SynMatrix": ["FreqSweep"]},
            "owns_desktop": False,
        }

    def save_project(
        self,
        file_name: str | Path | None = None,
        *,
        overwrite: bool = True,
    ) -> str:
        del overwrite
        self._require_connected()
        output = Path(file_name) if file_name else self._project_path
        return str(output or "SIM::AEDT")

    def create_sparameter_report(
        self,
        expressions: list[str] | None = None,
        *,
        setup_name: str | None = None,
        sweep_name: str | None = None,
        plot_name: str | None = None,
    ) -> dict[str, Any]:
        self._require_connected()
        return {
            "plot_name": plot_name or "S Parameters",
            "setup_sweep": f"{setup_name or 'SynMatrix'} : {sweep_name or 'FreqSweep'}",
            "expressions": expressions or ["dB(S(1,1))", "dB(S(2,1))"],
        }

    def export_convergence(
        self,
        setup_name: str | None = None,
        output_file: str | Path | None = None,
    ) -> str:
        self._require_connected()
        return str(output_file or f"{setup_name or 'SynMatrix'}.conv")

    def remove_solution_data(
        self,
        *,
        entire_solution: bool = False,
        field: bool = False,
        mesh: bool = True,
        linked_data: bool = False,
    ) -> bool:
        del entire_solution, field, mesh, linked_data
        self._require_connected()
        return True

    def configure_analysis(self, config: dict[str, Any]) -> dict[str, Any]:
        self._require_connected()
        self._analysis_config = dict(config)
        return {
            "configured": True,
            "setup": config.get("name", "FilterSetup"),
            "sweep": config.get("sweep_name", "FilterSweep"),
            "config": dict(config),
        }

    def build_model(self, plan: dict[str, Any]) -> dict[str, Any]:
        self._require_connected()
        result = {
            "built": not bool(plan.get("dry_run")),
            "dry_run": bool(plan.get("dry_run")),
            "recipe": plan["recipe"],
            "name": plan["name"],
            "objects": [item["name"] for item in plan["objects"]],
            "object_count": len(plan["objects"]),
            "operations": list(plan.get("operations", [])),
            "ports": list(plan.get("ports", [])) if plan.get("assign_ports", True) else [],
            "setup": self.configure_analysis(plan["setup"]),
            "plan": plan,
        }
        self._model_history.append(result)
        return result

    def validate_design(self, expected_ports: int | None = None) -> dict[str, Any]:
        self._require_connected()
        return {
            "valid": True,
            "messages": [],
            "expected_ports": expected_ports,
            "backend": "simulated",
        }

    def export_results(self, output_dir: str | Path) -> list[str]:
        self._require_connected()
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        touchstone = output / "simulated_results.s2p"
        write_s2p(touchstone, self._synthetic_network(), comment="simulated AEDT results")
        return [str(touchstone)]

    def stop_analysis(self, clean_stop: bool = True) -> bool:
        del clean_stop
        self._require_connected()
        return True

    def release(
        self,
        *,
        close_projects: bool = False,
        close_desktop: bool = False,
    ) -> bool:
        del close_projects, close_desktop
        self._state = AdapterState(False, "simulated", "SIM::AEDT")
        return True

    def _synthetic_network(self) -> list[NetworkPoint]:
        points: list[NetworkPoint] = []
        start_hz = 600_000_000.0
        stop_hz = 1_100_000_000.0
        total = 101
        scale = _as_float(self._variables.get("arm_scale_a"), 1.0)
        center = 880_000_000.0 / max(scale, 0.1)
        for index in range(total):
            freq = start_hz + (stop_hz - start_hz) * index / (total - 1)
            offset = (freq - center) / 95_000_000.0
            mag = min(0.95, 0.08 + 0.75 * abs(math.tanh(offset)))
            phase = offset * 0.9
            s11 = complex(mag * math.cos(phase), mag * math.sin(phase))
            s21 = complex(0.15 * math.cos(phase / 2), 0.15 * math.sin(phase / 2))
            points.append(NetworkPoint(freq_hz=freq, s11=s11, s21=s21))
        return points

    def _require_connected(self) -> None:
        if not self._state.connected:
            raise RuntimeError("AEDT adapter is not connected")


def _as_float(value: object, default: float) -> float:
    try:
        text = str(value).strip().lower()
        for suffix in ("mm", "ghz", "mhz", "hz"):
            if text.endswith(suffix):
                text = text[: -len(suffix)]
                break
        return float(text)
    except (TypeError, ValueError):
        return default
