from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from hfss_vna_bridge.core.models import AdapterState, NetworkPoint, SweepConfig
from hfss_vna_bridge.core.touchstone import write_s2p


class SimulatedVnaAdapter:
    """Deterministic VNA used for integration tests and UI development."""

    def __init__(self, resource: str = "SIM::VNA") -> None:
        self._resource = resource
        self._state = AdapterState(False, "simulated", resource)
        self._config = SweepConfig()
        self._last_sweep: list[NetworkPoint] = []
        self._sweep_type = "LIN"
        self._continuous = False
        self._markers: dict[int, float] = {}
        self._traces: dict[int, dict[str, Any]] = {}
        self._averaging = {"enabled": False, "count": 1}
        self._correction = False
        self._trigger_source = "IMM"
        self._rf_output = False
        self._calibration: dict[str, Any] | None = None

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
        self._sweep_type = "LIN"
        self._continuous = False
        self._markers.clear()
        self._traces.clear()
        self._averaging = {"enabled": False, "count": 1}
        self._correction = False
        self._trigger_source = "IMM"
        self._rf_output = False
        self._calibration = None
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
            s12 = s21 * complex(0.998, 0.002)
            s22 = s11 * complex(0.98, -0.01)
            points.append(NetworkPoint(freq_hz=freq, s11=s11, s21=s21, s12=s12, s22=s22))
        self._last_sweep = points
        return points

    def save_touchstone(self, path: str | Path) -> Path:
        self._require_connected()
        if not self._last_sweep:
            self.single_sweep()
        return write_s2p(path, self._last_sweep, comment="simulated VNA sweep")

    def close(self) -> AdapterState:
        self._state = AdapterState(False, "simulated", self._resource)
        return self._state

    def capabilities(self) -> dict[str, Any]:
        return {
            "identity": "HFSS Filter Studio,Simulated VNA,0,1.0",
            "profile": "SIMULATED",
            "parameters": ["S11", "S21", "S12", "S22"],
            "sweep_types": ["LIN", "LOG"],
            "markers": True,
            "continuous": True,
        }

    def query_errors(self) -> list[str]:
        return []

    def clear_errors(self) -> list[str]:
        return []

    def set_sweep_type(self, sweep_type: str) -> str:
        value = sweep_type.strip().upper()
        if value not in {"LIN", "LOG"}:
            raise ValueError("Simulated VNA supports LIN and LOG sweep types")
        self._sweep_type = value
        return value

    def set_continuous(self, enabled: bool) -> bool:
        self._continuous = bool(enabled)
        return self._continuous

    def sweep_time(self) -> float:
        return max(0.05, self._config.points / self._config.ifbw_hz * 0.025)

    def configure_marker(self, marker: int, frequency_hz: float) -> dict[str, Any]:
        self._require_connected()
        self._markers[int(marker)] = float(frequency_hz)
        return self.marker_value(marker)

    def marker_value(self, marker: int) -> dict[str, float]:
        self._require_connected()
        marker_id = int(marker)
        if marker_id not in self._markers:
            raise ValueError(f"Marker {marker_id} is not configured")
        if not self._last_sweep:
            self.single_sweep()
        frequency = self._markers[marker_id]
        nearest = min(self._last_sweep, key=lambda point: abs(point.freq_hz - frequency))
        return {
            "marker": marker_id,
            "freq_hz": nearest.freq_hz,
            "real": nearest.s11.real,
            "imag": nearest.s11.imag,
            "magnitude_db": 20.0 * math.log10(max(abs(nearest.s11), 1e-15)),
        }

    def autoscale(self, trace: int = 1) -> bool:
        del trace
        self._require_connected()
        return True

    def define_trace(
        self,
        parameter: str,
        *,
        trace: int = 1,
        window: int = 1,
    ) -> dict[str, Any]:
        self._require_connected()
        value = parameter.strip().upper()
        if value not in {"S11", "S21", "S12", "S22"}:
            raise ValueError("parameter must be S11, S21, S12, or S22")
        self._traces[int(trace)] = {
            "parameter": value,
            "trace": int(trace),
            "window": int(window),
            "visible": True,
        }
        return dict(self._traces[int(trace)])

    def set_trace_visible(
        self,
        enabled: bool,
        *,
        trace: int = 1,
        window: int = 1,
    ) -> bool:
        self._require_connected()
        item = self._traces.setdefault(
            int(trace),
            {"parameter": "S11", "trace": int(trace), "window": int(window)},
        )
        item["visible"] = bool(enabled)
        return bool(enabled)

    def set_averaging(self, enabled: bool, count: int = 1) -> dict[str, Any]:
        self._require_connected()
        if not 1 <= int(count) <= 65_536:
            raise ValueError("averaging count must be between 1 and 65536")
        self._averaging = {"enabled": bool(enabled), "count": int(count)}
        return dict(self._averaging)

    def set_correction(self, enabled: bool) -> bool:
        self._require_connected()
        self._correction = bool(enabled)
        return self._correction

    def set_trigger_source(self, source: str) -> str:
        self._require_connected()
        value = source.strip().upper()
        if value not in {"IMM", "INT", "EXT", "BUS", "MAN"}:
            raise ValueError("Unsupported trigger source")
        self._trigger_source = value
        return value

    def set_rf_output(self, enabled: bool) -> bool:
        self._require_connected()
        self._rf_output = bool(enabled)
        return self._rf_output

    def calibration_begin(
        self,
        calibration_type: str,
        ports: list[int],
    ) -> dict[str, Any]:
        self._require_connected()
        value = calibration_type.strip().upper()
        if value not in {"SOLT1", "SOLT2", "THRU", "OPEN", "SHORT"}:
            raise ValueError("Unsupported calibration type")
        self._calibration = {
            "type": value,
            "ports": [int(port) for port in ports],
            "standards": [],
            "state": "collecting",
        }
        return dict(self._calibration)

    def calibration_acquire(
        self,
        standard: str,
        ports: list[int],
    ) -> dict[str, Any]:
        self._require_connected()
        if not self._calibration or self._calibration["state"] != "collecting":
            raise RuntimeError("No calibration collection is active")
        item = {"standard": standard.strip().upper(), "ports": [int(port) for port in ports]}
        self._calibration["standards"].append(item)
        return {**self._calibration, "last_acquisition": item}

    def calibration_save(self) -> dict[str, Any]:
        self._require_connected()
        if not self._calibration:
            raise RuntimeError("No calibration collection is active")
        self._calibration["state"] = "saved"
        self._correction = True
        return dict(self._calibration)

    def calibration_abort(self) -> dict[str, Any]:
        self._require_connected()
        result = dict(self._calibration or {"state": "idle"})
        result["state"] = "aborted"
        self._calibration = None
        return result

    def save_state(self, path: str) -> bool:
        self._require_connected()
        return bool(path.strip())

    def _require_connected(self) -> None:
        if not self._state.connected:
            raise RuntimeError("VNA adapter is not connected")
