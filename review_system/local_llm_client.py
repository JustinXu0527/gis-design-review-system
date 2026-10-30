from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any


class LocalOllamaClient:
    """Local Ollama client used by the website and smoke tests."""

    def __init__(self) -> None:
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:12000").rstrip("/")
        self.llm_model = os.getenv("OLLAMA_LLM_MODEL", os.getenv("OLLAMA_MODEL", "qwen2.5:32b")).strip()
        self.embed_model = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3").strip()
        self.temperature = float(os.getenv("OLLAMA_TEMPERATURE", "0"))
        self.num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
        self.last_model = ""
        self.last_error = ""

    @property
    def enabled(self) -> bool:
        return bool(self.llm_model and _langchain_ollama_available())

    @property
    def embeddings_enabled(self) -> bool:
        return bool(self.embed_model and _langchain_ollama_available())

    def status(self) -> dict[str, Any]:
        available, models, error = self._server_status()
        self.last_error = error
        return {
            "provider": "ollama",
            "enabled": self.enabled,
            "embeddings_enabled": self.embeddings_enabled,
            "available": available,
            "base_url": self.base_url,
            "llm_model": self.llm_model,
            "embed_model": self.embed_model,
            "temperature": self.temperature,
            "num_ctx": self.num_ctx,
            "last_model": self.last_model,
            "models": models,
            "error": error,
        }

    def chat_json(self, system_prompt: str, user_prompt: str, timeout: int = 120, task: str = "review_agent") -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("langchain-ollama is not installed or OLLAMA_LLM_MODEL is empty")

        selected_model = self.choose_model(task)
        self.last_model = selected_model
        payload = {
            "model": selected_model,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_ctx": self.num_ctx,
            },
            "messages": [
                {"role": "system", "content": system_prompt + "\n只输出一个合法 JSON 对象，不要输出 Markdown。"},
                {"role": "user", "content": user_prompt},
            ],
        }
        content = self._post_ollama_json("/api/chat", payload, timeout).get("message", {}).get("content", "")
        return json.loads(_extract_json(str(content)))

    def embed_query(self, text: str) -> list[float]:
        if not self.embeddings_enabled:
            raise RuntimeError("langchain-ollama is not installed or OLLAMA_EMBED_MODEL is empty")
        from langchain_ollama import OllamaEmbeddings

        embeddings = OllamaEmbeddings(model=self.embed_model, base_url=self.base_url)
        return embeddings.embed_query(text)

    def _post_ollama_json(self, path: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama HTTP {exc.code}: {body or exc.reason}") from exc

    def choose_model(self, task: str = "review_agent") -> str:
        return self.llm_model

    def _server_status(self) -> tuple[bool, list[str], str]:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=3) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return False, [], str(exc)
        models = []
        for item in data.get("models", []):
            name = item.get("name") or item.get("model")
            if name:
                models.append(str(name))
        return True, models, ""


def _extract_json(content: str) -> str:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fenced:
        text = fenced.group(1).strip()
    if text.startswith("{"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _langchain_ollama_available() -> bool:
    try:
        import langchain_ollama  # noqa: F401
    except ImportError:
        return False
    return True
