from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AdapterStateResponse(BaseModel):
    connected: bool
    backend: str
    resource: str | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    ok: bool
    version: str
    aedt: AdapterStateResponse
    vna: AdapterStateResponse


class AedtSessionRequest(BaseModel):
    backend: Literal["simulated", "pyaedt"] = "pyaedt"
    project_path: str | None = None
    design_name: str | None = None
    new_desktop: bool = False
    non_graphical: bool = False


class VariableUpdateRequest(BaseModel):
    variables: dict[str, str | float | int] = Field(default_factory=dict)


class AedtAnalyzeRequest(BaseModel):
    setup_name: str | None = None
    sweep_name: str | None = None
    output_touchstone: str | None = None


class AedtAnalyzeResponse(BaseModel):
    project: str | None = None
    design: str | None = None
    setup: str | None = None
    sweep: str | None = None
    touchstone: str | None = None


class VnaConnectRequest(BaseModel):
    backend: Literal["simulated", "pyvisa"] = "simulated"
    resource: str = "SIM::VNA"
    timeout_ms: int = 30_000


class SweepConfigRequest(BaseModel):
    start_hz: float
    stop_hz: float
    points: int = 201
    ifbw_hz: float = 1_000
    power_dbm: float = -10


class SweepConfigResponse(SweepConfigRequest):
    pass


class NetworkPointResponse(BaseModel):
    freq_hz: float
    s11_real: float
    s11_imag: float
    s21_real: float
    s21_imag: float
    s12_real: float
    s12_imag: float
    s22_real: float
    s22_imag: float


class SweepResponse(BaseModel):
    config: SweepConfigResponse
    points: list[NetworkPointResponse]


class SaveTouchstoneRequest(BaseModel):
    path: str


class SaveTouchstoneResponse(BaseModel):
    path: str


class FrequencyRequest(BaseModel):
    start_hz: float | None = None
    stop_hz: float | None = None
    center_hz: float | None = None
    span_hz: float | None = None


class ScalarRequest(BaseModel):
    value: float

