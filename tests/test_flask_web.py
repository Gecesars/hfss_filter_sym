from hfss_vna_bridge.web.app import create_app


def test_flask_health_and_index() -> None:
    app = create_app()
    client = app.test_client()

    health = client.get("/health")
    index = client.get("/")

    assert health.status_code == 200
    assert health.get_json()["supported"]["vna"]
    assert index.status_code == 200
    assert b"HFSS Filter Studio" in index.data
    assert b"Coupling Matrix" in index.data


def test_filter_synthesis_returns_chart_matrix_and_topology() -> None:
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/synthesis/calculate",
        json={
            "filter_type": "BPF",
            "order": 4,
            "return_loss_db": 25,
            "f0_ghz": 1,
            "bandwidth_ghz": 0.05,
            "start_ghz": 0.875,
            "stop_ghz": 1.125,
            "points": 301,
            "zeros": [{"frequency_ghz": 1.08, "depth_db": 60}],
        },
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data["status"] == 0
    assert len(data["series"]["frequencies_ghz"]) == 301
    assert len(data["series"]["s11_db"]) == 301
    assert data["matrix"]["labels"] == ["S", "1", "2", "3", "4", "L"]
    assert len(data["matrix"]["values"]) == 6
    assert len(data["topology"]["nodes"]) == 6
    assert any(edge["kind"] == "cross" for edge in data["topology"]["edges"])


def test_filter_synthesis_rejects_invalid_frequency_span() -> None:
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/synthesis/calculate",
        json={"start_ghz": 1.2, "stop_ghz": 1.0},
    )

    assert response.status_code == 400
    assert response.get_json()["status"] == -400


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


def test_aedt_2026_operational_surface_in_simulation() -> None:
    app = create_app()
    client = app.test_client()

    opened = client.post(
        "/aedt/openproject",
        json={"backend": "simulated", "version": "2026.1"},
    ).get_json()
    report = client.post(
        "/aedt/createreport",
        json={"expressions": ["dB(S(1,1))"], "setup": "SynMatrix"},
    ).get_json()
    convergence = client.post(
        "/aedt/callconvergence",
        json={"setup": "SynMatrix", "output_file": "data/convergence.conv"},
    ).get_json()
    mesh = client.post("/aedt/callkillmesh", json={"mesh": True}).get_json()
    saved = client.post("/hfss/saveproject", json={}).get_json()

    assert opened["session"]["version"] == "2026.1"
    assert report["report"]["expressions"] == ["dB(S(1,1))"]
    assert convergence["output_file"].endswith("convergence.conv")
    assert mesh["removed"] is True
    assert saved["project_path"] == "SIM::AEDT"
