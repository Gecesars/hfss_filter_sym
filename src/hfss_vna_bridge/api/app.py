from __future__ import annotations

from fastapi import FastAPI, HTTPException

from hfss_vna_bridge import __version__
from hfss_vna_bridge.adapters.aedt.pyaedt_adapter import PyAedtAdapter
from hfss_vna_bridge.adapters.aedt.simulated import SimulatedAedtAdapter
from hfss_vna_bridge.adapters.vna.pyvisa_adapter import PyVisaVnaAdapter
from hfss_vna_bridge.adapters.vna.simulated import SimulatedVnaAdapter
from hfss_vna_bridge.core.models import AdapterState, SweepConfig
from hfss_vna_bridge.core.registry import RuntimeRegistry
from hfss_vna_bridge.settings import Settings

from .schemas import (
    AdapterStateResponse,
    AedtAnalyzeRequest,
    AedtAnalyzeResponse,
    AedtSessionRequest,
    FrequencyRequest,
    HealthResponse,
    SaveTouchstoneRequest,
    SaveTouchstoneResponse,
    ScalarRequest,
    SweepConfigRequest,
    SweepConfigResponse,
    SweepResponse,
    VariableUpdateRequest,
    VnaConnectRequest,
)


def create_app(
    settings: Settings | None = None,
    registry: RuntimeRegistry | None = None,
) -> FastAPI:
    app = FastAPI(
        title="HFSS VNA Bridge",
        version=__version__,
        description="Original API for AEDT/HFSS automation and VNA acquisition.",
    )
    app.state.registry = registry or RuntimeRegistry.from_settings(settings)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        runtime = _runtime(app)
        return HealthResponse(
            ok=True,
            version=__version__,
            aedt=_state_response(runtime.aedt.state),
            vna=_state_response(runtime.vna.state),
        )

    @app.post("/aedt/session", response_model=AdapterStateResponse)
    def connect_aedt(request: AedtSessionRequest) -> AdapterStateResponse:
        runtime = _runtime(app)
        adapter = SimulatedAedtAdapter() if request.backend == "simulated" else PyAedtAdapter()
        try:
            state = adapter.connect(
                project_path=request.project_path,
                design_name=request.design_name,
                new_desktop=request.new_desktop,
                non_graphical=request.non_graphical,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        runtime.aedt = adapter
        return _state_response(state)

    @app.get("/aedt/designs", response_model=list[str])
    def list_designs() -> list[str]:
        try:
            return _runtime(app).aedt.list_designs()
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/aedt/variables", response_model=dict[str, str])
    def get_variables() -> dict[str, str]:
        try:
            return _runtime(app).aedt.get_variables()
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/aedt/variables", response_model=dict[str, str])
    def set_variables(request: VariableUpdateRequest) -> dict[str, str]:
        try:
            return _runtime(app).aedt.set_variables(request.variables)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/aedt/analyze", response_model=AedtAnalyzeResponse)
    def analyze(request: AedtAnalyzeRequest) -> AedtAnalyzeResponse:
        try:
            result = _runtime(app).aedt.analyze(
                setup_name=request.setup_name,
                sweep_name=request.sweep_name,
                output_touchstone=request.output_touchstone,
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return AedtAnalyzeResponse(**result)

    @app.post("/vna/connect", response_model=AdapterStateResponse)
    def connect_vna(request: VnaConnectRequest) -> AdapterStateResponse:
        runtime = _runtime(app)
        adapter = (
            SimulatedVnaAdapter(request.resource)
            if request.backend == "simulated"
            else PyVisaVnaAdapter(request.resource, timeout_ms=request.timeout_ms)
        )
        try:
            state = adapter.connect()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        runtime.vna = adapter
        return _state_response(state)

    @app.get("/vna/status", response_model=AdapterStateResponse)
    def vna_status() -> AdapterStateResponse:
        return _state_response(_runtime(app).vna.state)

    @app.post("/vna/reset", response_model=AdapterStateResponse)
    def reset_vna() -> AdapterStateResponse:
        try:
            return _state_response(_runtime(app).vna.reset())
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/vna/configure-sweep", response_model=SweepConfigResponse)
    def configure_sweep(request: SweepConfigRequest) -> SweepConfigResponse:
        try:
            config = _runtime(app).vna.configure_sweep(_sweep_config(request))
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _config_response(config)

    @app.post("/vna/single-sweep", response_model=SweepResponse)
    def single_sweep() -> SweepResponse:
        runtime = _runtime(app)
        try:
            points = runtime.vna.single_sweep()
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return SweepResponse(
            config=_config_response(runtime.vna.sweep_config),
            points=[point.to_json() for point in points],
        )

    @app.post("/vna/save-touchstone", response_model=SaveTouchstoneResponse)
    def save_touchstone(request: SaveTouchstoneRequest) -> SaveTouchstoneResponse:
        try:
            path = _runtime(app).vna.save_touchstone(request.path)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return SaveTouchstoneResponse(path=str(path))

    # Compatibility aliases for simple local integrations.
    app.post("/connect", response_model=AdapterStateResponse)(connect_vna)
    app.get("/status", response_model=AdapterStateResponse)(vna_status)
    app.post("/reset", response_model=AdapterStateResponse)(reset_vna)
    app.post("/singlesweep", response_model=SweepResponse)(single_sweep)
    app.post("/savetracedata", response_model=SaveTouchstoneResponse)(save_touchstone)

    @app.post("/setfrequency", response_model=SweepConfigResponse)
    def set_frequency(request: FrequencyRequest) -> SweepConfigResponse:
        runtime = _runtime(app)
        current = runtime.vna.sweep_config
        if request.center_hz is not None or request.span_hz is not None:
            center = request.center_hz if request.center_hz is not None else (current.start_hz + current.stop_hz) / 2
            span = request.span_hz if request.span_hz is not None else current.stop_hz - current.start_hz
            start_hz = center - span / 2
            stop_hz = center + span / 2
        else:
            start_hz = request.start_hz if request.start_hz is not None else current.start_hz
            stop_hz = request.stop_hz if request.stop_hz is not None else current.stop_hz
        config = SweepConfig(
            start_hz=start_hz,
            stop_hz=stop_hz,
            points=current.points,
            ifbw_hz=current.ifbw_hz,
            power_dbm=current.power_dbm,
        )
        try:
            return _config_response(runtime.vna.configure_sweep(config))
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/setifbw", response_model=SweepConfigResponse)
    def set_ifbw(request: ScalarRequest) -> SweepConfigResponse:
        return _replace_sweep_value(app, ifbw_hz=request.value)

    @app.post("/setpower", response_model=SweepConfigResponse)
    def set_power(request: ScalarRequest) -> SweepConfigResponse:
        return _replace_sweep_value(app, power_dbm=request.value)

    return app


def _runtime(app: FastAPI) -> RuntimeRegistry:
    return app.state.registry


def _state_response(state: AdapterState) -> AdapterStateResponse:
    return AdapterStateResponse(
        connected=state.connected,
        backend=state.backend,
        resource=state.resource,
        detail=state.detail,
    )


def _sweep_config(request: SweepConfigRequest) -> SweepConfig:
    return SweepConfig(
        start_hz=request.start_hz,
        stop_hz=request.stop_hz,
        points=request.points,
        ifbw_hz=request.ifbw_hz,
        power_dbm=request.power_dbm,
    )


def _config_response(config: SweepConfig) -> SweepConfigResponse:
    return SweepConfigResponse(
        start_hz=config.start_hz,
        stop_hz=config.stop_hz,
        points=config.points,
        ifbw_hz=config.ifbw_hz,
        power_dbm=config.power_dbm,
    )


def _replace_sweep_value(app: FastAPI, **changes: float) -> SweepConfigResponse:
    runtime = _runtime(app)
    current = runtime.vna.sweep_config
    data = {
        "start_hz": current.start_hz,
        "stop_hz": current.stop_hz,
        "points": current.points,
        "ifbw_hz": current.ifbw_hz,
        "power_dbm": current.power_dbm,
    }
    data.update(changes)
    try:
        return _config_response(runtime.vna.configure_sweep(SweepConfig(**data)))
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

