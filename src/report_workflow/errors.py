"""Shared workflow exceptions."""


class QAHardBlockError(Exception):
    """Raised when the workflow must stop before publishing.

    Attributes:
        hint: Optional actionable suggestion for fixing the error.
    """

    _last_hint: str = ""

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.hint = hint or ""
        if hint:
            self._last_hint = hint

    @classmethod
    def with_hint(cls, message: str, hint: str) -> "QAHardBlockError":
        """Factory to create QAHardBlockError with actionable hint."""
        exc = cls(message, hint=hint)
        return exc

    def __str__(self) -> str:
        base = super().__str__()
        if self.hint:
            return f"{base}\n  → Hint: {self.hint}"
        return base


class AgentWorkRequired(QAHardBlockError):
    """Raised when an external agent must create required workflow artifacts."""

    def __init__(self, message: str, missing_artifacts: list[str] | None = None):
        super().__init__(message)
        self.missing_artifacts = missing_artifacts or []
