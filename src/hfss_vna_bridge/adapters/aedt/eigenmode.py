from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4


def run_hfss_eigenmode_study(
    adapter: Any,
    plan: dict[str, Any],
    *,
    cores: int | None = None,
    tasks: int | None = None,
    gpus: int | None = None,
    save_project: bool = True,
) -> dict[str, Any]:
    """Build and solve an FD3D component study in the real HFSS Eigenmode solver.

    This function intentionally rejects simulated adapters. Characterization data
    returned here is eligible for engineering review because every sample is
    produced by an HFSS solve. Approval is still a separate user action.
    """

    state = getattr(adapter, "state", None)
    if state is None or not getattr(state, "connected", False):
        raise RuntimeError("AEDT adapter is not connected")
    if str(getattr(state, "backend", "")).lower() != "pyaedt":
        raise RuntimeError(
            "FD3D Eigenmode characterization requires the real PyAEDT/HFSS backend"
        )
    if str(plan.get("analysis_kind")) != "eigenmode":
        raise ValueError("plan must be an FD3D eigenmode component study")
    if bool(plan.get("dry_run", False)):
        raise ValueError("dry_run plans cannot be solved in HFSS")
    if plan.get("ports"):
        raise ValueError("Eigenmode component studies must not define excitation ports")

    hfss = _require_hfss(adapter)
    original_design = str(getattr(hfss, "design_name", "") or "")
    design_name = _insert_eigenmode_design(hfss, plan)
    study = dict(plan.get("study") or {})
    setup_config = dict(plan.get("setup") or {})
    parameter_name = str(study.get("parameter_name") or "").strip()
    parameter_unit = str(study.get("parameter_unit") or "").strip()
    sample_values = [float(item) for item in study.get("sample_values", [])]
    if not parameter_name or len(sample_values) < 2:
        raise ValueError("study parameter and at least two sample values are required")

    try:
        _set_design_variables(hfss, plan)
        objects = _build_component_geometry(hfss, plan, parameter_name)
        setup_name = _configure_eigenmode_setup(hfss, setup_config)
        samples: list[dict[str, Any]] = []
        for sample_index, parameter_value in enumerate(sample_values):
            hfss[parameter_name] = _quantity(parameter_value, parameter_unit)
            solved = hfss.analyze_setup(
                setup_name,
                cores=cores,
                tasks=tasks,
                gpus=gpus,
                blocking=True,
            )
            if solved is False:
                raise RuntimeError(
                    f"HFSS Eigenmode solve failed for {parameter_name}={parameter_value:g}{parameter_unit}"
                )
            modes = _extract_eigenmodes(
                hfss,
                setup_name=setup_name,
                parameter_name=parameter_name,
                parameter_value=parameter_value,
                parameter_unit=parameter_unit,
            )
            if not modes:
                raise RuntimeError(
                    f"HFSS returned no Eigenmode result for {parameter_name}={parameter_value:g}{parameter_unit}"
                )
            samples.append(
                {
                    "parameter_value": parameter_value,
                    "frequencies_hz": [float(item["frequency_hz"]) for item in modes],
                    "quality_factors": [item.get("quality_factor") for item in modes],
                    "mode_labels": [str(item["mode_name"]) for item in modes],
                    "metadata": {
                        "backend": "pyaedt-hfss-eigenmode",
                        "approved": False,
                        "design_name": design_name,
                        "setup_name": setup_name,
                        "sample_index": sample_index,
                        "variation": _quantity(parameter_value, parameter_unit),
                        "component_id": plan.get("component_id"),
                        "component_version": plan.get("component_version"),
                    },
                }
            )
        if save_project:
            saved = hfss.save_project()
            if saved is False:
                raise RuntimeError("HFSS solved the Eigenmode study but failed to save the project")
        return {
            "backend": "pyaedt-hfss-eigenmode",
            "solver": "HFSS Eigenmode",
            "eligible_for_approval": True,
            "approved": False,
            "project": getattr(hfss, "project_name", None),
            "project_file": getattr(hfss, "project_file", None),
            "design": design_name,
            "setup": setup_name,
            "component_id": plan.get("component_id"),
            "component_version": plan.get("component_version"),
            "study_kind": study.get("kind"),
            "parameter_name": parameter_name,
            "parameter_unit": parameter_unit,
            "samples": samples,
            "objects": objects,
            "sample_count": len(samples),
            "mode_count_requested": int(setup_config.get("num_modes", 4)),
        }
    except Exception:
        _restore_design(hfss, original_design)
        raise


def _require_hfss(adapter: Any) -> Any:
    getter = getattr(adapter, "_require_hfss", None)
    if not callable(getter):
        raise TypeError("adapter does not expose an active PyAEDT HFSS application")
    return getter()


def _insert_eigenmode_design(hfss: Any, plan: dict[str, Any]) -> str:
    component_id = str(plan.get("component_id") or "component").replace("-", "_")
    study = dict(plan.get("study") or {})
    parameter = str(study.get("parameter_name") or "parameter").replace("-", "_")
    requested = f"FD3D_{component_id}_{parameter}_{uuid4().hex[:8]}"[:64]
    inserted = hfss.insert_design(name=requested, solution_type="Eigenmode")
    if not inserted:
        raise RuntimeError("AEDT failed to insert an HFSS Eigenmode design")
    design_name = str(inserted)
    if str(getattr(hfss, "solution_type", "")).lower() != "eigenmode":
        try:
            hfss.solution_type = "Eigenmode"
        except (AttributeError, RuntimeError, TypeError):
            pass
    if str(getattr(hfss, "solution_type", "")).lower() != "eigenmode":
        raise RuntimeError("The active HFSS design is not configured as Eigenmode")
    return design_name


def _set_design_variables(hfss: Any, plan: dict[str, Any]) -> None:
    for name, value in dict(plan.get("variables") or {}).items():
        unit = "mm" if str(name).endswith("_mm") else ""
        hfss[str(name)] = _quantity(float(value), unit)


def _build_component_geometry(
    hfss: Any,
    plan: dict[str, Any],
    parameter_name: str,
) -> list[str]:
    modeler = hfss.modeler
    modeler.model_units = str(plan.get("units") or "mm")
    primitives = _parameterized_primitives(plan, parameter_name)
    objects: dict[str, Any] = {}
    for primitive in primitives:
        kind = str(primitive["primitive"])
        if kind == "box":
            created = modeler.create_box(
                origin=primitive["origin"],
                sizes=primitive["sizes"],
                name=primitive["name"],
                material=primitive["material"],
            )
        elif kind == "cylinder":
            created = modeler.create_cylinder(
                orientation=primitive["orientation"],
                origin=primitive["origin"],
                radius=primitive["radius"],
                height=primitive["height"],
                name=primitive["name"],
                material=primitive["material"],
            )
        else:
            raise ValueError(f"unsupported Eigenmode primitive: {kind}")
        if created is False:
            raise RuntimeError(f"HFSS failed to create object {primitive['name']!r}")
        objects[str(primitive["name"])] = created

    for operation in plan.get("operations", []):
        blank = objects[str(operation["blank"])]
        tools = [objects[str(name)] for name in operation.get("tools", [])]
        if operation["operation"] == "subtract":
            result = blank.subtract(
                tools,
                keep_originals=bool(operation.get("keep_originals", False)),
            )
        elif operation["operation"] == "unite":
            result = blank.unite(tools)
        else:
            raise ValueError(f"unsupported Eigenmode operation: {operation['operation']}")
        if result is False:
            raise RuntimeError(
                f"HFSS failed to execute {operation['operation']} on {operation['blank']}"
            )

    # Finite-conductivity metal is the default because Q is one of the required
    # observables. Perfect-E boundaries are used only when explicitly requested.
    if str(plan.get("loss_model") or "finite_conductivity") == "pec":
        for boundary in plan.get("boundaries", []):
            if str(boundary.get("type")) != "perfect_e":
                continue
            assignment = [objects[str(name)] for name in boundary.get("objects", [])]
            created = hfss.assign_perfect_e(
                assignment=assignment,
                name=str(boundary.get("name") or "FD3D_PEC"),
            )
            if created is False:
                raise RuntimeError("HFSS failed to assign the requested Perfect-E boundary")
    try:
        modeler.fit_all()
    except (AttributeError, RuntimeError):
        pass
    return list(objects)


def _parameterized_primitives(
    plan: dict[str, Any],
    parameter_name: str,
) -> list[dict[str, Any]]:
    primitives = deepcopy(list(plan.get("objects") or []))
    recipe = str(plan.get("recipe") or "")
    if recipe == "combline_resonator_eigenmode":
        rod = next(item for item in primitives if str(item["name"]).endswith("_rod"))
        if parameter_name == "resonator_height_mm":
            rod["height"] = parameter_name
        elif parameter_name == "resonator_radius_mm":
            rod["radius"] = parameter_name
    elif recipe == "combline_pair_eigenmode":
        aperture = next(
            item for item in primitives if str(item["name"]).endswith("_iris_cut")
        )
        if parameter_name == "iris_width_mm":
            aperture["origin"][1] = f"(cavity_width_mm-{parameter_name})/2"
            aperture["sizes"][1] = parameter_name
    return primitives


def _configure_eigenmode_setup(hfss: Any, config: dict[str, Any]) -> str:
    setup_name = str(config.get("name") or "FD3D_Eigenmode")
    setup = hfss.create_setup(name=setup_name, setup_type="HFSSEigen")
    if setup is False:
        raise RuntimeError(f"HFSS failed to create Eigenmode setup {setup_name!r}")
    setup.props["MinimumFrequency"] = (
        f"{float(config.get('minimum_frequency_ghz', 0.65))}GHz"
    )
    setup.props["NumModes"] = int(config.get("num_modes", 4))
    setup.props["ConvergeOnRealFreq"] = True
    setup.props["MaximumPasses"] = int(config.get("maximum_passes", 15))
    setup.props["MinimumPasses"] = int(config.get("minimum_converged_passes", 2))
    setup.props["MaxDeltaFreq"] = float(
        config.get("max_delta_frequency_percent", 0.1)
    )
    if setup.update() is False:
        raise RuntimeError(f"HFSS failed to update Eigenmode setup {setup_name!r}")
    return str(getattr(setup, "name", setup_name))


def _extract_eigenmodes(
    hfss: Any,
    *,
    setup_name: str,
    parameter_name: str,
    parameter_value: float,
    parameter_unit: str,
) -> list[dict[str, float | str | None]]:
    post = hfss.post
    solution = f"{setup_name} : LastAdaptive"
    q_names = list(
        post.available_report_quantities(
            quantities_category="Eigen Q",
            solution=solution,
        )
    )
    frequency_names = list(
        post.available_report_quantities(
            quantities_category="Eigen Modes",
            solution=solution,
        )
    )
    if not frequency_names:
        # PyAEDT 1.3 examples omit the solution argument. Keep this fallback for
        # compatibility with that documented behavior.
        q_names = list(post.available_report_quantities(quantities_category="Eigen Q"))
        frequency_names = list(
            post.available_report_quantities(quantities_category="Eigen Modes")
        )
    variation = {
        parameter_name: [_quantity(parameter_value, parameter_unit)],
    }
    modes: list[dict[str, float | str | None]] = []
    for index, frequency_name in enumerate(frequency_names):
        frequency_data = _get_eigen_solution(
            post,
            expression=str(frequency_name),
            solution=solution,
            variation=variation,
        )
        frequency_hz = _solution_scalar(frequency_data)
        quality_factor: float | None = None
        if index < len(q_names):
            q_data = _get_eigen_solution(
                post,
                expression=str(q_names[index]),
                solution=solution,
                variation=variation,
            )
            quality_factor = _solution_scalar(q_data)
        modes.append(
            {
                "mode_name": str(frequency_name),
                "frequency_hz": frequency_hz,
                "quality_factor": quality_factor,
            }
        )
    modes.sort(key=lambda item: float(item["frequency_hz"]))
    return modes


def _get_eigen_solution(
    post: Any,
    *,
    expression: str,
    solution: str,
    variation: dict[str, list[str]],
) -> Any:
    try:
        return post.get_solution_data(
            expressions=expression,
            setup_sweep_name=solution,
            variations=variation,
            report_category="Eigenmode",
        )
    except TypeError:
        try:
            return post.get_solution_data(
                expressions=expression,
                sweep=solution,
                variations=variation,
                report_category="Eigenmode",
            )
        except TypeError:
            return post.get_solution_data(
                expressions=expression,
                variations=variation,
                report_category="Eigenmode",
            )


def _solution_scalar(solution: Any) -> float:
    if solution is False or solution is None:
        raise RuntimeError("HFSS did not return Eigenmode solution data")
    getter = getattr(solution, "get_expression_data", None)
    if callable(getter):
        raw = getter()
        if isinstance(raw, (tuple, list)) and len(raw) > 1:
            values = raw[1]
            if values:
                return float(values[0])
    for name in ("data_real", "data_magnitude"):
        getter = getattr(solution, name, None)
        if callable(getter):
            values = getter()
            if values:
                return float(values[0])
    raise RuntimeError("Unable to read a scalar from the HFSS Eigenmode result")


def _restore_design(hfss: Any, design_name: str) -> None:
    if not design_name:
        return
    try:
        hfss.set_active_design(design_name)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        pass


def _quantity(value: float, unit: str) -> str:
    return f"{float(value):.15g}{unit}"
