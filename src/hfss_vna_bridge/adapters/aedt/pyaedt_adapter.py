from __future__ import annotations

from pathlib import Path
from typing import Any

from hfss_vna_bridge.core.models import AdapterState


class PyAedtAdapter:
    """AEDT/HFSS adapter implemented with PyAEDT.

    Imports are intentionally lazy so the application can run in simulator mode
    on machines without AEDT installed.
    """

    def __init__(self) -> None:
        self._state = AdapterState(False, "pyaedt")
        self._hfss: Any = None
        self._project_path: Path | None = None
        self._design_name: str | None = None

    @property
    def state(self) -> AdapterState:
        return self._state

    def connect(
        self,
        project_path: str | Path | None = None,
        design_name: str | None = None,
        *,
        new_desktop: bool = False,
        non_graphical: bool = False,
    ) -> AdapterState:
        try:
            from ansys.aedt.core import Hfss
        except Exception as exc:
            raise RuntimeError(
                "PyAEDT is not available. Install with: pip install '.[aedt]'"
            ) from exc

        self._project_path = Path(project_path) if project_path else None
        self._design_name = design_name
        kwargs: dict[str, Any] = {
            "design": design_name,
            "non_graphical": non_graphical,
            "new_desktop": new_desktop,
            "close_on_exit": False,
        }
        if self._project_path:
            kwargs["project"] = str(self._project_path)

        self._hfss = Hfss(**{key: value for key, value in kwargs.items() if value is not None})
        self._design_name = getattr(self._hfss, "design_name", design_name)
        resource = str(self._project_path) if self._project_path else getattr(self._hfss, "project_name", None)
        self._state = AdapterState(True, "pyaedt", resource, self._design_name)
        return self._state

    def list_designs(self) -> list[str]:
        hfss = self._require_hfss()
        for attr in ("design_list", "design_names"):
            value = getattr(hfss, attr, None)
            if value:
                return list(value)
        project = getattr(hfss, "oproject", None)
        if project is not None and hasattr(project, "GetTopDesignList"):
            return list(project.GetTopDesignList())
        current = getattr(hfss, "design_name", None)
        return [current] if current else []

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
    ) -> dict[str, str | None]:
        hfss = self._require_hfss()
        if setup_name:
            hfss.analyze_setup(setup_name)
        else:
            analyze = getattr(hfss, "analyze", None)
            if analyze is None:
                raise RuntimeError("AEDT object does not expose analyze/analyze_setup")
            analyze()

        exported: str | None = None
        if output_touchstone:
            exported = str(output_touchstone)
            _export_touchstone(hfss, setup_name, sweep_name, exported)

        return {
            "project": str(self._project_path) if self._project_path else getattr(hfss, "project_name", None),
            "design": getattr(hfss, "design_name", self._design_name),
            "setup": setup_name,
            "sweep": sweep_name,
            "touchstone": exported,
        }

    def _require_hfss(self) -> Any:
        if self._hfss is None:
            raise RuntimeError("AEDT adapter is not connected")
        return self._hfss


def _value_to_text(value: Any) -> str:
    expression = getattr(value, "expression", None)
    if expression is not None:
        return str(expression)
    value_attr = getattr(value, "value", None)
    if value_attr is not None:
        return str(value_attr)
    return str(value)


def _export_touchstone(hfss: Any, setup: str | None, sweep: str | None, path: str) -> None:
    export = getattr(hfss, "export_touchstone", None)
    if export is None:
        raise RuntimeError("AEDT object does not expose export_touchstone")

    attempts = [
        {"setup": setup, "sweep": sweep, "file_name": path},
        {"solution_name": setup, "sweep_name": sweep, "file_name": path},
        {"file_name": path},
    ]
    last_error: Exception | None = None
    for kwargs in attempts:
        clean = {key: value for key, value in kwargs.items() if value is not None}
        try:
            export(**clean)
            return
        except TypeError as exc:
            last_error = exc
    if last_error:
        raise last_error
