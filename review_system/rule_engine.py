from __future__ import annotations

import itertools
import uuid
from collections import defaultdict, deque
from typing import Any, Callable

from .geometry import geometry_distance, risk_geometry, to_shape
from .models import DesignObject, ReviewEvidence, RiskFinding


class RuleEngine:
    """Deterministic rule engine for unified GIS engineering objects."""

    def __init__(self, clauses: list[dict[str, Any]]) -> None:
        self.clauses = clauses
        self.execution_log: list[dict[str, Any]] = []

    def review(
        self,
        objects_data: list[dict[str, Any]],
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        objects = [DesignObject(**item) for item in objects_data]
        findings: list[RiskFinding] = []
        self.execution_log = []
        total_rules = sum(len(clause.get("rules", [])) for clause in self.clauses)
        completed_rules = 0
        for clause in self.clauses:
            for rule in clause.get("rules", []):
                before = len(findings)
                rule_type = str(rule.get("type") or "manual_review")
                findings.extend(self._run_rule(rule, clause, objects))
                self.execution_log.append(
                    {
                        "rule_id": rule.get("id"),
                        "rule_type": rule_type,
                        "clause_id": clause.get("clause_id"),
                        "standard_name": clause.get("standard_name"),
                        "finding_count": len(findings) - before,
                        "computable": rule_type != "manual_review",
                    }
                )
                completed_rules += 1
                if progress_callback:
                    try:
                        progress_callback(
                            {
                                "event": "rule_progress",
                                "objects_read": len(objects),
                                "rules_total": total_rules,
                                "rules_completed": completed_rules,
                                "risk_count": len(findings),
                                "current_rule": str(rule.get("id") or rule_type),
                            }
                        )
                    except Exception:
                        pass
        return [finding.to_dict() for finding in findings], self.execution_log

    def _run_rule(self, rule: dict[str, Any], clause: dict[str, Any], objects: list[DesignObject]) -> list[RiskFinding]:
        rule_type = str(rule.get("type") or "manual_review")
        params = rule.get("params") or {}
        if rule_type == "manual_review":
            return []
        if rule_type == "min_distance":
            return self._min_distance(rule, clause, params, objects)
        if rule_type == "min_property":
            return self._property_threshold(rule, clause, params, objects, mode="min")
        if rule_type == "max_property":
            return self._property_threshold(rule, clause, params, objects, mode="max")
        if rule_type == "required_properties":
            return self._required_properties(rule, clause, params, objects)
        if rule_type == "required_any_property":
            return self._required_any_property(rule, clause, params, objects)
        if rule_type == "allowed_values":
            return self._allowed_values(rule, clause, params, objects)
        if rule_type == "unique_resource":
            return self._unique_resource(rule, clause, params, objects)
        if rule_type == "max_ratio":
            return self._max_ratio(rule, clause, params, objects)
        if rule_type == "capacity_check":
            return self._capacity_check(rule, clause, params, objects)
        if rule_type == "topology_connectivity":
            return self._topology_connectivity(rule, clause, params, objects)
        if rule_type == "required_geometry":
            return self._required_geometry(rule, clause, params, objects)
        if rule_type == "geometry_validity":
            return self._geometry_validity(rule, clause, params, objects)
        if rule_type == "min_feature_count":
            return self._min_feature_count(rule, clause, params, objects)
        if rule_type == "must_be_within":
            return self._must_be_within(rule, clause, params, objects)
        if rule_type == "forbidden_intersection":
            return self._forbidden_intersection(rule, clause, params, objects)
        if rule_type == "crossing_requires_properties":
            return self._crossing_requires_properties(rule, clause, params, objects)
        return []

    def _min_distance(self, rule: dict[str, Any], clause: dict[str, Any], params: dict[str, Any], objects: list[DesignObject]) -> list[RiskFinding]:
        types = params.get("object_types") or []
        if len(types) != 2:
            return []
        threshold = float(params.get("threshold_m", 0))
        max_findings = int(params.get("max_findings", 200))
        left = self._matching_objects(types[0], objects)
        right = self._matching_objects(types[1], objects)
        findings: list[RiskFinding] = []
        for a, b in itertools.product(left, right):
            if a.id == b.id:
                continue
            actual = geometry_distance(a.geometry, b.geometry)
            if actual is not None and actual < threshold:
                findings.append(
                    self._finding(
                        "空间距离不足",
                        "GIS空间审查",
                        clause,
                        ReviewEvidence(
                            calculation=f"{a.id} 与 {b.id} 的最小空间距离",
                            actual_value=round(actual, 3),
                            threshold=threshold,
                            unit="m",
                            object_ids=[a.id, b.id],
                        ),
                        f"{a.name} 与 {b.name} 的距离为 {actual:.2f}m，小于阈值 {threshold:.2f}m。",
                        risk_geometry(a.geometry, b.geometry),
                    )
                )
                if len(findings) >= max_findings:
                    break
        return findings

    def _property_threshold(
        self,
        rule: dict[str, Any],
        clause: dict[str, Any],
        params: dict[str, Any],
        objects: list[DesignObject],
        mode: str,
    ) -> list[RiskFinding]:
        prop = str(params.get("property") or "").strip()
        if not prop:
            return []
        try:
            threshold = _to_float(params.get("threshold"))
        except (TypeError, ValueError):
            return []
        object_spec: Any = {"type": params.get("object_type"), "filters": params.get("filters") or {}}
        unit = str(params.get("unit") or "")
        max_findings = int(params.get("max_findings", 0) or 0)
        findings: list[RiskFinding] = []
        for obj in self._matching_objects(object_spec, objects):
            raw_value = obj.properties.get(prop)
            try:
                actual = _to_float(raw_value)
            except (TypeError, ValueError):
                continue
            failed = actual < threshold if mode == "min" else actual > threshold
            if not failed:
                continue
            op_text = ">=" if mode == "min" else "<="
            findings.append(
                self._finding(
                    "指标阈值不满足",
                    "属性阈值审查",
                    clause,
                    ReviewEvidence(
                        calculation=f"{obj.id}: {prop} {op_text} {threshold:g}{unit}",
                        actual_value=actual,
                        threshold=threshold,
                        unit=unit,
                        object_ids=[obj.id],
                    ),
                    f"{obj.name} 的 {prop} 为 {actual:g}{unit}，不满足阈值 {op_text} {threshold:g}{unit}。",
                    risk_geometry(obj.geometry),
                )
            )
            if max_findings and len(findings) >= max_findings:
                break
        return findings

    def _required_properties(self, rule: dict[str, Any], clause: dict[str, Any], params: dict[str, Any], objects: list[DesignObject]) -> list[RiskFinding]:
        object_spec: Any = {"type": params.get("object_type"), "filters": params.get("filters") or {}}
        props = [str(prop) for prop in params.get("properties") or []]
        max_findings = int(params.get("max_findings", 0) or 0)
        findings: list[RiskFinding] = []
        for obj in self._matching_objects(object_spec, objects):
            missing = [prop for prop in props if _is_blank(obj.properties.get(prop))]
            if missing:
                findings.append(
                    self._finding(
                        "属性资料不完整",
                        "数据适配审查",
                        clause,
                        ReviewEvidence(
                            calculation=f"{obj.id} 必填属性校验",
                            actual_value="缺失：" + ", ".join(missing),
                            threshold="必填",
                            object_ids=[obj.id],
                        ),
                        f"{obj.name} 缺少必填属性：{', '.join(missing)}。",
                        risk_geometry(obj.geometry),
                    )
                )
                if max_findings and len(findings) >= max_findings:
                    break
        return findings

    def _required_any_property(self, rule: dict[str, Any], clause: dict[str, Any], params: dict[str, Any], objects: list[DesignObject]) -> list[RiskFinding]:
        object_spec: Any = {"type": params.get("object_type"), "filters": params.get("filters") or {}}
        props = [str(prop) for prop in params.get("properties") or []]
        max_findings = int(params.get("max_findings", 0) or 0)
        findings: list[RiskFinding] = []
        for obj in self._matching_objects(object_spec, objects):
            if props and all(_is_blank(obj.properties.get(prop)) for prop in props):
                findings.append(
                    self._finding(
                        "属性资料不完整",
                        "数据适配审查",
                        clause,
                        ReviewEvidence(
                            calculation=f"{obj.id} 至少填写一个属性：{', '.join(props)}",
                            actual_value="全部缺失",
                            threshold="至少一项",
                            object_ids=[obj.id],
                        ),
                        f"{obj.name} 至少需要提供 {', '.join(props)} 中的一项。",
                        risk_geometry(obj.geometry),
                    )
                )
                if max_findings and len(findings) >= max_findings:
                    break
        return findings

    def _allowed_values(self, rule: dict[str, Any], clause: dict[str, Any], params: dict[str, Any], objects: list[DesignObject]) -> list[RiskFinding]:
        object_spec: Any = {"type": params.get("object_type"), "filters": params.get("filters") or {}}
        prop = str(params.get("property") or "")
        allowed = {str(item) for item in params.get("values") or []}
        if not prop or not allowed:
            return []
        max_findings = int(params.get("max_findings", 0) or 0)
        findings: list[RiskFinding] = []
        for obj in self._matching_objects(object_spec, objects):
            actual = obj.properties.get(prop)
            if _is_blank(actual) or str(actual) in allowed:
                continue
            findings.append(
                self._finding(
                    "枚举值不符合项目字典",
                    "数据标准化审查",
                    clause,
                    ReviewEvidence(
                        calculation=f"{obj.id}: {prop} 属于 {sorted(allowed)}",
                        actual_value=str(actual),
                        threshold="允许值",
                        object_ids=[obj.id],
                    ),
                    f"{obj.name} 的 {prop} 为 {actual}，不在项目允许值范围内。",
                    risk_geometry(obj.geometry),
                )
            )
            if max_findings and len(findings) >= max_findings:
                break
        return findings

    def _unique_resource(self, rule: dict[str, Any], clause: dict[str, Any], params: dict[str, Any], objects: list[DesignObject]) -> list[RiskFinding]:
        object_spec: Any = {"type": params.get("object_type"), "filters": params.get("filters") or {}}
        props = [str(prop) for prop in params.get("properties") or []]
        groups: dict[tuple[str, ...], list[DesignObject]] = defaultdict(list)
        for obj in self._matching_objects(object_spec, objects):
            key = tuple(str(obj.properties.get(prop, "")).strip() for prop in props)
            if all(key):
                groups[key].append(obj)
        findings: list[RiskFinding] = []
        for key, items in groups.items():
            if len(items) <= 1:
                continue
            findings.append(
                self._finding(
                    "资源重复占用",
                    "项目业务规则",
                    clause,
                    ReviewEvidence(
                        calculation=f"{params.get('object_type')} 资源键 {dict(zip(props, key))} 唯一性校验",
                        actual_value=len(items),
                        threshold=1,
                        object_ids=[item.id for item in items],
                    ),
                    f"{len(items)} 个对象重复使用资源 {dict(zip(props, key))}。",
                    risk_geometry(items[0].geometry),
                )
            )
        return findings

    def _max_ratio(self, rule: dict[str, Any], clause: dict[str, Any], params: dict[str, Any], objects: list[DesignObject]) -> list[RiskFinding]:
        object_spec: Any = {"type": params.get("object_type"), "filters": params.get("filters") or {}}
        length_prop = str(params.get("length_property") or "")
        direct_prop = str(params.get("direct_distance_property") or "")
        max_ratio = float(params.get("max_ratio", 1.0))
        findings: list[RiskFinding] = []
        for obj in self._matching_objects(object_spec, objects):
            try:
                ratio = _to_float(obj.properties.get(length_prop)) / max(_to_float(obj.properties.get(direct_prop)), 0.001)
            except (TypeError, ValueError):
                continue
            if ratio > max_ratio:
                findings.append(
                    self._finding(
                        "路径绕行率过高",
                        "工程合理性审查",
                        clause,
                        ReviewEvidence(
                            calculation=f"{obj.id}: {length_prop}/{direct_prop}",
                            actual_value=round(ratio, 3),
                            threshold=max_ratio,
                            object_ids=[obj.id],
                        ),
                        f"{obj.name} 绕行率 {ratio:.2f}，超过上限 {max_ratio:.2f}。",
                        risk_geometry(obj.geometry),
                    )
                )
        return findings

    def _capacity_check(self, rule: dict[str, Any], clause: dict[str, Any], params: dict[str, Any], objects: list[DesignObject]) -> list[RiskFinding]:
        object_spec: Any = {"type": params.get("object_type"), "filters": params.get("filters") or {}}
        capacity_prop = str(params.get("capacity_property") or "")
        demand_prop = str(params.get("demand_property") or "")
        findings: list[RiskFinding] = []
        for obj in self._matching_objects(object_spec, objects):
            try:
                capacity = _to_float(obj.properties.get(capacity_prop))
                demand = _to_float(obj.properties.get(demand_prop))
            except (TypeError, ValueError):
                continue
            if capacity < demand:
                findings.append(
                    self._finding(
                        "容量配置不足",
                        "项目业务规则",
                        clause,
                        ReviewEvidence(
                            calculation=f"{obj.id}: {capacity_prop} >= {demand_prop}",
                            actual_value=capacity,
                            threshold=demand,
                            object_ids=[obj.id],
                        ),
                        f"{obj.name} 配置容量 {capacity:g} 小于需求 {demand:g}。",
                        risk_geometry(obj.geometry),
                    )
                )
        return findings

    def _topology_connectivity(self, rule: dict[str, Any], clause: dict[str, Any], params: dict[str, Any], objects: list[DesignObject]) -> list[RiskFinding]:
        edge_type = params.get("edge_type")
        start_prop = params.get("start_property", "start_node")
        end_prop = params.get("end_property", "end_node")
        edges = [obj for obj in objects if obj.type == edge_type]
        graph: dict[str, set[str]] = defaultdict(set)
        bad_edges: list[DesignObject] = []
        for edge in edges:
            start = str(edge.properties.get(start_prop, "")).strip()
            end = str(edge.properties.get(end_prop, "")).strip()
            if not start or not end:
                bad_edges.append(edge)
                continue
            graph[start].add(end)
            graph[end].add(start)
        findings: list[RiskFinding] = []
        if bad_edges:
            findings.append(
                self._finding(
                    "拓扑端点缺失",
                    "GIS拓扑审查",
                    clause,
                    ReviewEvidence(
                        calculation=f"{edge_type} 起止节点属性完整性",
                        actual_value=len(bad_edges),
                        threshold=0,
                        object_ids=[edge.id for edge in bad_edges],
                    ),
                    f"{len(bad_edges)} 条链路缺少起点或终点，可能形成拓扑断点。",
                    risk_geometry(bad_edges[0].geometry),
                )
            )
        components = _component_count(graph)
        if components > 1:
            findings.append(
                self._finding(
                    "拓扑不连通",
                    "GIS拓扑审查",
                    clause,
                    ReviewEvidence(
                        calculation=f"{edge_type} 连通分量数量",
                        actual_value=components,
                        threshold=1,
                        object_ids=[edge.id for edge in edges],
                    ),
                    f"{edge_type} 网络存在 {components} 个连通分量，需要复核断点或孤岛路由。",
                    None,
                )
            )
        return findings

    def _required_geometry(self, rule: dict[str, Any], clause: dict[str, Any], params: dict[str, Any], objects: list[DesignObject]) -> list[RiskFinding]:
        object_spec: Any = {"type": params.get("object_type", "*"), "filters": params.get("filters") or {}}
        allowed_types = {str(item) for item in params.get("geometry_types") or []}
        findings: list[RiskFinding] = []
        for obj in self._matching_objects(object_spec, objects):
            if not obj.geometry:
                findings.append(
                    self._finding(
                        "空间几何缺失",
                        "通用GIS数据质量",
                        clause,
                        ReviewEvidence(
                            calculation=f"{obj.id} geometry 必填",
                            actual_value="缺失",
                            threshold="必须包含几何",
                            object_ids=[obj.id],
                        ),
                        f"{obj.name} 缺少空间几何，无法参与距离、相交、包含等空间审查。",
                        None,
                    )
                )
                continue
            actual_type = str(obj.geometry.get("type") or "")
            if allowed_types and actual_type not in allowed_types:
                findings.append(
                    self._finding(
                        "几何类型不符合图层语义",
                        "通用GIS数据质量",
                        clause,
                        ReviewEvidence(
                            calculation=f"{obj.id} geometry.type 属于 {sorted(allowed_types)}",
                            actual_value=actual_type,
                            threshold="允许几何类型",
                            object_ids=[obj.id],
                        ),
                        f"{obj.name} 的几何类型为 {actual_type}，不符合该对象类型要求。",
                        risk_geometry(obj.geometry),
                    )
                )
        return findings

    def _geometry_validity(self, rule: dict[str, Any], clause: dict[str, Any], params: dict[str, Any], objects: list[DesignObject]) -> list[RiskFinding]:
        object_spec: Any = {"type": params.get("object_type", "*"), "filters": params.get("filters") or {}}
        findings: list[RiskFinding] = []
        for obj in self._matching_objects(object_spec, objects):
            if not obj.geometry:
                continue
            geom = to_shape(obj.geometry)
            if geom is None or not getattr(geom, "is_valid", True):
                findings.append(
                    self._finding(
                        "几何对象无效",
                        "通用GIS数据质量",
                        clause,
                        ReviewEvidence(
                            calculation=f"{obj.id} Shapely 几何有效性校验",
                            actual_value="invalid",
                            threshold="valid",
                            object_ids=[obj.id],
                        ),
                        f"{obj.name} 的空间几何无效，可能导致空间关系计算不可靠。",
                        risk_geometry(obj.geometry),
                    )
                )
        return findings

    def _min_feature_count(self, rule: dict[str, Any], clause: dict[str, Any], params: dict[str, Any], objects: list[DesignObject]) -> list[RiskFinding]:
        object_spec: Any = {"type": params.get("object_type", "*"), "filters": params.get("filters") or {}}
        min_count = int(params.get("min_count", 1))
        matched = self._matching_objects(object_spec, objects)
        if len(matched) >= min_count:
            return []
        return [
            self._finding(
                "关键图层或对象缺失",
                "通用GIS数据质量",
                clause,
                ReviewEvidence(
                    calculation=f"{params.get('object_type', '*')} 要素数量 >= {min_count}",
                    actual_value=len(matched),
                    threshold=min_count,
                    object_ids=[],
                ),
                f"当前工程中 {params.get('object_type', '*')} 要素数量为 {len(matched)}，少于最低要求 {min_count}。",
                None,
            )
        ]

    def _must_be_within(self, rule: dict[str, Any], clause: dict[str, Any], params: dict[str, Any], objects: list[DesignObject]) -> list[RiskFinding]:
        inner_spec = params.get("inner_type") or params.get("object_type")
        outer_spec = params.get("outer_type") or params.get("container_type")
        if not inner_spec or not outer_spec:
            return []
        inner_objects = self._matching_objects(inner_spec, objects)
        outer_objects = self._matching_objects(outer_spec, objects)
        outer_shapes = [(obj, to_shape(obj.geometry)) for obj in outer_objects]
        outer_shapes = [(obj, geom) for obj, geom in outer_shapes if geom is not None]
        findings: list[RiskFinding] = []
        max_findings = int(params.get("max_findings", 100))
        for obj in inner_objects:
            geom = to_shape(obj.geometry)
            if geom is None or not outer_shapes:
                continue
            inside = any(_covered_by(geom, outer_geom) for _, outer_geom in outer_shapes)
            if inside:
                continue
            findings.append(
                self._finding(
                    "对象超出工程范围",
                    "GIS空间审查",
                    clause,
                    ReviewEvidence(
                        calculation=f"{obj.id} 必须位于 {outer_spec} 内",
                        actual_value="不在范围内",
                        threshold="within",
                        object_ids=[obj.id],
                    ),
                    f"{obj.name} 未落在指定工程范围或工作区范围内。",
                    risk_geometry(obj.geometry),
                )
            )
            if len(findings) >= max_findings:
                break
        return findings

    def _forbidden_intersection(self, rule: dict[str, Any], clause: dict[str, Any], params: dict[str, Any], objects: list[DesignObject]) -> list[RiskFinding]:
        types = params.get("object_types") or []
        if len(types) != 2:
            return []
        relation = str(params.get("relation") or "intersects")
        ignore_touches = bool(params.get("ignore_touches", True))
        max_findings = int(params.get("max_findings", 100))
        left = self._matching_objects(types[0], objects)
        right = self._matching_objects(types[1], objects)
        right_shapes = [(obj, to_shape(obj.geometry)) for obj in right]
        right_shapes = [(obj, geom) for obj, geom in right_shapes if geom is not None]
        findings: list[RiskFinding] = []
        for a in left:
            ga = to_shape(a.geometry)
            if ga is None:
                continue
            for b, gb in right_shapes:
                if a.id == b.id or not _bbox_intersects(ga.bounds, gb.bounds):
                    continue
                if not _relation_matched(ga, gb, relation, ignore_touches):
                    continue
                findings.append(
                    self._finding(
                        "空间关系冲突",
                        "GIS空间审查",
                        clause,
                        ReviewEvidence(
                            calculation=f"{a.id} 与 {b.id} 不允许 {relation}",
                            actual_value=relation,
                            threshold="禁止",
                            object_ids=[a.id, b.id],
                        ),
                        f"{a.name} 与 {b.name} 存在不允许的空间关系：{relation}。",
                        risk_geometry(a.geometry, b.geometry),
                    )
                )
                if len(findings) >= max_findings:
                    return findings
        return findings

    def _crossing_requires_properties(self, rule: dict[str, Any], clause: dict[str, Any], params: dict[str, Any], objects: list[DesignObject]) -> list[RiskFinding]:
        types = params.get("object_types") or []
        props = [str(prop) for prop in params.get("properties") or []]
        if len(types) != 2 or not props:
            return []
        max_findings = int(params.get("max_findings", 100))
        left = self._matching_objects(types[0], objects)
        right = self._matching_objects(types[1], objects)
        right_shapes = [(obj, to_shape(obj.geometry)) for obj in right]
        right_shapes = [(obj, geom) for obj, geom in right_shapes if geom is not None]
        findings: list[RiskFinding] = []
        for a in left:
            ga = to_shape(a.geometry)
            if ga is None:
                continue
            missing = [prop for prop in props if _is_blank(a.properties.get(prop))]
            if not missing:
                continue
            for b, gb in right_shapes:
                if a.id == b.id or not _bbox_intersects(ga.bounds, gb.bounds):
                    continue
                if not _relation_matched(ga, gb, "intersects", ignore_touches=True):
                    continue
                findings.append(
                    self._finding(
                        "交叉穿越资料缺失",
                        "项目业务规则",
                        clause,
                        ReviewEvidence(
                            calculation=f"{a.id} 与 {b.id} 交叉时需填写 {', '.join(props)}",
                            actual_value="缺失：" + ", ".join(missing),
                            threshold="交叉穿越资料",
                            object_ids=[a.id, b.id],
                        ),
                        f"{a.name} 与 {b.name} 发生交叉或重叠，但缺少穿越保护、审批或施工说明字段：{', '.join(missing)}。",
                        risk_geometry(a.geometry, b.geometry),
                    )
                )
                if len(findings) >= max_findings:
                    return findings
                break
        return findings

    def _matching_objects(self, spec: Any, objects: list[DesignObject]) -> list[DesignObject]:
        if isinstance(spec, str):
            object_type = spec
            filters: dict[str, Any] = {}
        elif isinstance(spec, dict):
            object_type = spec.get("type") or spec.get("object_type") or ""
            filters = spec.get("filters") or {}
        else:
            return []
        object_type = str(object_type or "").strip()
        match_all = object_type in {"", "*", "all"}
        return [obj for obj in objects if (match_all or obj.type == object_type) and _matches_filters(obj, filters)]

    def _finding(
        self,
        title: str,
        category: str,
        clause: dict[str, Any],
        evidence: ReviewEvidence,
        description: str,
        geometry: dict[str, Any] | None,
    ) -> RiskFinding:
        level = str(clause.get("risk_level") or "medium")
        priority = {"high": 1, "medium": 2, "low": 3}.get(level, 2)
        marker = "（规则待专家校准）" if clause.get("is_placeholder") else ""
        return RiskFinding(
            id=uuid.uuid4().hex[:12],
            title=title,
            category=category,
            level=level,
            description=description,
            impact=f"{marker}可能影响GIS成果质量、空间一致性、工程可实施性或标准符合性。",
            recommendation=clause.get("recommendation", "按规则依据复核并补充或修正设计成果。"),
            priority=priority,
            clause={
                "standard_name": clause.get("standard_name"),
                "version": clause.get("version"),
                "clause_id": clause.get("clause_id"),
                "summary": clause.get("summary"),
                "is_placeholder": clause.get("is_placeholder", False),
                "applicable_reason": clause.get("scenario") or "规则对象类型与统一工程对象模型匹配。",
            },
            evidence=evidence,
            geometry=geometry,
        )


def _component_count(graph: dict[str, set[str]]) -> int:
    if not graph:
        return 0
    seen = set()
    count = 0
    for start in graph:
        if start in seen:
            continue
        count += 1
        queue = deque([start])
        seen.add(start)
        while queue:
            node = queue.popleft()
            for nxt in graph[node]:
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
    return count


def _matches_filters(obj: DesignObject, filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        actual = obj.properties.get(key)
        if actual is None and hasattr(obj, key):
            actual = getattr(obj, key)
        if isinstance(expected, list):
            if str(actual) not in {str(item) for item in expected}:
                return False
        elif str(actual) != str(expected):
            return False
    return True


def _to_float(value: Any) -> float:
    if value is None:
        raise ValueError("missing numeric value")
    text = str(value).strip()
    if not text:
        raise ValueError("missing numeric value")
    text = text.translate(str.maketrans("０１２３４５６７８９．，", "0123456789.,"))
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    return float(text)


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "none", "null", "n/a"}


def _covered_by(inner: Any, outer: Any) -> bool:
    if hasattr(outer, "covers"):
        return bool(outer.covers(inner))
    return bool(inner.within(outer) or outer.contains(inner))


def _relation_matched(left: Any, right: Any, relation: str, ignore_touches: bool) -> bool:
    if ignore_touches and left.touches(right):
        return False
    if relation == "crosses":
        return bool(left.crosses(right))
    if relation == "overlaps":
        return bool(left.overlaps(right))
    if relation == "within":
        return bool(left.within(right))
    if relation == "contains":
        return bool(left.contains(right))
    return bool(left.intersects(right))


def _bbox_intersects(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> bool:
    return not (left[2] < right[0] or left[0] > right[2] or left[3] < right[1] or left[1] > right[3])
