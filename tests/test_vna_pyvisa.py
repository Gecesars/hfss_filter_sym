from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from hfss_vna_bridge.adapters.vna.pyvisa_adapter import PyVisaVnaAdapter
from hfss_vna_bridge.core.models import SweepConfig


class FakeInstrument:
    def __init__(self) -> None:
        self.timeout = 0
        self.selected = "S11"
        self.closed = False
        self.writes: list[str] = []

    def write(self, command: str) -> None:
        self.writes.append(command)
        if "PAR:SEL" in command:
            self.selected = command.split("HFSSFS_", 1)[1].split("'", 1)[0]

    def query(self, command: str) -> str:
        if command == "*IDN?":
            return "Keysight Technologies,N5222B,MY123,1.0"
        if command == "SYST:ERR?":
            return '0,"No error"'
        if "SWE:TIME?" in command:
            return "0.2"
        if command == "*OPC?":
            return "1"
        return "0"

    def query_ascii_values(self, command: str, separator: str = ",") -> list[float]:
        del separator
        if "FREQ:DATA?" in command:
            return [1e9, 1.1e9, 1.2e9]
        values = {
            "S11": [0.1, 0, 0.2, 0, 0.3, 0],
            "S21": [0.8, 0, 0.7, 0, 0.6, 0],
            "S12": [0.79, 0, 0.69, 0, 0.59, 0],
            "S22": [0.11, 0, 0.21, 0, 0.31, 0],
        }
        return values[self.selected]

    def close(self) -> None:
        self.closed = True


class FakeManager:
    def __init__(self, instrument: FakeInstrument) -> None:
        self.instrument = instrument
        self.closed = False
        self.visalib = "fake"

    def open_resource(self, resource: str) -> FakeInstrument:
        assert resource == "TCPIP0::vna::INSTR"
        return self.instrument

    def list_resources(self) -> tuple[str, ...]:
        return ("TCPIP0::vna::INSTR",)

    def close(self) -> None:
        self.closed = True


def test_pyvisa_adapter_acquires_full_two_port(monkeypatch: pytest.MonkeyPatch) -> None:
    instrument = FakeInstrument()
    manager = FakeManager(instrument)
    monkeypatch.setitem(
        sys.modules,
        "pyvisa",
        SimpleNamespace(ResourceManager=lambda *args: manager),
    )
    adapter = PyVisaVnaAdapter("TCPIP0::vna::INSTR", brand="KS", channel=2)

    state = adapter.connect()
    adapter.configure_sweep(
        SweepConfig(start_hz=1e9, stop_hz=1.2e9, points=3, ifbw_hz=1000, power_dbm=-10)
    )
    adapter.set_continuous(True)
    points = adapter.single_sweep()

    assert state.connected is True
    assert adapter.capabilities()["profile"] == "KEYSIGHT"
    assert len(points) == 3
    assert points[0].s11 == 0.1 + 0j
    assert points[0].s21 == 0.8 + 0j
    assert points[0].s12 == 0.79 + 0j
    assert points[0].s22 == 0.11 + 0j
    assert any(
        "CALC2:PAR:DEF:EXT" in command and "S21" in command
        for command in instrument.writes
    )
    assert "SENS2:FREQ:STAR 1000000000.0" in instrument.writes
    assert adapter.capabilities()["channel"] == 2
    assert adapter.sweep_time() == 0.2
    assert adapter.query_errors() == []
    assert adapter.clear_errors() == []
    assert "*CLS" in instrument.writes
    assert instrument.writes[-1] == "*CLS"
    assert instrument.writes.count("INIT2:CONT ON") == 2
    adapter.close()
    assert instrument.closed is True
