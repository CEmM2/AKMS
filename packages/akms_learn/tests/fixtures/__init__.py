"""Test fixtures for akms_learn.

Re-exports the in-process fixture factory so test files can import it
directly::

    from tests.fixtures import fixture_graph
"""

from akms_learn.graph_import import fixture_graph

__all__ = ["fixture_graph"]
