"""akms-learn's export templates ship with the installed package.

CI runs this suite against the built wheels, so it fails when packaging
drops the Jinja templates the markdown and HTML exporters load.
"""

from __future__ import annotations

from importlib.resources import files

import jinja2
import pytest

TEMPLATES = (
    "templates/markdown_default.md.j2",
    "templates/markdown_expanded.md.j2",
    "templates/pedagogical_template.md.j2",
    "exporters/templates/preview.html.j2",
    "exporters/templates/preview_rich.html.j2",
)


@pytest.mark.parametrize("relative", TEMPLATES)
def test_template_ships_and_parses(relative: str) -> None:
    resource = files("akms_learn").joinpath(relative)
    assert resource.is_file(), f"akms_learn/{relative} is missing from the install"
    env = jinja2.Environment(autoescape=jinja2.select_autoescape(["html", "xml"]))
    env.parse(resource.read_text(encoding="utf-8"))


def test_exporters_find_their_templates() -> None:
    from akms_learn.exporters import html, markdown

    for directory in (markdown._TEMPLATES_DIR, html._TEMPLATES_DIR):
        assert any(directory.glob("*.j2")), f"no templates in {directory}"
