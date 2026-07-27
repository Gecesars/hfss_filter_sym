from __future__ import annotations

from pathlib import Path
from typing import Protocol

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

