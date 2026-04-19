"""Shared workflow exceptions."""


class QAHardBlockError(Exception):
    """Raised when the workflow must stop before publishing."""


class AgentWorkRequired(QAHardBlockError):
    """Raised when an external agent must create required workflow artifacts."""

    def __init__(self, message: str, missing_artifacts: list[str] | None = None):
        super().__init__(message)
        self.missing_artifacts = missing_artifacts or []
