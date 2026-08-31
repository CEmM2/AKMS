"""AKMS local OpenAI-compatible agent backend.

Reuses ``AKMSCodexAgent``'s openai-agents tool machinery (the full
Read/Write/Edit/… + ``mcp__akms__akms_*`` function-tool registry) but points the
SDK at a **local OpenAI-compatible endpoint** (vLLM, Ollama, LM Studio, …) via
``AKMS_LLM_API_BASE`` / ``OPENAI_API_BASE``. Only the model/client wiring differs
from the Codex SDK backend; ``run()`` stays sealed and the agent writes its own
AgentMemory.

The ``openai-agents`` SDK is a pip dependency (already needed by the Codex SDK
backend); the local server is a **runtime** endpoint read from env at call time.

Select with::

    AKMS_LLM_API_BASE=http://localhost:8000/v1 \\
      akms orchestrate ... --backend local --model my-local-model
    # equivalently: --agent akms.agents.local.AKMSLocalAgent
"""

from __future__ import annotations

import os

from akms.agents.base import Loadout
from akms.agents.base_codex import AKMSCodexAgent


class AKMSLocalAgent(AKMSCodexAgent):
    """openai-agents runtime pointed at a local OpenAI-compatible endpoint.

    Inherits the function-tool registry from :class:`AKMSCodexAgent`; overrides
    ``execute()`` only to build a local-client model and reuse the Codex runner.
    """

    def __init__(self, config, repo_root, model=None):
        super().__init__(config, repo_root, model)
        # The local OpenAI-compatible server needs a concrete served-model name;
        # there is no sensible default, so require an explicit one rather than
        # inheriting the orchestrator's Claude config default.
        self.explicit_model = model

    def _resolve_api_base(self) -> str:
        base = os.environ.get("AKMS_LLM_API_BASE") or os.environ.get("OPENAI_API_BASE")
        if not base:
            raise RuntimeError(
                "The local backend requires a local OpenAI-compatible endpoint. "
                "Set AKMS_LLM_API_BASE (or OPENAI_API_BASE), e.g. "
                "http://localhost:8000/v1."
            )
        return base

    def _build_local_model(self):
        """Construct an ``OpenAIChatCompletionsModel`` bound to the local endpoint."""
        if not self.explicit_model:
            raise RuntimeError(
                "The local backend requires an explicit model (the served model "
                "name on your local endpoint), e.g. --model my-local-model. It "
                "has no default."
            )
        try:
            from agents import OpenAIChatCompletionsModel
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError(
                "The 'openai-agents' package is required for AKMSLocalAgent. "
                "Install it with: uv add openai-agents"
            ) from exc

        client = AsyncOpenAI(
            base_url=self._resolve_api_base(),
            # Local servers usually ignore the key; default to a placeholder.
            api_key=os.environ.get("OPENAI_API_KEY") or "sk-no-key-required",
        )
        return OpenAIChatCompletionsModel(
            model=self.explicit_model, openai_client=client
        )

    async def execute(
        self,
        task_json: dict,
        loadout: Loadout,
        system_prompt: str,
    ) -> None:
        from akms.agents.base_codex import _codex_sdk_execute

        user_message = self._build_task_prompt(task_json)
        await _codex_sdk_execute(
            user_message,
            loadout,
            system_prompt,
            self._build_local_model(),  # local OpenAIChatCompletionsModel
            self.repo_root,
            allowed_tools=self._resolve_allowed_tools(task_json),
        )
