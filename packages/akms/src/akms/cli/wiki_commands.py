"""``akms wiki``: the ``repo-wiki`` command under the ``akms`` CLI.

Everything after ``wiki`` is handed to :func:`akms.repo_wiki.cli.main`
unchanged, so ``akms wiki scan --json`` and ``repo-wiki scan --json`` are the
same command. The root ``--repo`` becomes ``--repo-root``; a ``--repo-root``
given after ``wiki`` still wins, because it is parsed later.

Registered via :func:`register_wiki_commands`.
"""

from __future__ import annotations

import argparse


def cmd_wiki(args: argparse.Namespace) -> int:
    from akms.repo_wiki.cli import main as repo_wiki_main

    return repo_wiki_main(["--repo-root", args.repo, *args.wiki_args])


def register_wiki_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``wiki`` passthrough on the root parser."""
    wiki = subparsers.add_parser(
        "wiki",
        help="Run repo-wiki (repository wiki and code-mirror export)",
        description="Same subcommands and flags as `repo-wiki`; see `akms wiki --help`.",
        # Every token, `--help` included, belongs to repo-wiki. A prefix
        # character no argument can start with keeps argparse from claiming any.
        add_help=False,
        prefix_chars="\0",
    )
    wiki.add_argument("wiki_args", nargs=argparse.REMAINDER)
    wiki.set_defaults(func=cmd_wiki)
