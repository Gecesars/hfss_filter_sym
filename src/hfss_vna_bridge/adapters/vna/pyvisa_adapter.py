from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from hfss_vna_bridge.adapters.vna.profiles import PROFILES, ScpiProfile, select_profile
from hfss_vna_bridge.core.models import AdapterState, NetworkPoint, SweepConfig
from hfss_vna_bridge.core.touchstone import write_s2p


class PyVisaVnaAdapter:
    """Two-port VNA adapter with vendor profiles and corrected complex acquisition."""

    PARAMETERS = ("S11", "S21", "S12", "S22")

    def __init__(
        self,
        resource: str,
        *,
        timeout_ms: int = 30_000,
        brand: str | None = None,
        visa_library: str | None = None,
        channel: int = 1,
    ) -> None:
        self._resource_name = resource
        self._timeout_ms = timeout_ms
        self._requested_brand = brand
        self._visa_library = visa_library
        self._channel = int(channel)
        self._state = AdapterState(False, "pyvisa", resource)
        self._config = SweepConfig()
        self._rm: Any = None
        self._instrument: Any = None
        self._last_sweep: list[NetworkPoint] = []
        self._identity = ""
        self._profile: ScpiProfile = PROFILES["GENERIC"]
        self._sweep_type = "LIN"
        self._continuous = False
        self._measurement_names: dict[str, str] = {}

    @property
    def state(self) -> AdapterState:
        return self._state

    @property
    def sweep_config(self) -> SweepConfig:
        return self._config

    @classmethod
    def discover(cls, visa_library: str | None = None) -> dict[str, Any]:
        pyvisa = _load_pyvisa()
        manager = pyvisa.ResourceManager(visa_library) if visa_library else pyvisa.ResourceManager()
        try:
            resources = list(manager.list_resources())
            return {
                "resources": resources,
                "count": len(resources),
                "visa_library": str(getattr(manager, "visalib", "")),
            }
        finally:
            manager.close()

    def connect(self) -> AdapterState:
        pyvisa = _load_pyvisa()
        self._rm = (
            pyvisa.ResourceManager(self._visa_library)
            if self._visa_library
            else pyvisa.ResourceManager()
        )
        try:
            self._instrument = self._rm.open_resource(self._resource_name)
            self._instrument.timeout = self._timeout_ms
            self._identity = self._query("*IDN?").strip()
            self._profile = select_profile(self._identity, self._requested_brand)
            self._state = AdapterState(
                True,
                "pyvisa",
                self._resource_name,
                f"{self._profile.display_name} | {self._identity}",
            )
            return self._state
        except Exception:
            self.close()
            raise

    def close(self) -> AdapterState:
        instrument, manager = self._instrument, self._rm
        self._instrument = None
        self._rm = None
        try:
            if instrument is not None:
                instrument.close()
        finally:
            if manager is not None:
                manager.close()
        self._state = AdapterState(False, "pyvisa", self._resource_name)
        return self._state

    def reset(self) -> AdapterState:
        self._require_instrument()
        self._write("*RST")
        self._write("*CLS")
        self._query("*OPC?")
        self._config = SweepConfig()
        self._last_sweep = []
        self._measurement_names.clear()
        self._sweep_type = "LIN"
        self._continuous = False
        self._state = AdapterState(
            True,
            "pyvisa",
            self._resource_name,
            f"{self._profile.display_name} | reset",
        )
        return self._state

    def capabilities(self) -> dict[str, Any]:
        return {
            "identity": self._identity,
            "profile": self._profile.key,
            "profile_name": self._profile.display_name,
            "resource": self._resource_name,
            "channel": self._channel,
            "parameters": list(self.PARAMETERS),
            "sweep_types": ["LIN", "LOG", "SEGM", "POW"],
            "markers": True,
            "continuous": True,
            "binary_transfer": False,
            "corrected_complex_data": True,
        }

    def query_errors(self) -> list[str]:
        self._require_instrument()
        errors: list[str] = []
        for _ in range(32):
            response = self._query("SYST:ERR?").strip()
            normalized = response.lstrip().split(",", 1)[0].strip()
            if normalized in {"0", "+0"} or "NO ERROR" in response.upper():
                break
            errors.append(response)
        return errors

    def clear_errors(self) -> list[str]:
        self._write("*CLS")
        return self.query_errors()

    def configure_sweep(self, config: SweepConfig) -> SweepConfig:
        self._require_instrument()
        config.validate()
        channel = self._channel
        self._write(f"SENS{channel}:FREQ:STAR {config.start_hz}")
        self._write(f"SENS{channel}:FREQ:STOP {config.stop_hz}")
        self._write(f"SENS{channel}:SWE:POIN {config.points}")
        self._write(f"SENS{channel}:BAND {config.ifbw_hz}")
        self._write(f"SOUR{channel}:POW {config.power_dbm}")
        self._config = config
        self._last_sweep = []
        return self._config

    def set_sweep_type(self, sweep_type: str) -> str:
        value = sweep_type.strip().upper()
        if value not in {"LIN", "LOG", "SEGM", "POW"}:
            raise ValueError("sweep_type must be LIN, LOG, SEGM, or POW")
        self._write(f"SENS{self._channel}:SWE:TYPE {value}")
        self._sweep_type = value
        return value

    def set_continuous(self, enabled: bool) -> bool:
        self._write(f"INIT{self._channel}:CONT {'ON' if enabled else 'OFF'}")
        self._continuous = bool(enabled)
        return self._continuous

    def sweep_time(self) -> float:
        self._require_instrument()
        try:
            return float(self._query(f"SENS{self._channel}:SWE:TIME?"))
        except (ValueError, RuntimeError):
            return max(0.05, self._config.points / max(self._config.ifbw_hz, 1.0) * 0.025)

    def single_sweep(self) -> list[NetworkPoint]:
        self._require_instrument()
        for parameter in self.PARAMETERS:
            self._ensure_measurement(parameter)
        previous_continuous = self._continuous
        self.set_continuous(False)
        try:
            self._write("FORM:DATA ASCII")
            self._write(f"INIT{self._channel}:IMM")
            self._query("*OPC?")

            frequencies = self._query_frequencies()
            parameter_data: dict[str, list[complex]] = {}
            for parameter in self.PARAMETERS:
                self._write(
                    self._profile.select(
                        self._measurement_names[parameter],
                        self._channel,
                    )
                )
                values = self._query_ascii_values(self._profile.data(self._channel))
                parameter_data[parameter] = self._parse_complex_values(values, parameter)

            point_count = min(
                len(frequencies),
                *(len(parameter_data[parameter]) for parameter in self.PARAMETERS),
            )
            if point_count < 2:
                raise RuntimeError("VNA returned fewer than two complete two-port points")
            points = [
                NetworkPoint(
                    freq_hz=frequencies[index],
                    s11=parameter_data["S11"][index],
                    s21=parameter_data["S21"][index],
                    s12=parameter_data["S12"][index],
                    s22=parameter_data["S22"][index],
                )
                for index in range(point_count)
            ]
            self._last_sweep = points
        finally:
            if previous_continuous:
                self.set_continuous(True)
        return points

    def save_touchstone(self, path: str | Path) -> Path:
        self._require_instrument()
        points = self._last_sweep or self.single_sweep()
        return write_s2p(
            path,
            points,
            comment=(
                f"resource={self._resource_name}\n"
                f"identity={self._identity}\n"
                f"profile={self._profile.key}"
            ),
        )

    def configure_marker(self, marker: int, frequency_hz: float) -> dict[str, Any]:
        marker_id = int(marker)
        if marker_id < 1:
            raise ValueError("marker must be greater than zero")
        self._write(f"CALC{self._channel}:MARK{marker_id}:STAT ON")
        self._write(f"CALC{self._channel}:MARK{marker_id}:X {float(frequency_hz)}")
        return self.marker_value(marker_id)

    def marker_value(self, marker: int) -> dict[str, float]:
        marker_id = int(marker)
        frequency = float(self._query(f"CALC{self._channel}:MARK{marker_id}:X?"))
        values = self._query_ascii_values(f"CALC{self._channel}:MARK{marker_id}:Y?")
        real = values[0] if values else 0.0
        imaginary = values[1] if len(values) > 1 else 0.0
        magnitude = abs(complex(real, imaginary))
        return {
            "marker": marker_id,
            "freq_hz": frequency,
            "real": real,
            "imag": imaginary,
            "magnitude_db": 20.0 * math.log10(max(magnitude, 1e-15)),
        }

    def delete_markers(self) -> bool:
        self._write(f"CALC{self._channel}:MARK:AOFF")
        return True

    def autoscale(self, trace: int = 1) -> bool:
        self._write(f"DISP:WIND1:TRAC{int(trace)}:Y:AUTO")
        return True

    def load_state(self, path: str) -> bool:
        escaped = path.replace("'", "''")
        self._write(f"MMEM:LOAD:STAT 1,'{escaped}'")
        self._query("*OPC?")
        return True

    def _ensure_measurement(self, parameter: str) -> None:
        if parameter in self._measurement_names:
            return
        name = f"HFSSFS_{parameter}"
        try:
            self._write(self._profile.delete(name, self._channel))
        except (OSError, RuntimeError, TypeError, ValueError):
            self._measurement_names.pop(parameter, None)
        try:
            self._write(self._profile.define(name, parameter, self._channel))
        except (OSError, RuntimeError, TypeError, ValueError) as first_error:
            for fallback in PROFILES.values():
                if fallback.key == self._profile.key:
                    continue
                try:
                    self._write(fallback.define(name, parameter, self._channel))
                    self._profile = fallback
                    break
                except (OSError, RuntimeError, TypeError, ValueError):
                    continue
            else:
                raise RuntimeError(
                    f"Unable to define VNA measurement {parameter}: {first_error}"
                ) from first_error
        self._measurement_names[parameter] = name

    def _query_frequencies(self) -> list[float]:
        for command in self._profile.stimulus(self._channel):
            try:
                values = self._query_ascii_values(command)
                if len(values) >= 2:
                    return values
            except (OSError, RuntimeError, TypeError, ValueError):
                continue
        config = self._config
        if config.points < 2:
            return [config.start_hz]
        if self._sweep_type == "LOG":
            ratio = (config.stop_hz / config.start_hz) ** (1.0 / (config.points - 1))
            return [config.start_hz * ratio**index for index in range(config.points)]
        return [
            config.start_hz
            + (config.stop_hz - config.start_hz) * index / (config.points - 1)
            for index in range(config.points)
        ]

    @staticmethod
    def _parse_complex_values(values: list[float], parameter: str) -> list[complex]:
        if len(values) % 2:
            raise RuntimeError(f"VNA returned an odd number of {parameter} SDATA values")
        return [
            complex(values[index], values[index + 1])
            for index in range(0, len(values), 2)
        ]

    def _query_ascii_values(self, command: str) -> list[float]:
        instrument = self._require_instrument()
        query_values = getattr(instrument, "query_ascii_values", None)
        if callable(query_values):
            return [float(value) for value in query_values(command, separator=",")]
        response = str(instrument.query(command))
        return [
            float(part)
            for part in response.replace("\n", ",").split(",")
            if part.strip()
        ]

    def _write(self, command: str) -> None:
        self._require_instrument().write(command)

    def _query(self, command: str) -> str:
        return str(self._require_instrument().query(command))

    def _require_instrument(self) -> Any:
        if self._instrument is None:
            raise RuntimeError("VNA adapter is not connected")
        return self._instrument


def _load_pyvisa() -> Any:
    try:
        import pyvisa
    except Exception as exc:
        raise RuntimeError(
            "PyVISA is not available. Install with: uv sync --extra vna"
        ) from exc
    return pyvisa
