"""Run the batch picker locally:

    uvpy -m akms_nodes_gen.batch_picker
    # or
    uv --project Packages/AKMS_nodes_gen run python -m akms_nodes_gen.batch_picker

Then open http://127.0.0.1:8765/.
"""

from __future__ import annotations

import argparse
import webbrowser

import uvicorn

from .config import Paths
from .server import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="akms-batch-picker")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--reload", action="store_true", help="dev: hot-reload on file change")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    paths = Paths.resolve()
    app = create_app(paths)

    if not args.no_browser:
        try:
            webbrowser.open_new_tab(f"http://{args.host}:{args.port}/")
        except Exception:
            pass

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
