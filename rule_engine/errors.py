"""Exception types for the local rule engine."""


class RuleEngineError(Exception):
    """Base class for all rule engine errors."""


class RuleValidationError(RuleEngineError):
    """Raised when static validation of a rule set fails."""

    def __init__(self, problems):
        self.problems = list(problems)
        message = "rule validation failed:\n" + "\n".join(
            f"  - {p}" for p in self.problems
        )
        super().__init__(message)


class RuleFileError(RuleEngineError):
    """Raised when a rules/facts file cannot be read or parsed."""
