from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from hfss_vna_bridge.adapters.aedt.installations import (
    detect_aedt_installations,
    detect_running_aedt_sessions,
)
from hfss_vna_bridge.core.models import AdapterState


class PyAedtAdapter:
    """HFSS adapter for AEDT 2026 through the supported PyAEDT API."""

    def __init__(self) -> None:
        self._state = AdapterState(False, "pyaedt")
        self._hfss: Any = None
        self._project_path: Path | None = None
        self._design_name: str | None = None
        self._version: str | None = None
        self._owns_desktop = False

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
        try:
            from ansys.aedt.core import Hfss
        except Exception as exc:
            raise RuntimeError(
                "PyAEDT is not available. Install with: uv sync --extra aedt"
            ) from exc

        self._project_path = _validated_project_path(project_path)
        self._design_name = design_name
        self._version = version or _latest_installed_version()
        self._owns_desktop = new_desktop
        previous_processes = {
            int(session["process_id"])
            for session in detect_running_aedt_sessions()
        }
        connect_started_at = time.time()
        grpc_port = int(port or 0)
        kwargs: dict[str, Any] = {
            "project": str(self._project_path) if self._project_path else None,
            "design": design_name,
            "version": self._version,
            "non_graphical": non_graphical,
            "new_desktop": new_desktop,
            "close_on_exit": close_on_exit,
            "student_version": student_version,
            "machine": machine or ("localhost" if grpc_port else ""),
            "port": grpc_port,
            "aedt_process_id": None if grpc_port else aedt_process_id,
            "remove_lock": remove_lock,
        }
        try:
            self._hfss = Hfss(**kwargs)
        except Exception:
            if new_desktop:
                _close_new_desktops(
                    self._version,
                    previous_processes,
                    created_after=connect_started_at,
                )
            raise
        if not getattr(self._hfss, "valid_design", True):
            self.release(close_projects=False, close_desktop=self._owns_desktop)
            raise RuntimeError("AEDT opened, but the selected HFSS design is not valid")

        self._design_name = getattr(self._hfss, "design_name", design_name)
        actual_project = _project_file(self._hfss) or self._project_path
        if actual_project:
            self._project_path = Path(actual_project)
        info = self.session_info()
        detail = (
            f"{info.get('version')} | PID {info.get('process_id')} | "
            f"{self._design_name or 'no design'}"
        )
        self._state = AdapterState(
            True,
            "pyaedt",
            str(self._project_path) if self._project_path else info.get("project_name"),
            detail,
        )
        return self._state

    def list_designs(self) -> list[str]:
        hfss = self._require_hfss()
        desktop = getattr(hfss, "desktop_class", None)
        if desktop is not None:
            try:
                values = desktop.design_list(getattr(hfss, "project_name", None))
                if values:
                    return [_clean_design_name(value) for value in values]
            except (AttributeError, RuntimeError, TypeError):
                pass
        for attr in ("design_list", "design_names"):
            value = getattr(hfss, attr, None)
            if value:
                return [_clean_design_name(item) for item in value]
        project = getattr(hfss, "oproject", None)
        if project is not None and hasattr(project, "GetTopDesignList"):
            return [_clean_design_name(item) for item in project.GetTopDesignList()]
        current = getattr(hfss, "design_name", None)
        return [current] if current else []

    def set_active_design(self, design_name: str) -> AdapterState:
        hfss = self._require_hfss()
        designs = self.list_designs()
        if design_name not in designs:
            raise ValueError(f"HFSS design {design_name!r} not found. Available: {designs}")
        result = hfss.set_active_design(design_name)
        if result is False:
            raise RuntimeError(f"AEDT failed to activate design {design_name!r}")
        self._design_name = getattr(hfss, "design_name", design_name)
        info = self.session_info()
        self._state = AdapterState(
            True,
            "pyaedt",
            self._state.resource,
            f"{info.get('version')} | PID {info.get('process_id')} | {self._design_name}",
        )
        return self._state

    def get_variables(self) -> dict[str, str]:
        hfss = self._require_hfss()
        variables: dict[str, str] = {}
        manager = getattr(hfss, "variable_manager", None)
        if manager is not None:
            for attr in ("variables", "design_variables", "project_variables"):
                data = getattr(manager, attr, None)
                if isinstance(data, dict):
                    for name, value in data.items():
                        variables[str(name)] = _value_to_text(value)
        if not variables:
            for attr in ("variable_names", "design_variable_names"):
                names = getattr(hfss, attr, None)
                if names:
                    for name in names:
                        try:
                            variables[str(name)] = str(hfss[name])
                        except (AttributeError, KeyError, RuntimeError, TypeError):
                            variables[str(name)] = ""
        return variables

    def set_variables(self, variables: dict[str, str | float | int]) -> dict[str, str]:
        hfss = self._require_hfss()
        for name, value in variables.items():
            hfss[str(name)] = str(value)
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
        hfss = self._require_hfss()
        setups = list(hfss.get_setups())
        selected_setup = setup_name or (setups[0] if setups else None)
        if setup_name and setup_name not in setups:
            raise ValueError(f"HFSS setup {setup_name!r} not found. Available: {setups}")
        if selected_setup:
            solved = hfss.analyze_setup(
                selected_setup,
                cores=cores,
                tasks=tasks,
                gpus=gpus,
                blocking=blocking,
                revert_to_initial_mesh=revert_to_initial_mesh,
            )
        else:
            solved = hfss.analyze(
                setup=None,
                cores=cores,
                tasks=tasks,
                gpus=gpus,
                blocking=blocking,
            )
        if solved is False:
            raise RuntimeError("AEDT reported that the HFSS analysis failed")

        sweeps = list(hfss.get_sweeps(selected_setup)) if selected_setup else []
        selected_sweep = sweep_name or (sweeps[0] if sweeps else None)
        if sweep_name and sweep_name not in sweeps:
            raise ValueError(
                f"HFSS sweep {sweep_name!r} not found in {selected_setup!r}. Available: {sweeps}"
            )

        exported: str | None = None
        if output_touchstone:
            output = Path(output_touchstone).expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            exported = _export_touchstone(
                hfss,
                selected_setup,
                selected_sweep,
                output,
            )

        return {
            "project": str(self._project_path) if self._project_path else _project_file(hfss),
            "design": getattr(hfss, "design_name", self._design_name),
            "setup": selected_setup,
            "sweep": selected_sweep,
            "touchstone": exported,
            "solved": bool(solved),
            "blocking": blocking,
            "session": self.session_info(),
        }

    def session_info(self) -> dict[str, Any]:
        hfss = self._require_hfss()
        desktop = getattr(hfss, "desktop_class", None)
        setups = list(hfss.get_setups())
        sweeps = {
            setup: list(hfss.get_sweeps(setup))
            for setup in setups
        }
        return {
            "connected": True,
            "version": getattr(desktop, "aedt_version_id", self._version),
            "version_full": getattr(desktop, "aedt_version", None),
            "process_id": getattr(desktop, "aedt_process_id", None),
            "grpc_port": getattr(desktop, "port", None),
            "grpc": getattr(desktop, "is_grpc_api", None),
            "install_dir": getattr(desktop, "aedt_install_dir", None),
            "project_name": getattr(hfss, "project_name", None),
            "project_file": _project_file(hfss),
            "design_name": getattr(hfss, "design_name", self._design_name),
            "design_type": getattr(hfss, "design_type", None),
            "solution_type": str(getattr(hfss, "solution_type", "")),
            "setups": setups,
            "sweeps": sweeps,
            "owns_desktop": self._owns_desktop,
        }

    def save_project(
        self,
        file_name: str | Path | None = None,
        *,
        overwrite: bool = True,
    ) -> str:
        hfss = self._require_hfss()
        output = Path(file_name).expanduser().resolve() if file_name else None
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
        saved = hfss.save_project(file_name=output, overwrite=overwrite)
        if saved is False:
            raise RuntimeError("AEDT failed to save the project")
        actual = output or Path(_project_file(hfss) or "")
        if not actual:
            raise RuntimeError("AEDT saved the project but did not expose its path")
        self._project_path = actual
        self._state = AdapterState(
            True,
            "pyaedt",
            str(actual),
            self._state.detail,
        )
        return str(actual)

    def create_sparameter_report(
        self,
        expressions: list[str] | None = None,
        *,
        setup_name: str | None = None,
        sweep_name: str | None = None,
        plot_name: str | None = None,
    ) -> dict[str, Any]:
        hfss = self._require_hfss()
        traces = expressions or list(hfss.get_traces_for_plot())
        if not traces:
            traces = ["dB(S(1,1))", "dB(S(2,1))"]
        setup_sweep = _setup_sweep(hfss, setup_name, sweep_name)
        report = hfss.post.create_report(
            expressions=traces,
            setup_sweep_name=setup_sweep,
            domain="Sweep",
            primary_sweep_variable="Freq",
            plot_name=plot_name,
        )
        if report is False:
            raise RuntimeError("AEDT failed to create the S-parameter report")
        return {
            "plot_name": getattr(report, "plot_name", plot_name),
            "setup_sweep": setup_sweep,
            "expressions": traces,
        }

    def export_convergence(
        self,
        setup_name: str | None = None,
        output_file: str | Path | None = None,
    ) -> str:
        hfss = self._require_hfss()
        setups = list(hfss.get_setups())
        selected_setup = setup_name or (setups[0] if setups else None)
        if not selected_setup:
            raise RuntimeError("The active HFSS design has no setup")
        output = Path(output_file).expanduser().resolve() if output_file else None
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
        exported = hfss.export_convergence(
            setup=selected_setup,
            output_file=str(output) if output else None,
        )
        if not exported:
            raise RuntimeError("AEDT failed to export convergence data")
        return str(Path(exported).resolve())

    def remove_solution_data(
        self,
        *,
        entire_solution: bool = False,
        field: bool = False,
        mesh: bool = True,
        linked_data: bool = False,
    ) -> bool:
        hfss = self._require_hfss()
        removed = hfss.cleanup_solution(
            variations="All",
            entire_solution=entire_solution,
            field=field,
            mesh=mesh,
            linked_data=linked_data,
        )
        if removed is False:
            raise RuntimeError("AEDT failed to remove the selected solution data")
        return True

    def release(
        self,
        *,
        close_projects: bool = False,
        close_desktop: bool = False,
    ) -> bool:
        if self._hfss is None:
            return True
        hfss = self._hfss
        try:
            released = bool(
                hfss.release_desktop(
                    close_projects=close_projects,
                    close_desktop=close_desktop,
                )
            )
        finally:
            self._hfss = None
            self._state = AdapterState(False, "pyaedt")
        return released

    def _require_hfss(self) -> Any:
        if self._hfss is None:
            raise RuntimeError("AEDT adapter is not connected")
        return self._hfss


def _validated_project_path(project_path: str | Path | None) -> Path | None:
    if project_path is None or str(project_path).strip() == "":
        return None
    path = Path(project_path).expanduser().resolve()
    if path.suffix.lower() in {".aedt", ".aedtz"} and not path.is_file():
        raise FileNotFoundError(f"AEDT project not found: {path}")
    return path


def _latest_installed_version() -> str:
    installations = detect_aedt_installations()
    if not installations:
        raise RuntimeError("No AEDT installation was detected")
    return installations[0].version


def _project_file(hfss: Any) -> str | None:
    value = getattr(hfss, "project_file", None)
    if value:
        return str(value)
    project_path = getattr(hfss, "project_path", None)
    project_name = getattr(hfss, "project_name", None)
    if project_path and project_name:
        return str(Path(project_path) / f"{project_name}.aedt")
    return None


def _clean_design_name(value: Any) -> str:
    text = str(value)
    return text.split(";")[-1]


def _value_to_text(value: Any) -> str:
    expression = getattr(value, "expression", None)
    if expression is not None:
        return str(expression)
    value_attr = getattr(value, "value", None)
    if value_attr is not None:
        return str(value_attr)
    return str(value)


def _export_touchstone(
    hfss: Any,
    setup: str | None,
    sweep: str | None,
    output: Path,
) -> str:
    exported = hfss.export_touchstone(
        setup=setup,
        sweep=sweep,
        output_file=str(output),
    )
    if exported is False:
        raise RuntimeError("AEDT failed to export the Touchstone file")
    path = Path(exported) if isinstance(exported, str) else output
    if not path.is_file():
        raise RuntimeError(f"AEDT reported export success, but the file was not created: {path}")
    return str(path.resolve())


def _close_new_desktops(
    version: str,
    previous_processes: set[int],
    *,
    created_after: float,
) -> None:
    try:
        from ansys.aedt.core import Desktop
    except ImportError:
        return
    current = detect_running_aedt_sessions()
    for session in current:
        process_id = int(session["process_id"])
        if (
            process_id in previous_processes
            or session.get("version") != version
            or float(session.get("created_at") or 0) < created_after - 2.0
        ):
            continue
        try:
            desktop = Desktop(
                version=version,
                new_desktop=False,
                non_graphical=bool(session.get("non_graphical")),
                aedt_process_id=process_id,
                close_on_exit=False,
            )
            desktop.close_desktop()
        except (RuntimeError, TypeError, ValueError):
            continue


def _setup_sweep(
    hfss: Any,
    setup_name: str | None,
    sweep_name: str | None,
) -> str:
    setups = list(hfss.get_setups())
    selected_setup = setup_name or (setups[0] if setups else None)
    if not selected_setup:
        raise RuntimeError("The active HFSS design has no setup")
    sweeps = list(hfss.get_sweeps(selected_setup))
    selected_sweep = sweep_name or (sweeps[0] if sweeps else "LastAdaptive")
    return f"{selected_setup} : {selected_sweep}"
