from __future__ import annotations

from fastapi import FastAPI, HTTPException

from hfss_vna_bridge import __version__
from hfss_vna_bridge.adapters.aedt.installations import aedt_environment_diagnostics
from hfss_vna_bridge.adapters.aedt.pyaedt_adapter import PyAedtAdapter
from hfss_vna_bridge.adapters.aedt.simulated import SimulatedAedtAdapter
from hfss_vna_bridge.adapters.vna.pyvisa_adapter import PyVisaVnaAdapter
from hfss_vna_bridge.adapters.vna.simulated import SimulatedVnaAdapter
from hfss_vna_bridge.core.models import AdapterState, SweepConfig
from hfss_vna_bridge.core.registry import RuntimeRegistry
from hfss_vna_bridge.core.touchstone import compare_networks, points_from_json, read_s2p
from hfss_vna_bridge.engines.engineering import (
    monte_carlo_filter,
    optimize_filter_specification,
    transmission_line,
    tuning_recommendations,
)
from hfss_vna_bridge.services.advanced_algorithms import (
    run_algorithm,
    supported_algorithms,
)
from hfss_vna_bridge.services.library import get_library_entry, list_library
from hfss_vna_bridge.services.modeling import model_plan
from hfss_vna_bridge.services.multiplexer import synthesize_multiplexer
from hfss_vna_bridge.services.project_store import ProjectStore
from hfss_vna_bridge.services.symmatrix import SymMatrixDispatcher
from hfss_vna_bridge.services.synthesis import (
    evaluate_coupling_matrix,
    synthesize_filter,
)
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
    resolved_settings = settings or Settings.from_env()
    app = FastAPI(
        title="HFSS VNA Bridge",
        version=__version__,
        description="Original API for AEDT/HFSS automation and VNA acquisition.",
    )
    app.state.registry = registry or RuntimeRegistry.from_settings(resolved_settings)
    app.state.dispatcher = SymMatrixDispatcher(app.state.registry)
    app.state.projects = ProjectStore(resolved_settings.project_dir)

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
                version=request.version,
                new_desktop=request.new_desktop,
                non_graphical=request.non_graphical,
                close_on_exit=request.close_on_exit,
                student_version=request.student_version,
                machine=request.machine,
                port=request.port,
                aedt_process_id=request.aedt_process_id,
                remove_lock=request.remove_lock,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        runtime.aedt = adapter
        return _state_response(state)

    @app.get("/aedt/installations")
    def aedt_installations() -> dict[str, object]:
        return aedt_environment_diagnostics()

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
                cores=request.cores,
                tasks=request.tasks,
                gpus=request.gpus,
                blocking=request.blocking,
                revert_to_initial_mesh=request.revert_to_initial_mesh,
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return AedtAnalyzeResponse(**result)

    @app.post("/vna/connect", response_model=AdapterStateResponse)
    def connect_vna(request: VnaConnectRequest) -> AdapterStateResponse:
        runtime = _runtime(app)
        if request.backend == "simulated":
            adapter = SimulatedVnaAdapter(request.resource)
        else:
            adapter = PyVisaVnaAdapter(
                request.resource,
                timeout_ms=request.timeout_ms,
                brand=request.brand,
                visa_library=request.visa_library,
                channel=request.channel,
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

    @app.get("/state")
    def state() -> dict[str, object]:
        return app.state.dispatcher.snapshot()

    @app.post("/synthesis/calculate")
    def synthesis_calculate(payload: dict[str, object]) -> dict[str, object]:
        return _call_service(synthesize_filter, payload)

    @app.post("/synthesis/multiplexer")
    def synthesis_multiplexer(payload: dict[str, object]) -> dict[str, object]:
        return _call_service(synthesize_multiplexer, payload)

    @app.post("/synthesis/matrix-response")
    def synthesis_matrix_response(payload: dict[str, object]) -> dict[str, object]:
        return _call_service(evaluate_coupling_matrix, payload)

    @app.post("/touchstone/import")
    def touchstone_import(payload: dict[str, object]) -> dict[str, object]:
        path = str(payload.get("path") or "")
        if not path:
            raise HTTPException(status_code=400, detail="path is required")
        try:
            return {"status": 0, "ok": True, "touchstone": read_s2p(path).to_json()}
        except (OSError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/analysis/compare")
    def analysis_compare(payload: dict[str, object]) -> dict[str, object]:
        try:
            reference = _network_payload(payload, "reference")
            candidate = _network_payload(payload, "candidate")
            return {
                "status": 0,
                "ok": True,
                "comparison": compare_networks(reference, candidate),
            }
        except (OSError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/engineering/tuning")
    def engineering_tuning(payload: dict[str, object]) -> dict[str, object]:
        return _call_service(
            tuning_recommendations,
            payload.get("target") or {},
            payload.get("measured") or {},
            sensitivities=payload.get("sensitivities"),
        )

    @app.post("/engineering/monte-carlo")
    def engineering_monte_carlo(payload: dict[str, object]) -> dict[str, object]:
        return _call_service(monte_carlo_filter, payload)

    @app.post("/engineering/optimize")
    def engineering_optimize(payload: dict[str, object]) -> dict[str, object]:
        return _call_service(optimize_filter_specification, payload)

    @app.post("/engineering/transmission-line")
    def engineering_transmission_line(payload: dict[str, object]) -> dict[str, object]:
        return _call_service(transmission_line, payload)

    @app.post("/modeling/plan")
    def modeling_plan(payload: dict[str, object]) -> dict[str, object]:
        data = dict(payload)
        method = str(data.pop("method", "buildcavityfull3d"))
        return _call_service(
            lambda: {"status": 0, "ok": True, "plan": model_plan(method, data)}
        )

    @app.get("/algorithms")
    def algorithms() -> dict[str, object]:
        return {
            "status": 0,
            "ok": True,
            "algorithms": supported_algorithms(),
        }

    @app.post("/algorithms/{method}")
    def algorithm(method: str, payload: dict[str, object]) -> dict[str, object]:
        return _call_service(run_algorithm, method, payload)

    @app.post("/api/v1/algorithm/general/{method}")
    def algorithm_compat(method: str, payload: dict[str, object]) -> dict[str, object]:
        return _call_service(run_algorithm, method, payload)

    @app.get("/library")
    def library(category: str | None = None) -> dict[str, object]:
        return {"status": 0, "ok": True, "entries": list_library(category)}

    @app.get("/library/{entry_id}")
    def library_entry(entry_id: str) -> dict[str, object]:
        return _call_service(
            lambda: {"status": 0, "ok": True, "entry": get_library_entry(entry_id)}
        )

    @app.get("/projects")
    def projects() -> dict[str, object]:
        return {"status": 0, "ok": True, "projects": app.state.projects.list_projects()}

    @app.post("/projects")
    def create_project(payload: dict[str, object]) -> dict[str, object]:
        return _call_service(
            lambda: {
                "status": 0,
                "ok": True,
                "project": app.state.projects.create(payload),
            }
        )

    @app.get("/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, object]:
        return _call_service(
            lambda: {
                "status": 0,
                "ok": True,
                "project": app.state.projects.get(project_id),
            }
        )

    @app.put("/projects/{project_id}")
    def update_project(project_id: str, payload: dict[str, object]) -> dict[str, object]:
        return _call_service(
            lambda: {
                "status": 0,
                "ok": True,
                "project": app.state.projects.update(project_id, payload),
            }
        )

    @app.delete("/projects/{project_id}")
    def delete_project(project_id: str) -> dict[str, object]:
        return _call_service(
            lambda: {
                "status": 0,
                "ok": True,
                "deleted": app.state.projects.delete(project_id),
            }
        )

    @app.get("/jobs")
    def jobs() -> dict[str, object]:
        return {"status": 0, "ok": True, "jobs": app.state.dispatcher.list_jobs()}

    @app.post("/jobs")
    def submit_job(payload: dict[str, object]) -> dict[str, object]:
        return {
            "status": 0,
            "ok": True,
            "job": app.state.dispatcher.submit_aedt_job(payload),
        }

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, object]:
        return _call_service(
            lambda: {"status": 0, "ok": True, "job": app.state.dispatcher.get_job(job_id)}
        )

    @app.post("/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict[str, object]:
        return _call_service(
            lambda: {
                "status": 0,
                "ok": True,
                "job": app.state.dispatcher.cancel_job(job_id),
            }
        )

    @app.get("/vna/resources")
    def vna_resources(visa_library: str | None = None) -> dict[str, object]:
        return _call_service(PyVisaVnaAdapter.discover, visa_library)

    @app.get("/vna/capabilities")
    def vna_capabilities() -> dict[str, object]:
        return {
            "status": 0,
            "ok": True,
            "capabilities": _runtime(app).vna.capabilities(),
        }

    @app.get("/vna/errors")
    def vna_errors() -> dict[str, object]:
        return {"status": 0, "ok": True, "errors": _runtime(app).vna.query_errors()}

    @app.post("/vna/close")
    def vna_close() -> dict[str, object]:
        return {
            "status": 0,
            "ok": True,
            "state": _state_response(_runtime(app).vna.close()).model_dump(),
        }

    @app.post("/aedt/configure-analysis")
    def aedt_configure_analysis(payload: dict[str, object]) -> dict[str, object]:
        return _call_service(
            lambda: {
                "status": 0,
                "ok": True,
                "configuration": _runtime(app).aedt.configure_analysis(payload),
            }
        )

    @app.post("/aedt/model")
    def aedt_model(payload: dict[str, object]) -> dict[str, object]:
        data = dict(payload)
        method = str(data.pop("method", "buildcavityfull3d"))
        return _call_service(
            lambda: {
                "status": 0,
                "ok": True,
                "model": _runtime(app).aedt.build_model(model_plan(method, data)),
            }
        )

    @app.post("/aedt/validate")
    def aedt_validate(payload: dict[str, object]) -> dict[str, object]:
        ports = payload.get("expected_ports")
        expected_ports = int(ports) if ports is not None else None
        return _call_service(
            lambda: {
                "status": 0,
                "ok": True,
                "validation": _runtime(app).aedt.validate_design(expected_ports),
            }
        )

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


def _call_service(call, *args, **kwargs) -> dict[str, object]:
    try:
        result = call(*args, **kwargs)
        if isinstance(result, dict):
            return result
        return {"status": 0, "ok": True, "result": result}
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _network_payload(payload: dict[str, object], key: str):
    path = payload.get(f"{key}_path")
    if path:
        return read_s2p(str(path)).points
    value = payload.get(key)
    if isinstance(value, dict) and value.get("path"):
        return read_s2p(str(value["path"])).points
    if isinstance(value, dict):
        value = value.get("points")
    if not isinstance(value, list):
        raise TypeError(f"{key} must provide a path or a points array")
    return points_from_json(value)
