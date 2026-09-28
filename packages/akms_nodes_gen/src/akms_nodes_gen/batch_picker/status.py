"""Start-up checks for the batch picker's inputs.

The picker has one hard input, the generation plan, and one data source, a
Zotero library export. Neither being present is a reason to crash: the server
still starts, and each missing piece becomes a notice shown in the terminal and
at the top of the page, saying what is missing and how to supply it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .config import DOCS_URL, ZSUM_URL, Paths

ZSUM_HINT = "This stage can be simplified using zsum"


@dataclass(frozen=True)
class Notice:
    level: str  # "error", "warning" or "info"
    message: str
    link: str = ""
    link_text: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def for_terminal(self) -> str:
        suffix = f" ({self.link_text}: {self.link})" if self.link else ""
        return f"[{self.level}] {self.message}{suffix}"


def check_inputs(
    paths: Paths,
    *,
    batches: int,
    catalog_error: str = "",
    plan_error: str = "",
) -> list[Notice]:
    notices: list[Notice] = []

    if plan_error:
        notices.append(
            Notice(
                "error",
                f"Could not read the generation plan at {paths.plan_md}: {plan_error}",
                f"{DOCS_URL}data-sources/",
                "plan format",
            )
        )
    elif not paths.plan_md.is_file():
        notices.append(
            Notice(
                "error",
                f"No generation plan at {paths.plan_md}. Start the picker with "
                "--plan PATH, or set AKMS_PLAN_MD, to point at your plan.",
                f"{DOCS_URL}data-sources/",
                "plan format",
            )
        )
    elif batches == 0:
        notices.append(
            Notice(
                "warning",
                f"The plan at {paths.plan_md} contains no batches. Batch headings "
                "look like `## R1_B1 — Title (5 nodes)`.",
                f"{DOCS_URL}data-sources/",
                "plan format",
            )
        )

    if catalog_error:
        notices.append(
            Notice(
                "error",
                f"Could not read the Zotero export at {paths.bbt_json}: "
                f"{catalog_error}",
            )
        )
    elif not paths.bbt_json.is_file():
        notices.append(
            Notice(
                "warning",
                f"No Zotero library export at {paths.bbt_json}, so there are no "
                "papers to assign. Export your library from Zotero with Better "
                "BibTeX (format: Better BibTeX JSON) and pass --bibtex-json PATH. "
                f"{ZSUM_HINT}, which keeps this export up to date for you.",
                ZSUM_URL,
                "zsum",
            )
        )

    if not (paths.zotsums_root / "Papers").is_dir():
        notices.append(
            Notice(
                "info",
                "Per-paper summaries and keywords are off: no zsum vault at "
                f"{paths.zotsums_root}. Paper search and suggestions still work "
                f"from titles, abstracts and Zotero tags. {ZSUM_HINT}.",
                ZSUM_URL,
                "zsum",
            )
        )
    return notices
