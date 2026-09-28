"""Run the batch picker:

    akms-pick --plan path/to/generation_plan.md --bibtex-json path/to/library.json

Then open http://127.0.0.1:8765/. Every flag falls back to its environment
variable and then to a default; see `akms-pick --help`.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser

import uvicorn

from .config import Paths
from .server import create_app


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="akms-batch-picker",
        description=(
            "Local web UI for assigning papers from a Zotero library to the "
            "batches of a node-generation plan."
        ),
    )
    inputs = parser.add_argument_group("inputs")
    inputs.add_argument(
        "--plan",
        metavar="PATH",
        help="generation plan markdown (env AKMS_PLAN_MD; "
        "default ./generation_plan.md)",
    )
    inputs.add_argument(
        "--bibtex-json",
        metavar="PATH",
        help="Zotero library exported as Better BibTeX JSON (env AKMS_BBT_JSON; "
        "default <zsum-root>/zsumbib.json)",
    )
    inputs.add_argument(
        "--zsum-root",
        metavar="DIR",
        help="optional zsum vault with per-paper summaries (env "
        "AKMS_ZOTSUMS_ROOT; default ~/ZotSums)",
    )
    inputs.add_argument(
        "--workspace",
        metavar="DIR",
        help="where assignments, saved queries, plan JSON and staged PDFs go "
        "(env AKMS_PICKER_WORKSPACE; default: the plan's directory)",
    )
    server = parser.add_argument_group("server")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument(
        "--reload", action="store_true", help="dev: hot-reload on file change"
    )
    server.add_argument("--no-browser", action="store_true")
    return parser


def main() -> None:
    args = _parser().parse_args()

    paths = Paths.resolve(
        plan=args.plan,
        bibtex_json=args.bibtex_json,
        zsum_root=args.zsum_root,
        workspace=args.workspace,
    )
    app = create_app(paths)

    for notice in app.state.picker.notices:
        print(notice.for_terminal(), file=sys.stderr)

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
