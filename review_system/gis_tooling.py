from __future__ import annotations

from collections import Counter
import time
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from .geometry import to_shape
from .qgis_mcp_client import QgisMcpClient


MAX_PLAN_ITEMS = 8
MAX_TOOL_OBJECTS = 16
MAX_MCP_OBJECTS = 4


class GisToolPlan(BaseModel):
    """Whitelisted, read-only GIS tool request produced by the planning node."""

    tool: Literal["inspect_object_context", "validate_geometry", "summarize_rule_evidence"]
    object_ids: list[str] = Field(default_factory=list, max_length=MAX_TOOL_OBJECTS)
    reason: str = "补充 GIS 审查证据"


def build_data_profile(project: dict[str, Any]) -> dict[str, Any]:
    """Collect factual GIS metadata without using an LLM."""

    objects = _objects(project)
    type_counts: Counter[str] = Counter()
    geometry_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    missing_geometry: list[str] = []
    invalid_geometry: list[str] = []
    property_keys: Counter[str] = Counter()

    for obj in objects:
        object_id = str(obj.get("id") or "")
        object_type = str(obj.get("type") or "unknown")
        type_counts[object_type] += 1
        geometry = obj.get("geometry")
        if not geometry:
            missing_geometry.append(object_id)
        else:
            geometry_counts[str(geometry.get("type") or "unknown")] += 1
            if to_shape(geometry) is None:
                invalid_geometry.append(object_id)
        props = obj.get("properties") or {}
        property_keys.update(str(key) for key in props)
        source = str(obj.get("source") or props.get("source_location") or "未知来源")
        source_counts[source.split(" / ")[0]] += 1

    return {
        "object_count": len(objects),
        "object_types": dict(type_counts.most_common(20)),
        "geometry_types": dict(geometry_counts),
        "source_layers": dict(source_counts.most_common(20)),
        "missing_geometry_count": len(missing_geometry),
        "invalid_geometry_count": len(invalid_geometry),
        "missing_geometry_samples": [item for item in missing_geometry if item][:12],
        "invalid_geometry_samples": [item for item in invalid_geometry if item][:12],
        "common_properties": [key for key, _ in property_keys.most_common(24)],
    }


def fallback_tool_plan(project: dict[str, Any], computed_risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Use deterministic planning whenever the model is unavailable or returns invalid JSON."""

    object_ids = _risk_object_ids(computed_risks)
    if not object_ids:
        object_ids = [str(obj.get("id")) for obj in _objects(project) if obj.get("geometry")][:MAX_TOOL_OBJECTS]
    selected = object_ids[:MAX_TOOL_OBJECTS]
    return [
        {"tool": "inspect_object_context", "object_ids": selected, "reason": "提取命中对象的图层、属性和空间上下文"},
        {"tool": "validate_geometry", "object_ids": selected, "reason": "核验命中对象的几何有效性和可定位性"},
        {"tool": "summarize_rule_evidence", "object_ids": selected, "reason": "将正式规则命中与工程对象绑定为可追溯证据"},
    ]


def normalize_tool_plan(payload: Any, project: dict[str, Any], computed_risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_items = payload.get("plans", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list):
        raw_items = []
    valid_ids = {str(obj.get("id")) for obj in _objects(project)}
    plans: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for item in raw_items[:MAX_PLAN_ITEMS]:
        try:
            plan = GisToolPlan.model_validate(item)
        except Exception:
            continue
        object_ids = [object_id for object_id in plan.object_ids if object_id in valid_ids][:MAX_TOOL_OBJECTS]
        key = (plan.tool, tuple(sorted(object_ids)))
        if key in seen:
            continue
        seen.add(key)
        plans.append({"tool": plan.tool, "object_ids": object_ids, "reason": plan.reason[:240]})
    return plans or fallback_tool_plan(project, computed_risks)


def execute_gis_tool_plan(
    project: dict[str, Any],
    computed_risks: list[dict[str, Any]],
    plans: list[dict[str, Any]],
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Execute QGIS MCP object checks and the existing deterministic local tools."""

    objects = _objects(project)
    object_by_id = {str(obj.get("id")): obj for obj in objects}
    results: list[dict[str, Any]] = []
    runtime = {
        "node": "mcp_gis_tools",
        "provider": "local_geopandas_shapely_adapter",
        "mcp_server_configured": False,
        "status": "fallback_local_tools",
        "supported_tools": ["inspect_project_object", "inspect_object_context", "validate_geometry", "summarize_rule_evidence"],
        "note": "当前未接入 QGIS MCP Server，执行的是只读本地 GIS 工具适配层。",
    }
    mcp_client = QgisMcpClient()
    if mcp_client.configured:
        runtime["mcp_server_configured"] = True
        capabilities: dict[str, Any] = {}
        try:
            capability_reason = "通过 QGIS MCP 验证当前项目及其可发布图层"
            _emit_tool_progress(progress_callback, "tool_started", "get_project_capabilities", "qgis_mcp", capability_reason)
            started = time.perf_counter()
            capabilities = mcp_client.call_tool("get_project_capabilities", {"project_id": str(project.get("id") or "")}, timeout=70.0)
            if not capabilities.get("valid"):
                raise RuntimeError(str(capabilities.get("error") or "QGIS MCP returned an invalid project response."))
            capability_record = {
                "tool": "get_project_capabilities",
                "reason": capability_reason,
                "status": "ok",
                "provider": "qgis_mcp",
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "object_ids": [],
                "result": capabilities,
            }
            results.append(capability_record)
            _emit_tool_progress(progress_callback, "tool_completed", tool_call=capability_record)

            published_layers = {
                str(layer.get("name") or "").strip().casefold()
                for layer in capabilities.get("layers", [])
                if isinstance(layer, dict) and str(layer.get("name") or "").strip()
            }
            object_checks = 0
            object_successes = 0
            for obj in _mcp_sample_objects(plans, object_by_id):
                payload = _mcp_object_payload(project, obj, computed_risks)
                if not payload or str(payload["layer_name"]).casefold() not in published_layers:
                    continue
                object_checks += 1
                object_id = str(obj.get("id") or "")
                reason = f"通过 QGIS MCP 查询图层并读取对象 {object_id} 的字段"
                _emit_tool_progress(
                    progress_callback,
                    "tool_started",
                    "inspect_project_object",
                    "qgis_mcp",
                    reason,
                    object_id,
                )
                started = time.perf_counter()
                try:
                    query_result = mcp_client.call_tool("inspect_project_object", payload, timeout=70.0)
                    status = "ok" if query_result.get("valid") else "error"
                    if status == "ok":
                        object_successes += 1
                    object_record = {
                        "tool": "inspect_project_object",
                        "reason": reason,
                        "status": status,
                        "provider": "qgis_mcp",
                        "duration_ms": round((time.perf_counter() - started) * 1000),
                        "object_ids": [object_id],
                        "result": query_result,
                        "error": "" if status == "ok" else str(query_result.get("error") or query_result.get("message") or "对象未定位"),
                    }
                except Exception as exc:
                    object_record = {
                        "tool": "inspect_project_object",
                        "reason": reason,
                        "status": "error",
                        "provider": "qgis_mcp",
                        "duration_ms": round((time.perf_counter() - started) * 1000),
                        "object_ids": [object_id],
                        "result": {
                            "object_id": object_id,
                            "layer_name": payload["layer_name"],
                            "source_feature_id": payload.get("source_feature_id", ""),
                        },
                        "error": str(exc),
                    }
                results.append(object_record)
                _emit_tool_progress(progress_callback, "tool_completed", tool_call=object_record)
            runtime.update(
                {
                    "provider": "qgis_mcp_streamable_http + local_geopandas_shapely_adapter",
                    "status": "connected",
                    "url": mcp_client.base_url,
                    "mcp_object_check_count": object_checks,
                    "mcp_object_success_count": object_successes,
                    "note": f"QGIS MCP 已完成工程验证，并对 {object_successes}/{object_checks} 个风险对象执行图层查询、字段读取和定位核验；批量规则计算仍由本地适配层完成。",
                }
            )
        except Exception as exc:
            capability_record = {
                "tool": "get_project_capabilities",
                "reason": "通过 QGIS MCP 验证当前项目及其可发布图层",
                "status": "error",
                "provider": "qgis_mcp",
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "object_ids": [],
                "error": str(exc),
                "result": capabilities,
            }
            results.append(capability_record)
            _emit_tool_progress(progress_callback, "tool_completed", tool_call=capability_record)
            runtime.update(
                {
                    "status": "fallback_local_tools",
                    "url": mcp_client.base_url,
                    "error": str(exc),
                    "note": "QGIS MCP 调用失败，已回退到只读本地 GIS 工具适配层。",
                }
            )

    for raw_plan in plans:
        try:
            plan = GisToolPlan.model_validate(raw_plan)
        except Exception:
            continue
        selected = [object_by_id[object_id] for object_id in plan.object_ids if object_id in object_by_id]
        _emit_tool_progress(progress_callback, "tool_started", plan.tool, "local_geopandas_shapely_adapter", plan.reason)
        started = time.perf_counter()
        if plan.tool == "inspect_object_context":
            result = _inspect_object_context(selected)
        elif plan.tool == "validate_geometry":
            result = _validate_geometry(selected)
        else:
            result = _summarize_rule_evidence(selected, computed_risks)
        record = {
            "tool": plan.tool,
            "reason": plan.reason,
            "status": "ok",
            "provider": "local_geopandas_shapely_adapter",
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "object_ids": [str(obj.get("id")) for obj in selected],
            "result": result,
        }
        results.append(record)
        _emit_tool_progress(progress_callback, "tool_completed", tool_call=record)
    return results, runtime


def validate_gis_evidence(
    project: dict[str, Any], plans: list[dict[str, Any]], results: list[dict[str, Any]]
) -> dict[str, Any]:
    """Validate tool output before it becomes evidence for the final LLM node."""

    valid_ids = {str(obj.get("id")) for obj in _objects(project)}
    referenced_ids = {str(object_id) for plan in plans for object_id in plan.get("object_ids", [])}
    unresolved_ids = sorted(referenced_ids - valid_ids)
    planned_tool_names = {str(plan.get("tool")) for plan in plans}
    planned_results = [result for result in results if str(result.get("tool")) in planned_tool_names]
    succeeded = [result for result in planned_results if result.get("status") == "ok"]
    external_results = [result for result in results if str(result.get("tool")) not in planned_tool_names]
    warnings: list[str] = []
    for result in succeeded:
        if not isinstance(result.get("result"), dict):
            warnings.append(f"{result.get('tool')} 返回结构不是对象")
    if unresolved_ids:
        warnings.append(f"计划中有 {len(unresolved_ids)} 个对象编号不属于当前项目")
    return {
        "valid": len(succeeded) == len(plans) and not unresolved_ids and not warnings,
        "planned_tool_count": len(plans),
        "executed_tool_count": len(succeeded),
        "external_evidence_count": len(external_results),
        "validated_object_count": len(referenced_ids & valid_ids),
        "unresolved_object_ids": unresolved_ids[:12],
        "warnings": warnings,
    }


def enrich_risks_with_mcp_remediation(
    project: dict[str, Any], risks: list[dict[str, Any]], tool_results: list[dict[str, Any]], runtime: dict[str, Any]
) -> list[dict[str, Any]]:
    """Attach traceable QGIS MCP remediation context to formal rule findings.

    This deliberately does not alter a rule's level, evidence, or recommendation.
    The added context is only emitted after QGIS MCP has verified that the active
    project is usable and supplies an actionable layer/object route in the UI.
    """

    if runtime.get("status") != "connected":
        return risks
    capabilities = next(
        (
            result.get("result")
            for result in tool_results
            if result.get("tool") == "get_project_capabilities" and result.get("status") == "ok"
        ),
        None,
    )
    if not isinstance(capabilities, dict) or not capabilities.get("valid"):
        return risks

    published_layers = {
        str(layer.get("name")).strip().casefold(): str(layer.get("name")).strip()
        for layer in capabilities.get("layers", [])
        if isinstance(layer, dict) and str(layer.get("name") or "").strip()
    }
    objects = {str(obj.get("id")): obj for obj in _objects(project)}
    object_checks = {
        str((result.get("result") or {}).get("object_id") or ""): result.get("result") or {}
        for result in tool_results
        if result.get("tool") == "inspect_project_object" and result.get("status") == "ok" and isinstance(result.get("result"), dict)
    }
    for risk in risks:
        object_ids = [str(item) for item in (risk.get("evidence") or {}).get("object_ids", []) if str(item)]
        object_ref, source, layer_name = _risk_object_reference(object_ids, objects, published_layers)
        object_check = next((object_checks[object_id] for object_id in object_ids if object_id in object_checks), {})
        layer_name = str(object_check.get("layer_name") or layer_name)
        layer_published = bool(layer_name)
        location_step = (
            f"在 QGIS 工程图层“{layer_name}”中按“{object_ref}”筛选并定位该要素。"
            if layer_published
            else "在 QGIS 工程中按风险对象编号筛选并定位该要素，核对其来源图层和属性。"
        )
        risk["mcp_remediation"] = {
            "verified": True,
            "provider": "QGIS MCP",
            "project_id": capabilities.get("resolved_project_id") or capabilities.get("project_id"),
            "project_available": True,
            "layer_count": int(capabilities.get("layer_count") or 0),
            "layer_name": layer_name,
            "layer_published": layer_published,
            "object_reference": object_ref,
            "source": source,
            "object_verified": bool(object_check.get("location_verified")),
            "source_feature_id": str(object_check.get("source_feature_id") or ""),
            "qgis_feature_id": str(object_check.get("qgis_feature_id") or ""),
            "query_method": str(object_check.get("query_method") or ""),
            "field_names": list(object_check.get("field_names") or []),
            "fields": dict(object_check.get("fields") or {}),
            "action": (
                f"{location_step} 根据上述规则建议完成字段或几何修改，保存编辑并重新发布/刷新图层后再次执行审查。"
            ),
        }
    return risks


def _risk_object_reference(
    object_ids: list[str], objects: dict[str, dict[str, Any]], published_layers: dict[str, str]
) -> tuple[str, str, str]:
    for object_id in object_ids:
        obj = objects.get(object_id)
        if not obj:
            continue
        props = obj.get("properties") or {}
        source = str(obj.get("source") or props.get("source_location") or "")
        candidates = [str(props.get("source_layer") or "").strip()]
        candidates.extend(part.strip() for part in source.split("/") if part.strip())
        candidates.extend([str(obj.get("type") or ""), str(obj.get("name") or "")])
        layer_name = ""
        for candidate in candidates:
            normalized = candidate.removesuffix(".gpkg").strip().casefold()
            if normalized in published_layers:
                layer_name = published_layers[normalized]
                break
        reference = str(obj.get("name") or object_id)
        if source:
            reference = f"{reference}（{source}）"
        return reference, source, layer_name
    return "关联对象", "", ""


def _emit_tool_progress(
    callback: Callable[[dict[str, Any]], None] | None,
    event: str,
    tool: str = "",
    provider: str = "",
    reason: str = "",
    object_id: str = "",
    tool_call: dict[str, Any] | None = None,
) -> None:
    if not callback:
        return
    payload: dict[str, Any] = {
        "event": event,
        "node": "mcp_gis_tools",
        "tool": tool,
        "provider": provider,
        "reason": reason,
        "object_id": object_id,
    }
    if tool_call is not None:
        payload["tool_call"] = tool_call
    try:
        callback(payload)
    except Exception:
        return


def _mcp_sample_objects(plans: list[dict[str, Any]], object_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for plan in plans:
        for raw_id in plan.get("object_ids", []):
            object_id = str(raw_id)
            obj = object_by_id.get(object_id)
            if not obj or object_id in seen or not obj.get("geometry"):
                continue
            props = obj.get("properties") or {}
            if not str(props.get("source_layer") or "").strip():
                continue
            seen.add(object_id)
            selected.append(obj)
            if len(selected) >= MAX_MCP_OBJECTS:
                return selected
    return selected


def _mcp_object_payload(
    project: dict[str, Any], obj: dict[str, Any], computed_risks: list[dict[str, Any]]
) -> dict[str, Any] | None:
    props = obj.get("properties") or {}
    coordinate = _representative_coordinate(obj.get("geometry"))
    layer_name = str(props.get("source_layer") or "").strip()
    if not coordinate or not layer_name:
        return None
    preview = project.get("qgis_preview") or {}
    return {
        "project_id": str(project.get("id") or ""),
        "object_id": str(obj.get("id") or ""),
        "layer_name": layer_name,
        "coordinate": coordinate,
        "source_feature_id": str(props.get("source_feature_id") or ""),
        "requested_fields": _requested_fields(obj, computed_risks),
        "crs": str(preview.get("crs") or "EPSG:25832"),
        "search_radius": 25.0,
    }


def _representative_coordinate(geometry: dict[str, Any] | None) -> list[float] | None:
    geom = to_shape(geometry)
    if geom is None or geom.is_empty:
        return None
    point = geom.representative_point()
    return [float(point.x), float(point.y)]


def _requested_fields(obj: dict[str, Any], computed_risks: list[dict[str, Any]]) -> list[str]:
    object_id = str(obj.get("id") or "")
    props = obj.get("properties") or {}
    evidence_text = " ".join(
        str((risk.get("evidence") or {}).get("calculation") or "")
        for risk in computed_risks
        if object_id in {str(value) for value in (risk.get("evidence") or {}).get("object_ids", [])}
    ).casefold()
    selected = [str(key) for key in props if str(key).casefold() in evidence_text]
    for key, value in props.items():
        key_text = str(key)
        if key_text.startswith("source_") or key_text.startswith("auxiliary_") or value is None or key_text in selected:
            continue
        selected.append(key_text)
        if len(selected) >= 8:
            break
    return selected[:8]


def _inspect_object_context(objects: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    for obj in objects[:MAX_TOOL_OBJECTS]:
        geometry = obj.get("geometry")
        geom = to_shape(geometry)
        props = obj.get("properties") or {}
        items.append(
            {
                "id": obj.get("id"),
                "name": obj.get("name"),
                "type": obj.get("type"),
                "source": obj.get("source") or props.get("source_location"),
                "geometry_type": geometry.get("type") if geometry else None,
                "bounds": [round(value, 3) for value in geom.bounds] if geom is not None else None,
                "properties": {key: props.get(key) for key in list(props)[:12]},
            }
        )
    return {"object_count": len(items), "items": items}


def _validate_geometry(objects: list[dict[str, Any]]) -> dict[str, Any]:
    missing: list[str] = []
    invalid: list[str] = []
    valid = 0
    for obj in objects:
        object_id = str(obj.get("id") or "")
        geometry = obj.get("geometry")
        if not geometry:
            missing.append(object_id)
            continue
        geom = to_shape(geometry)
        if geom is None or not geom.is_valid:
            invalid.append(object_id)
            continue
        valid += 1
    return {
        "checked_count": len(objects),
        "valid_geometry_count": valid,
        "missing_geometry_ids": missing[:12],
        "invalid_geometry_ids": invalid[:12],
    }


def _summarize_rule_evidence(objects: list[dict[str, Any]], computed_risks: list[dict[str, Any]]) -> dict[str, Any]:
    selected_ids = {str(obj.get("id")) for obj in objects}
    matches = []
    for risk in computed_risks:
        evidence = risk.get("evidence") or {}
        risk_ids = {str(item) for item in evidence.get("object_ids", [])}
        if selected_ids and not (selected_ids & risk_ids):
            continue
        matches.append(
            {
                "risk_id": risk.get("id"),
                "title": risk.get("title"),
                "level": risk.get("level"),
                "object_ids": sorted(selected_ids & risk_ids),
                "clause_id": (risk.get("clause") or {}).get("clause_id"),
                "calculation": evidence.get("calculation"),
            }
        )
        if len(matches) >= 30:
            break
    return {"matched_rule_count": len(matches), "matches": matches}


def _risk_object_ids(risks: list[dict[str, Any]]) -> list[str]:
    object_ids: list[str] = []
    for risk in risks:
        evidence = risk.get("evidence") or {}
        for object_id in evidence.get("object_ids", []):
            value = str(object_id)
            if value and value not in object_ids:
                object_ids.append(value)
            if len(object_ids) >= MAX_TOOL_OBJECTS:
                return object_ids
    return object_ids


def _objects(project: dict[str, Any]) -> list[dict[str, Any]]:
    objects = project.get("objects") or []
    return [obj for obj in objects if isinstance(obj, dict)]
