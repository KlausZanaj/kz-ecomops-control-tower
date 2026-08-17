"""Public API for synthetic platform export normalization."""

from .core import (
    NormalizationErrorCode,
    NormalizationIssue,
    NormalizationResult,
    normalize_all_platforms,
    normalize_platform_exports,
    normalize_source_dataframes,
    write_canonical_csvs,
)
from .mappings import (
    PLATFORM_MAPPINGS,
    SUPPORTED_SOURCE_PLATFORMS,
    PlatformMapping,
    SourceAmountStyle,
    SourceDateStyle,
)

__all__ = [
    "NormalizationErrorCode",
    "NormalizationIssue",
    "NormalizationResult",
    "normalize_all_platforms",
    "normalize_platform_exports",
    "normalize_source_dataframes",
    "write_canonical_csvs",
    "PLATFORM_MAPPINGS",
    "SUPPORTED_SOURCE_PLATFORMS",
    "PlatformMapping",
    "SourceAmountStyle",
    "SourceDateStyle",
]
