"""Local, file-based business rule engine (no external services)."""

from .engine import (
    STATUS_COMPLETED,
    STATUS_MAX_STEPS_EXCEEDED,
    ExecutionResult,
    RuleEngine,
)
from .errors import RuleEngineError, RuleFileError, RuleValidationError
from .loader import load_facts, load_rules
from .validation import validate_rules

__all__ = [
    "RuleEngine",
    "ExecutionResult",
    "STATUS_COMPLETED",
    "STATUS_MAX_STEPS_EXCEEDED",
    "RuleEngineError",
    "RuleFileError",
    "RuleValidationError",
    "load_facts",
    "load_rules",
    "validate_rules",
]
