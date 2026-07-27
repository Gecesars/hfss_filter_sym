from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit

from hfss_vna_bridge.core.registry import RuntimeRegistry
from hfss_vna_bridge.services.symmatrix import SymMatrixDispatcher
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

    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
    app.config["SOCKETIO"] = socketio

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/health")
    def health():
        return _json(app.config["DISPATCHER"].health())

    @app.get("/api/state")
    def api_state():
        return _json(app.config["DISPATCHER"].snapshot())

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
        return _dispatch_vna(app, method)

    @socketio.on("deepOptimization")
    def deep_optimization(payload: dict[str, Any] | None = None) -> None:
        emit(
            "deepOptimization:status",
            {
                "status": -501,
                "ok": False,
                "implemented": False,
                "event": "deepOptimization",
                "payload": payload or {},
            },
        )

    @socketio.on("portTuning", namespace="/portTuning")
    def port_tuning(payload: dict[str, Any] | None = None) -> None:
        emit(
            "portTuning:status",
            {
                "status": -501,
                "ok": False,
                "implemented": False,
                "event": "portTuning",
                "payload": payload or {},
            },
            namespace="/portTuning",
        )

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
    status_code = 200 if int(payload.get("status", 0)) in {0, -501, -404} else 500
    return _json(payload, status_code)
