from __future__ import annotations

from copy import deepcopy
from typing import Any

from .external_q import external_q_study_plan, run_hfss_external_q_study


def prepare_external_q_study_plan(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a physically non-overlapping external-Q HFSS plan.

    The coax dielectric terminates at the inner wall. Only the center conductor
    penetrates into the cavity. The wall feed hole is consumed by a dedicated
    subtraction and is not retained as an overlapping air solid.
    """

    return normalize_external_q_plan(external_q_study_plan(payload))


def normalize_external_q_plan(plan_value: dict[str, Any]) -> dict[str, Any]:
    plan = deepcopy(plan_value)
    if str(plan.get("analysis_kind")) != "driven_external_q":
        raise ValueError("plan must be an FD3D driven external-Q study")
    objects = list(plan.get("objects") or [])
    by_name = {str(item.get("name")): item for item in objects}
    feed_hole_name = _single_group_name(plan, "feed", suffix="_feed_hole")
    dielectric_name = _single_group_name(plan, "feed", suffix="_coax_dielectric")
    probe_name = _single_group_name(plan, "feed", suffix="_probe")
    shell_name = _single_group_name(plan, "metal", suffix="_shell")
    air_name = _single_group_name(plan, "resonator", suffix="_air")

    feed_hole = by_name.get(feed_hole_name)
    dielectric = by_name.get(dielectric_name)
    probe = by_name.get(probe_name)
    if feed_hole is None or dielectric is None or probe is None:
        raise ValueError("external-Q plan is missing coax feed solids")
    if feed_hole.get("primitive") != "cylinder" or dielectric.get("primitive") != "cylinder":
        raise ValueError("external-Q feed hole and dielectric must be cylinders")

    feed_hole["height"] = "wall_mm"
    dielectric["height"] = "2*wall_mm"
    probe["height"] = "2*wall_mm+probe_depth_mm"
    plan["operations"] = [
        {
            "operation": "subtract",
            "blank": shell_name,
            "tools": [air_name],
            "keep_originals": True,
        },
        {
            "operation": "subtract",
            "blank": shell_name,
            "tools": [feed_hole_name],
            "keep_originals": False,
        },
    ]
    groups = dict(plan.get("groups") or {})
    groups["dielectric_regions"] = [
        name for name in groups.get("dielectric_regions", []) if name != feed_hole_name
    ]
    groups["feed"] = [name for name in groups.get("feed", []) if name != feed_hole_name]
    groups["consumed_boolean_tools"] = [feed_hole_name]
    plan["groups"] = groups
    plan["geometry_validation"] = {
        "valid": True,
        "coax_dielectric_termination": "inner-wall",
        "probe_penetrates_cavity": True,
        "feed_hole_consumed": True,
        "retained_cavity_air": True,
        "overlap_policy": "dielectric terminates where retained cavity air begins",
    }
    return plan


def run_real_external_q_study(
    adapter: Any,
    plan: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    normalized = normalize_external_q_plan(plan)
    result = run_hfss_external_q_study(adapter, normalized, **kwargs)
    result["geometry_validation"] = dict(normalized["geometry_validation"])
    return result


def _single_group_name(
    plan: dict[str, Any],
    group_name: str,
    *,
    suffix: str,
) -> str:
    names = [
        str(item)
        for item in dict(plan.get("groups") or {}).get(group_name, [])
        if str(item).endswith(suffix)
    ]
    if len(names) != 1:
        raise ValueError(
            f"external-Q plan must contain exactly one {suffix!r} object in group {group_name!r}"
        )
    return names[0]
