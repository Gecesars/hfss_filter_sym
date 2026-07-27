from __future__ import annotations

from pathlib import Path
from typing import Any

from hfss_vna_bridge.core.models import AdapterState, NetworkPoint, SweepConfig
from hfss_vna_bridge.core.touchstone import write_s2p


class PyVisaVnaAdapter:
    """Generic SCPI VNA adapter.

    The command set is intentionally conservative. Vendor-specific adapters can
    subclass this class and override only the SCPI command map when needed.
    """

    def __init__(self, resource: str, *, timeout_ms: int = 30_000) -> None:
        self._resource_name = resource
        self._timeout_ms = timeout_ms
        self._state = AdapterState(False, "pyvisa", resource)
        self._config = SweepConfig()
        self._rm: Any = None
        self._instrument: Any = None
        self._last_sweep: list[NetworkPoint] = []

    @property
    def state(self) -> AdapterState:
        return self._state

    @property
    def sweep_config(self) -> SweepConfig:
        return self._config

    def connect(self) -> AdapterState:
        try:
            import pyvisa
        except Exception as exc:
            raise RuntimeError("PyVISA is not available. Install with: pip install '.[vna]'") from exc

        self._rm = pyvisa.ResourceManager()
        self._instrument = self._rm.open_resource(self._resource_name)
        self._instrument.timeout = self._timeout_ms
        idn = self._query("*IDN?").strip()
        self._state = AdapterState(True, "pyvisa", self._resource_name, idn)
        return self._state

    def reset(self) -> AdapterState:
        self._require_instrument()
        self._write("*RST")
        self._write("*CLS")
        self._config = SweepConfig()
        self._last_sweep = []
        self._state = AdapterState(True, "pyvisa", self._resource_name, "reset")
        return self._state

    def configure_sweep(self, config: SweepConfig) -> SweepConfig:
        self._require_instrument()
        config.validate()
        self._write(f"SENS1:FREQ:STAR {config.start_hz}")
        self._write(f"SENS1:FREQ:STOP {config.stop_hz}")
        self._write(f"SENS1:SWE:POIN {config.points}")
        self._write(f"SENS1:BAND {config.ifbw_hz}")
        self._write(f"SOUR1:POW {config.power_dbm}")
        self._config = config
        return self._config

    def single_sweep(self) -> list[NetworkPoint]:
        self._require_instrument()
        self._write("FORM:DATA ASCII")
        self._write("INIT1:IMM;*WAI")
        response = self._query("CALC1:DATA? SDATA")
        points = self._parse_sdata(response)
        self._last_sweep = points
        return points

    def save_touchstone(self, path: str | Path) -> Path:
        self._require_instrument()
        points = self._last_sweep or self.single_sweep()
        return write_s2p(path, points, comment=f"pyvisa resource={self._resource_name}")

    def _parse_sdata(self, response: str) -> list[NetworkPoint]:
        values = [float(part) for part in response.replace("\n", ",").split(",") if part.strip()]
        if len(values) % 2:
            raise RuntimeError("VNA returned an odd number of SDATA values")
        complex_values = [complex(values[i], values[i + 1]) for i in range(0, len(values), 2)]
        config = self._config
        if len(complex_values) != config.points:
            config = SweepConfig(
                start_hz=config.start_hz,
                stop_hz=config.stop_hz,
                points=len(complex_values),
                ifbw_hz=config.ifbw_hz,
                power_dbm=config.power_dbm,
            )
        points: list[NetworkPoint] = []
        for index, s11 in enumerate(complex_values):
            if config.points == 1:
                freq = config.start_hz
            else:
                freq = config.start_hz + (config.stop_hz - config.start_hz) * index / (config.points - 1)
            points.append(NetworkPoint(freq_hz=freq, s11=s11, s21=0j))
        return points

    def _write(self, command: str) -> None:
        instrument = self._require_instrument()
        instrument.write(command)

    def _query(self, command: str) -> str:
        instrument = self._require_instrument()
        return str(instrument.query(command))

    def _require_instrument(self) -> Any:
        if self._instrument is None:
            raise RuntimeError("VNA adapter is not connected")
        return self._instrument

