"""Web research backends for external fact-checking and claim verification.

Ported from report-from-notebooklm, adapted to report_workflow package conventions.

Provides pluggable backends for executing web research tasks:
  - ManualAgentWebBackend: no-op fallback (always available)
  - TavilyBackend: Tavily Search API (TAVILY_API_KEY)
  - SerperBackend: Serper Google Search API (SERPER_API_KEY)
  - SerpApiBackend: SerpAPI Google Search API (SERPAPI_API_KEY)
  - BrowserMcpBackend: shell-based browser MCP search (BROWSER_MCP_SEARCH_COMMAND)

All backends implement the ResearchBackend ABC and share a common
result schema:
  {"task_id", "status", "answer", "sources", "confidence", "backend"}

Usage:
    from report_workflow.connectors.research_backends import select_backend
    backend = select_backend("web_fallback")
    result = backend.execute({"id": "task_1", "query": "Reynolds number formula"})
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------

def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Perform an HTTP request and parse the JSON response."""
    data = None
    request_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method.upper())
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def detect_source_type(url: str) -> str:
    """Infer source trustworthiness category from URL domain."""
    lowered = url.lower()
    if ".gov" in lowered:
        return "gov"
    if ".edu" in lowered:
        return "edu"
    if "wikipedia.org" in lowered:
        return "reference"
    if any(token in lowered for token in ("nature.com", "sciencedirect.com", "springer.com", "ieee.org")):
        return "peer_reviewed_or_publisher"
    return "web"


def trust_reason(url: str) -> str:
    """Generate a human-readable trust reason based on source type."""
    source_type = detect_source_type(url)
    reasons = {
        "gov": "Government domain with authoritative public-reference content.",
        "edu": "University or educational domain likely to provide instructional or technical references.",
        "peer_reviewed_or_publisher": "Recognized academic publisher or technical society domain.",
        "reference": "General reference source; useful for orientation but should be cross-checked.",
    }
    return reasons.get(source_type, "Public web source; verify relevance and credibility against stronger references when possible.")


def shorten_text(value: str, limit: int = 280) -> str:
    """Collapse whitespace and truncate text."""
    value = " ".join(value.split())
    return value if len(value) <= limit else f"{value[: limit - 3]}..."


def ensure_source_shape(source: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw search result into the standard evidence source shape."""
    return {
        "title": source.get("title", ""),
        "url": source.get("url", ""),
        "source_type": source.get("source_type") or detect_source_type(str(source.get("url", ""))),
        "trust_reason": source.get("trust_reason") or trust_reason(str(source.get("url", ""))),
        "verification_note": source.get("verification_note") or shorten_text(str(source.get("snippet", ""))),
    }


# ------------------------------------------------------------------
# Abstract backend
# ------------------------------------------------------------------

class ResearchBackend(ABC):
    """Abstract base class for web research execution backends."""

    name: str = "base"
    auto_execution: bool = False
    supported_modes: tuple[str, ...] = ("web_fallback", "deep_research")

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if this backend's prerequisites are met."""
        ...

    @abstractmethod
    def configuration_details(self) -> dict[str, Any]:
        """Return metadata about this backend's configuration."""
        ...

    @abstractmethod
    def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        """Execute a research task and return the standard result dict."""
        ...

    def supports(self, mode: str) -> bool:
        return mode in self.supported_modes

    def capability_info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "configured": self.is_configured(),
            "auto_execution": self.auto_execution,
            "supported_modes": list(self.supported_modes),
            **self.configuration_details(),
        }


# ------------------------------------------------------------------
# Concrete backends
# ------------------------------------------------------------------

class ManualAgentWebBackend(ResearchBackend):
    """No-op fallback: leaves tasks pending for manual/agent execution."""

    name = "manual_agent_web"
    auto_execution = False

    def is_configured(self) -> bool:
        return True

    def configuration_details(self) -> dict[str, Any]:
        return {
            "requires_third_party": False,
            "description": "Fallback planner backend that leaves tasks pending for manual or agent-driven execution.",
        }

    def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": task["id"],
            "status": "pending",
            "answer": "",
            "sources": [],
            "confidence": 0.0,
            "conflicts_with_notebook": None,
            "backend": self.name,
            "note": "No autonomous research backend is configured. Use manual or agent web research for this task.",
        }


class TavilyBackend(ResearchBackend):
    """Tavily Search API backend."""

    name = "tavily"
    auto_execution = True
    api_url = "https://api.tavily.com/search"

    def is_configured(self) -> bool:
        return bool(os.environ.get("TAVILY_API_KEY"))

    def configuration_details(self) -> dict[str, Any]:
        return {"env": "TAVILY_API_KEY", "requires_third_party": True}

    def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "api_key": os.environ["TAVILY_API_KEY"],
            "query": task["query"],
            "search_depth": "advanced" if task.get("mode") == "deep_research" else "basic",
            "max_results": 5,
            "include_answer": True,
        }
        try:
            response = _http_json("POST", self.api_url, payload=payload)
        except Exception as exc:
            logger.warning(f"[RESEARCH] Tavily API call failed: {exc}")
            return {"task_id": task["id"], "status": "failed", "answer": "", "sources": [], "confidence": 0.0, "backend": self.name, "error": str(exc)}

        sources = [
            ensure_source_shape({"title": item.get("title", ""), "url": item.get("url", ""), "snippet": item.get("content", "")})
            for item in response.get("results", [])
        ]
        return {
            "task_id": task["id"],
            "status": "completed" if sources or response.get("answer") else "failed",
            "answer": response.get("answer", ""),
            "sources": sources,
            "confidence": 0.8 if sources else 0.2,
            "conflicts_with_notebook": None,
            "backend": self.name,
        }


class SerperBackend(ResearchBackend):
    """Serper Google Search API backend."""

    name = "serper"
    auto_execution = True
    api_url = "https://google.serper.dev/search"

    def is_configured(self) -> bool:
        return bool(os.environ.get("SERPER_API_KEY"))

    def configuration_details(self) -> dict[str, Any]:
        return {"env": "SERPER_API_KEY", "requires_third_party": True}

    def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        try:
            response = _http_json(
                "POST",
                self.api_url,
                headers={"X-API-KEY": os.environ["SERPER_API_KEY"]},
                payload={"q": task["query"], "num": 5},
            )
        except Exception as exc:
            logger.warning(f"[RESEARCH] Serper API call failed: {exc}")
            return {"task_id": task["id"], "status": "failed", "answer": "", "sources": [], "confidence": 0.0, "backend": self.name, "error": str(exc)}

        sources = [
            ensure_source_shape({"title": item.get("title", ""), "url": item.get("link", ""), "snippet": item.get("snippet", "")})
            for item in response.get("organic", [])
        ]
        answer = response.get("answerBox", {}).get("answer") or response.get("answerBox", {}).get("snippet") or ""
        return {
            "task_id": task["id"],
            "status": "completed" if sources or answer else "failed",
            "answer": answer,
            "sources": sources,
            "confidence": 0.7 if sources else 0.2,
            "conflicts_with_notebook": None,
            "backend": self.name,
        }


class SerpApiBackend(ResearchBackend):
    """SerpAPI Google Search backend."""

    name = "serpapi"
    auto_execution = True

    def is_configured(self) -> bool:
        return bool(os.environ.get("SERPAPI_API_KEY"))

    def configuration_details(self) -> dict[str, Any]:
        return {"env": "SERPAPI_API_KEY", "requires_third_party": True}

    def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        query = urllib.parse.urlencode(
            {"engine": "google", "q": task["query"], "num": 5, "api_key": os.environ["SERPAPI_API_KEY"]}
        )
        try:
            response = _http_json("GET", f"https://serpapi.com/search.json?{query}")
        except Exception as exc:
            logger.warning(f"[RESEARCH] SerpAPI call failed: {exc}")
            return {"task_id": task["id"], "status": "failed", "answer": "", "sources": [], "confidence": 0.0, "backend": self.name, "error": str(exc)}

        sources = [
            ensure_source_shape({"title": item.get("title", ""), "url": item.get("link", ""), "snippet": item.get("snippet", "")})
            for item in response.get("organic_results", [])
        ]
        answer = response.get("answer_box", {}).get("answer") or response.get("answer_box", {}).get("snippet") or ""
        return {
            "task_id": task["id"],
            "status": "completed" if sources or answer else "failed",
            "answer": answer,
            "sources": sources,
            "confidence": 0.7 if sources else 0.2,
            "conflicts_with_notebook": None,
            "backend": self.name,
        }


class BrowserMcpBackend(ResearchBackend):
    """Shell-based Browser MCP search backend."""

    name = "browser_mcp"
    auto_execution = True

    def is_configured(self) -> bool:
        return bool(os.environ.get("BROWSER_MCP_SEARCH_COMMAND"))

    def configuration_details(self) -> dict[str, Any]:
        return {"env": "BROWSER_MCP_SEARCH_COMMAND", "requires_third_party": True}

    def execute(self, task: dict[str, Any]) -> dict[str, Any]:
        template = os.environ["BROWSER_MCP_SEARCH_COMMAND"]
        command = template.replace("{query}", task["query"]).replace("{mode}", task.get("mode", "web_fallback"))
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, check=False, timeout=60)
        except Exception as exc:
            logger.warning(f"[RESEARCH] BrowserMCP command failed: {exc}")
            return {"task_id": task["id"], "status": "failed", "answer": "", "sources": [], "confidence": 0.0, "backend": self.name, "error": str(exc)}

        stdout = result.stdout.strip()
        payload: dict[str, Any]
        try:
            payload = json.loads(stdout) if stdout else {}
        except json.JSONDecodeError:
            payload = {"answer": stdout}
        sources = [ensure_source_shape(item) for item in payload.get("sources", [])]
        answer = payload.get("answer", stdout)
        status = payload.get("status") or ("completed" if result.returncode == 0 and (answer or sources) else "failed")
        return {
            "task_id": task["id"],
            "status": status,
            "answer": answer,
            "sources": sources,
            "confidence": float(payload.get("confidence", 0.6 if sources else 0.2)),
            "conflicts_with_notebook": payload.get("conflicts_with_notebook"),
            "backend": self.name,
        }


# ------------------------------------------------------------------
# Registry and selection
# ------------------------------------------------------------------

BACKEND_REGISTRY: dict[str, ResearchBackend] = {
    backend.name: backend
    for backend in (
        ManualAgentWebBackend(),
        TavilyBackend(),
        SerperBackend(),
        SerpApiBackend(),
        BrowserMcpBackend(),
    )
}


def get_backend_registry() -> dict[str, ResearchBackend]:
    """Return the full backend registry."""
    return BACKEND_REGISTRY


def get_recommended_backend_order(mode: str) -> list[str]:
    """Return the recommended fallback order for a given research mode."""
    if mode == "deep_research":
        return ["tavily", "browser_mcp", "serper", "serpapi", "manual_agent_web"]
    return ["tavily", "serper", "serpapi", "browser_mcp", "manual_agent_web"]


def select_backend(mode: str, preferred: list[str] | None = None) -> ResearchBackend:
    """Select the best available backend for the given mode.

    Falls through the preferred order (or default order) until a
    configured backend is found. Always returns ManualAgentWebBackend
    as the ultimate fallback.
    """
    order = preferred or get_recommended_backend_order(mode)
    registry = get_backend_registry()
    for name in order:
        backend = registry.get(name)
        if backend and backend.supports(mode) and backend.is_configured():
            logger.info(f"[RESEARCH] Selected backend: {name}")
            return backend
    logger.info("[RESEARCH] No configured backend found — using manual_agent_web fallback")
    return registry["manual_agent_web"]


def get_backend_capability_matrix() -> dict[str, dict[str, Any]]:
    """Return a diagnostic matrix of all backends and their status."""
    return {name: backend.capability_info() for name, backend in get_backend_registry().items()}
