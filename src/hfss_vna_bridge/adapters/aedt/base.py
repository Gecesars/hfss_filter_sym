from __future__ import annotations

from pathlib import Path
from typing import Protocol

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
        new_desktop: bool = False,
        non_graphical: bool = False,
    ) -> AdapterState:
        raise NotImplementedError

    def list_designs(self) -> list[str]:
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
    ) -> dict[str, str | None]:
        raise NotImplementedError

