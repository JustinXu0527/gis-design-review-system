from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from .extractors import extract_marked_json, extract_text
from .local_llm_client import LocalOllamaClient


RULE_SCHEMA_HINT = {
    "clauses": [
        {
            "standard_id": "string",
            "standard_name": "string",
            "version": "string",
            "is_placeholder": False,
            "clause_id": "string",
            "title": "string",
            "summary": "string",
            "applicable_objects": ["fiber_cable"],
            "scenario": "string",
            "risk_level": "high|medium|low",
            "recommendation": "string",
            "rules": [
                {
                    "id": "string",
                    "type": "min_distance|min_property|max_property|required_properties|unique_resource|max_ratio|capacity_check|topology_connectivity|manual_review",
                    "params": {},
                }
            ],
        }
    ]
}


class StandardParser:
    def __init__(self) -> None:
        self.client = LocalOllamaClient()

    def parse_upload(self, filename: str, raw: bytes) -> dict[str, Any]:
        text = extract_text(filename, raw)
        suffix = Path(filename).suffix.lower()
        embedded = extract_marked_json(text, "BEGIN_STANDARD_RULES_JSON", "END_STANDARD_RULES_JSON")
        if embedded is not None:
            return _normalize_standard_doc(embedded, filename)
        if suffix in {".json", ".geojson"}:
            try:
                data = json.loads(text)
                if "clauses" in data:
                    return _normalize_standard_doc(data, filename)
            except json.JSONDecodeError:
                pass
        if self.client.enabled and self.client.status().get("available"):
            return self._parse_with_llm(filename, text)
        return self._parse_without_llm(filename, text)

    def _parse_with_llm(self, filename: str, text: str) -> dict[str, Any]:
        system_prompt = (
            "你是通信工程设计审查标准解析器。只输出 JSON。"
            "把行业规范、企业标准、地方建设要求、设计审查手册或历史审查案例"
            "转成可追溯的结构化条款和可计算规则。"
            "不得编造原文不存在的强制阈值；无法计算的条款用 manual_review 规则。"
        )
        user_prompt = (
            f"文件名：{filename}\n"
            f"目标 JSON Schema 示例：{json.dumps(RULE_SCHEMA_HINT, ensure_ascii=False)}\n"
            "规则 params 约定：min_distance 需要 object_types、threshold_m；"
            "min_property/max_property 需要 object_type、property、threshold，可选 filters、unit；"
            "required_properties 需要 object_type、properties；unique_resource 需要 object_type、properties；"
            "max_ratio 需要 object_type、length_property、direct_distance_property、max_ratio；"
            "capacity_check 需要 object_type、capacity_property、demand_property；"
            "topology_connectivity 需要 edge_type、start_property、end_property。\n"
            "请优先抽取审查对象、适用场景、约束条件、距离阈值、资源要求、风险等级、整改建议和条款摘要。\n"
            "标准文本如下：\n"
            f"{text[:18000]}"
        )
        data = self.client.chat_json(system_prompt, user_prompt, task="standard_parse")
        parsed = _normalize_standard_doc(data, filename)
        parsed["parser"] = {"provider": "ollama", "selected_model": self.client.last_model, "base_url": self.client.base_url}
        return parsed

    def _parse_without_llm(self, filename: str, text: str) -> dict[str, Any]:
        clauses = []
        for index, part in enumerate(_split_clauses(text), start=1):
            clause_id = f"UNPARSED-{index:03d}"
            clauses.append(
                {
                    "standard_id": Path(filename).stem,
                    "standard_name": Path(filename).stem,
                    "version": "uploaded",
                    "is_placeholder": False,
                    "clause_id": clause_id,
                    "title": part[:40] or clause_id,
                    "summary": part[:240],
                    "applicable_objects": [],
                    "scenario": "待 LLM 解析或人工结构化",
                    "risk_level": "medium",
                    "recommendation": "请启动本地 Ollama 服务后重新解析，或上传已结构化 JSON 标准库。",
                    "rules": [{"id": f"{clause_id}-manual", "type": "manual_review", "params": {}}],
                }
            )
        return _normalize_standard_doc({"clauses": clauses}, filename)


def _split_clauses(text: str) -> list[str]:
    chunks = [chunk.strip() for chunk in re.split(r"\n\s*(?=(?:第?\d+[.、]|\d+\.\d+|[一二三四五六七八九十]+、))", text) if chunk.strip()]
    if not chunks and text.strip():
        chunks = [text.strip()]
    return chunks[:100]


def _normalize_standard_doc(data: dict[str, Any], filename: str) -> dict[str, Any]:
    clauses = []
    for index, clause in enumerate(data.get("clauses", []), start=1):
        standard_id = str(clause.get("standard_id") or Path(filename).stem)
        clause_id = str(clause.get("clause_id") or f"C-{index:03d}")
        normalized_rules = []
        for rule_index, rule in enumerate(clause.get("rules", []), start=1):
            normalized_rules.append(
                {
                    "id": str(rule.get("id") or f"{standard_id}-{clause_id}-R{rule_index}"),
                    "type": str(rule.get("type") or "manual_review"),
                    "params": rule.get("params") or {},
                }
            )
        if not normalized_rules:
            normalized_rules = [{"id": f"{standard_id}-{clause_id}-manual", "type": "manual_review", "params": {}}]
        clauses.append(
            {
                "id": str(clause.get("id") or uuid.uuid4().hex),
                "standard_id": standard_id,
                "standard_name": str(clause.get("standard_name") or standard_id),
                "version": str(clause.get("version") or "uploaded"),
                "is_placeholder": bool(clause.get("is_placeholder", False)),
                "clause_id": clause_id,
                "title": str(clause.get("title") or clause_id),
                "summary": str(clause.get("summary") or ""),
                "applicable_objects": clause.get("applicable_objects") or [],
                "scenario": str(clause.get("scenario") or ""),
                "risk_level": str(clause.get("risk_level") or "medium"),
                "recommendation": str(clause.get("recommendation") or "结合现场与设计资料复核后整改。"),
                "rules": normalized_rules,
            }
        )
    return {"source_file": filename, "clauses": clauses}
