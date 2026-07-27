from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hfss_vna_bridge import __version__
from hfss_vna_bridge.adapters.aedt.pyaedt_adapter import PyAedtAdapter
from hfss_vna_bridge.adapters.aedt.simulated import SimulatedAedtAdapter
from hfss_vna_bridge.adapters.vna.pyvisa_adapter import PyVisaVnaAdapter
from hfss_vna_bridge.adapters.vna.simulated import SimulatedVnaAdapter
from hfss_vna_bridge.core.models import AdapterState, NetworkPoint, SweepConfig
from hfss_vna_bridge.core.registry import RuntimeRegistry

VNA_METHODS = [
    "status",
    "connect",
    "close",
    "reset",
    "clearerrmsg",
    "initialize2",
    "loadpreset",
    "setfrequency",
    "setifbw",
    "setpower",
    "setsweeppoints",
    "setsweeptype",
    "setcontinoussweep",
    "settrace",
    "settracestatus",
    "setmarkers",
    "setautoscaletrace",
    "getsweeptime",
    "getmarkeryvalue",
    "savetracedata",
    "deleteallmarkers",
    "deletetraces",
    "singlesweep",
    "beginbackgroundsweep",
    "endbackgroundsweep",
    "exports2p",
]

AEDT_METHODS = [
    "openproject",
    "getdesigns",
    "setactivedesign",
    "getvariables",
    "getvariablesvalue",
    "setvariablesvalue",
    "setsettings",
    "createreport",
    "makelpfmodel",
    "evaluatedimension",
    "evaluatedimensionnos2p",
    "callconvergence",
    "callkillmesh",
    "stop",
]

HFSS_METHODS = [
    "openproject",
    "closeproject",
    "saveproject",
    "updatevalues",
    "removemesh",
    "updatemeshsetting",
    "analyzeall",
    "iosimulation",
    "full3dsimulation",
    "lumpportsimulation",
    "planarsimulation",
    "planarupdatemodel",
    "ccsinglemodeling",
    "ccupdatelumpport",
    "ccthermalmodeling",
    "ccpowerhandling",
    "cccouplingmodeling",
    "cciomodeling",
    "wgrsinglemodeling",
    "wgrcouplingmodeling",
    "wgriomodeling",
    "wgcsinglemodeling",
    "wgccouplingmodeling",
    "wgciomodeling",
    "siwsinglemodeling",
    "siwcouplingmodeling",
    "siwiomodeling",
    "siwfull3d",
    "buildcavityfull3d",
    "updatecavityfull3d",
    "lpf_step_modeling",
    "lpf_openstub_modeling",
    "lpf_elliptic_modeling",
    "lpf_custom_modeling",
]


@dataclass
class VnaSessionState:
    brand: str = "SIM"
    sweep_type: str = "LIN"
    continuous_sweep: bool = False
    background_sweep: bool = False
    markers: dict[str, dict[str, Any]] = field(default_factory=dict)
    traces: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_sweep: list[dict[str, float]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class AedtSessionState:
    settings: dict[str, Any] = field(default_factory=dict)
    active_design: str | None = None
    last_analysis: dict[str, Any] | None = None


class SymMatrixDispatcher:
    """Original implementation of the recovered SymMatrix-style local contract."""

    def __init__(self, registry: RuntimeRegistry) -> None:
        self.registry = registry
        self.vna_state = VnaSessionState()
        self.aedt_state = AedtSessionState()

    def health(self) -> dict[str, Any]:
        return self._ok(
            version=__version__,
            aedt=self._adapter_state(self.registry.aedt.state),
            vna=self._adapter_state(self.registry.vna.state),
            supported=self.supported_methods(),
        )

    def supported_methods(self) -> dict[str, list[str]]:
        return {
            "vna": list(VNA_METHODS),
            "aedt": list(AEDT_METHODS),
            "hfss": list(HFSS_METHODS),
        }

    def snapshot(self) -> dict[str, Any]:
        return self._ok(
            version=__version__,
            aedt={
                "state": self._adapter_state(self.registry.aedt.state),
                "session": {
                    "active_design": self.aedt_state.active_design,
                    "settings": self.aedt_state.settings,
                    "last_analysis": self.aedt_state.last_analysis,
                },
            },
            vna={
                "state": self._adapter_state(self.registry.vna.state),
                "config": self._sweep_config(self.registry.vna.sweep_config),
                "session": {
                    "brand": self.vna_state.brand,
                    "sweep_type": self.vna_state.sweep_type,
                    "continuous_sweep": self.vna_state.continuous_sweep,
                    "background_sweep": self.vna_state.background_sweep,
                    "markers": self.vna_state.markers,
                    "traces": self.vna_state.traces,
                    "last_sweep_points": len(self.vna_state.last_sweep),
                },
            },
            supported=self.supported_methods(),
        )

    def invoke_vna(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = _normalize_method(method)
        handler = getattr(self, f"_vna_{normalized}", None)
        if handler is None:
            return self._unsupported("vna", method)
        return handler(payload or {})

    def invoke_aedt(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = _normalize_method(method)
        handler = getattr(self, f"_aedt_{normalized}", None)
        if handler is None:
            return self._unsupported("aedt", method)
        return handler(payload or {})

    def invoke_hfss(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = _normalize_method(method)
        handler = getattr(self, f"_hfss_{normalized}", None)
        if handler is None:
            return self._planned("hfss", method)
        return handler(payload or {})

    def _vna_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        return self._ok(
            connected=self.registry.vna.state.connected,
            state=self._adapter_state(self.registry.vna.state),
            config=self._sweep_config(self.registry.vna.sweep_config),
            brand=self.vna_state.brand,
            methods=VNA_METHODS,
            last_sweep_points=len(self.vna_state.last_sweep),
        )

    def _vna_connect(self, payload: dict[str, Any]) -> dict[str, Any]:
        brand = str(payload.get("brand") or payload.get("targetType") or "SIM").upper()
        backend = str(payload.get("backend") or "").lower()
        resource = _first_text(payload, "resource", "visaAddress", "VISA_ADDRESS", "address")
        ip_addr = _first_text(payload, "IPaddr", "ip", "host", "hostname")
        if not resource and ip_addr:
            resource = f"TCPIP0::{ip_addr}::inst0::INSTR"

        if not backend:
            backend = "simulated" if brand in {"SIM", "MOCK", "OFFLINE"} and not ip_addr else "pyvisa"

        if backend == "simulated":
            adapter = SimulatedVnaAdapter(resource or f"SIM::{brand}")
        elif backend == "pyvisa":
            timeout_ms = int(payload.get("timeout_ms") or payload.get("timeout") or 30_000)
            if not resource:
                raise ValueError("VNA resource or IPaddr is required for pyvisa backend")
            adapter = PyVisaVnaAdapter(resource, timeout_ms=timeout_ms)
        else:
            raise ValueError(f"Unsupported VNA backend: {backend}")

        state = adapter.connect()
        self.registry.vna = adapter
        self.vna_state.brand = brand
        return self._ok(state=self._adapter_state(state), brand=brand)

    def _vna_close(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        resource = self.registry.vna.state.resource or "SIM::VNA"
        self.registry.vna = SimulatedVnaAdapter(resource)
        self.vna_state.last_sweep = []
        return self._ok(state=self._adapter_state(self.registry.vna.state))

    def _vna_reset(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        state = self.registry.vna.reset()
        self.vna_state.last_sweep = []
        self.vna_state.markers.clear()
        self.vna_state.traces.clear()
        return self._ok(state=self._adapter_state(state), config=self._sweep_config(self.registry.vna.sweep_config))

    def _vna_clearerrmsg(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        self.vna_state.errors.clear()
        return self._ok(errors=[])

    def _vna_initialize2(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        return self._ok(initialized=True)

    def _vna_loadpreset(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.vna_state.traces["preset"] = {"payload": payload}
        return self._ok(loaded=True, preset=payload)

    def _vna_setfrequency(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.registry.vna.sweep_config
        unit = str(payload.get("unit") or payload.get("freqUnit") or "").lower() or None
        start = _first(payload, "start_hz", "startHz")
        stop = _first(payload, "stop_hz", "stopHz")
        start_freq = _first(payload, "startFreq", "start", "start_frequency")
        stop_freq = _first(payload, "stopFreq", "stop", "stop_frequency")
        center = _first(payload, "center_hz", "centerHz")
        span = _first(payload, "span_hz", "spanHz")
        center_freq = _first(payload, "centerFreq", "center")
        span_freq = _first(payload, "spanFreq", "span")

        start_hz = _coerce_float(start) if start is not None else None
        stop_hz = _coerce_float(stop) if stop is not None else None
        if start_hz is None and start_freq is not None:
            start_hz = _frequency_to_hz(start_freq, unit)
        if stop_hz is None and stop_freq is not None:
            stop_hz = _frequency_to_hz(stop_freq, unit)

        center_hz = _coerce_float(center) if center is not None else None
        span_hz = _coerce_float(span) if span is not None else None
        if center_hz is None and center_freq is not None:
            center_hz = _frequency_to_hz(center_freq, unit)
        if span_hz is None and span_freq is not None:
            span_hz = _frequency_to_hz(span_freq, unit)

        if center_hz is not None or span_hz is not None:
            center_hz = center_hz if center_hz is not None else (current.start_hz + current.stop_hz) / 2
            span_hz = span_hz if span_hz is not None else current.stop_hz - current.start_hz
            start_hz = center_hz - span_hz / 2
            stop_hz = center_hz + span_hz / 2

        config = SweepConfig(
            start_hz=start_hz if start_hz is not None else current.start_hz,
            stop_hz=stop_hz if stop_hz is not None else current.stop_hz,
            points=current.points,
            ifbw_hz=current.ifbw_hz,
            power_dbm=current.power_dbm,
        )
        updated = self.registry.vna.configure_sweep(config)
        return self._ok(config=self._sweep_config(updated))

    def _vna_configuresweep(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.registry.vna.sweep_config
        config = SweepConfig(
            start_hz=_coerce_float(_first(payload, "start_hz", "startHz") or current.start_hz),
            stop_hz=_coerce_float(_first(payload, "stop_hz", "stopHz") or current.stop_hz),
            points=int(_coerce_float(_first(payload, "points", "sweepPoints") or current.points)),
            ifbw_hz=_coerce_float(_first(payload, "ifbw_hz", "ifbw", "bandwidth") or current.ifbw_hz),
            power_dbm=_coerce_float(_first(payload, "power_dbm", "power") or current.power_dbm),
        )
        return self._ok(config=self._sweep_config(self.registry.vna.configure_sweep(config)))

    def _vna_setifbw(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.registry.vna.sweep_config
        ifbw = _coerce_float(_first(payload, "ifbw_hz", "ifbw", "bandwidth", "value"))
        config = SweepConfig(
            start_hz=current.start_hz,
            stop_hz=current.stop_hz,
            points=current.points,
            ifbw_hz=ifbw,
            power_dbm=current.power_dbm,
        )
        return self._ok(config=self._sweep_config(self.registry.vna.configure_sweep(config)))

    def _vna_setpower(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.registry.vna.sweep_config
        power = _coerce_float(_first(payload, "power_dbm", "power", "value"))
        config = SweepConfig(
            start_hz=current.start_hz,
            stop_hz=current.stop_hz,
            points=current.points,
            ifbw_hz=current.ifbw_hz,
            power_dbm=power,
        )
        return self._ok(config=self._sweep_config(self.registry.vna.configure_sweep(config)))

    def _vna_setsweeppoints(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.registry.vna.sweep_config
        points = int(_coerce_float(_first(payload, "points", "sweepPoints", "numPoints", "value")))
        config = SweepConfig(
            start_hz=current.start_hz,
            stop_hz=current.stop_hz,
            points=points,
            ifbw_hz=current.ifbw_hz,
            power_dbm=current.power_dbm,
        )
        return self._ok(config=self._sweep_config(self.registry.vna.configure_sweep(config)))

    def _vna_setsweeptype(self, payload: dict[str, Any]) -> dict[str, Any]:
        sweep_type = str(_first(payload, "sweepType", "type", "value") or "LIN").upper()
        self.vna_state.sweep_type = sweep_type
        return self._ok(sweep_type=sweep_type)

    def _vna_setcontinoussweep(self, payload: dict[str, Any]) -> dict[str, Any]:
        enabled = bool(_first(payload, "enabled", "on", "continuous", "value"))
        self.vna_state.continuous_sweep = enabled
        return self._ok(continuous_sweep=enabled)

    def _vna_settrace(self, payload: dict[str, Any]) -> dict[str, Any]:
        trace_id = str(_first(payload, "trace", "traceNum", "index", "sensorNum") or len(self.vna_state.traces) + 1)
        self.vna_state.traces[trace_id] = dict(payload)
        return self._ok(trace=trace_id, traces=self.vna_state.traces)

    def _vna_settracestatus(self, payload: dict[str, Any]) -> dict[str, Any]:
        trace_id = str(_first(payload, "trace", "traceNum", "index", "sensorNum") or "1")
        trace = self.vna_state.traces.setdefault(trace_id, {})
        trace["visible"] = bool(_first(payload, "visible", "enabled", "on", "value"))
        return self._ok(trace=trace_id, traces=self.vna_state.traces)

    def _vna_setmarkers(self, payload: dict[str, Any]) -> dict[str, Any]:
        marker_id = str(_first(payload, "marker", "markerNum", "index") or len(self.vna_state.markers) + 1)
        self.vna_state.markers[marker_id] = dict(payload)
        return self._ok(marker=marker_id, markers=self.vna_state.markers)

    def _vna_setautoscaletrace(self, payload: dict[str, Any]) -> dict[str, Any]:
        trace_id = str(_first(payload, "trace", "traceNum", "index") or "1")
        trace = self.vna_state.traces.setdefault(trace_id, {})
        trace["autoscale"] = True
        return self._ok(trace=trace_id, traces=self.vna_state.traces)

    def _vna_getsweeptime(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        config = self.registry.vna.sweep_config
        seconds = max(0.05, config.points / max(config.ifbw_hz, 1.0) * 0.025)
        return self._ok(time=seconds)

    def _vna_getmarkeryvalue(self, payload: dict[str, Any]) -> dict[str, Any]:
        marker_freq = _first(payload, "freq_hz", "frequency", "freq", "x")
        if marker_freq is None or not self.vna_state.last_sweep:
            return self._ok(value=None)
        freq_hz = _frequency_to_hz(marker_freq, str(payload.get("unit") or "").lower() or None)
        nearest = min(self.vna_state.last_sweep, key=lambda point: abs(point["freq_hz"] - freq_hz))
        return self._ok(value=nearest["s11_db"], point=nearest)

    def _vna_savetracedata(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = _first_text(payload, "filePath", "path", "output", "filename") or "data/vna_trace.s2p"
        output = self.registry.vna.save_touchstone(path)
        return self._ok(filePath=str(output), path=str(output))

    def _vna_exports2p(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._vna_savetracedata(payload)

    def _vna_savetouchstone(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._vna_savetracedata(payload)

    def _vna_deleteallmarkers(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        self.vna_state.markers.clear()
        return self._ok(markers={})

    def _vna_deletetraces(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        self.vna_state.traces.clear()
        return self._ok(traces={})

    def _vna_singlesweep(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        points = self.registry.vna.single_sweep()
        self.vna_state.last_sweep = [_point_summary(point) for point in points]
        return self._ok(config=self._sweep_config(self.registry.vna.sweep_config), data=self.vna_state.last_sweep)

    def _vna_beginbackgroundsweep(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        self.vna_state.background_sweep = True
        return self._ok(background_sweep=True)

    def _vna_endbackgroundsweep(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        self.vna_state.background_sweep = False
        return self._ok(background_sweep=False)

    def _aedt_openproject(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = _first_text(payload, "project_path", "project", "file", "filename")
        design = _first_text(payload, "design_name", "design", "designName")
        backend = str(payload.get("backend") or ("pyaedt" if project else "simulated")).lower()
        if backend == "simulated":
            adapter = SimulatedAedtAdapter()
        elif backend == "pyaedt":
            adapter = PyAedtAdapter()
        else:
            raise ValueError(f"Unsupported AEDT backend: {backend}")

        state = adapter.connect(
            project_path=project,
            design_name=design,
            new_desktop=bool(payload.get("new_desktop", False)),
            non_graphical=bool(payload.get("non_graphical", False)),
        )
        self.registry.aedt = adapter
        self.aedt_state.active_design = design or state.detail
        return self._ok(state=self._adapter_state(state), designs=self._safe_designs())

    def _aedt_getdesigns(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        designs = self.registry.aedt.list_designs()
        return self._ok(designs=designs, data=designs)

    def _aedt_setactivedesign(self, payload: dict[str, Any]) -> dict[str, Any]:
        design = _first_text(payload, "design_name", "design", "designName", "name")
        if not design:
            raise ValueError("design name is required")
        state = self.registry.aedt.connect(
            project_path=None if self.registry.aedt.state.resource == "SIM::AEDT" else self.registry.aedt.state.resource,
            design_name=design,
            new_desktop=False,
            non_graphical=False,
        )
        self.aedt_state.active_design = design
        return self._ok(state=self._adapter_state(state), active_design=design)

    def _aedt_getvariables(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        variables = self.registry.aedt.get_variables()
        return self._ok(variables=variables, names=list(variables), values=list(variables.values()))

    def _aedt_getvariablesvalue(self, payload: dict[str, Any]) -> dict[str, Any]:
        variables = self.registry.aedt.get_variables()
        names = payload.get("names")
        if isinstance(names, list):
            variables = {str(name): variables.get(str(name), "") for name in names}
        return self._ok(variables=variables, names=list(variables), values=list(variables.values()))

    def _aedt_setvariablesvalue(self, payload: dict[str, Any]) -> dict[str, Any]:
        variables = _variables_from_payload(payload)
        updated = self.registry.aedt.set_variables(variables)
        return self._ok(variables=updated, names=list(updated), values=list(updated.values()))

    def _aedt_setsettings(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.aedt_state.settings.update(payload)
        return self._ok(settings=self.aedt_state.settings)

    def _aedt_createreport(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._planned("aedt", "createreport", payload=payload)

    def _aedt_makelpfmodel(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._planned("aedt", "makelpfmodel", payload=payload)

    def _aedt_evaluatedimension(self, payload: dict[str, Any]) -> dict[str, Any]:
        variables = _variables_from_payload(payload, names_key="names", values_key="dimension")
        if variables:
            self.registry.aedt.set_variables(variables)
        output = _touchstone_output_from_payload(payload)
        result = self.registry.aedt.analyze(
            setup_name=str(payload.get("setup_name") or payload.get("setup") or "SynMatrix"),
            sweep_name=str(payload.get("sweep_name") or payload.get("sweep") or "FreqSweep"),
            output_touchstone=output,
        )
        self.aedt_state.last_analysis = result
        return self._ok(result=result, variables=variables)

    def _aedt_evaluatedimensionnos2p(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = dict(payload)
        payload.pop("output", None)
        payload.pop("output_touchstone", None)
        payload.pop("tempFileName", None)
        result = self._aedt_evaluatedimension(payload)
        result["result"]["touchstone"] = None
        return result

    def _aedt_callconvergence(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._planned("aedt", "callconvergence", payload=payload)

    def _aedt_callkillmesh(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._planned("aedt", "callkillmesh", payload=payload)

    def _aedt_stop(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        return self._ok(stopped=True)

    def _hfss_openproject(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._aedt_openproject(payload)

    def _hfss_closeproject(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        self.registry.aedt = SimulatedAedtAdapter()
        self.aedt_state = AedtSessionState()
        return self._ok(state=self._adapter_state(self.registry.aedt.state))

    def _hfss_updatevalues(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._aedt_setvariablesvalue(payload)

    def _hfss_analyzeall(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._aedt_evaluatedimensionnos2p(payload)

    def _hfss_ping(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        return self._ok(pong=True)

    def _adapter_state(self, state: AdapterState) -> dict[str, Any]:
        return {
            "connected": state.connected,
            "backend": state.backend,
            "resource": state.resource,
            "detail": state.detail,
        }

    def _safe_designs(self) -> list[str]:
        try:
            return self.registry.aedt.list_designs()
        except RuntimeError:
            return []

    def _sweep_config(self, config: SweepConfig) -> dict[str, float | int]:
        return {
            "start_hz": config.start_hz,
            "stop_hz": config.stop_hz,
            "points": config.points,
            "ifbw_hz": config.ifbw_hz,
            "power_dbm": config.power_dbm,
        }

    def _ok(self, **data: Any) -> dict[str, Any]:
        return {"status": 0, "ok": True, **data}

    def _unsupported(self, category: str, method: str) -> dict[str, Any]:
        return {
            "status": -404,
            "ok": False,
            "category": category,
            "method": method,
            "message": "Method is not part of the current compatibility surface.",
        }

    def _planned(self, category: str, method: str, **data: Any) -> dict[str, Any]:
        return {
            "status": -501,
            "ok": False,
            "implemented": False,
            "category": category,
            "method": method,
            "message": "Endpoint is reserved for the SymMatrix-compatible roadmap.",
            **data,
        }


def _normalize_method(method: str) -> str:
    return method.replace("-", "").replace("_", "").lower()


def _first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def _first_text(payload: dict[str, Any], *keys: str) -> str | None:
    value = _first(payload, *keys)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_float(value: Any) -> float:
    if value is None:
        raise ValueError("numeric value is required")
    return float(str(value).strip())


def _frequency_to_hz(value: Any, unit: str | None = None) -> float:
    numeric = _coerce_float(value)
    if unit in {"hz", "hertz"}:
        return numeric
    if unit in {"khz", "kilohz", "kilohertz"}:
        return numeric * 1_000
    if unit in {"mhz", "megahz", "megahertz"}:
        return numeric * 1_000_000
    if unit in {"ghz", "gigahz", "gigahertz"}:
        return numeric * 1_000_000_000
    if abs(numeric) < 100:
        return numeric * 1_000_000_000
    if abs(numeric) < 100_000:
        return numeric * 1_000_000
    return numeric


def _variables_from_payload(
    payload: dict[str, Any],
    *,
    names_key: str = "names",
    values_key: str = "values",
) -> dict[str, str | float | int]:
    variables = payload.get("variables")
    if isinstance(variables, dict):
        return dict(variables)
    names = payload.get(names_key)
    values = payload.get(values_key)
    if names is None or values is None:
        return {}
    if not isinstance(names, list) or not isinstance(values, list):
        raise TypeError(f"{names_key} and {values_key} must be lists")
    if len(names) != len(values):
        raise ValueError(f"{names_key} and {values_key} must have the same length")
    return {str(name): value for name, value in zip(names, values, strict=True)}


def _touchstone_output_from_payload(payload: dict[str, Any]) -> str | None:
    explicit = _first_text(payload, "output_touchstone", "touchstone", "filePath")
    if explicit:
        return explicit
    output_dir = _first_text(payload, "output", "outputDir")
    temp_name = _first_text(payload, "tempFileName", "runName", "name")
    if not output_dir and not temp_name:
        return None
    filename = temp_name or "hfss_export"
    if not filename.lower().endswith(".s2p"):
        filename = f"{filename}.s2p"
    return str(Path(output_dir or "data") / filename)


def _point_summary(point: NetworkPoint) -> dict[str, float]:
    s11_mag = abs(point.s11)
    s21_mag = abs(point.s21)
    return {
        **point.to_json(),
        "s11_db": _mag_to_db(s11_mag),
        "s21_db": _mag_to_db(s21_mag),
    }


def _mag_to_db(value: float) -> float:
    import math

    return 20 * math.log10(max(value, 1e-12))
