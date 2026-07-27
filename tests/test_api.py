from fastapi.testclient import TestClient

from hfss_vna_bridge.api.app import create_app
from hfss_vna_bridge.settings import Settings


def test_health_reports_simulated_defaults() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["aedt"]["backend"] == "simulated"
    assert payload["vna"]["backend"] == "simulated"


def test_simulated_vna_sweep() -> None:
    client = TestClient(create_app())

    assert client.post("/vna/connect", json={"backend": "simulated", "resource": "SIM::VNA"}).status_code == 200
    config = {
        "start_hz": 600_000_000,
        "stop_hz": 1_100_000_000,
        "points": 11,
        "ifbw_hz": 1_000,
        "power_dbm": -10,
    }
    assert client.post("/vna/configure-sweep", json=config).status_code == 200

    response = client.post("/vna/single-sweep")

    assert response.status_code == 200
    payload = response.json()
    assert payload["config"]["points"] == 11
    assert len(payload["points"]) == 11
    assert payload["points"][0]["freq_hz"] == 600_000_000


def test_simulated_aedt_variables_roundtrip() -> None:
    client = TestClient(create_app())

    response = client.post("/aedt/session", json={"backend": "simulated", "design_name": "UnitTest"})
    assert response.status_code == 200

    response = client.post("/aedt/variables", json={"variables": {"arm_scale_a": 1.02}})

    assert response.status_code == 200
    assert response.json()["arm_scale_a"] == "1.02"


def test_fastapi_engineering_and_project_surfaces(tmp_path) -> None:
    client = TestClient(create_app(Settings(project_dir=tmp_path / "projects")))

    line = client.post(
        "/engineering/transmission-line",
        json={
            "kind": "microstrip",
            "width_mm": 2.9,
            "height_mm": 1.6,
            "epsilon_r": 4.4,
            "frequency_ghz": 1,
        },
    )
    project = client.post(
        "/projects",
        json={
            "name": "API Project",
            "specification": {"filter_type": "BPF", "order": 4},
        },
    )

    assert line.status_code == 200
    assert line.json()["impedance_ohm"] > 0
    assert project.status_code == 200
    project_id = project.json()["project"]["id"]
    assert client.get(f"/projects/{project_id}").status_code == 200
