from hfss_vna_bridge.web.app import create_app


def test_flask_health_and_index() -> None:
    app = create_app()
    client = app.test_client()

    health = client.get("/health")
    index = client.get("/")

    assert health.status_code == 200
    assert health.get_json()["supported"]["vna"]
    assert index.status_code == 200
    assert b"HFSS VNA Bridge" in index.data


def test_symmatrix_vna_compatibility_flow(tmp_path) -> None:
    app = create_app()
    client = app.test_client()

    assert client.post("/connect", json={"backend": "simulated", "brand": "SIM"}).get_json()["status"] == 0
    assert client.post("/setfrequency", json={"startFreq": 0.6, "stopFreq": 1.1}).get_json()["status"] == 0
    assert client.post("/setsweeppoints", json={"points": 9}).get_json()["status"] == 0

    sweep = client.post("/singlesweep", json={}).get_json()

    assert sweep["status"] == 0
    assert len(sweep["data"]) == 9

    output = tmp_path / "trace.s2p"
    saved = client.post("/savetracedata", json={"filePath": str(output)}).get_json()

    assert saved["status"] == 0
    assert output.exists()


def test_flask_rest_aliases_on_default_server() -> None:
    app = create_app()
    client = app.test_client()

    connect = client.post("/vna/connect", json={"backend": "simulated"}).get_json()
    config = client.post(
        "/vna/configure-sweep",
        json={"start_hz": 600_000_000, "stop_hz": 1_100_000_000, "points": 7},
    ).get_json()
    sweep = client.post("/vna/single-sweep", json={}).get_json()
    aedt = client.post("/aedt/session", json={"backend": "simulated"}).get_json()

    assert connect["status"] == 0
    assert config["config"]["points"] == 7
    assert len(sweep["data"]) == 7
    assert aedt["status"] == 0


def test_symmatrix_aedt_compatibility_flow(tmp_path) -> None:
    app = create_app()
    client = app.test_client()

    opened = client.post(
        "/aedt/openproject",
        json={"backend": "simulated", "design_name": "MvpDesign"},
    ).get_json()
    assert opened["status"] == 0

    variables = client.post(
        "/aedt/setvariablesvalue",
        json={"names": ["arm_scale_a"], "values": [1.04]},
    ).get_json()
    assert variables["status"] == 0
    assert variables["variables"]["arm_scale_a"] == "1.04"

    output = tmp_path / "hfss.s2p"
    evaluated = client.post(
        "/aedt/evaluatedimension",
        json={"names": ["dist_refletor"], "dimension": ["22mm"], "output_touchstone": str(output)},
    ).get_json()

    assert evaluated["status"] == 0
    assert output.exists()


def test_symmatrix_hfss_planned_surface() -> None:
    app = create_app()
    client = app.test_client()

    response = client.post("/hfss/full3dsimulation", json={})

    assert response.status_code == 200
    assert response.get_json()["status"] == -501
