from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from hfss_vna_bridge.core.models import AdapterState, NetworkPoint, SweepConfig


class VnaAdapter(Protocol):
    @property
    def state(self) -> AdapterState:
        raise NotImplementedError

    @property
    def sweep_config(self) -> SweepConfig:
        raise NotImplementedError

    def connect(self) -> AdapterState:
        raise NotImplementedError

    def reset(self) -> AdapterState:
        raise NotImplementedError

    def configure_sweep(self, config: SweepConfig) -> SweepConfig:
        raise NotImplementedError

    def single_sweep(self) -> list[NetworkPoint]:
        raise NotImplementedError

    def save_touchstone(self, path: str | Path) -> Path:
        raise NotImplementedError

    def close(self) -> AdapterState:
        raise NotImplementedError

    def capabilities(self) -> dict[str, Any]:
        raise NotImplementedError

    def query_errors(self) -> list[str]:
        raise NotImplementedError

    def clear_errors(self) -> list[str]:
        raise NotImplementedError

    def set_sweep_type(self, sweep_type: str) -> str:
        raise NotImplementedError

    def set_continuous(self, enabled: bool) -> bool:
        raise NotImplementedError

    def sweep_time(self) -> float:
        raise NotImplementedError

    def configure_marker(self, marker: int, frequency_hz: float) -> dict[str, Any]:
        raise NotImplementedError

    def marker_value(self, marker: int) -> dict[str, float]:
        raise NotImplementedError

    def autoscale(self, trace: int = 1) -> bool:
        raise NotImplementedError
