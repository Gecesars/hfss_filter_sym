from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from hfss_vna_bridge.core.models import AdapterState


class AedtAdapter(Protocol):
    @property
    def state(self) -> AdapterState:
        raise NotImplementedError

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
        raise NotImplementedError

    def list_designs(self) -> list[str]:
        raise NotImplementedError

    def set_active_design(self, design_name: str) -> AdapterState:
        raise NotImplementedError

    def get_variables(self) -> dict[str, str]:
        raise NotImplementedError

    def set_variables(self, variables: dict[str, str | float | int]) -> dict[str, str]:
        raise NotImplementedError

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
        raise NotImplementedError

    def session_info(self) -> dict[str, Any]:
        raise NotImplementedError

    def save_project(
        self,
        file_name: str | Path | None = None,
        *,
        overwrite: bool = True,
    ) -> str:
        raise NotImplementedError

    def create_sparameter_report(
        self,
        expressions: list[str] | None = None,
        *,
        setup_name: str | None = None,
        sweep_name: str | None = None,
        plot_name: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def export_convergence(
        self,
        setup_name: str | None = None,
        output_file: str | Path | None = None,
    ) -> str:
        raise NotImplementedError

    def remove_solution_data(
        self,
        *,
        entire_solution: bool = False,
        field: bool = False,
        mesh: bool = True,
        linked_data: bool = False,
    ) -> bool:
        raise NotImplementedError

    def configure_analysis(self, config: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def build_model(self, plan: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def validate_design(self, expected_ports: int | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def export_results(self, output_dir: str | Path) -> list[str]:
        raise NotImplementedError

    def stop_analysis(self, clean_stop: bool = True) -> bool:
        raise NotImplementedError

    def release(
        self,
        *,
        close_projects: bool = False,
        close_desktop: bool = False,
    ) -> bool:
        raise NotImplementedError
