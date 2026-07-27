from __future__ import annotations

import math
from pathlib import Path

from hfss_vna_bridge.core.models import AdapterState, NetworkPoint, SweepConfig
from hfss_vna_bridge.core.touchstone import write_s2p


class SimulatedVnaAdapter:
    """Deterministic VNA used for integration tests and UI development."""

    def __init__(self, resource: str = "SIM::VNA") -> None:
        self._resource = resource
        self._state = AdapterState(False, "simulated", resource)
        self._config = SweepConfig()
        self._last_sweep: list[NetworkPoint] = []

    @property
    def state(self) -> AdapterState:
        return self._state

    @property
    def sweep_config(self) -> SweepConfig:
        return self._config

    def connect(self) -> AdapterState:
        self._state = AdapterState(True, "simulated", self._resource, "ready")
        return self._state

    def reset(self) -> AdapterState:
        self._config = SweepConfig()
        self._last_sweep = []
        self._state = AdapterState(True, "simulated", self._resource, "reset")
        return self._state

    def configure_sweep(self, config: SweepConfig) -> SweepConfig:
        self._require_connected()
        config.validate()
        self._config = config
        return self._config

    def single_sweep(self) -> list[NetworkPoint]:
        self._require_connected()
        config = self._config
        center = (config.start_hz + config.stop_hz) / 2
        bandwidth = max((config.stop_hz - config.start_hz) / 7, 1.0)
        points: list[NetworkPoint] = []
        for index in range(config.points):
            freq = config.start_hz + (config.stop_hz - config.start_hz) * index / (config.points - 1)
            detune = (freq - center) / bandwidth
            notch_mag = 0.05 + 0.7 * (abs(detune) / (1 + abs(detune)))
            ripple = 0.015 * math.sin(index * 0.37)
            mag = max(0.01, min(0.95, notch_mag + ripple))
            phase = math.atan(detune)
            s11 = complex(mag * math.cos(phase), mag * math.sin(phase))
            through_mag = max(0.01, 0.85 - mag * 0.35)
            s21 = complex(through_mag * math.cos(-phase / 3), through_mag * math.sin(-phase / 3))
            points.append(NetworkPoint(freq_hz=freq, s11=s11, s21=s21))
        self._last_sweep = points
        return points

    def save_touchstone(self, path: str | Path) -> Path:
        self._require_connected()
        if not self._last_sweep:
            self.single_sweep()
        return write_s2p(path, self._last_sweep, comment="simulated VNA sweep")

    def _require_connected(self) -> None:
        if not self._state.connected:
            raise RuntimeError("VNA adapter is not connected")

