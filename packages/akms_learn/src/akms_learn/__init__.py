"""akms_learn: Learning Source Packet compiler and exporters for AKMS."""

from akms_learn.cli import main
from akms_learn.compiler import (
    STAGES,
    CompileResult,
    compile_learning_source,
)
from akms_learn.domain_packs import (
    CapabilityStatus,
    CompanionRole,
    DomainPackDescriptor,
    DomainPackRegistry,
    DomainPackWarning,
    LearningCapabilityError,
    RuntimeHint,
    SourcePackDescriptor,
    build_registry_from_paths,
    load_descriptor_from_yaml,
    load_source_pack_from_yaml,
    warn_planned_companion,
)
from akms_learn.exporters.bundle import MANIFEST_VERSION
from akms_learn.exporters.bundle import export as bundle_export
from akms_learn.exporters.markdown import export as markdown_export
from akms_learn.graph_import import (
    GraphSlice,
    compute_graph_hash,
    fixture_graph,
    load_graph,
)
from akms_learn.modes.anthology import (
    TEACHING_SECTIONS,
    AnthologyEntry,
    anthology_mode,
)
from akms_learn.modes.bundle_source import bundle_source_mode
from akms_learn.modes.outline import outline_mode
from akms_learn.modes.pitfall import (
    PITFALL_EDGE_TYPES,
    STRUCTURED_FIELDS,
    pitfall_mode,
)
from akms_learn.models import (
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
from akms_learn.ordering import LEARNING_BUCKETS, order_nodes
from akms_learn.requests import (
    LearningRequest,
    normalize_request,
    request_hash,
    to_canonical_dict,
)
from akms_learn.section_extraction import (
    APPROVED_HEADINGS,
    EXCERPT_MAX_CHARS,
    ExtractedSection,
    ExtractionMethod,
    extract_sections_from_node,
    extract_sections_from_nodes,
)
from akms_learn.sections import APPROVED_SECTIONS, SectionView, extract_sections
from akms_learn.validation import PacketValidationError, validate_packet
from akms_learn.warnings import (
    WarningAccumulator,
    emit_dangling_reference_warning,
    emit_missing_section_warning,
)

__all__ = [
    # Compiler
    "STAGES",
    "CompileResult",
    "compile_learning_source",
    # Graph import
    "GraphSlice",
    "load_graph",
    "compute_graph_hash",
    "fixture_graph",
    # Ordering
    "LEARNING_BUCKETS",
    "order_nodes",
    # Sections
    "APPROVED_SECTIONS",
    "SectionView",
    "extract_sections",
    # Node-level section extraction
    "APPROVED_HEADINGS",
    "EXCERPT_MAX_CHARS",
    "ExtractedSection",
    "ExtractionMethod",
    "extract_sections_from_node",
    "extract_sections_from_nodes",
    # LSP models
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
    "LearningRequest",
    "normalize_request",
    "request_hash",
    "to_canonical_dict",
    "WarningAccumulator",
    "emit_missing_section_warning",
    "emit_dangling_reference_warning",
    "PacketValidationError",
    "validate_packet",
    # Domain-pack foundation
    "CapabilityStatus",
    "CompanionRole",
    "DomainPackDescriptor",
    "DomainPackRegistry",
    "DomainPackWarning",
    "LearningCapabilityError",
    "RuntimeHint",
    "SourcePackDescriptor",
    "build_registry_from_paths",
    "load_descriptor_from_yaml",
    "load_source_pack_from_yaml",
    "warn_planned_companion",
    # Exporters
    "markdown_export",
    "bundle_export",
    "MANIFEST_VERSION",
    # Structured modes
    "outline_mode",
    "anthology_mode",
    "AnthologyEntry",
    "TEACHING_SECTIONS",
    "pitfall_mode",
    "PITFALL_EDGE_TYPES",
    "STRUCTURED_FIELDS",
    "bundle_source_mode",
    # CLI
    "main",
]
