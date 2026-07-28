from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hfss_vna_bridge.adapters.aedt.pyaedt_adapter import PyAedtAdapter
from hfss_vna_bridge.services.fd3d import execute_hfss_eigenmode_study


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute an FD3D component characterization in the real HFSS Eigenmode solver."
    )
    parser.add_argument("--plan", required=True, help="FD3D component study plan JSON")
    parser.add_argument("--output", required=True, help="Output JSON for HFSS samples and curve")
    parser.add_argument("--project", help="Existing .aedt project; omit to create a new project")
    parser.add_argument("--design", help="Initial design to activate before creating the study design")
    parser.add_argument("--version", default="2026.1", help="AEDT version")
    parser.add_argument("--machine", default=None, help="AEDT gRPC machine")
    parser.add_argument("--port", type=int, default=None, help="Existing AEDT gRPC port")
    parser.add_argument("--pid", type=int, default=None, help="Existing AEDT process ID")
    parser.add_argument("--new-desktop", action="store_true", help="Start a new AEDT Desktop")
    parser.add_argument("--non-graphical", action="store_true", help="Run AEDT non-graphically")
    parser.add_argument("--cores", type=int, default=None)
    parser.add_argument("--tasks", type=int, default=None)
    parser.add_argument("--gpus", type=int, default=None)
    parser.add_argument("--mode-index", type=int, default=0)
    parser.add_argument("--lower-mode-index", type=int, default=0)
    parser.add_argument("--upper-mode-index", type=int, default=1)
    parser.add_argument("--coupling-sign", type=float, default=1.0)
    parser.add_argument("--close-desktop", action="store_true")
    args = parser.parse_args()

    plan_path = Path(args.plan).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    plan = _read_object(plan_path)
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
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        print(f"HFSS Eigenmode study completed: {output_path}")
        print(f"Design: {result['study']['design']}")
        print(f"Samples: {result['study']['sample_count']}")
        print(f"Curve: {result['curve']['curve_id']}")
        print("Approval: pending engineering mode/field review")
        return 0
    finally:
        adapter.release(close_projects=False, close_desktop=args.close_desktop)


def _read_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Plan file not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("Plan JSON must contain an object")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
