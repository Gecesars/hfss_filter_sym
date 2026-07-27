from __future__ import annotations

import argparse
import json
from pathlib import Path

from hfss_vna_bridge.adapters.aedt.installations import aedt_environment_diagnostics
from hfss_vna_bridge.adapters.aedt.pyaedt_adapter import PyAedtAdapter


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the local AEDT 2026/PyAEDT connection.",
    )
    parser.add_argument("--project", type=Path)
    parser.add_argument("--design")
    parser.add_argument("--version", default="2026.1")
    parser.add_argument("--graphical", action="store_true")
    parser.add_argument("--attach", action="store_true")
    parser.add_argument("--process-id", type=int)
    parser.add_argument("--machine")
    parser.add_argument("--port", type=int)
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--setup")
    parser.add_argument("--sweep")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    print(json.dumps(aedt_environment_diagnostics(), indent=2))
    adapter = PyAedtAdapter()
    owns_desktop = not args.attach
    try:
        state = adapter.connect(
            project_path=args.project,
            design_name=args.design,
            version=args.version,
            new_desktop=owns_desktop,
            non_graphical=not args.graphical,
            close_on_exit=False,
            machine=args.machine,
            port=args.port,
            aedt_process_id=args.process_id,
        )
        payload: dict[str, object] = {
            "state": {
                "connected": state.connected,
                "backend": state.backend,
                "resource": state.resource,
                "detail": state.detail,
            },
            "session": adapter.session_info(),
            "designs": adapter.list_designs(),
            "variables": adapter.get_variables(),
        }
        if args.analyze:
            payload["analysis"] = adapter.analyze(
                setup_name=args.setup,
                sweep_name=args.sweep,
                output_touchstone=args.output,
            )
        print(json.dumps(payload, indent=2, default=str))
    finally:
        adapter.release(
            close_projects=owns_desktop,
            close_desktop=owns_desktop,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
