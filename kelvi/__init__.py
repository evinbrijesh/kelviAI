"""Kelvi AI: Indian-language-first framework for reliable, action-taking voice agents."""

from kelvi.core import KelviEngine, PendingConfirmation, Session, TurnResult, XRayEvent, XRayTrace
from kelvi.indic import (
    clean_discourse_markers,
    default_voice,
    detect_language,
    format_spoken_date,
    format_spoken_slot,
    format_spoken_time,
    normalize_language,
    resolve_language,
    transliterate_indic,
)
from kelvi.tools import (
    ToolArgumentError,
    ToolConfirmationRequired,
    ToolError,
    ToolRegistry,
    ToolSpec,
    ToolTimeoutError,
    UnknownToolError,
    tool,
)

__version__ = "0.2.0"

__all__ = [
    "__version__",
    "KelviEngine",
    "Session",
    "TurnResult",
    "PendingConfirmation",
    "XRayTrace",
    "XRayEvent",
    "tool",
    "ToolRegistry",
    "ToolSpec",
    "ToolError",
    "UnknownToolError",
    "ToolArgumentError",
    "ToolTimeoutError",
    "ToolConfirmationRequired",
    "detect_language",
    "normalize_language",
    "resolve_language",
    "clean_discourse_markers",
    "transliterate_indic",
    "format_spoken_date",
    "format_spoken_time",
    "format_spoken_slot",
    "default_voice",
]
