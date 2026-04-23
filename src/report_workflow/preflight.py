"""Preflight checks for the local MVP workflow."""
from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass, field
from pathlib import Path

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

# External CLI tools: (executable_name, severity, install_hint, description)
EXTERNAL_TOOLS = [
    (
        "pandoc",
        "critical",
        {
            "windows": "winget install JohnMacFarlane.Pandoc",
            "linux": "apt install pandoc",
            "macos": "brew install pandoc",
            "generic": "https://pandoc.org/installing.html",
        },
        "Required for high-quality DOCX rendering. Without pandoc, the pipeline "
        "falls back to a limited python-docx converter with degraded table/list "
        "formatting and no TOC support.",
    ),
    (
        "mmdc",
        "optional",
        {
            "generic": "npm install -g @mermaid-js/mermaid-cli",
        },
        "Optional. Converts mermaid code fences to PNG diagrams. Without mmdc, "
        "mermaid blocks are preserved as code blocks in the final DOCX.",
    ),
]


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    missing_packages: list[str]
    external_tool_warnings: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "missing_packages": self.missing_packages,
            "external_tool_warnings": self.external_tool_warnings,
        }


def _missing_packages() -> list[str]:
    missing = []
    for module_name, package_name in REQUIRED_PACKAGES.items():
        if importlib.util.find_spec(module_name) is None:
            missing.append(package_name)
    return sorted(missing)


def _find_executable(name: str) -> str | None:
    """Find an executable on PATH or in common install locations."""
    found = shutil.which(name)
    if found:
        return found
    # Check common Windows install locations
    if name == "pandoc":
        for candidate in [
            Path(r"C:\Program Files\Pandoc\pandoc.exe"),
            Path.home() / "AppData" / "Local" / "Pandoc" / "pandoc.exe",
        ]:
            if candidate.exists():
                return str(candidate)
    elif name == "mmdc":
        for candidate in [
            Path.home() / "AppData" / "Roaming" / "npm" / "mmdc.cmd",
            Path(r"C:\Program Files\nodejs\mmdc.cmd"),
            Path("/usr/local/bin/mmdc"),
            Path("/usr/bin/mmdc"),
        ]:
            if candidate.exists():
                return str(candidate)
    return None


def _check_external_tools() -> list[dict]:
    """Check for external CLI tools and return warnings for missing ones."""
    warnings = []
    for exe_name, severity, install_hints, description in EXTERNAL_TOOLS:
        found = _find_executable(exe_name)
        if not found:
            import platform
            system = platform.system().lower()
            hint_key = (
                "windows" if system == "windows"
                else "macos" if system == "darwin"
                else "linux" if system == "linux"
                else "generic"
            )
            install_cmd = install_hints.get(hint_key, install_hints.get("generic", ""))
            warnings.append({
                "tool": exe_name,
                "severity": severity,
                "installed": False,
                "install_command": install_cmd,
                "description": description,
            })
    return warnings


def check_preflight() -> PreflightResult:
    """Return dependency/env readiness without mutating workflow state."""
    missing = _missing_packages()
    tool_warnings = _check_external_tools()
    return PreflightResult(
        ok=not missing,
        missing_packages=missing,
        external_tool_warnings=tool_warnings,
    )


# -----------------------------------------------------------------------
# Feature Discovery — tells the agent what optional features exist,
# which are ready, and which need user action.
# -----------------------------------------------------------------------

@dataclass(frozen=True)
class FeatureInfo:
    """Describes one optional integration feature."""
    feature_id: str
    name: str
    description: str
    enabled: bool
    ready: bool            # True if all deps/keys are present
    missing_setup: list[str]   # What's needed to make it ready
    install_commands: list[str] # Exact commands to fix missing setup
    config_flag: str       # The workflow_config.yaml flag name

    def as_dict(self) -> dict:
        return {
            "feature_id": self.feature_id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "ready": self.ready,
            "missing_setup": self.missing_setup,
            "install_commands": self.install_commands,
            "config_flag": self.config_flag,
        }


@dataclass(frozen=True)
class FeatureDiscovery:
    """Result of feature discovery — what the agent should show/ask."""
    features: list[FeatureInfo]

    @property
    def available_features(self) -> list[FeatureInfo]:
        """Features that are ready to use (deps installed, keys set)."""
        return [f for f in self.features if f.ready]

    @property
    def configurable_features(self) -> list[FeatureInfo]:
        """Features that exist but need setup."""
        return [f for f in self.features if not f.ready]

    @property
    def agent_should_ask_user(self) -> list[dict]:
        """Features the agent MUST ask the user about.

        These are features that are ready but not enabled, or features
        that need simple setup the user might want.
        """
        prompts = []
        for f in self.features:
            if f.ready and not f.enabled:
                prompts.append({
                    "feature_id": f.feature_id,
                    "question": f"要啟用「{f.name}」嗎？{f.description}",
                    "question_en": f"Enable '{f.name}'? {f.description}",
                    "action": f"Set {f.config_flag}=true in workflow_config.yaml or pass to start_report_task",
                })
            elif not f.ready and f.missing_setup:
                prompts.append({
                    "feature_id": f.feature_id,
                    "question": f"要設定「{f.name}」嗎？需要: {', '.join(f.missing_setup)}",
                    "question_en": f"Set up '{f.name}'? Requires: {', '.join(f.missing_setup)}",
                    "setup_commands": f.install_commands,
                    "action": f"After setup, set {f.config_flag}=true",
                })
        return prompts

    def as_dict(self) -> dict:
        return {
            "features": [f.as_dict() for f in self.features],
            "agent_should_ask_user": self.agent_should_ask_user,
            "summary": {
                "total": len(self.features),
                "ready": len(self.available_features),
                "needs_setup": len(self.configurable_features),
            },
        }


def discover_features(
    enable_research: bool = False,
    enable_notebook_sync: bool = False,
) -> FeatureDiscovery:
    """Scan the environment and return what optional features are available.

    This is called during start_report_task to build the feature_discovery
    section of the return value. The agent uses this to:
    1. Tell the user what tools to install
    2. Ask the user whether to enable available features
    3. Show what's already configured
    """
    import importlib.util
    import os

    features: list[FeatureInfo] = []

    # ---- Feature: Web Research (Tavily/Serper/SerpAPI) ----
    research_missing: list[str] = []
    research_install: list[str] = []
    has_tavily = bool(os.environ.get("TAVILY_API_KEY"))
    has_serper = bool(os.environ.get("SERPER_API_KEY"))
    has_serpapi = bool(os.environ.get("SERPAPI_API_KEY"))
    has_browser_mcp = bool(os.environ.get("BROWSER_MCP_SEARCH_COMMAND"))
    has_any_key = has_tavily or has_serper or has_serpapi or has_browser_mcp

    if not has_any_key:
        research_missing.append("至少一個搜尋 API key (TAVILY_API_KEY 建議)")
        research_install.append(
            '將 API key 寫入 .env 檔案：TAVILY_API_KEY=tvly-xxxxx  '
            '(或設定環境變數)'
        )

    features.append(FeatureInfo(
        feature_id="web_research",
        name="外部網路研究 (Web Research)",
        description=(
            "自動搜尋驗證被標記為 blocked/disputed 的 claim，"
            "交叉比對外部來源並升級驗證狀態。"
            f" 目前後端狀態: Tavily={'✓' if has_tavily else '✗'}"
            f" Serper={'✓' if has_serper else '✗'}"
            f" SerpAPI={'✓' if has_serpapi else '✗'}"
        ),
        enabled=enable_research,
        ready=has_any_key,
        missing_setup=research_missing,
        install_commands=research_install,
        config_flag="enable_research",
    ))

    # ---- Feature: NotebookLM Sync ----
    nb_missing: list[str] = []
    nb_install: list[str] = []
    has_notebooklm_py = importlib.util.find_spec("notebooklm") is not None
    if not has_notebooklm_py:
        nb_missing.append("notebooklm-py 套件")
        nb_install.append("pip install notebooklm-py")
    # We don't hard-require auth here — the node handles that

    features.append(FeatureInfo(
        feature_id="notebook_sync",
        name="NotebookLM 知識同步",
        description=(
            "連接 Google NotebookLM 筆記本，同步來源資料上下文並執行分析問題，"
            "豐富報告的知識基礎。"
        ),
        enabled=enable_notebook_sync,
        ready=has_notebooklm_py,
        missing_setup=nb_missing,
        install_commands=nb_install,
        config_flag="enable_notebook_sync",
    ))

    # ---- Feature: pandoc rendering ----
    has_pandoc = _find_executable("pandoc") is not None
    pandoc_missing: list[str] = []
    pandoc_install: list[str] = []
    if not has_pandoc:
        pandoc_missing.append("pandoc 3.x")
        import platform
        system = platform.system().lower()
        if system == "windows":
            pandoc_install.append("winget install JohnMacFarlane.Pandoc")
        elif system == "darwin":
            pandoc_install.append("brew install pandoc")
        else:
            pandoc_install.append("apt install pandoc")

    features.append(FeatureInfo(
        feature_id="pandoc_render",
        name="Pandoc DOCX 渲染",
        description=(
            "使用 pandoc 產生高品質 DOCX（含目錄、表格、學術排版）。"
            "若未安裝則退回至有限的 python-docx 轉換器。"
        ),
        enabled=True,  # Always enabled when available
        ready=has_pandoc,
        missing_setup=pandoc_missing,
        install_commands=pandoc_install,
        config_flag="(always enabled when installed)",
    ))

    # ---- Feature: mermaid diagrams ----
    has_mmdc = _find_executable("mmdc") is not None
    mmdc_missing: list[str] = []
    mmdc_install: list[str] = []
    if not has_mmdc:
        mmdc_missing.append("mermaid-cli (mmdc)")
        mmdc_install.append("npm install -g @mermaid-js/mermaid-cli")

    features.append(FeatureInfo(
        feature_id="mermaid_diagrams",
        name="Mermaid 圖表轉換",
        description=(
            "將 mermaid 語法自動轉換為 PNG 圖片。"
            "若未安裝則保留為原始程式碼區塊。"
        ),
        enabled=True,
        ready=has_mmdc,
        missing_setup=mmdc_missing,
        install_commands=mmdc_install,
        config_flag="(always enabled when installed)",
    ))

    return FeatureDiscovery(features=features)


def run_preflight_checks(state: ReportState) -> ReportState:
    """Fail fast when deterministic local runtime requirements are missing.

    Also checks for external CLI tools (pandoc, mmdc) and surfaces
    warnings to the agent even when they are non-blocking.
    """
    result = check_preflight()
    state.runtime["preflight"] = result.as_dict()
    state.runtime.setdefault("warnings", [])

    # Surface external tool warnings so the agent sees them in the return value
    for tw in result.external_tool_warnings:
        severity_label = "⚠️ CRITICAL" if tw["severity"] == "critical" else "ℹ️ OPTIONAL"
        msg = (
            f"{severity_label}: '{tw['tool']}' not found. {tw['description']} "
            f"Install: {tw['install_command']}"
        )
        state.runtime["warnings"].append(msg)

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

