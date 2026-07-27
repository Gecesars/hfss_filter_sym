from pathlib import Path
from types import SimpleNamespace

from hfss_vna_bridge.adapters.aedt.installations import detect_aedt_installations
from hfss_vna_bridge.adapters.aedt.pyaedt_adapter import PyAedtAdapter


def test_detect_aedt_2026_from_environment(tmp_path) -> None:
    root = tmp_path / "v261" / "AnsysEM"
    root.mkdir(parents=True)
    executable = root / "ansysedt.exe"
    executable.touch()

    installations = detect_aedt_installations(
        {
            "ANSYSEM_ROOT261": str(root),
            "ProgramFiles": str(tmp_path / "empty-program-files"),
        }
    )

    assert len(installations) == 1
    assert installations[0].version == "2026.1"
    assert installations[0].executable == executable.resolve()


def test_pyaedt_adapter_uses_2026_contract_and_output_file(
    monkeypatch,
    tmp_path,
) -> None:
    import ansys.aedt.core

    import hfss_vna_bridge.adapters.aedt.pyaedt_adapter as adapter_module

    project = tmp_path / "filter.aedt"
    project.touch()
    captured: dict[str, object] = {}

    class FakeHfss:
        valid_design = True
        design_name = "FilterDesign"
        project_name = "filter"
        project_file = str(project)
        design_type = "HFSS"
        solution_type = "Modal"
        variable_manager = SimpleNamespace(
            variables={"width": SimpleNamespace(expression="10mm")},
            design_variables={},
            project_variables={},
        )
        desktop_class = SimpleNamespace(
            aedt_version_id="2026.1",
            aedt_version="2026.1.0",
            aedt_process_id=1234,
            port=50051,
            is_grpc_api=True,
            aedt_install_dir=r"C:\Program Files\ANSYS Inc\v261\AnsysEM",
        )

        def __init__(self, **kwargs) -> None:
            captured["connect"] = kwargs

        def get_setups(self):
            return ["Setup1"]

        def get_sweeps(self, setup):
            assert setup == "Setup1"
            return ["Sweep1"]

        def analyze_setup(self, name, **kwargs):
            captured["analyze"] = {"name": name, **kwargs}
            return True

        def export_touchstone(self, **kwargs):
            captured["export"] = kwargs
            output = Path(kwargs["output_file"])
            output.write_text("# Hz S RI R 50\n", encoding="ascii")
            return str(output)

        def release_desktop(self, **kwargs):
            captured["release"] = kwargs
            return True

    monkeypatch.setattr(ansys.aedt.core, "Hfss", FakeHfss)
    monkeypatch.setattr(adapter_module, "detect_running_aedt_sessions", list)

    adapter = PyAedtAdapter()
    state = adapter.connect(
        project_path=project,
        design_name="FilterDesign",
        version="2026.1",
        new_desktop=True,
        non_graphical=True,
    )
    output = tmp_path / "network.s2p"
    result = adapter.analyze(output_touchstone=output, cores=4)
    adapter.release(close_projects=True, close_desktop=True)

    assert state.connected is True
    assert captured["connect"]["version"] == "2026.1"
    assert captured["connect"]["project"] == str(project.resolve())
    assert captured["analyze"]["name"] == "Setup1"
    assert captured["analyze"]["cores"] == 4
    assert captured["export"]["setup"] == "Setup1"
    assert captured["export"]["sweep"] == "Sweep1"
    assert captured["export"]["output_file"] == str(output.resolve())
    assert result["touchstone"] == str(output.resolve())
    assert captured["release"] == {"close_projects": True, "close_desktop": True}
