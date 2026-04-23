"""Configuration loader for Report Workflow.

Loads settings from three sources with increasing priority:
  1. workflow_config.yaml  (persistent feature flags)
  2. .env file             (API keys and environment overrides)
  3. Environment variables (always win)
  4. Function parameters   (highest priority, passed at call site)

All file paths are resolved relative to the project root (where
pyproject.toml lives) unless absolute paths are provided.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import logging
import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Project root detection
# ---------------------------------------------------------------------------

def _find_project_root() -> Path:
    """Walk up from this file to find the directory containing pyproject.toml."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "pyproject.toml").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    # Fallback: use cwd
    return Path.cwd()


PROJECT_ROOT = _find_project_root()

# ---------------------------------------------------------------------------
# .env loader (stdlib only — no python-dotenv dependency)
# ---------------------------------------------------------------------------

def _load_dotenv(env_path: Path) -> dict[str, str]:
    """Parse a .env file into a dict. Does NOT modify os.environ."""
    result: dict[str, str] = {}
    if not env_path.exists():
        return result
    try:
        with open(env_path, encoding="utf-8") as f:
            for line_no, raw_line in enumerate(f, 1):
                line = raw_line.strip()
                # Skip comments and blank lines
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Strip surrounding quotes
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                if key and value:  # Only set if value is non-empty
                    result[key] = value
    except Exception as e:
        logger.warning("Failed to load .env file %s: %s", env_path, e)
    return result


# ---------------------------------------------------------------------------
# workflow_config.yaml loader
# ---------------------------------------------------------------------------

def _load_yaml_config(yaml_path: Path) -> dict[str, Any]:
    """Load workflow_config.yaml and return as nested dict."""
    if not yaml_path.exists():
        return {}
    try:
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("Failed to load %s: %s", yaml_path, e)
        return {}


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class WorkflowConfig:
    """Resolved configuration for a workflow run."""

    # Feature flags (from yaml → env → params)
    enable_research: bool = False
    enable_notebook_sync: bool = False

    # NotebookLM settings
    notebooklm_notebook_id: str | None = None
    notebooklm_storage_path: str | None = None

    # Research settings
    preferred_research_backend: str = "auto"

    # API keys (from .env → env vars)
    tavily_api_key: str | None = None
    serper_api_key: str | None = None
    serpapi_api_key: str | None = None
    browser_mcp_search_command: str | None = None

    # Resolved file paths
    env_file_path: str | None = None
    config_file_path: str | None = None

    # Raw sources for debugging
    _sources: dict = field(default_factory=dict)

    def has_any_research_key(self) -> bool:
        """Return True if at least one research API key is configured."""
        return bool(
            self.tavily_api_key
            or self.serper_api_key
            or self.serpapi_api_key
            or self.browser_mcp_search_command
        )

    def as_env_summary(self) -> dict[str, Any]:
        """Return a safe summary (no secrets) for agent display."""
        return {
            "enable_research": self.enable_research,
            "enable_notebook_sync": self.enable_notebook_sync,
            "has_tavily_key": bool(self.tavily_api_key),
            "has_serper_key": bool(self.serper_api_key),
            "has_serpapi_key": bool(self.serpapi_api_key),
            "has_browser_mcp": bool(self.browser_mcp_search_command),
            "notebooklm_notebook_id": self.notebooklm_notebook_id,
            "preferred_research_backend": self.preferred_research_backend,
            "env_file_loaded": self.env_file_path is not None,
            "config_file_loaded": self.config_file_path is not None,
        }


def _update_yaml_config(yaml_path: Path, key_path: list[str], value: Any) -> None:
    """Update a single value in workflow_config.yaml, preserving structure."""
    data = _load_yaml_config(yaml_path)
    # Navigate to parent
    current = data
    for key in key_path[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[key_path[-1]] = value
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# Main config loader
# ---------------------------------------------------------------------------

def load_config(
    *,
    enable_research: bool | None = None,
    enable_notebook_sync: bool | None = None,
    notebooklm_notebook_id: str | None = None,
    notebooklm_storage_path: str | None = None,
    project_root: Path | None = None,
) -> WorkflowConfig:
    """Load configuration from all sources and merge.

    Priority (highest wins):
      1. Function parameters (if not None)
      2. Environment variables
      3. .env file
      4. workflow_config.yaml
    """
    root = project_root or PROJECT_ROOT
    sources: dict[str, str] = {}

    # --- Layer 1: workflow_config.yaml ---
    yaml_path = root / "workflow_config.yaml"
    yaml_cfg = _load_yaml_config(yaml_path)
    features = yaml_cfg.get("features", {}) if isinstance(yaml_cfg.get("features"), dict) else {}
    notebooklm_cfg = yaml_cfg.get("notebooklm", {}) if isinstance(yaml_cfg.get("notebooklm"), dict) else {}
    research_cfg = yaml_cfg.get("research", {}) if isinstance(yaml_cfg.get("research"), dict) else {}

    cfg = WorkflowConfig()
    if yaml_path.exists():
        cfg.config_file_path = str(yaml_path)
        sources["config_file"] = str(yaml_path)

    # Apply yaml values
    if features.get("enable_research") is True:
        cfg.enable_research = True
        sources["enable_research"] = "workflow_config.yaml"
    if features.get("enable_notebook_sync") is True:
        cfg.enable_notebook_sync = True
        sources["enable_notebook_sync"] = "workflow_config.yaml"
    if notebooklm_cfg.get("notebook_id"):
        cfg.notebooklm_notebook_id = str(notebooklm_cfg["notebook_id"])
    if notebooklm_cfg.get("storage_path"):
        cfg.notebooklm_storage_path = str(notebooklm_cfg["storage_path"])
    if research_cfg.get("preferred_backend"):
        cfg.preferred_research_backend = str(research_cfg["preferred_backend"])

    # --- Layer 2: .env file ---
    env_path = root / ".env"
    dotenv = _load_dotenv(env_path)
    if dotenv:
        cfg.env_file_path = str(env_path)
        sources["env_file"] = str(env_path)

    # --- Layer 3: Environment variables (override .env) ---
    # Merge: .env values → real env vars (real env wins)
    def _get_env(key: str) -> str | None:
        # Real env var takes priority over .env file
        return os.environ.get(key) or dotenv.get(key) or None

    cfg.tavily_api_key = _get_env("TAVILY_API_KEY")
    cfg.serper_api_key = _get_env("SERPER_API_KEY")
    cfg.serpapi_api_key = _get_env("SERPAPI_API_KEY")
    cfg.browser_mcp_search_command = _get_env("BROWSER_MCP_SEARCH_COMMAND")

    # NotebookLM env overrides
    env_nb_id = _get_env("NOTEBOOKLM_NOTEBOOK_ID")
    if env_nb_id:
        cfg.notebooklm_notebook_id = env_nb_id
    env_nb_path = _get_env("NOTEBOOKLM_STORAGE_PATH")
    if env_nb_path:
        cfg.notebooklm_storage_path = env_nb_path

    # --- Layer 4: Function parameters (highest priority) ---
    if enable_research is not None:
        cfg.enable_research = enable_research
        sources["enable_research"] = "function_parameter"
    if enable_notebook_sync is not None:
        cfg.enable_notebook_sync = enable_notebook_sync
        sources["enable_notebook_sync"] = "function_parameter"
    if notebooklm_notebook_id is not None:
        cfg.notebooklm_notebook_id = notebooklm_notebook_id
    if notebooklm_storage_path is not None:
        cfg.notebooklm_storage_path = notebooklm_storage_path

    # Inject API keys into os.environ so downstream code can use them
    if cfg.tavily_api_key and "TAVILY_API_KEY" not in os.environ:
        os.environ["TAVILY_API_KEY"] = cfg.tavily_api_key
    if cfg.serper_api_key and "SERPER_API_KEY" not in os.environ:
        os.environ["SERPER_API_KEY"] = cfg.serper_api_key
    if cfg.serpapi_api_key and "SERPAPI_API_KEY" not in os.environ:
        os.environ["SERPAPI_API_KEY"] = cfg.serpapi_api_key

    cfg._sources = sources
    return cfg


def save_feature_flag(flag_name: str, value: bool, project_root: Path | None = None) -> None:
    """Persist a feature flag change to workflow_config.yaml."""
    root = project_root or PROJECT_ROOT
    yaml_path = root / "workflow_config.yaml"
    _update_yaml_config(yaml_path, ["features", flag_name], value)
    logger.info("Updated workflow_config.yaml: features.%s = %s", flag_name, value)
