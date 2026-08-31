"""Sub-package for akms_learn models.

Re-exports everything from the original ``models.py`` surface (now
``models/lsp.py``) plus the structured-mode models.

This package replaces the top-level ``models.py`` module.  All import paths
that previously used ``from akms_learn.models import <X>`` continue to work
unchanged because this ``__init__.py`` re-exports the full original surface.
"""

from akms_learn.models.assessment import (
    ASSESSMENT_ITEM_KINDS,
    AssessmentItem,
    AssessmentItemKind,
)
from akms_learn.models.learner_profile import LearnerProfile
from akms_learn.models.llm_expansion import (
    LLM_EXPANSION_POLICIES,
    LLM_VALIDATION_STATUSES,
    GeneratedSection,
    GeneratedSectionValidationStatus,
    LLMExpansionPolicy,
    build_llm_provenance,
    compute_content_hash,
)
from akms_learn.models.lsp import (
    AssessmentView,
    CodeLinkView,
    CompilerInfo,
    LearningEdgeView,
    LearningNodeView,
    LearningRequestInfo,
    LearningSourcePacket,
    LearningWarning,
    PacketBody,
    PitfallView,
    ReferenceView,
    SourceInfo,
)

__all__ = [
    # Original models.py surface (lsp.py)
    "LearningSourcePacket",
    "CompilerInfo",
    "SourceInfo",
    "LearningRequestInfo",
    "PacketBody",
    "LearningNodeView",
    "LearningEdgeView",
    "PitfallView",
    "CodeLinkView",
    "AssessmentView",
    "ReferenceView",
    "LearningWarning",
    # Structured-mode additions
    "LearnerProfile",
    "AssessmentItem",
    "AssessmentItemKind",
    "ASSESSMENT_ITEM_KINDS",
    # LLM-expansion additions
    "GeneratedSection",
    "GeneratedSectionValidationStatus",
    "LLMExpansionPolicy",
    "LLM_EXPANSION_POLICIES",
    "LLM_VALIDATION_STATUSES",
    "compute_content_hash",
    "build_llm_provenance",
]

# ``PacketBody.generated_sections`` is annotated ``list[GeneratedSection]`` under
# ``from __future__ import annotations`` and ``GeneratedSection`` is imported in
# ``lsp.py`` only under ``TYPE_CHECKING`` (to avoid an import cycle through the
# package ``__init__``). Rebuild here, where both ``PacketBody`` and
# ``GeneratedSection`` are bound in this module namespace, so pydantic can
# resolve the forward reference and the model is fully defined.
PacketBody.model_rebuild()
