from __future__ import annotations

import math
from pathlib import Path

from hfss_vna_bridge.core.models import AdapterState, NetworkPoint
from hfss_vna_bridge.core.touchstone import write_s2p


class SimulatedAedtAdapter:
    """Deterministic AEDT stand-in used for tests and offline development."""

    def __init__(self) -> None:
        self._state = AdapterState(False, "simulated", "SIM::AEDT")
        self._project_path: Path | None = None
        self._design_name = "SimulatedHFSSDesign"
        self._variables: dict[str, str] = {
            "arm_scale_a": "1.0",
            "arm_scale_b": "1.0",
            "dist_refletor": "20mm",
            "comp_refletor": "80mm",
            "refl_lat": "16mm",
        }

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
        del new_desktop, non_graphical
        self._project_path = Path(project_path) if project_path else None
        if design_name:
            self._design_name = design_name
        resource = str(self._project_path) if self._project_path else "SIM::AEDT"
        self._state = AdapterState(True, "simulated", resource, self._design_name)
        return self._state

    def list_designs(self) -> list[str]:
        self._require_connected()
        return [self._design_name]

    def get_variables(self) -> dict[str, str]:
        self._require_connected()
        return dict(self._variables)

    def set_variables(self, variables: dict[str, str | float | int]) -> dict[str, str]:
        self._require_connected()
        for name, value in variables.items():
            self._variables[name] = str(value)
        return self.get_variables()

    def analyze(
        self,
        setup_name: str | None = None,
        sweep_name: str | None = None,
        output_touchstone: str | Path | None = None,
    ) -> dict[str, str | None]:
        self._require_connected()
        output = None
        if output_touchstone:
            output = write_s2p(
                output_touchstone,
                self._synthetic_network(),
                comment=f"simulated AEDT setup={setup_name or 'default'} sweep={sweep_name or 'default'}",
            )
        return {
            "project": str(self._project_path) if self._project_path else None,
            "design": self._design_name,
            "setup": setup_name,
            "sweep": sweep_name,
            "touchstone": str(output) if output else None,
        }

    def _synthetic_network(self) -> list[NetworkPoint]:
        points: list[NetworkPoint] = []
        start_hz = 600_000_000.0
        stop_hz = 1_100_000_000.0
        total = 101
        scale = _as_float(self._variables.get("arm_scale_a"), 1.0)
        center = 880_000_000.0 / max(scale, 0.1)
        for index in range(total):
            freq = start_hz + (stop_hz - start_hz) * index / (total - 1)
            offset = (freq - center) / 95_000_000.0
            mag = min(0.95, 0.08 + 0.75 * abs(math.tanh(offset)))
            phase = offset * 0.9
            s11 = complex(mag * math.cos(phase), mag * math.sin(phase))
            s21 = complex(0.15 * math.cos(phase / 2), 0.15 * math.sin(phase / 2))
            points.append(NetworkPoint(freq_hz=freq, s11=s11, s21=s21))
        return points

    def _require_connected(self) -> None:
        if not self._state.connected:
            raise RuntimeError("AEDT adapter is not connected")


def _as_float(value: object, default: float) -> float:
    try:
        text = str(value).strip().lower()
        for suffix in ("mm", "ghz", "mhz", "hz"):
            if text.endswith(suffix):
                text = text[: -len(suffix)]
                break
        return float(text)
    except (TypeError, ValueError):
        return default
