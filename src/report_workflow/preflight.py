"""Preflight checks for the local MVP workflow."""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass

from .errors import QAHardBlockError
from .state import ReportState


REQUIRED_PACKAGES = {
    "docx": "python-docx",
    "filetype": "filetype",
    "pandas": "pandas",
    "pdfplumber": "pdfplumber",
    "pydantic": "pydantic",
    "yaml": "pyyaml",
}


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    missing_packages: list[str]

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "missing_packages": self.missing_packages,
        }


def _missing_packages() -> list[str]:
    missing = []
    for module_name, package_name in REQUIRED_PACKAGES.items():
        if importlib.util.find_spec(module_name) is None:
            missing.append(package_name)
    return sorted(missing)


def check_preflight() -> PreflightResult:
    """Return dependency/env readiness without mutating workflow state."""
    missing = _missing_packages()
    return PreflightResult(
        ok=not missing,
        missing_packages=missing,
    )


def run_preflight_checks(state: ReportState) -> ReportState:
    """Fail fast when deterministic local runtime requirements are missing."""
    result = check_preflight()
    state.runtime["preflight"] = result.as_dict()
    state.runtime.setdefault("warnings", [])

    if result.ok:
        return state

    parts = []
    if result.missing_packages:
        parts.append(
            "missing packages: "
            + ", ".join(result.missing_packages)
            + " (install with: pip install -r requirements.txt)"
        )
    parts.append("local setup command: pip install -r requirements.txt")

    raise QAHardBlockError("Preflight failed: " + "; ".join(parts))
