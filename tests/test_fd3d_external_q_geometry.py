from __future__ import annotations

from hfss_vna_bridge.fd3d.external_q_workflow import prepare_external_q_study_plan
from hfss_vna_bridge.services.fd3d import create_project_blueprint


def _probe_component() -> dict:
    project = create_project_blueprint(
        {
            "name": "External Q geometry",
            "technology": "combline",
            "specification": {
                "filter_type": "BPF",
                "response_family": "chebyshev",
                "order": 3,
                "return_loss_db": 20.0,
                "f0_ghz": 1.0,
                "bandwidth_ghz": 0.05,
                "start_ghz": 0.9,
                "stop_ghz": 1.1,
                "points": 201,
            },
        }
    )["project"]
    return next(item for item in project["components"] if item["kind"] == "EXTERNAL_COUPLING")


def test_external_q_coax_dielectric_stops_at_inner_wall() -> None:
    plan = prepare_external_q_study_plan(
        {
            "component": _probe_component(),
            "center_frequency_ghz": 1.0,
            "sample_values": [8.0, 12.0, 16.0],
            "dry_run": False,
        }
    )
    objects = {item["name"]: item for item in plan["objects"]}
    feed_hole = next(name for name in objects if name.endswith("_feed_hole"))
    dielectric = next(name for name in objects if name.endswith("_coax_dielectric"))
    probe = next(name for name in objects if name.endswith("_probe"))

    assert objects[feed_hole]["height"] == "wall_mm"
    assert objects[dielectric]["height"] == "2*wall_mm"
    assert objects[probe]["height"] == "2*wall_mm+probe_depth_mm"
    assert plan["operations"][0]["keep_originals"] is True
    assert plan["operations"][1]["tools"] == [feed_hole]
    assert plan["operations"][1]["keep_originals"] is False
    assert feed_hole not in plan["groups"]["feed"]
    assert feed_hole not in plan["groups"]["dielectric_regions"]
    assert plan["groups"]["consumed_boolean_tools"] == [feed_hole]
    assert plan["geometry_validation"]["valid"] is True
