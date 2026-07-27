from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit

from hfss_vna_bridge.core.registry import RuntimeRegistry
from hfss_vna_bridge.core.touchstone import (
    compare_networks,
    points_from_json,
    read_s2p,
)
from hfss_vna_bridge.engines.engineering import (
    monte_carlo_filter,
    optimize_filter_specification,
    transmission_line,
    tuning_recommendations,
)
from hfss_vna_bridge.services.advanced_algorithms import (
    algorithm_exists,
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


def create_app(
    settings: Settings | None = None,
    registry: RuntimeRegistry | None = None,
) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["JSON_SORT_KEYS"] = False
    app.config["SETTINGS"] = settings or Settings.from_env()
    app.config["REGISTRY"] = registry or RuntimeRegistry.from_settings(app.config["SETTINGS"])
    app.config["DISPATCHER"] = SymMatrixDispatcher(app.config["REGISTRY"])
    app.config["PROJECT_STORE"] = ProjectStore(app.config["SETTINGS"].project_dir)

    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
    app.config["SOCKETIO"] = socketio

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/favicon.ico")
    def favicon():
        return "", 204

    @app.get("/health")
    def health():
        return _json(app.config["DISPATCHER"].health())

    @app.get("/api/state")
    def api_state():
        return _json(app.config["DISPATCHER"].snapshot())

    @app.post("/api/synthesis/calculate")
    def api_synthesis_calculate():
        try:
            return _json(synthesize_filter(_payload()))
        except (TypeError, ValueError) as exc:
            return _json({"status": -400, "ok": False, "message": str(exc)}, 400)

    @app.post("/api/synthesis/multiplexer")
    def api_synthesis_multiplexer():
        return _service_call(synthesize_multiplexer, _payload())

    @app.post("/api/synthesis/matrix-response")
    def api_synthesis_matrix_response():
        return _service_call(evaluate_coupling_matrix, _payload())

    @app.post("/api/touchstone/import")
    def api_touchstone_import():
        path = str(_payload().get("path") or "").strip()
        if not path:
            return _json({"status": -400, "ok": False, "message": "path is required"}, 400)
        try:
            return _json({"status": 0, "ok": True, "touchstone": read_s2p(path).to_json()})
        except (OSError, TypeError, ValueError) as exc:
            return _json({"status": -400, "ok": False, "message": str(exc)}, 400)

    @app.post("/api/analysis/compare")
    def api_analysis_compare():
        payload = _payload()
        try:
            reference = _network_from_payload(payload, "reference")
            candidate = _network_from_payload(payload, "candidate")
            return _json({"status": 0, "ok": True, "comparison": compare_networks(reference, candidate)})
        except (OSError, TypeError, ValueError) as exc:
            return _json({"status": -400, "ok": False, "message": str(exc)}, 400)

    @app.post("/api/engineering/tuning")
    def api_engineering_tuning():
        payload = _payload()
        return _service_call(
            tuning_recommendations,
            payload.get("target") or {},
            payload.get("measured") or {},
            sensitivities=payload.get("sensitivities"),
        )

    @app.post("/api/engineering/monte-carlo")
    def api_engineering_monte_carlo():
        return _service_call(monte_carlo_filter, _payload())

    @app.post("/api/engineering/optimize")
    def api_engineering_optimize():
        return _service_call(optimize_filter_specification, _payload())

    @app.post("/api/engineering/transmission-line")
    def api_engineering_transmission_line():
        return _service_call(transmission_line, _payload())

    @app.post("/api/modeling/plan")
    def api_modeling_plan():
        payload = _payload()
        method = str(payload.pop("method", "buildcavityfull3d"))
        return _service_call(
            lambda: {"status": 0, "ok": True, "plan": model_plan(method, payload)}
        )

    @app.get("/api/algorithms")
    def api_algorithms():
        return _json(
            {
                "status": 0,
                "ok": True,
                "algorithms": supported_algorithms(),
            }
        )

    @app.post("/api/algorithms/<method>")
    def api_algorithm(method: str):
        return _service_call(run_algorithm, method, _payload())

    @app.post("/api/v1/algorithm/general/<method>")
    def api_v1_algorithm(method: str):
        return _service_call(run_algorithm, method, _payload())

    @app.route("/api/projects", methods=["GET", "POST"])
    def api_projects():
        store: ProjectStore = app.config["PROJECT_STORE"]
        if request.method == "GET":
            return _json({"status": 0, "ok": True, "projects": store.list_projects()})
        return _service_call(
            lambda payload: {"status": 0, "ok": True, "project": store.create(payload)},
            _payload(),
        )

    @app.route("/api/projects/<project_id>", methods=["GET", "PUT", "DELETE"])
    def api_project(project_id: str):
        store: ProjectStore = app.config["PROJECT_STORE"]
        try:
            if request.method == "GET":
                result = {"status": 0, "ok": True, "project": store.get(project_id)}
            elif request.method == "PUT":
                result = {
                    "status": 0,
                    "ok": True,
                    "project": store.update(project_id, _payload()),
                }
            else:
                result = {"status": 0, "ok": True, "deleted": store.delete(project_id)}
            return _json(result)
        except (KeyError, OSError, TypeError, ValueError) as exc:
            return _json({"status": -404, "ok": False, "message": str(exc)}, 404)

    @app.get("/api/projects/<project_id>/versions")
    def api_project_versions(project_id: str):
        store: ProjectStore = app.config["PROJECT_STORE"]
        return _json({"status": 0, "ok": True, "versions": store.versions(project_id)})

    @app.post("/api/projects/<project_id>/restore/<int:revision>")
    def api_project_restore(project_id: str, revision: int):
        store: ProjectStore = app.config["PROJECT_STORE"]
        return _service_call(
            lambda: {
                "status": 0,
                "ok": True,
                "project": store.restore(project_id, revision),
            }
        )

    @app.get("/api/library")
    def api_library():
        return _json(
            {
                "status": 0,
                "ok": True,
                "entries": list_library(request.args.get("category")),
            }
        )

    @app.get("/api/library/<entry_id>")
    def api_library_entry(entry_id: str):
        return _service_call(
            lambda: {"status": 0, "ok": True, "entry": get_library_entry(entry_id)}
        )

    @app.route("/api/jobs", methods=["GET", "POST"])
    def api_jobs():
        dispatcher: SymMatrixDispatcher = app.config["DISPATCHER"]
        if request.method == "GET":
            return _json({"status": 0, "ok": True, "jobs": dispatcher.list_jobs()})
        return _service_call(
            lambda payload: {
                "status": 0,
                "ok": True,
                "job": dispatcher.submit_aedt_job(payload),
            },
            _payload(),
        )

    @app.get("/api/jobs/<job_id>")
    def api_job(job_id: str):
        dispatcher: SymMatrixDispatcher = app.config["DISPATCHER"]
        return _service_call(
            lambda: {"status": 0, "ok": True, "job": dispatcher.get_job(job_id)}
        )

    @app.post("/api/jobs/<job_id>/cancel")
    def api_job_cancel(job_id: str):
        dispatcher: SymMatrixDispatcher = app.config["DISPATCHER"]
        return _service_call(
            lambda: {"status": 0, "ok": True, "job": dispatcher.cancel_job(job_id)}
        )

    @app.get("/ping")
    def ping():
        return _json({"status": 0, "ok": True, "pong": True})

    @app.route("/status", methods=["GET", "POST"])
    def status():
        return _dispatch_vna(app, "status")

    @app.route("/api/vna/<method>", methods=["GET", "POST"])
    def api_vna(method: str):
        return _dispatch_vna(app, method)

    @app.route("/vna/<method>", methods=["GET", "POST"])
    def rest_vna(method: str):
        return _dispatch_vna(app, method)

    @app.route("/api/aedt/<method>", methods=["GET", "POST"])
    def api_aedt(method: str):
        return _dispatch_aedt(app, method)

    @app.get("/api/aedt/installations")
    def api_aedt_installations():
        return _dispatch_aedt(app, "diagnostics")

    @app.route("/api/hfss/<method>", methods=["GET", "POST"])
    def api_hfss(method: str):
        return _dispatch_hfss(app, method)

    @app.post("/aedt/session")
    def rest_aedt_session():
        return _dispatch_aedt(app, "openproject")

    @app.get("/aedt/designs")
    def rest_aedt_designs():
        return _dispatch_aedt(app, "getdesigns")

    @app.route("/aedt/variables", methods=["GET", "POST"])
    def rest_aedt_variables():
        method = "getvariables" if request.method == "GET" else "setvariablesvalue"
        return _dispatch_aedt(app, method)

    @app.post("/aedt/analyze")
    def rest_aedt_analyze():
        return _dispatch_aedt(app, "evaluatedimension")

    @app.route("/aedt/<method>", methods=["POST"])
    def compat_aedt(method: str):
        return _dispatch_aedt(app, method)

    @app.route("/hfss/<method>", methods=["GET", "POST"])
    def compat_hfss(method: str):
        return _dispatch_hfss(app, method)

    @app.route("/<method>", methods=["POST"])
    def compat_vna(method: str):
        if method == "shutdown":
            return _json({"status": 0, "ok": True, "shutdown": "not-enabled"})
        if algorithm_exists(method):
            return _service_call(run_algorithm, method, _payload())
        return _dispatch_vna(app, method)

    @socketio.on("deepOptimization")
    def deep_optimization(payload: dict[str, Any] | None = None) -> None:
        try:
            result = optimize_filter_specification(payload or {})
        except (TypeError, ValueError) as exc:
            result = {"status": -400, "ok": False, "message": str(exc)}
        emit("deepOptimization:status", result)

    @socketio.on("portTuning", namespace="/portTuning")
    def port_tuning(payload: dict[str, Any] | None = None) -> None:
        data = payload or {}
        try:
            result = tuning_recommendations(
                data.get("target") or {},
                data.get("measured") or {},
                sensitivities=data.get("sensitivities"),
            )
        except (TypeError, ValueError) as exc:
            result = {"status": -400, "ok": False, "message": str(exc)}
        emit("portTuning:status", result, namespace="/portTuning")

    @socketio.on("startTuning")
    def start_tuning(payload: dict[str, Any] | None = None) -> None:
        emit("tuning:status", {"status": 0, "ok": True, "running": True, "payload": payload or {}})

    @socketio.on("stopTuning")
    def stop_tuning(payload: dict[str, Any] | None = None) -> None:
        emit("tuning:status", {"status": 0, "ok": True, "running": False, "payload": payload or {}})

    return app


def run_flask_app(host: str = "127.0.0.1", port: int = 8765, debug: bool = False) -> None:
    app = create_app()
    socketio: SocketIO = app.config["SOCKETIO"]
    socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)


def _json(payload: dict[str, Any], status_code: int = 200):
    response = jsonify(payload)
    response.status_code = status_code
    return response


def _payload() -> dict[str, Any]:
    if request.method == "GET":
        return dict(request.args)
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _dispatch_vna(app: Flask, method: str):
    return _dispatch(app, lambda dispatcher, payload: dispatcher.invoke_vna(method, payload))


def _dispatch_aedt(app: Flask, method: str):
    return _dispatch(app, lambda dispatcher, payload: dispatcher.invoke_aedt(method, payload))


def _dispatch_hfss(app: Flask, method: str):
    return _dispatch(app, lambda dispatcher, payload: dispatcher.invoke_hfss(method, payload))


def _dispatch(app: Flask, call):
    dispatcher: SymMatrixDispatcher = app.config["DISPATCHER"]
    try:
        payload = call(dispatcher, _payload())
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        payload = {"status": -500, "ok": False, "message": str(exc)}
    status_code = 200 if int(payload.get("status", 0)) in {0, -404} else 500
    return _json(payload, status_code)


def _service_call(call, *args, **kwargs):
    try:
        result = call(*args, **kwargs)
        if isinstance(result, dict):
            return _json(result)
        return _json({"status": 0, "ok": True, "result": result})
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": -400, "ok": False, "message": str(exc)}, 400)


def _network_from_payload(payload: dict[str, Any], key: str):
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
