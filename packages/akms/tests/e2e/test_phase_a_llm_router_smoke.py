"""Phase A E2E: llm_router end-to-end with mocked LiteLLM."""

from unittest.mock import MagicMock, patch

from akms.orchestrator.llm_router import check_dedup_similarity
from akms.schema.models import PropagationConfig


def test_dedup_similarity_e2e():
    """Full path: config → model resolution → LiteLLM call → float parsing."""
    config = PropagationConfig()  # defaults

    with patch("akms.orchestrator.llm_router.litellm") as mock:
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "0.72"
        mock.completion.return_value = mock_resp

        score = check_dedup_similarity(
            "new text", "old title", "old content", config=config
        )

    assert 0.0 <= score <= 1.0
    mock.completion.assert_called_once()
