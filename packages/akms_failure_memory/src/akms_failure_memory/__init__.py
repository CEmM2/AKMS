"""Optional deterministic failure-memory workflows for AKMS projects."""

from akms_failure_memory.config import ProjectConfig, load_project_config

__version__ = "0.3.0"
PROJECT_CONFIG_SCHEMA_VERSION = "failure-memory-project/v1"
REGISTRY_SCHEMA_VERSION = "failure-memory-registry/v1"
PROVIDER_REQUEST_SCHEMA_VERSION = "failure-memory-provider-request/v1"
PROVIDER_RESULT_SCHEMA_VERSION = "failure-memory-provider-result/v1"

__all__ = [
    "PROJECT_CONFIG_SCHEMA_VERSION",
    "PROVIDER_REQUEST_SCHEMA_VERSION",
    "PROVIDER_RESULT_SCHEMA_VERSION",
    "ProjectConfig",
    "REGISTRY_SCHEMA_VERSION",
    "__version__",
    "load_project_config",
]
