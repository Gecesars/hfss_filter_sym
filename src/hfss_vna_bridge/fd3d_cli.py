from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hfss_vna_bridge.adapters.aedt.pyaedt_adapter import PyAedtAdapter
from hfss_vna_bridge.fd3d.assembly import build_combline_assembly_plan
from hfss_vna_bridge.services.fd3d import execute_hfss_eigenmode_study


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="hfss-fd3d",
        description="HFSS Filter Studio FD3D project, characterization and assembly tools.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    eigen = subcommands.add_parser(
        "eigenmode",
        help="Run a real HFSS Eigenmode component characterization.",
    )
    eigen.add_argument("--plan", required=True)
    eigen.add_argument("--output", required=True)
    eigen.add_argument("--project")
    eigen.add_argument("--design")
    eigen.add_argument("--version", default="2026.1")
    eigen.add_argument("--machine", default=None)
    eigen.add_argument("--port", type=int, default=None)
    eigen.add_argument("--pid", type=int, default=None)
    eigen.add_argument("--new-desktop", action="store_true")
    eigen.add_argument("--non-graphical", action="store_true")
    eigen.add_argument("--cores", type=int, default=None)
    eigen.add_argument("--tasks", type=int, default=None)
    eigen.add_argument("--gpus", type=int, default=None)
    eigen.add_argument("--mode-index", type=int, default=0)
    eigen.add_argument("--lower-mode-index", type=int, default=0)
    eigen.add_argument("--upper-mode-index", type=int, default=1)
    eigen.add_argument("--coupling-sign", type=float, choices=(-1.0, 1.0), default=1.0)
    eigen.add_argument("--close-desktop", action="store_true")

    assembly = subcommands.add_parser(
        "assembly-plan",
        help="Create a part-by-part combline HFSS assembly plan from mapped dimensions.",
    )
    assembly.add_argument("--project", required=True, help="FD3D project JSON")
    assembly.add_argument("--mapping", required=True, help="Target-to-dimension mapping JSON")
    assembly.add_argument("--output", required=True)
    assembly.add_argument("--allow-pending-curves", action="store_true")
    assembly.add_argument("--allow-seed-resonance", action="store_true")
    assembly.add_argument("--allow-seed-coupling", action="store_true")
    assembly.add_argument("--require-characterized-external-q", action="store_true")
    assembly.add_argument("--without-tuning-screws", action="store_true")

    args = parser.parse_args()
    if args.command == "eigenmode":
        return _run_eigenmode(args)
    if args.command == "assembly-plan":
        return _write_assembly_plan(args)
    raise RuntimeError(f"unsupported command: {args.command}")


def _run_eigenmode(args: argparse.Namespace) -> int:
    plan = _read_object(args.plan)
    output = Path(args.output).expanduser().resolve()
    adapter = PyAedtAdapter()
    try:
        adapter.connect(
            project_path=args.project,
            design_name=args.design,
            version=args.version,
            new_desktop=args.new_desktop,
            non_graphical=args.non_graphical,
            close_on_exit=False,
            machine=args.machine,
            port=args.port,
            aedt_process_id=args.pid,
        )
        result = execute_hfss_eigenmode_study(
            adapter,
            {
                "plan": plan,
                "cores": args.cores,
                "tasks": args.tasks,
                "gpus": args.gpus,
                "mode_index": args.mode_index,
                "lower_mode_index": args.lower_mode_index,
                "upper_mode_index": args.upper_mode_index,
                "sign": args.coupling_sign,
                "save_project": True,
            },
        )
        _write_object(output, result)
        print(f"HFSS Eigenmode study completed: {output}")
        print(f"Design: {result['study']['design']}")
        print(f"Samples: {result['study']['sample_count']}")
        print("Engineering approval: pending field and mode review")
        return 0
    finally:
        adapter.release(close_projects=False, close_desktop=args.close_desktop)


def _write_assembly_plan(args: argparse.Namespace) -> int:
    project = _read_object(args.project)
    mapping = _read_object(args.mapping)
    plan = build_combline_assembly_plan(
        project,
        mapping,
        require_approved_curves=not args.allow_pending_curves,
        allow_seed_external_q=not args.require_characterized_external_q,
        allow_seed_resonance=args.allow_seed_resonance,
        allow_seed_coupling=args.allow_seed_coupling,
        include_tuning_screws=not args.without_tuning_screws,
    )
    output = Path(args.output).expanduser().resolve()
    _write_object(output, plan)
    print(f"FD3D assembly plan written: {output}")
    print(f"HFSS build ready: {plan['ready_for_hfss']}")
    for blocker in plan["validation"]["blockers"]:
        print(f"BLOCKER: {blocker}")
    for warning in plan["validation"]["warnings"]:
        print(f"WARNING: {warning}")
    return 0 if plan["ready_for_hfss"] else 2


def _read_object(path_value: str | Path) -> dict[str, Any]:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"JSON file not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON file must contain an object: {path}")
    return value


def _write_object(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
