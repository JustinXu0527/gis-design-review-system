from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import httpx

from .env_config import load_env_file


class QgisMcpClient:
    """Synchronous MCP JSON-RPC adapter for the Docker-hosted stateless HTTP service."""

    def __init__(self) -> None:
        # Keep command-line tools and ASGI launchers consistent with main.py.
        load_env_file(Path(__file__).resolve().parents[1] / ".env")
        self.base_url = os.getenv("QGIS_MCP_SERVER_URL", "").strip().rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def call_tool(self, tool_name: str, arguments: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("QGIS_MCP_SERVER_URL is not configured.")
        try:
            response = httpx.post(
                self.base_url,
                headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
                json={
                    "jsonrpc": "2.0",
                    "id": uuid.uuid4().hex,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                },
                timeout=timeout,
                trust_env=False,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                raise RuntimeError(str(payload["error"]))
            result = payload.get("result") or {}
            if result.get("isError"):
                raise RuntimeError(str(result.get("content") or "MCP tool returned an error."))
            structured = result.get("structuredContent")
            if isinstance(structured, dict):
                return structured
            for item in result.get("content") or []:
                if item.get("type") != "text" or not item.get("text"):
                    continue
                text = str(item["text"])
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    return {"content": text}
                if isinstance(parsed, dict):
                    return parsed
            return {"content": result.get("content") or []}
        except Exception as exc:
            raise RuntimeError(f"QGIS MCP tool {tool_name} failed: {exc}") from exc
