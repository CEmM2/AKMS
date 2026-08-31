"""Built-in post-processors for the NotebookLM batch generator.

``yaml_to_markdown`` converts a generated AKMS node YAML file into a schema-shaped
``.md`` node; ``validate_markdown`` runs the canonical ``akms.tools.node_validator``
against a ``.md`` node. Both are wired as the defaults in
``akms_nodes_gen.nlm_batch.BatchRunConfig`` and are overridable on the CLI.
"""

from pathlib import Path

#: Directory holding the built-in converter/validator scripts.
TOOLS_DIR = Path(__file__).resolve().parent

#: Default converter script (YAML -> Markdown).
CONVERTER_PATH = TOOLS_DIR / "yaml_to_markdown.py"

#: Default validator script (Markdown -> schema validation).
VALIDATOR_PATH = TOOLS_DIR / "validate_markdown.py"

__all__ = ["TOOLS_DIR", "CONVERTER_PATH", "VALIDATOR_PATH"]
