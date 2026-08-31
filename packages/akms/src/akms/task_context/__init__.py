"""Task-context resolution: routes, queries, manifests, and review context.

This module is a regular package (rather than an implicit namespace package)
so that static analysis tools can traverse it. ``mkdocstrings``/``griffe``
resolve documented symbols by walking ``paths:`` from ``mkdocs.yml`` without
importing anything; without this file griffe raises ``KeyError: 'task_context'``
for every ``akms.task_context.*`` module and the strict docs build aborts.
"""
