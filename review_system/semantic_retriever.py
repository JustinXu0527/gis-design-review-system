from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from .local_llm_client import LocalOllamaClient


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT / "data" / "knowledge_base" / "ollama_clause_embeddings.json"


class StandardSemanticRetriever:
    """Embedding-backed clause retrieval for the local review agent."""

    def __init__(self, clauses: list[dict[str, Any]], client: LocalOllamaClient | None = None, cache_path: Path = DEFAULT_CACHE) -> None:
        self.clauses = clauses
        self.client = client or LocalOllamaClient()
        self.cache_path = cache_path
        self.enabled = os.getenv("OLLAMA_ENABLE_EMBEDDING_RETRIEVAL", "1").strip().lower() not in {"0", "false", "no"}

    def retrieve(
        self,
        project: dict[str, Any],
        computed_risks: list[dict[str, Any]],
        execution_log: list[dict[str, Any]],
        limit: int = 60,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        meta: dict[str, Any] = {
            "enabled": self.enabled and self.client.embeddings_enabled,
            "provider": "ollama",
            "model": self.client.embed_model,
            "cache": str(self.cache_path.relative_to(ROOT)),
            "status": "disabled",
            "selected_count": 0,
            "error": "",
        }
        if not self.clauses:
            return [], meta | {"status": "empty"}
        if not self.enabled or not self.client.embeddings_enabled:
            selected = self.clauses[:limit]
            meta.update({"selected_count": len(selected), "top_clauses": _selected_meta(selected)})
            return selected, meta

        status = self.client.status()
        if not status.get("available"):
            selected = self._hybrid_fallback(computed_risks, execution_log, limit)
            meta.update({"status": "unavailable", "selected_count": len(selected), "top_clauses": _selected_meta(selected), "error": status.get("error", "")})
            return selected, meta

        query = _project_query(project, computed_risks, execution_log)
        if not query.strip():
            selected = self._hybrid_fallback(computed_risks, execution_log, limit)
            meta.update({"status": "empty_query", "selected_count": len(selected), "top_clauses": _selected_meta(selected)})
            return selected, meta

        try:
            cache = _read_cache(self.cache_path)
            query_vec = self.client.embed_query(query)
            scored: list[tuple[float, int, dict[str, Any]]] = []
            changed = False
            for index, clause in enumerate(self.clauses):
                text = _clause_text(clause)
                key = _cache_key(clause, text, self.client.base_url, self.client.embed_model)
                cached = cache.get(key, {})
                vector = cached.get("embedding")
                if not _valid_vector(vector):
                    vector = self.client.embed_query(text[:5000])
                    cache[key] = {
                        "embedding": vector,
                        "model": self.client.embed_model,
                        "base_url": self.client.base_url,
                        "standard_name": clause.get("standard_name"),
                        "clause_id": clause.get("clause_id"),
                    }
                    changed = True
                scored.append((_cosine(query_vec, vector), index, clause))
            if changed:
                _write_cache(self.cache_path, cache)
        except Exception as exc:
            selected = self._hybrid_fallback(computed_risks, execution_log, limit)
            meta.update({"status": "error", "selected_count": len(selected), "top_clauses": _selected_meta(selected), "error": str(exc)})
            return selected, meta

        selected = self._merge_anchored_and_scored(computed_risks, execution_log, scored, limit)
        meta.update({"status": "ok", "selected_count": len(selected), "top_clauses": _selected_meta(selected), "query_chars": len(query)})
        return selected, meta

    def _hybrid_fallback(self, computed_risks: list[dict[str, Any]], execution_log: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        anchored = _anchored_clause_keys(computed_risks, execution_log)
        selected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for clause in self.clauses:
            key = _clause_identity(clause)
            if key in anchored:
                selected.append({**clause, "_retrieval_reason": "rule_hit"})
                seen.add(key)
        for clause in self.clauses:
            if len(selected) >= limit:
                break
            key = _clause_identity(clause)
            if key not in seen:
                selected.append(clause)
                seen.add(key)
        return selected[:limit]

    def _merge_anchored_and_scored(
        self,
        computed_risks: list[dict[str, Any]],
        execution_log: list[dict[str, Any]],
        scored: list[tuple[float, int, dict[str, Any]]],
        limit: int,
    ) -> list[dict[str, Any]]:
        anchored = _anchored_clause_keys(computed_risks, execution_log)
        selected: list[dict[str, Any]] = []
        seen: set[str] = set()
        score_by_key = {_clause_identity(clause): score for score, _, clause in scored}
        for clause in self.clauses:
            key = _clause_identity(clause)
            if key in anchored:
                selected.append({**clause, "_semantic_score": round(score_by_key.get(key, 0.0), 4), "_retrieval_reason": "rule_hit"})
                seen.add(key)
        for score, _, clause in sorted(scored, key=lambda item: item[0], reverse=True):
            if len(selected) >= limit:
                break
            key = _clause_identity(clause)
            if key in seen:
                continue
            selected.append({**clause, "_semantic_score": round(score, 4), "_retrieval_reason": "embedding"})
            seen.add(key)
        return selected[:limit]


def _project_query(project: dict[str, Any], computed_risks: list[dict[str, Any]], execution_log: list[dict[str, Any]]) -> str:
    parts: list[str] = [
        str(project.get("name") or ""),
        " ".join(str(doc.get("filename") or "") for doc in project.get("documents", [])[:20]),
    ]
    for obj in project.get("objects", [])[:120]:
        props = obj.get("properties") or {}
        prop_text = " ".join(f"{key}={value}" for key, value in list(props.items())[:20])
        parts.append(f"{obj.get('id')} {obj.get('type')} {obj.get('name')} {prop_text}")
    for risk in computed_risks[:80]:
        clause = risk.get("clause") or {}
        evidence = risk.get("evidence") or {}
        parts.append(
            " ".join(
                str(item or "")
                for item in [
                    risk.get("title"),
                    risk.get("category"),
                    risk.get("description"),
                    risk.get("recommendation"),
                    clause.get("standard_name"),
                    clause.get("clause_id"),
                    clause.get("summary"),
                    evidence.get("calculation"),
                ]
            )
        )
    for item in execution_log[:160]:
        if item.get("finding_count", 0):
            parts.append(f"{item.get('standard_name')} {item.get('clause_id')} {item.get('rule_type')} finding={item.get('finding_count')}")
    return "\n".join(part for part in parts if part)[:12000]


def _selected_meta(clauses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "standard_name": clause.get("standard_name"),
            "version": clause.get("version"),
            "clause_id": clause.get("clause_id"),
            "title": clause.get("title"),
            "semantic_score": clause.get("_semantic_score"),
            "retrieval_reason": clause.get("_retrieval_reason"),
        }
        for clause in clauses[:10]
    ]


def _clause_text(clause: dict[str, Any]) -> str:
    return "\n".join(
        [
            str(clause.get("standard_name") or ""),
            str(clause.get("version") or ""),
            str(clause.get("clause_id") or ""),
            str(clause.get("title") or ""),
            str(clause.get("summary") or ""),
            str(clause.get("scenario") or ""),
            str(clause.get("recommendation") or ""),
            " ".join(str(item) for item in clause.get("applicable_objects") or []),
            str(clause.get("source_excerpt") or ""),
            json.dumps(clause.get("rules") or [], ensure_ascii=False, sort_keys=True),
        ]
    )


def _anchored_clause_keys(computed_risks: list[dict[str, Any]], execution_log: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for risk in computed_risks:
        clause = risk.get("clause") or {}
        key = _identity_from_parts(clause.get("standard_name"), clause.get("clause_id"))
        if key:
            keys.add(key)
    for item in execution_log:
        if item.get("finding_count", 0):
            key = _identity_from_parts(item.get("standard_name"), item.get("clause_id"))
            if key:
                keys.add(key)
    return keys


def _clause_identity(clause: dict[str, Any]) -> str:
    return _identity_from_parts(clause.get("standard_name"), clause.get("clause_id")) or str(clause.get("id") or "")


def _identity_from_parts(standard_name: Any, clause_id: Any) -> str:
    left = str(standard_name or "").strip()
    right = str(clause_id or "").strip()
    return f"{left}::{right}" if left or right else ""


def _cache_key(clause: dict[str, Any], text: str, base_url: str, model: str) -> str:
    fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
    identity = _clause_identity(clause)
    return hashlib.sha256(f"{base_url}|{model}|{identity}|{fingerprint}".encode("utf-8")).hexdigest()


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _valid_vector(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, (int, float)) for item in value[:8])


def _read_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_cache(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
