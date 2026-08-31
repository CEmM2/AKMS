"""Concrete LLMProvider adapters for the ``llm_expanded`` mode.

Each adapter satisfies :class:`akms_learn.llm.protocol.LLMProvider` and registers
itself in :mod:`akms_learn.llm.registry` on import. Adapters adapt *existing*
clients — they do not implement their own LLM SDK.
"""
