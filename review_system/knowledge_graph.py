from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GRAPH_PATH = ROOT / "data" / "knowledge_base" / "standards_knowledge_graph.json"


def ensure_knowledge_graph(clauses: list[dict[str, Any]], path: Path = DEFAULT_GRAPH_PATH) -> dict[str, Any]:
    """Build and cache a lightweight standards knowledge graph.

    The graph is intentionally stored as JSON so the current project does not
    need a graph database. It models standards, clauses, rules, object types,
    checked properties, risk levels and their relationships.
    """

    fingerprint = _clauses_fingerprint(clauses)
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if cached.get("fingerprint") == fingerprint:
                return cached
        except (OSError, json.JSONDecodeError):
            pass

    graph = build_knowledge_graph(clauses)
    graph["fingerprint"] = fingerprint
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    return graph


def build_knowledge_graph(clauses: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edge_keys: set[tuple[str, str, str]] = set()
    edges: list[dict[str, str]] = []

    def add_node(node_id: str, node_type: str, name: str, **extra: Any) -> None:
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "type": node_type, "name": name, **{k: v for k, v in extra.items() if v not in (None, "", [])}}

    def add_edge(source: str, target: str, relation: str) -> None:
        key = (source, target, relation)
        if source and target and key not in edge_keys:
            edge_keys.add(key)
            edges.append({"source": source, "target": target, "relation": relation})

    for clause in clauses:
        standard_name = str(clause.get("standard_name") or "未命名标准").strip()
        standard_id = f"standard:{_slug(clause.get('standard_id') or standard_name)}"
        clause_key = _clause_key(clause)
        clause_id = f"clause:{clause_key}"
        risk_level = str(clause.get("risk_level") or "medium")

        add_node(standard_id, "standard", standard_name, source_file=clause.get("source_file"))
        add_node(
            clause_id,
            "clause",
            str(clause.get("title") or clause.get("clause_id") or clause_key),
            standard_name=standard_name,
            clause_id=clause.get("clause_id"),
            summary=clause.get("summary"),
            scenario=clause.get("scenario"),
            recommendation=clause.get("recommendation"),
            risk_level=risk_level,
        )
        add_edge(standard_id, clause_id, "contains_clause")

        risk_id = f"risk_level:{risk_level}"
        add_node(risk_id, "risk_level", _risk_level_label(risk_level))
        add_edge(clause_id, risk_id, "may_trigger")

        for object_type in _as_list(clause.get("applicable_objects")):
            object_node = f"object_type:{_slug(object_type)}"
            add_node(object_node, "object_type", str(object_type))
            add_edge(clause_id, object_node, "applies_to")

        for rule in clause.get("rules") or []:
            rule_id = f"rule:{_slug(rule.get('id') or f'{clause_key}:{len(edges)}')}"
            rule_type = str(rule.get("type") or "manual_review")
            add_node(rule_id, "rule", str(rule.get("id") or rule_type), rule_type=rule_type)
            add_edge(clause_id, rule_id, "has_rule")

            rule_type_node = f"rule_type:{_slug(rule_type)}"
            add_node(rule_type_node, "rule_type", _rule_type_label(rule_type))
            add_edge(rule_id, rule_type_node, "uses_rule_type")

            params = rule.get("params") or {}
            for object_type in _object_types_from_params(params):
                object_node = f"object_type:{_slug(object_type)}"
                add_node(object_node, "object_type", str(object_type))
                add_edge(rule_id, object_node, "checks_object")
                add_edge(clause_id, object_node, "applies_to")

            for prop in _properties_from_params(params):
                prop_node = f"property:{_slug(prop)}"
                add_node(prop_node, "property", str(prop))
                add_edge(rule_id, prop_node, "checks_property")

            relation = _spatial_relation(rule_type)
            if relation:
                relation_node = f"spatial_relation:{_slug(relation)}"
                add_node(relation_node, "spatial_relation", relation)
                add_edge(rule_id, relation_node, "checks_spatial_relation")

    node_values = list(nodes.values())
    type_counts = Counter(node["type"] for node in node_values)
    return {
        "version": "1.0",
        "description": "轻量标准知识图谱：标准-条款-规则-对象-属性-空间关系-风险等级。",
        "node_count": len(node_values),
        "edge_count": len(edges),
        "node_type_counts": dict(sorted(type_counts.items())),
        "nodes": sorted(node_values, key=lambda item: (item["type"], item["id"])),
        "edges": edges,
    }


def retrieve_knowledge_graph_context(
    clauses: list[dict[str, Any]],
    project: dict[str, Any],
    computed_risks: list[dict[str, Any]],
    execution_log: list[dict[str, Any]],
    retrieved_clauses: list[dict[str, Any]] | None = None,
    limit: int = 2000,
) -> dict[str, Any]:
    graph = ensure_knowledge_graph(clauses)
    clause_by_key = {_clause_key(clause): clause for clause in clauses}
    object_by_id = {str(obj.get("id")): obj for obj in project.get("objects", [])}
    selected_keys = _selected_clause_keys(computed_risks, execution_log, retrieved_clauses or [])

    chains = []
    for risk in computed_risks[:limit]:
        clause = risk.get("clause") or {}
        key = _identity_key(clause.get("standard_name"), clause.get("clause_id"))
        source_clause = clause_by_key.get(key) or clause
        object_ids = [str(item) for item in (risk.get("evidence") or {}).get("object_ids", []) if str(item)]
        objects = [object_by_id[item] for item in object_ids if item in object_by_id][:4]
        chain = _risk_chain(risk, source_clause, objects)
        if chain:
            chains.append(chain)

    applicable = []
    for key in selected_keys[:limit]:
        clause = clause_by_key.get(key)
        if clause:
            applicable.append(_clause_context(clause))

    return {
        "status": "ok",
        "graph_path": str(DEFAULT_GRAPH_PATH.relative_to(ROOT)),
        "node_count": graph.get("node_count", 0),
        "edge_count": graph.get("edge_count", 0),
        "node_type_counts": graph.get("node_type_counts", {}),
        "selected_clause_count": len(applicable),
        "risk_chain_count": len(chains),
        "applicable_clauses": applicable[:limit],
        "risk_chains": chains[:limit],
    }


def enrich_risks_with_knowledge_graph(risks: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
    chains = {str(chain.get("risk_id")): chain for chain in context.get("risk_chains", []) if chain.get("risk_id")}
    if not chains:
        return risks
    enriched = []
    for risk in risks:
        item = dict(risk)
        chain = chains.get(str(item.get("id")))
        if chain:
            item["knowledge_graph"] = {
                "verified": True,
                "chain": chain.get("chain", []),
                "checked_properties": chain.get("checked_properties", []),
                "applicable_objects": chain.get("applicable_objects", []),
                "rule_types": chain.get("rule_types", []),
            }
        enriched.append(item)
    return enriched


def _risk_chain(risk: dict[str, Any], clause: dict[str, Any], objects: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = risk.get("evidence") or {}
    checked_properties = sorted(_properties_for_clause(clause))
    applicable_objects = [str(item) for item in _as_list(clause.get("applicable_objects"))]
    rule_types = sorted({str(rule.get("type") or "manual_review") for rule in clause.get("rules") or []})
    object_names = [str(obj.get("name") or obj.get("id")) for obj in objects]

    chain = [
        str(clause.get("standard_name") or (risk.get("clause") or {}).get("standard_name") or "导入标准库"),
        f"条款 {(clause.get('clause_id') or (risk.get('clause') or {}).get('clause_id') or '-')}：{clause.get('title') or (risk.get('title') or '')}",
        f"适用对象：{'、'.join(applicable_objects) if applicable_objects else '按规则匹配'}",
        f"命中对象：{'、'.join(object_names) if object_names else '未绑定具体对象'}",
        f"计算证据：{evidence.get('calculation') or '规则执行证据'}",
        f"风险等级：{_risk_level_label(str(risk.get('level') or clause.get('risk_level') or 'medium'))}",
    ]
    return {
        "risk_id": risk.get("id"),
        "title": risk.get("title"),
        "level": risk.get("level"),
        "clause_key": _clause_key(clause),
        "checked_properties": checked_properties,
        "applicable_objects": applicable_objects,
        "rule_types": rule_types,
        "chain": chain,
    }


def _clause_context(clause: dict[str, Any]) -> dict[str, Any]:
    return {
        "standard_name": clause.get("standard_name"),
        "clause_id": clause.get("clause_id"),
        "title": clause.get("title"),
        "summary": clause.get("summary"),
        "risk_level": clause.get("risk_level"),
        "applicable_objects": _as_list(clause.get("applicable_objects")),
        "checked_properties": sorted(_properties_for_clause(clause)),
        "rule_types": sorted({str(rule.get("type") or "manual_review") for rule in clause.get("rules") or []}),
        "recommendation": clause.get("recommendation"),
    }


def _selected_clause_keys(
    computed_risks: list[dict[str, Any]], execution_log: list[dict[str, Any]], retrieved_clauses: list[dict[str, Any]]
) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for risk in computed_risks:
        clause = risk.get("clause") or {}
        key = _identity_key(clause.get("standard_name"), clause.get("clause_id"))
        if key and key not in seen:
            keys.append(key)
            seen.add(key)
    for item in execution_log:
        if item.get("finding_count", 0):
            key = _identity_key(item.get("standard_name"), item.get("clause_id"))
            if key and key not in seen:
                keys.append(key)
                seen.add(key)
    for clause in retrieved_clauses:
        key = _clause_key(clause)
        if key and key not in seen:
            keys.append(key)
            seen.add(key)
    return keys


def _clauses_fingerprint(clauses: list[dict[str, Any]]) -> str:
    text = json.dumps(clauses, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clause_key(clause: dict[str, Any]) -> str:
    return _identity_key(clause.get("standard_name"), clause.get("clause_id")) or str(clause.get("id") or "")


def _identity_key(standard_name: Any, clause_id: Any) -> str:
    left = str(standard_name or "").strip()
    right = str(clause_id or "").strip()
    return f"{left}::{right}" if left or right else ""


def _properties_for_clause(clause: dict[str, Any]) -> set[str]:
    props: set[str] = set()
    for rule in clause.get("rules") or []:
        props.update(_properties_from_params(rule.get("params") or {}))
    return props


def _properties_from_params(params: dict[str, Any]) -> set[str]:
    keys = {
        "property",
        "length_property",
        "direct_distance_property",
        "capacity_property",
        "demand_property",
        "start_property",
        "end_property",
    }
    props = {str(params.get(key)) for key in keys if params.get(key)}
    props.update(str(item) for item in _as_list(params.get("properties")) if item)
    filters = params.get("filters")
    if isinstance(filters, dict):
        props.update(str(key) for key in filters.keys())
    return props


def _object_types_from_params(params: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for key in ("object_type", "edge_type", "container_type", "contained_type"):
        if params.get(key):
            values.add(str(params[key]))
    for item in _as_list(params.get("object_types")):
        if isinstance(item, dict):
            if item.get("type"):
                values.add(str(item["type"]))
        elif item:
            values.add(str(item))
    return values


def _spatial_relation(rule_type: str) -> str:
    return {
        "min_distance": "最小距离",
        "must_be_within": "包含/位于范围内",
        "forbidden_intersection": "禁止相交",
        "crossing_requires_properties": "穿越关系",
        "topology_connectivity": "拓扑连通",
        "geometry_validity": "几何有效性",
        "required_geometry": "几何存在性",
    }.get(rule_type, "")


def _rule_type_label(rule_type: str) -> str:
    return {
        "min_distance": "最小距离审查",
        "min_property": "属性下限审查",
        "max_property": "属性上限审查",
        "required_properties": "属性完整性审查",
        "required_any_property": "至少一项属性审查",
        "allowed_values": "枚举值审查",
        "unique_resource": "资源唯一性审查",
        "max_ratio": "比例上限审查",
        "capacity_check": "容量审查",
        "topology_connectivity": "拓扑连通审查",
        "required_geometry": "几何完整性审查",
        "geometry_validity": "几何有效性审查",
        "must_be_within": "包含关系审查",
        "forbidden_intersection": "禁止相交审查",
        "crossing_requires_properties": "穿越属性审查",
        "manual_review": "人工复核",
    }.get(rule_type, rule_type)


def _risk_level_label(level: str) -> str:
    return {"high": "高风险", "medium": "中风险", "low": "低风险", "unknown": "未定级"}.get(level, level)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _slug(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown"
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
