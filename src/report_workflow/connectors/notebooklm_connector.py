"""NotebookLM connector for report_workflow.

Provides optional integration with Google NotebookLM via the notebooklm-py
library. All functions gracefully degrade when notebooklm-py is not installed.

Ported from report-from-notebooklm (notebooklm_adapter.py + notebooklm_workflow.py),
adapted to use report_workflow's ReportState and logging conventions.

Usage:
    from report_workflow.connectors.notebooklm_connector import (
        notebooklm_available,
        sync_notebook_context,
        ask_analysis_questions,
    )
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Optional dependency import
# ------------------------------------------------------------------

try:
    from notebooklm import NotebookLMClient  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional dependency
    NotebookLMClient = None  # type: ignore[assignment]


def notebooklm_available() -> bool:
    """Return True if the notebooklm-py library is installed and importable."""
    return NotebookLMClient is not None


# ------------------------------------------------------------------
# Storage discovery
# ------------------------------------------------------------------

def discover_storage_path(explicit_path: str | None = None) -> str | None:
    """Find the NotebookLM authentication storage state file.

    Search order:
      1. explicit_path argument
      2. NOTEBOOKLM_STORAGE_PATH env var
      3. NOTEBOOKLM_HOME / storage_state.json
      4. ~/.notebooklm/storage_state.json (official default)
      5. LOCALAPPDATA MCP locations (Windows)
    """
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser().resolve())

    env_storage = os.environ.get("NOTEBOOKLM_STORAGE_PATH")
    if env_storage:
        candidates.append(Path(env_storage).expanduser().resolve())

    notebooklm_home = Path(os.environ.get("NOTEBOOKLM_HOME", str(Path.home() / ".notebooklm")))
    candidates.append(notebooklm_home / "storage_state.json")

    official_default = Path.home() / ".notebooklm" / "storage_state.json"
    candidates.append(official_default)

    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    if local_app_data and str(local_app_data) != ".":
        candidates.append(local_app_data / "notebooklm-mcp" / "Data" / "browser_state" / "state.json")
        candidates.append(local_app_data / "notebooklm-mcp-nodejs" / "Data" / "browser_state" / "state.json")

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return str(candidate)
    return None


def ensure_notebook_auth_ready(storage_path: str | None = None) -> str:
    """Validate that NotebookLM authentication is ready.

    Raises RuntimeError if notebooklm-py is not installed or auth is invalid.
    Returns the resolved storage path on success.
    """
    if NotebookLMClient is None:
        raise RuntimeError("NotebookLM integration requires notebooklm-py, but it is not installed.")
    resolved = discover_storage_path(storage_path)
    if not resolved:
        raise FileNotFoundError(
            "NotebookLM authentication state was not found. "
            "Authenticate NotebookLM before notebook-backed drafting."
        )
    try:
        asyncio.run(_list_notebooks_async(resolved))
    except Exception as exc:
        raise RuntimeError(
            "NotebookLM authentication is not ready or the stored session is invalid. "
            "Re-authenticate before notebook-backed drafting."
        ) from exc
    return resolved


# ------------------------------------------------------------------
# Low-level async API wrappers
# ------------------------------------------------------------------

def _to_dict(obj: Any) -> dict[str, Any]:
    """Convert any notebooklm-py model to a plain dict."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    return {"value": str(obj)}


async def _list_notebooks_async(storage_path: str | None = None) -> list[dict[str, Any]]:
    if NotebookLMClient is None:
        raise RuntimeError("notebooklm-py is not installed.")
    resolved = discover_storage_path(storage_path)
    if not resolved:
        raise FileNotFoundError("No NotebookLM storage state file was found.")
    async with await NotebookLMClient.from_storage(resolved) as client:
        notebooks = await client.notebooks.list()
        return [_to_dict(notebook) for notebook in notebooks]


async def _list_sources_async(notebook_id: str, storage_path: str | None = None) -> list[dict[str, Any]]:
    if NotebookLMClient is None:
        raise RuntimeError("notebooklm-py is not installed.")
    resolved = discover_storage_path(storage_path)
    if not resolved:
        raise FileNotFoundError("No NotebookLM storage state file was found.")
    async with await NotebookLMClient.from_storage(resolved) as client:
        sources = await client.sources.list(notebook_id)
        return [_to_dict(source) for source in sources]


async def _get_notebook_metadata_async(notebook_id: str, storage_path: str | None = None) -> dict[str, Any]:
    if NotebookLMClient is None:
        raise RuntimeError("notebooklm-py is not installed.")
    resolved = discover_storage_path(storage_path)
    if not resolved:
        raise FileNotFoundError("No NotebookLM storage state file was found.")
    async with await NotebookLMClient.from_storage(resolved) as client:
        metadata = await client.notebooks.get_metadata(notebook_id)
        return _to_dict(metadata)


async def _ask_notebook_async(notebook_id: str, question: str, storage_path: str | None = None) -> dict[str, Any]:
    if NotebookLMClient is None:
        raise RuntimeError("notebooklm-py is not installed.")
    resolved = discover_storage_path(storage_path)
    if not resolved:
        raise FileNotFoundError("No NotebookLM storage state file was found.")
    async with await NotebookLMClient.from_storage(resolved) as client:
        response = await client.chat.ask(notebook_id=notebook_id, question=question)
        return _to_dict(response)


async def _add_url_source_async(
    notebook_id: str, url: str, title: str | None = None, storage_path: str | None = None
) -> dict[str, Any]:
    if NotebookLMClient is None:
        raise RuntimeError("notebooklm-py is not installed.")
    resolved = discover_storage_path(storage_path)
    if not resolved:
        raise FileNotFoundError("No NotebookLM storage state file was found.")
    async with await NotebookLMClient.from_storage(resolved) as client:
        source = await client.sources.add_url(notebook_id=notebook_id, url=url, title=title)
        return _to_dict(source)


async def _add_text_source_async(
    notebook_id: str, text: str, title: str, storage_path: str | None = None
) -> dict[str, Any]:
    if NotebookLMClient is None:
        raise RuntimeError("notebooklm-py is not installed.")
    resolved = discover_storage_path(storage_path)
    if not resolved:
        raise FileNotFoundError("No NotebookLM storage state file was found.")
    async with await NotebookLMClient.from_storage(resolved) as client:
        source = await client.sources.add_text(notebook_id=notebook_id, text=text, title=title)
        return _to_dict(source)


# ------------------------------------------------------------------
# Synchronous public API
# ------------------------------------------------------------------

def list_notebooks(storage_path: str | None = None) -> list[dict[str, Any]]:
    """List all available notebooks."""
    return asyncio.run(_list_notebooks_async(storage_path))


def list_sources(notebook_id: str, storage_path: str | None = None) -> list[dict[str, Any]]:
    """List sources in a notebook."""
    return asyncio.run(_list_sources_async(notebook_id, storage_path))


def get_notebook_metadata(notebook_id: str, storage_path: str | None = None) -> dict[str, Any]:
    """Get metadata for a notebook."""
    return asyncio.run(_get_notebook_metadata_async(notebook_id, storage_path))


def ask_notebook(notebook_id: str, question: str, storage_path: str | None = None) -> dict[str, Any]:
    """Ask a question to a notebook and get a structured response."""
    return asyncio.run(_ask_notebook_async(notebook_id, question, storage_path))


def add_url_source(
    notebook_id: str, url: str, title: str | None = None, storage_path: str | None = None
) -> dict[str, Any]:
    """Add a URL source to a notebook."""
    return asyncio.run(_add_url_source_async(notebook_id, url, title, storage_path))


def add_text_source(
    notebook_id: str, text: str, title: str, storage_path: str | None = None
) -> dict[str, Any]:
    """Add a text source to a notebook."""
    return asyncio.run(_add_text_source_async(notebook_id, text, title, storage_path))


# ------------------------------------------------------------------
# High-level workflow functions (used by nodes/notebook_sync.py)
# ------------------------------------------------------------------

def choose_notebook(
    notebooks: list[dict[str, Any]],
    notebook_id: str | None = None,
    topic: str | None = None,
) -> dict[str, Any] | None:
    """Select a notebook by ID, topic match, or fall back to the first available."""
    if notebook_id:
        for nb in notebooks:
            if nb.get("id") == notebook_id:
                return nb
    if topic:
        for nb in notebooks:
            title = nb.get("title") or nb.get("name") or ""
            if topic.lower() in str(title).lower():
                return nb
    return notebooks[0] if notebooks else None


def sync_notebook_context(
    storage_path: str | None = None,
    notebook_id: str | None = None,
    topic: str | None = None,
) -> dict[str, Any]:
    """Sync context from a NotebookLM notebook.

    Returns a context dict with notebook metadata, sources, and sync status.
    """
    if not notebooklm_available():
        return {"available": False, "error": "notebooklm-py is not installed"}

    try:
        resolved = ensure_notebook_auth_ready(storage_path)
    except (RuntimeError, FileNotFoundError) as exc:
        return {"available": False, "error": str(exc)}

    notebooks = list_notebooks(resolved)
    selected = choose_notebook(notebooks, notebook_id=notebook_id, topic=topic)

    context: dict[str, Any] = {
        "available": True,
        "storage_path": resolved,
        "notebook_count": len(notebooks),
        "selected_notebook": selected,
        "sources": [],
        "metadata": None,
    }

    if selected:
        try:
            context["sources"] = list_sources(selected["id"], resolved)
        except Exception as exc:
            logger.warning(f"[NOTEBOOK] Failed to list sources: {exc}")
            context["sources"] = []
        try:
            context["metadata"] = get_notebook_metadata(selected["id"], resolved)
        except Exception as exc:
            logger.warning(f"[NOTEBOOK] Failed to get metadata: {exc}")
            context["metadata"] = None

    return context


def ask_analysis_questions(
    notebook_id: str,
    storage_path: str,
    questions: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Ask a set of analysis questions to the notebook.

    Returns a list of {question, answer, raw_response} dicts.
    """
    if not questions:
        questions = [
            "Identify any critical missing constants, dimensions, or formula definitions "
            "needed to complete the report accurately.",
            "Review the notebook content and point out any factual inconsistencies, "
            "unsupported claims, or likely overstatements in the draft report context.",
            "Suggest how to improve professionalism, precision, and persuasiveness without exaggeration.",
        ]

    results: list[dict[str, Any]] = []
    for question in questions:
        try:
            raw = ask_notebook(notebook_id, question, storage_path)
            results.append({
                "question": question,
                "answer": raw.get("answer") or raw.get("text") or str(raw),
                "raw_response": raw,
                "status": "completed",
            })
        except Exception as exc:
            logger.warning(f"[NOTEBOOK] Question failed: {exc}")
            results.append({
                "question": question,
                "answer": "",
                "raw_response": {"error": str(exc)},
                "status": "failed",
            })

    return results
