"""``python -m akms.repo_wiki`` runs the ``repo-wiki`` command."""

from __future__ import annotations

import sys

from akms.repo_wiki.cli import main

if __name__ == "__main__":
    sys.exit(main())
