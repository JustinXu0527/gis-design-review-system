from __future__ import annotations

import json
import time
import uuid
from importlib import metadata
from typing import Any, Callable, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from .local_llm_client import LocalOllamaClient
from .semantic_retriever import StandardSemanticRetriever
from .gis_tooling import build_data_profile, execute_gis_tool_plan, fallback_tool_plan, normalize_tool_plan, validate_gis_evidence
from .knowledge_graph import retrieve_knowledge_graph_context


class ReviewGraphState(TypedDict, total=False):
    project: dict[str, Any] # 工程项目
    clauses: list[dict[str, Any]] # 导入的标准条款
    computed_risks: list[dict[str, Any]] # 本地规则引擎计算的风险列表，即规则引擎结果
    execution_log: list[dict[str, Any]] # 执行日志
    client_status: dict[str, Any] # 客户端状态
    data_profile: dict[str, Any] # GIS 数据概况
    retrieved_clauses: list[dict[str, Any]] # 检索到的标准条款
    retrieval: dict[str, Any] # 检索结果
    knowledge_graph: dict[str, Any] # 标准知识图谱上下文
    gis_tool_plan: list[dict[str, Any]] # LLM 生成并校验后的 GIS 工具计划
    gis_tool_planning: dict[str, Any] # 工具计划元数据
    gis_tool_results: list[dict[str, Any]] # GIS 工具执行结果
    gis_tool_runtime: dict[str, Any] # MCP / 本地工具运行状态
    evidence_validation: dict[str, Any] # 工具证据校验结果
    llm_review_error: dict[str, Any] # 本地模型调用失败信息，供回退节点使用
    agent_review: dict[str, Any] # 代理审查结果


class LocalReviewAgent:
    """LangGraph-based local review agent.

    The server still runs deterministic rules before this agent. This graph then
    retrieves the most relevant standard clauses with bge-m3 and asks the local
    Ollama LLM to generate the Chinese review conclusion.
    """

    graph_nodes = [
        "runtime_status",
        "data_profile",
        "semantic_retrieval",
        "knowledge_graph_context",
        "gis_tool_planning",
        "mcp_gis_tools",
        "evidence_validation",
        "llm_review",
        "fallback_review",
    ]

    def __init__(
        self,
        clauses: list[dict[str, Any]],
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.client = LocalOllamaClient()
        self.clauses = clauses
        self.progress_callback = progress_callback
        self.graph = self._build_graph()

    def review(self, project: dict[str, Any], computed_risks: list[dict[str, Any]], execution_log: list[dict[str, Any]]) -> dict[str, Any]:
        initial_state: ReviewGraphState = {
            "project": project,
            "clauses": self.clauses,
            "computed_risks": computed_risks,
            "execution_log": execution_log,
        }
        final_state = self.graph.invoke(initial_state)
        return final_state["agent_review"]

    def _build_graph(self):
        graph = StateGraph(ReviewGraphState)
        graph.add_node("runtime_status", self._tracked_node("runtime_status", self._runtime_status_node))
        graph.add_node("data_profile", self._tracked_node("data_profile", self._data_profile_node))
        graph.add_node("semantic_retrieval", self._tracked_node("semantic_retrieval", self._semantic_retrieval_node))
        graph.add_node("knowledge_graph_context", self._tracked_node("knowledge_graph_context", self._knowledge_graph_context_node))
        graph.add_node("gis_tool_planning", self._tracked_node("gis_tool_planning", self._gis_tool_planning_node))
        graph.add_node("mcp_gis_tools", self._tracked_node("mcp_gis_tools", self._mcp_gis_tools_node))
        graph.add_node("evidence_validation", self._tracked_node("evidence_validation", self._evidence_validation_node))
        graph.add_node("llm_review", self._tracked_node("llm_review", self._llm_review_node))
        graph.add_node("fallback_review", self._tracked_node("fallback_review", self._fallback_review_node))
        graph.add_edge(START, "runtime_status")
        graph.add_edge("runtime_status", "data_profile")
        graph.add_edge("data_profile", "semantic_retrieval")
        graph.add_edge("semantic_retrieval", "knowledge_graph_context")
        graph.add_edge("knowledge_graph_context", "gis_tool_planning")
        graph.add_edge("gis_tool_planning", "mcp_gis_tools")
        graph.add_edge("mcp_gis_tools", "evidence_validation")
        graph.add_conditional_edges(
            "evidence_validation",
            self._route_after_evidence_validation,
            {"llm_review": "llm_review", "fallback_review": "fallback_review"},
        )
        graph.add_conditional_edges(
            "llm_review",
            self._route_after_llm_review,
            {"complete": END, "fallback_review": "fallback_review"},
        )
        graph.add_edge("fallback_review", END)
        return graph.compile()

    def _tracked_node(self, name: str, node: Callable[[ReviewGraphState], dict[str, Any]]):
        def run(state: ReviewGraphState) -> dict[str, Any]:
            started = time.perf_counter()
            self._emit_progress({"event": "node_started", "node": name})
            try:
                output = node(state)
            except Exception as exc:
                self._emit_progress(
                    {
                        "event": "node_failed",
                        "node": name,
                        "duration_ms": round((time.perf_counter() - started) * 1000),
                        "error": str(exc),
                    }
                )
                raise
            duration_ms = round((time.perf_counter() - started) * 1000)
            node_error = output.get("llm_review_error") or {}
            self._emit_progress(
                {
                    "event": "node_failed" if node_error else "node_completed",
                    "node": name,
                    "duration_ms": duration_ms,
                    "summary": _node_output_summary(name, output),
                    "error": str(node_error.get("message") or "") if node_error else "",
                    "tool_calls": output.get("gis_tool_results", []) if name == "mcp_gis_tools" else [],
                    "metrics": _node_progress_metrics(name, output),
                }
            )
            return output

        return run

    def _emit_progress(self, event: dict[str, Any]) -> None:
        if not self.progress_callback:
            return
        try:
            self.progress_callback(event)
        except Exception:
            # Progress reporting must never change the review result.
            return

    def _runtime_status_node(self, state: ReviewGraphState) -> dict[str, Any]:
        return {"client_status": self.client.status()}

    def _data_profile_node(self, state: ReviewGraphState) -> dict[str, Any]:
        return {"data_profile": build_data_profile(state["project"])}

    def _semantic_retrieval_node(self, state: ReviewGraphState) -> dict[str, Any]:
        retrieved_clauses, retrieval = StandardSemanticRetriever(state["clauses"], self.client).retrieve(
            state["project"],
            state["computed_risks"],
            state["execution_log"],
        )
        return {"retrieved_clauses": retrieved_clauses, "retrieval": retrieval}

    def _knowledge_graph_context_node(self, state: ReviewGraphState) -> dict[str, Any]:
        context = retrieve_knowledge_graph_context(
            state["clauses"],
            state["project"],
            state["computed_risks"],
            state["execution_log"],
            state.get("retrieved_clauses", []),
        )
        return {"knowledge_graph": context}

    def _gis_tool_planning_node(self, state: ReviewGraphState) -> dict[str, Any]:
        fallback = fallback_tool_plan(state["project"], state["computed_risks"])
        status = state.get("client_status") or {}
        if not (self.client.enabled and status.get("available")):
            return {
                "gis_tool_plan": fallback,
                "gis_tool_planning": {"provider": "deterministic_fallback", "status": "model_unavailable", "plan_count": len(fallback)},
            }
        system_prompt = (
            "你是 GIS 审查工具规划器。只输出 JSON，不能生成审查结论。"
            "只能从 inspect_object_context、validate_geometry、summarize_rule_evidence 三个只读工具中选择。"
            "object_ids 必须来自提供的风险对象编号，最多 8 个工具调用，每个调用最多 16 个对象。"
        )
        user_prompt = json.dumps(
            {
                "output_schema": {"plans": [{"tool": "允许的工具名", "object_ids": ["对象ID"], "reason": "中文原因"}]},
                "data_profile": state.get("data_profile", {}),
                "computed_risks": state["computed_risks"][:40],
                "retrieved_clauses": _compact_clauses(state.get("retrieved_clauses", []))[:20],
                "knowledge_graph": _compact_knowledge_graph(state.get("knowledge_graph", {})),
                "fallback_plan": fallback,
            },
            ensure_ascii=False,
        )
        try:
            payload = self.client.chat_json(system_prompt, user_prompt, timeout=90, task="gis_tool_planning")
            plans = normalize_tool_plan(payload, state["project"], state["computed_risks"])
            return {"gis_tool_plan": plans, "gis_tool_planning": {"provider": "ollama", "status": "ok", "plan_count": len(plans)}}
        except Exception as exc:
            return {
                "gis_tool_plan": fallback,
                "gis_tool_planning": {"provider": "deterministic_fallback", "status": "error", "plan_count": len(fallback), "error": str(exc)},
            }

    def _mcp_gis_tools_node(self, state: ReviewGraphState) -> dict[str, Any]:
        results, runtime = execute_gis_tool_plan(
            state["project"],
            state["computed_risks"],
            state.get("gis_tool_plan", []),
            progress_callback=self._emit_progress,
        )
        return {"gis_tool_results": results, "gis_tool_runtime": runtime}

    def _evidence_validation_node(self, state: ReviewGraphState) -> dict[str, Any]:
        validation = validate_gis_evidence(state["project"], state.get("gis_tool_plan", []), state.get("gis_tool_results", []))
        return {"evidence_validation": validation}

    def _route_after_evidence_validation(self, state: ReviewGraphState) -> Literal["llm_review", "fallback_review"]:
        status = state.get("client_status") or {}
        if self.client.enabled and status.get("available"):
            return "llm_review"
        return "fallback_review"

    def _route_after_llm_review(self, state: ReviewGraphState) -> Literal["complete", "fallback_review"]:
        return "fallback_review" if state.get("llm_review_error") else "complete"

    def _fallback_review_node(self, state: ReviewGraphState) -> dict[str, Any]:
        status = state.get("client_status") or {}
        llm_error = state.get("llm_review_error") or {}
        error_message = str(llm_error.get("message") or status.get("error") or "")
        if llm_error:
            summary = "本地模型生成超时，已由规则结果回退节点返回确定性审查结果。"
            key_points = ["正式风险与计算证据保持完整。", "模型解释未生成，可在模型服务稳定后重新审查。"]
            review_status = "fallback"
        else:
            summary = "本地 Ollama 服务未就绪，已由规则结果回退节点返回确定性审查结果。"
            key_points = ["正式风险由确定性规则引擎产生。", "本次未调用本地模型生成补充解释。"]
            review_status = "disabled"
        return {
            "agent_review": {
                "enabled": self.client.enabled,
                "status": review_status,
                "provider": "ollama",
                "model": str(llm_error.get("model") or self.client.llm_model),
                "summary": summary,
                "overall_level": "unknown",
                "key_points": key_points,
                "risks": state["computed_risks"],
                "retrieval": state.get("retrieval", {}),
                "data_profile": state.get("data_profile", {}),
                "knowledge_graph": state.get("knowledge_graph", {}),
                "gis_tool_planning": state.get("gis_tool_planning", {}),
                "gis_tool_results": state.get("gis_tool_results", []),
                "gis_tool_runtime": state.get("gis_tool_runtime", {}),
                "evidence_validation": state.get("evidence_validation", {}),
                "graph": _graph_meta(),
                "error": error_message,
            }
        }

    def _llm_review_node(self, state: ReviewGraphState) -> dict[str, Any]:
        project = state["project"]
        computed_risks = state["computed_risks"]
        retrieval = state.get("retrieval", {})
        system_prompt = (
            "你是通信基建设计智能审查 Agent。你必须使用中文输出 JSON。"
            "你的任务是结合导入的行业标准条款、工程设计对象、本地规则引擎证据和执行日志，"
            "给出安全、冲突、合理性、资源、拓扑、属性完整性、人工复核等维度的审查结论。"
            "每个风险必须尽量关联标准名称、版本、条款编号、条款摘要、适用原因和证据。"
            "不得编造不存在的标准名称、条款编号或强制阈值；资料不足时输出资料缺失或人工复核建议。"
            "只输出 JSON。"
        )
        user_prompt = json.dumps(
            {
                "output_schema": {
                    "summary": "中文总体结论",
                    "overall_level": "high|medium|low|pass|unknown",
                    "key_points": ["中文要点"],
                    "risks": [
                        {
                            "title": "风险名称",
                            "category": "安全审查|资源冲突|拓扑连通|工程合理性|属性完整性|资料缺失|人工复核",
                            "level": "high|medium|low",
                            "description": "风险原因",
                            "impact": "影响分析",
                            "recommendation": "整改建议",
                            "priority": 1,
                            "object_ids": ["关联对象ID"],
                            "clause": {
                                "standard_name": "标准名称",
                                "version": "版本",
                                "clause_id": "条款编号",
                                "summary": "条款摘要",
                                "is_placeholder": False,
                                "applicable_reason": "适用原因",
                            },
                            "evidence": {
                                "calculation": "计算或推理证据",
                                "actual_value": "实际值",
                                "threshold": "阈值或要求",
                                "unit": "单位",
                            },
                        }
                    ],
                },
                "project": {
                    "id": project.get("id"),
                    "name": project.get("name"),
                    "documents": project.get("documents", [])[:20],
                    "objects": _compact_objects(project.get("objects", [])),
                },
                "standards": _compact_clauses(state.get("retrieved_clauses", [])),
                "semantic_retrieval": retrieval,
                "knowledge_graph": _compact_knowledge_graph(state.get("knowledge_graph", {})),
                "data_profile": state.get("data_profile", {}),
                "gis_tool_plan": state.get("gis_tool_plan", []),
                "gis_tool_results": state.get("gis_tool_results", []),
                "evidence_validation": state.get("evidence_validation", {}),
                "computed_risks": computed_risks[:50],
                "execution_log": state["execution_log"][:150],
                "instructions": [
                    "优先保留本地规则引擎已经发现的风险，并用中文解释。",
                    "可以基于标准条款和对象属性补充资料缺失、人工复核和合理性风险。",
                    "风险条目必须可追溯到导入标准；如只能依据占位标准，请标记 is_placeholder=true。",
                    "如果没有足够证据形成高风险，请输出中低等级资料缺失或人工复核风险。",
                    "semantic_retrieval 中的 top_clauses 是 bge-m3 召回证据，优先使用这些条款。",
                    "knowledge_graph 中的 risk_chains 是标准-条款-对象-属性-风险等级证据链，生成原因和整改建议时优先沿证据链解释。",
                    "gis_tool_results 是受控 GIS 工具返回的事实证据；只能引用其中存在的数据，不得编造空间计算结论。",
                ],
            },
            ensure_ascii=False,
        )
        try:
            data = _normalize_agent_payload(self.client.chat_json(system_prompt, user_prompt, timeout=180, task="review_agent"))
        except Exception as exc:
            return {
                "llm_review_error": {
                    "message": str(exc),
                    "model": self.client.last_model or self.client.llm_model,
                }
            }
        risks = [_normalize_risk(item, project) for item in _as_list(data.get("risks"))]
        return {
            "agent_review": {
                "enabled": True,
                "status": "ok",
                "provider": "ollama",
                "model": self.client.last_model,
                "summary": str(data.get("summary") or "本地 Ollama 已完成智能审查。"),
                "overall_level": str(data.get("overall_level") or "unknown"),
                "key_points": [str(item) for item in _as_list(data.get("key_points"))][:8],
                "risks": risks or computed_risks,
                "retrieval": retrieval,
                "data_profile": state.get("data_profile", {}),
                "knowledge_graph": state.get("knowledge_graph", {}),
                "gis_tool_planning": state.get("gis_tool_planning", {}),
                "gis_tool_results": state.get("gis_tool_results", []),
                "gis_tool_runtime": state.get("gis_tool_runtime", {}),
                "evidence_validation": state.get("evidence_validation", {}),
                "graph": _graph_meta(),
            }
        }


def _graph_meta() -> dict[str, Any]:
    try:
        version = metadata.version("langgraph")
    except metadata.PackageNotFoundError:
        version = "unknown"
    return {
        "framework": "langgraph",
        "version": version,
        "nodes": LocalReviewAgent.graph_nodes,
        "entrypoint": "runtime_status",
    }


def _normalize_agent_payload(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {
            "summary": "本地模型返回了风险列表，系统已自动归一化为审查结果。",
            "overall_level": "unknown",
            "key_points": ["模型输出结构不是标准对象，已执行兼容处理。"],
            "risks": data,
        }
    return {
        "summary": str(data or "本地模型返回结构为空，已回退为资料复核结论。"),
        "overall_level": "unknown",
        "key_points": ["模型输出结构不是标准 JSON 对象，已执行兼容处理。"],
        "risks": [],
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _compact_objects(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for obj in objects[:120]:
        props = obj.get("properties") or {}
        compact.append(
            {
                "id": obj.get("id"),
                "type": obj.get("type"),
                "name": obj.get("name"),
                "has_geometry": bool(obj.get("geometry")),
                "geometry_type": (obj.get("geometry") or {}).get("type"),
                "properties": {key: props.get(key) for key in list(props)[:24]},
                "source": obj.get("source"),
            }
        )
    return compact


def _compact_clauses(clauses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for clause in clauses[:100]:
        compact.append(
            {
                "standard_name": clause.get("standard_name"),
                "version": clause.get("version"),
                "clause_id": clause.get("clause_id"),
                "title": clause.get("title"),
                "summary": clause.get("summary"),
                "scenario": clause.get("scenario"),
                "risk_level": clause.get("risk_level"),
                "is_placeholder": clause.get("is_placeholder", False),
                "source_excerpt": clause.get("source_excerpt", ""),
                "semantic_score": clause.get("_semantic_score"),
                "retrieval_reason": clause.get("_retrieval_reason"),
                "rules": clause.get("rules", [])[:6],
            }
        )
    return compact


def _compact_knowledge_graph(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": context.get("status"),
        "graph_path": context.get("graph_path"),
        "node_count": context.get("node_count", 0),
        "edge_count": context.get("edge_count", 0),
        "selected_clause_count": context.get("selected_clause_count", 0),
        "risk_chain_count": context.get("risk_chain_count", 0),
        "node_type_counts": context.get("node_type_counts", {}),
        "applicable_clauses": (context.get("applicable_clauses") or [])[:20],
        "risk_chains": (context.get("risk_chains") or [])[:40],
    }


def _node_output_summary(name: str, output: dict[str, Any]) -> str:
    if name == "runtime_status":
        status = output.get("client_status") or {}
        return "本地模型服务可用" if status.get("available") else "本地模型不可用，将使用规则回退"
    if name == "data_profile":
        profile = output.get("data_profile") or {}
        return f"完成 {profile.get('object_count', 0)} 个对象的数据画像"
    if name == "semantic_retrieval":
        retrieval = output.get("retrieval") or {}
        return f"召回 {retrieval.get('selected_count', 0)} 条标准证据"
    if name == "knowledge_graph_context":
        graph = output.get("knowledge_graph") or {}
        return f"构建 {graph.get('risk_chain_count', 0)} 条风险证据链"
    if name == "gis_tool_planning":
        planning = output.get("gis_tool_planning") or {}
        return f"生成 {planning.get('plan_count', 0)} 项受控 GIS 工具计划"
    if name == "mcp_gis_tools":
        runtime = output.get("gis_tool_runtime") or {}
        results = output.get("gis_tool_results") or []
        return f"执行 {len(results)} 项 GIS 工具调用，运行状态 {runtime.get('status', 'unknown')}"
    if name == "evidence_validation":
        validation = output.get("evidence_validation") or {}
        return (
            f"校验 {validation.get('executed_tool_count', 0)} 项工具证据，"
            f"外部证据 {validation.get('external_evidence_count', 0)} 项"
        )
    if name == "llm_review":
        error = output.get("llm_review_error") or {}
        if error:
            return f"本地模型调用失败：{error.get('message', '未知错误')}"[:160]
        review = output.get("agent_review") or {}
        return str(review.get("summary") or "本地模型完成智能解释")[:160]
    if name == "fallback_review":
        return "模型不可用，已返回确定性规则审查结果"
    return "节点执行完成"


def _node_progress_metrics(name: str, output: dict[str, Any]) -> dict[str, Any]:
    if name == "data_profile":
        return {"objects_read": int((output.get("data_profile") or {}).get("object_count") or 0)}
    if name == "semantic_retrieval":
        return {"evidence_recalled": int((output.get("retrieval") or {}).get("selected_count") or 0)}
    if name == "knowledge_graph_context":
        return {"knowledge_chains": int((output.get("knowledge_graph") or {}).get("risk_chain_count") or 0)}
    if name == "mcp_gis_tools":
        results = output.get("gis_tool_results") or []
        mcp_calls = [item for item in results if item.get("provider") == "qgis_mcp"]
        return {
            "mcp_calls_completed": len(mcp_calls),
            "mcp_objects_verified": sum(
                1
                for item in mcp_calls
                if item.get("tool") == "inspect_project_object" and item.get("status") == "ok"
            ),
            "mcp_current_call": "QGIS MCP 调用完成",
        }
    return {}


def _normalize_risk(item: Any, project: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {"description": str(item), "title": "本地模型审查提示", "category": "智能审查"}
    level = str(item.get("level") or "medium")
    priority = int(item.get("priority") or {"high": 1, "medium": 2, "low": 3}.get(level, 2))
    clause = _as_dict(item.get("clause"))
    evidence_raw = item.get("evidence")
    evidence = _as_dict(evidence_raw)
    if evidence_raw and not evidence:
        evidence = {"calculation": str(evidence_raw)}
    objects = project.get("objects", [])
    object_ids = item.get("object_ids") or evidence.get("object_ids") or []
    object_ids = [str(value) for value in _as_list(object_ids)]
    if not object_ids:
        object_ids = _infer_object_ids(item, clause, evidence, objects)
    geometry = _geometry_for_objects(objects, object_ids)
    return {
        "id": str(item.get("id") or uuid.uuid4().hex[:12]),
        "source": "ollama-langgraph",
        "title": str(item.get("title") or "本地模型审查风险"),
        "category": str(item.get("category") or "智能审查"),
        "level": level if level in {"high", "medium", "low"} else "medium",
        "description": str(item.get("description") or ""),
        "impact": str(item.get("impact") or "可能影响工程安全、资源一致性或方案合理性。"),
        "recommendation": str(item.get("recommendation") or "结合标准条款和现场资料进一步复核并整改。"),
        "priority": priority,
        "clause": {
            "standard_name": str(clause.get("standard_name") or "导入标准库"),
            "version": str(clause.get("version") or ""),
            "clause_id": str(clause.get("clause_id") or ""),
            "summary": str(clause.get("summary") or ""),
            "is_placeholder": bool(clause.get("is_placeholder", False)),
            "applicable_reason": str(clause.get("applicable_reason") or "LangGraph Agent 根据召回标准与工程对象匹配。"),
        },
        "evidence": {
            "calculation": str(evidence.get("calculation") or "LangGraph Agent 结合标准条款、对象属性和规则执行结果推理。"),
            "actual_value": evidence.get("actual_value"),
            "threshold": evidence.get("threshold"),
            "unit": str(evidence.get("unit") or ""),
            "object_ids": object_ids,
        },
        "geometry": geometry,
}


def _infer_object_ids(item: dict[str, Any], clause: dict[str, Any], evidence: dict[str, Any], objects: list[dict[str, Any]]) -> list[str]:
    risk_text = " ".join(
        str(value or "")
        for value in [
            item.get("title"),
            item.get("category"),
            item.get("description"),
            item.get("recommendation"),
            evidence.get("calculation"),
            clause.get("standard_name"),
            clause.get("summary"),
        ]
    )
    shared_keywords = ["接地", "防雷", "光缆", "管道", "管孔", "机房", "光交", "端口", "容量", "纤芯", "道路", "楼宇", "电力", "防火", "ODF"]
    matched: list[str] = []
    for obj in objects:
        props = obj.get("properties") or {}
        object_text = " ".join(
            str(value or "")
            for value in [
                obj.get("name"),
                obj.get("type"),
                props.get("raw_name"),
                props.get("keyword"),
                props.get("location_or_range"),
                props.get("description"),
                props.get("source_location"),
                props.get("source_excerpt"),
                props.get("extracted_from_text"),
            ]
        )
        direct_tokens = [
            str(value)
            for value in [obj.get("name"), obj.get("type"), props.get("raw_name"), props.get("keyword")]
            if len(str(value or "").strip()) >= 2
        ]
        if any(token in risk_text for token in direct_tokens) or any(keyword in risk_text and keyword in object_text for keyword in shared_keywords):
            matched.append(str(obj.get("id")))
        if len(matched) >= 3:
            break
    return matched


def _geometry_for_objects(objects: list[dict[str, Any]], object_ids: list[Any]) -> dict[str, Any] | None:
    wanted = {str(item) for item in object_ids}
    if not wanted:
        return None
    points = []
    for obj in objects:
        if str(obj.get("id")) not in wanted:
            continue
        geometry = obj.get("geometry")
        if not geometry:
            continue
        if geometry.get("type") == "Point":
            points.append(geometry.get("coordinates"))
        elif geometry.get("type") == "LineString":
            coords = geometry.get("coordinates") or []
            if coords:
                points.append(coords[len(coords) // 2])
    if len(points) >= 2:
        return {"type": "LineString", "coordinates": points[:2]}
    if len(points) == 1:
        return {"type": "Point", "coordinates": points[0]}
    return None
