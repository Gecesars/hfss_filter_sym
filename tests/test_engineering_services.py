from threading import Event

from hfss_vna_bridge.engines.engineering import (
    monte_carlo_filter,
    optimize_filter_specification,
    transmission_line,
    tuning_recommendations,
)
from hfss_vna_bridge.services.jobs import JobManager
from hfss_vna_bridge.services.modeling import model_plan
from hfss_vna_bridge.services.multiplexer import synthesize_multiplexer
from hfss_vna_bridge.services.project_store import ProjectStore


def test_model_plans_cover_cavity_planar_and_siw() -> None:
    cavity = model_plan("buildcavityfull3d", {"order": 4, "dry_run": True})
    planar = model_plan("planarupdatemodel", {"recipe": "planar", "order": 3})
    siw = model_plan("siwfull3d", {"order": 2, "recipe": "siw"})

    assert cavity["recipe"] == "cavity"
    assert len(cavity["groups"]["resonators"]) == 4
    assert len(cavity["ports"]) == 2
    assert any(item["name"].endswith("_substrate") for item in planar["objects"])
    assert siw["groups"]["vias"]


def test_project_store_versions_and_restores(tmp_path) -> None:
    store = ProjectStore(tmp_path / "projects")
    created = store.create(
        {
            "name": "Bandpass",
            "specification": {"filter_type": "BPF", "order": 4, "f0_ghz": 1.0},
        }
    )
    updated = store.update(
        created["id"],
        {"specification": {"filter_type": "BPF", "order": 5, "f0_ghz": 1.1}},
    )
    restored = store.restore(created["id"], 1)

    assert updated["revision"] == 2
    assert restored["revision"] == 3
    assert restored["specification"]["order"] == 4
    assert len(store.versions(created["id"])) == 3
    assert store.delete(created["id"]) is True


def test_engineering_calculators_and_tuning() -> None:
    microstrip = transmission_line(
        {
            "kind": "microstrip",
            "width_mm": 2.9,
            "height_mm": 1.6,
            "epsilon_r": 4.4,
            "frequency_ghz": 1,
        }
    )
    waveguide = transmission_line(
        {"kind": "rectangular_waveguide", "a_mm": 22.86, "b_mm": 10.16, "frequency_ghz": 10}
    )
    tuning = tuning_recommendations(
        {"center_hz": 1e9, "bandwidth_3db_hz": 50e6, "minimum_s11_db": -25},
        {"center_hz": 0.995e9, "bandwidth_3db_hz": 46e6, "minimum_s11_db": -18},
    )

    assert 40 < microstrip["impedance_ohm"] < 70
    assert waveguide["operating_above_cutoff"] is True
    assert len(tuning["actions"]) == 3
    assert tuning["errors"]["center_hz"] == 5e6


def test_monte_carlo_optimizer_and_multiplexer() -> None:
    specification = {
        "filter_type": "BPF",
        "order": 3,
        "return_loss_db": 20,
        "f0_ghz": 1,
        "bandwidth_ghz": 0.08,
        "start_ghz": 0.8,
        "stop_ghz": 1.2,
        "points": 101,
    }
    monte_carlo = monte_carlo_filter({"specification": specification, "samples": 10, "seed": 7})
    optimized = optimize_filter_specification(
        {
            "specification": specification,
            "variables": {
                "f0_ghz": [0.98, 1.02],
                "bandwidth_ghz": [0.07, 0.09],
            },
            "max_iterations": 1,
            "population": 4,
        }
    )
    multiplexer = synthesize_multiplexer(
        {
            "start_ghz": 0.8,
            "stop_ghz": 1.3,
            "points": 101,
            "channels": [
                {"name": "Low", "f0_ghz": 0.95, "bandwidth_ghz": 0.05, "order": 3},
                {"name": "High", "f0_ghz": 1.15, "bandwidth_ghz": 0.05, "order": 3},
            ],
        }
    )

    assert monte_carlo["samples"] == 10
    assert 0 <= monte_carlo["yield_percent"] <= 100
    assert optimized["evaluations"] > 0
    assert len(multiplexer["channels"]) == 2
    assert len(multiplexer["series"]["s21_db"]) == 101


def test_cancelling_queued_job_does_not_stop_running_backend() -> None:
    manager = JobManager(max_workers=1)
    started = Event()
    release = Event()
    stop_calls: list[bool] = []

    def running_operation(cancel_event, progress):
        del cancel_event, progress
        started.set()
        release.wait(timeout=2)
        return {"completed": True}

    manager.submit("running", {}, running_operation)
    assert started.wait(timeout=1)
    queued = manager.submit("queued", {}, running_operation)

    cancelled = manager.cancel(
        queued["id"],
        stop=lambda: stop_calls.append(True) or True,
    )
    release.set()

    assert cancelled["state"] == "cancelled"
    assert stop_calls == []
