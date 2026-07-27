from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the HFSS/VNA bridge API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--server", choices=("flask", "fastapi"), default="flask")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args(argv)

    if args.server == "flask":
        from hfss_vna_bridge.web.app import run_flask_app

        run_flask_app(host=args.host, port=args.port, debug=args.reload)
    else:
        import uvicorn

        uvicorn.run(
            "hfss_vna_bridge.api.app:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    return 0
