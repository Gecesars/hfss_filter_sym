from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdapterState:
    connected: bool
    backend: str
    resource: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class SweepConfig:
    start_hz: float = 600_000_000.0
    stop_hz: float = 1_100_000_000.0
    points: int = 201
    ifbw_hz: float = 1_000.0
    power_dbm: float = -10.0

    def validate(self) -> None:
        if self.start_hz <= 0:
            raise ValueError("start_hz must be positive")
        if self.stop_hz <= self.start_hz:
            raise ValueError("stop_hz must be greater than start_hz")
        if self.points < 2:
            raise ValueError("points must be at least 2")
        if self.ifbw_hz <= 0:
            raise ValueError("ifbw_hz must be positive")


@dataclass(frozen=True)
class NetworkPoint:
    freq_hz: float
    s11: complex
    s21: complex
    s12: complex = 0j
    s22: complex = 0j

    def to_json(self) -> dict[str, float]:
        return {
            "freq_hz": self.freq_hz,
            "s11_real": self.s11.real,
            "s11_imag": self.s11.imag,
            "s21_real": self.s21.real,
            "s21_imag": self.s21.imag,
            "s12_real": self.s12.real,
            "s12_imag": self.s12.imag,
            "s22_real": self.s22.real,
            "s22_imag": self.s22.imag,
        }

