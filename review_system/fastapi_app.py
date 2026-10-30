from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from .local_llm_client import LocalOllamaClient
from .gis_tooling import enrich_risks_with_mcp_remediation
from .knowledge_graph import enrich_risks_with_knowledge_graph
from .qgis_rendering import qgis_preview_status, qgis_project_map_path, request_qgis_map
from .reporting import risks_to_csv, risks_to_docx, risks_to_geojson, risks_to_html, risks_to_pdf, risks_to_xlsx
from .review_agent import LocalReviewAgent
from .rule_engine import RuleEngine
from .server import review_summary, run_local_review, standard_library_editable
from .storage import (
    ROOT,
    add_project_document,
    add_project_document_from_path,
    create_project,
    delete_project,
    delete_standard_doc,
    get_project,
    import_standard,
    list_projects,
    list_standard_docs,
    load_clauses,
    save_project,
)

STATIC = ROOT / "static"

WORKFLOW_NODE_LABELS = {
    "runtime_status": "运行状态检查",
    "data_profile": "工程数据画像",
    "semantic_retrieval": "标准语义检索",
    "knowledge_graph_context": "知识图谱检索",
    "gis_tool_planning": "GIS 工具规划",
    "mcp_gis_tools": "MCP 外部调用",
    "evidence_validation": "工具证据校验",
    "llm_review": "本地模型解释",
    "fallback_review": "规则结果回退",
}
_review_jobs: dict[str, dict[str, Any]] = {}
_review_jobs_lock = threading.Lock()


class ReviewProgressReporter:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id

    def __call__(self, event: dict[str, Any]) -> None:
        node_name = str(event.get("node") or "")
        event_type = str(event.get("event") or "")
        with _review_jobs_lock:
            job = _review_jobs.get(self.project_id)
            if not job:
                return
            metrics = job.setdefault("metrics", {})
            if event_type == "rule_progress":
                metrics.update(
                    {
                        "objects_read": int(event.get("objects_read") or 0),
                        "rules_total": int(event.get("rules_total") or 0),
                        "rules_completed": int(event.get("rules_completed") or 0),
                        "risk_count": int(event.get("risk_count") or 0),
                        "current_rule": str(event.get("current_rule") or ""),
                    }
                )
                total = max(1, metrics["rules_total"])
                job["progress"] = max(2, min(18, round(metrics["rules_completed"] / total * 18)))
                job["message"] = (
                    f"规则审查 {metrics['rules_completed']}/{metrics['rules_total']}，"
                    f"已形成 {metrics['risk_count']} 条命中"
                )
                job["updated_at"] = _now_iso()
                return
            if event_type == "tool_started":
                object_id = str(event.get("object_id") or "")
                tool_label = _tool_label(str(event.get("tool") or ""))
                current_call = f"{tool_label}：{object_id}" if object_id else tool_label
                if event.get("provider") == "qgis_mcp":
                    metrics["mcp_current_call"] = current_call
                    metrics["mcp_call_status"] = "running"
                    job["message"] = f"QGIS MCP 正在调用：{current_call}"
                else:
                    job["message"] = f"本地 GIS 工具正在执行：{current_call}"
                job["updated_at"] = _now_iso()
                return
            if event_type == "tool_completed" and isinstance(event.get("tool_call"), dict):
                public_call = _public_tool_call(event["tool_call"])
                job["tool_calls"].append(public_call)
                metrics["mcp_calls_completed"] = sum(1 for item in job["tool_calls"] if item.get("provider") == "qgis_mcp")
                metrics["mcp_objects_verified"] = sum(
                    1
                    for item in job["tool_calls"]
                    if item.get("provider") == "qgis_mcp"
                    and item.get("tool") == "inspect_project_object"
                    and item.get("status") == "ok"
                )
                if public_call.get("provider") == "qgis_mcp":
                    metrics["mcp_call_status"] = "completed" if public_call.get("status") == "ok" else "failed"
                    metrics["mcp_current_call"] = public_call.get("summary") or _tool_label(public_call.get("tool", ""))
                job["updated_at"] = _now_iso()
                return
            node = next((item for item in job["nodes"] if item["id"] == node_name), None)
            if node:
                if event.get("event") == "node_started":
                    node.update({"status": "running", "started_at": _now_iso(), "summary": "正在执行"})
                    job["current_node"] = node_name
                    job["message"] = f"正在执行：{node['label']}"
                elif event.get("event") == "node_completed":
                    node.update(
                        {
                            "status": "completed",
                            "completed_at": _now_iso(),
                            "duration_ms": int(event.get("duration_ms") or 0),
                            "summary": str(event.get("summary") or "执行完成"),
                        }
                    )
                elif event.get("event") == "node_failed":
                    node.update(
                        {
                            "status": "failed",
                            "completed_at": _now_iso(),
                            "duration_ms": int(event.get("duration_ms") or 0),
                            "summary": str(event.get("error") or "执行失败"),
                        }
                    )
            if event.get("tool_calls"):
                job["tool_calls"] = [_public_tool_call(item) for item in event["tool_calls"]]
            if isinstance(event.get("metrics"), dict):
                metrics.update(event["metrics"])
            completed = sum(1 for item in job["nodes"] if item["status"] == "completed")
            job["progress"] = max(int(job.get("progress") or 0), min(94, round(completed / 8 * 100)))
            job["updated_at"] = _now_iso()

    def workflow_trace(self) -> list[dict[str, Any]]:
        with _review_jobs_lock:
            job = _review_jobs.get(self.project_id) or {}
            nodes = copy.deepcopy(job.get("nodes") or [])
        for node in nodes:
            if node.get("status") == "pending":
                node.update({"status": "skipped", "summary": "本次工作流未经过该分支"})
        return nodes

    def tool_calls(self) -> list[dict[str, Any]]:
        with _review_jobs_lock:
            job = _review_jobs.get(self.project_id) or {}
            return copy.deepcopy(job.get("tool_calls") or [])

app = FastAPI(
    title="通信基建 GIS 设计成果智能审查系统",
    version="0.2.0",
    description="GeoPandas/Shapely + Pydantic + LangGraph/Ollama 的子课题三智能审查接口。",
)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/config")
def config() -> dict[str, Any]:
    return {
        "local_llm": LocalOllamaClient().status(),
        "agent_framework": {
            "framework": "langgraph",
            "nodes": LocalReviewAgent.graph_nodes,
        },
        "geometry_engine": {
            "gis_reader": "geopandas",
            "spatial_engine": "shapely",
            "direct_design_inputs": [".gpkg", ".shp", ".geojson", ".zip", ".rar"],
        },
        "api_framework": "fastapi",
        "qgis_preview": qgis_preview_status(),
        "standard_library": {
            "source": "backend",
            "editable": standard_library_editable(),
            "directory": "data/standards",
        },
    }


@app.get("/api/qgis/status")
def qgis_status(project_id: str | None = Query(None)) -> dict[str, Any]:
    return qgis_preview_status(project_id)


@app.get("/api/qgis/wms")
def qgis_wms(request: Request, project_id: str | None = Query(None)) -> Response:
    try:
        body, content_type = request_qgis_map(
            request.query_params.multi_items(),
            map_path=qgis_project_map_path(project_id),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(
        content=body,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=60, stale-while-revalidate=30"},
    )


@app.get("/api/standards")
def standards() -> dict[str, Any]:
    return {"items": list_standard_docs()}


@app.post("/api/standards/import")
def standards_import(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    if not standard_library_editable():
        raise HTTPException(status_code=403, detail="standard library is backend-managed and read-only")
    return _guard(lambda: import_standard(payload))


@app.delete("/api/standards/{filename}")
def standards_delete(filename: str) -> dict[str, Any]:
    if not standard_library_editable():
        raise HTTPException(status_code=403, detail="standard library is backend-managed and read-only")
    return _guard(lambda: delete_standard_doc(filename))


@app.get("/api/projects")
def projects() -> dict[str, Any]:
    return {"items": list_projects()}


@app.post("/api/projects")
def projects_create(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    return _guard(lambda: create_project(payload.get("name", "")))


@app.get("/api/projects/{project_id}/export")
def projects_export(project_id: str, format: str = Query("json")) -> Response:
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    return _export_response(project, format)


@app.get("/api/projects/{project_id}")
def projects_get(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@app.delete("/api/projects/{project_id}")
def projects_delete(project_id: str) -> dict[str, Any]:
    return _guard(lambda: delete_project(project_id))


@app.post("/api/projects/{project_id}/documents")
async def projects_documents(project_id: str, request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "").lower()
    if "multipart/form-data" not in content_type:
        try:
            payload = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="上传请求不是有效的 JSON 或 multipart 表单。") from exc
        return await run_in_threadpool(lambda: _guard(lambda: add_project_document(project_id, payload)))

    form = await request.form()
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise HTTPException(status_code=400, detail="上传请求中缺少 GIS 文件。")

    suffix = Path(upload.filename or "").suffix.lower()
    allowed = {".gpkg", ".geojson", ".shp", ".qgs", ".qgz", ".qml", ".sld", ".zip", ".rar"}
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"不支持的 GIS 文件格式：{suffix or '无扩展名'}。")

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="gis-upload-", suffix=suffix, delete=False) as target:
            temp_path = Path(target.name)
            total = 0
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > 2 * 1024 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="上传文件超过 2 GB 限制。")
                target.write(chunk)
        if not total:
            raise HTTPException(status_code=400, detail="上传文件为空。")
        return await run_in_threadpool(
            lambda: _guard(lambda: add_project_document_from_path(project_id, upload.filename or temp_path.name, temp_path))
        )
    finally:
        await upload.close()
        if temp_path:
            temp_path.unlink(missing_ok=True)


@app.post("/api/projects/{project_id}/review")
def projects_review(project_id: str) -> dict[str, Any]:
    _reviewable_project(project_id)
    return _run_review_pipeline(project_id)


@app.post("/api/projects/{project_id}/review/start")
def projects_review_start(project_id: str) -> dict[str, Any]:
    _reviewable_project(project_id)
    with _review_jobs_lock:
        active = _review_jobs.get(project_id)
        if active and active.get("status") in {"queued", "running"}:
            return copy.deepcopy(active)
        _review_jobs[project_id] = _new_review_job(project_id)
        snapshot = copy.deepcopy(_review_jobs[project_id])
    threading.Thread(target=_run_review_job, args=(project_id,), daemon=True, name=f"review-{project_id[:8]}").start()
    return snapshot


@app.get("/api/projects/{project_id}/review/status")
def projects_review_status(project_id: str) -> dict[str, Any]:
    if not get_project(project_id):
        raise HTTPException(status_code=404, detail="project not found")
    with _review_jobs_lock:
        job = _review_jobs.get(project_id)
        if job:
            return copy.deepcopy(job)
    return {
        "project_id": project_id,
        "status": "idle",
        "progress": 0,
        "current_node": "",
        "message": "尚未开始新的审查任务",
        "nodes": _workflow_nodes(),
        "tool_calls": [],
    }


def _reviewable_project(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    if not project.get("objects"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "项目没有可审查的 GIS 工程对象。请先上传 .gpkg/.shp/.geojson 设计成果并完成图层读取。",
                "code": "empty_project",
            },
        )
    return project


def _run_review_pipeline(project_id: str, reporter: ReviewProgressReporter | None = None) -> dict[str, Any]:
    project = _reviewable_project(project_id)
    clauses = load_clauses()
    computed_risks, log = RuleEngine(clauses).review(project.get("objects", []), progress_callback=reporter)
    agent_review = run_local_review(project, clauses, computed_risks, log, progress_callback=reporter)
    computed_risks = enrich_risks_with_knowledge_graph(computed_risks, agent_review.get("knowledge_graph", {}))
    computed_risks = enrich_risks_with_mcp_remediation(
        project,
        computed_risks,
        agent_review.get("gis_tool_results", []),
        agent_review.get("gis_tool_runtime", {}),
    )
    model_suggestions = agent_review.get("risks") or []
    agent_review["model_risk_count"] = len(model_suggestions)
    agent_review["formal_risk_count"] = len(computed_risks)
    agent_review["formal_risk_source"] = "rule_engine"
    agent_review["risks_are_suggestions"] = True
    if reporter:
        agent_review["workflow_trace"] = reporter.workflow_trace()
        agent_review["mcp_call_log"] = reporter.tool_calls()
    project["risks"] = sorted(computed_risks, key=lambda item: item.get("priority", 9))
    project["execution_log"] = log
    project["agent_review"] = agent_review
    save_project(project)
    return {
        "risk_count": len(project["risks"]),
        "summary": review_summary(project, log),
        "agent_review": agent_review,
        "computed_risk_count": len(computed_risks),
        "risks": project["risks"],
        "execution_log": log,
    }


def _run_review_job(project_id: str) -> None:
    reporter = ReviewProgressReporter(project_id)
    with _review_jobs_lock:
        job = _review_jobs[project_id]
        job.update(
            {
                "status": "running",
                "started_at": _now_iso(),
                "updated_at": _now_iso(),
                "message": "正在执行确定性规则审查",
                "progress": 2,
            }
        )
    try:
        result = _run_review_pipeline(project_id, reporter)
    except Exception as exc:
        with _review_jobs_lock:
            job = _review_jobs.get(project_id)
            if job:
                job.update(
                    {
                        "status": "error",
                        "message": "审查任务执行失败",
                        "error": str(exc),
                        "completed_at": _now_iso(),
                        "updated_at": _now_iso(),
                    }
                )
        return
    with _review_jobs_lock:
        job = _review_jobs.get(project_id)
        if not job:
            return
        for node in job["nodes"]:
            if node["status"] == "pending":
                node.update({"status": "skipped", "summary": "本次工作流未经过该分支"})
        job.update(
            {
                "status": "completed",
                "progress": 100,
                "current_node": "",
                "message": f"审查完成，形成 {result.get('risk_count', 0)} 条正式风险",
                "completed_at": _now_iso(),
                "updated_at": _now_iso(),
                "result": {"risk_count": result.get("risk_count", 0)},
            }
        )


def _new_review_job(project_id: str) -> dict[str, Any]:
    now = _now_iso()
    return {
        "project_id": project_id,
        "status": "queued",
        "progress": 0,
        "current_node": "",
        "message": "审查任务已进入队列",
        "created_at": now,
        "updated_at": now,
        "nodes": _workflow_nodes(),
        "tool_calls": [],
        "metrics": {
            "objects_read": 0,
            "rules_total": 0,
            "rules_completed": 0,
            "risk_count": 0,
            "evidence_recalled": 0,
            "knowledge_chains": 0,
            "mcp_calls_completed": 0,
            "mcp_objects_verified": 0,
            "mcp_current_call": "等待调用",
            "mcp_call_status": "pending",
        },
        "error": "",
    }


def _workflow_nodes() -> list[dict[str, Any]]:
    return [
        {
            "id": node_id,
            "label": WORKFLOW_NODE_LABELS[node_id],
            "status": "pending",
            "duration_ms": 0,
            "summary": "等待执行",
        }
        for node_id in LocalReviewAgent.graph_nodes
    ]


def _public_tool_call(item: dict[str, Any]) -> dict[str, Any]:
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    result_summary = ""
    if item.get("tool") == "get_project_capabilities":
        result_summary = "QGIS 工程可用" if result.get("valid") else str(item.get("error") or "工程验证未通过")
    elif item.get("tool") == "inspect_project_object":
        result_summary = (
            f"对象 {result.get('object_id') or (item.get('object_ids') or [''])[0]}："
            f"图层 {result.get('layer_name') or '-'}，读取 {len(result.get('field_names') or [])} 个字段，"
            f"定位{'通过' if result.get('location_verified') else '未通过'}"
        )
    elif item.get("tool") == "inspect_object_context":
        result_summary = f"读取 {result.get('object_count', 0)} 个对象的图层与属性上下文"
    elif item.get("tool") == "validate_geometry":
        result_summary = (
            f"核验 {result.get('checked_count', 0)} 个对象，"
            f"有效几何 {result.get('valid_geometry_count', 0)} 个"
        )
    elif item.get("tool") == "summarize_rule_evidence":
        result_summary = f"绑定 {result.get('matched_rule_count', 0)} 条规则证据"
    return {
        "tool": str(item.get("tool") or "unknown"),
        "provider": str(item.get("provider") or "local_adapter"),
        "reason": str(item.get("reason") or ""),
        "status": str(item.get("status") or "unknown"),
        "duration_ms": int(item.get("duration_ms") or 0),
        "object_count": len(item.get("object_ids") or []),
        "object_ids": [str(value) for value in item.get("object_ids") or []],
        "layer_name": str(result.get("layer_name") or ""),
        "source_feature_id": str(result.get("source_feature_id") or ""),
        "qgis_feature_id": str(result.get("qgis_feature_id") or ""),
        "field_names": [str(value) for value in result.get("field_names") or []],
        "fields": result.get("fields") if isinstance(result.get("fields"), dict) else {},
        "location_verified": bool(result.get("location_verified")),
        "query_method": str(result.get("query_method") or ""),
        "summary": result_summary or str(item.get("error") or "工具调用完成"),
    }


def _tool_label(tool: str) -> str:
    return {
        "get_project_capabilities": "工程能力验证",
        "inspect_project_object": "对象图层与字段核验",
        "inspect_object_context": "对象上下文读取",
        "validate_geometry": "几何有效性核验",
        "summarize_rule_evidence": "规则证据绑定",
    }.get(tool, tool or "GIS 工具")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _guard(fn: Any) -> Any:
    try:
        return fn()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _export_response(project: dict[str, Any], fmt: str) -> Response:
    risks = project.get("risks", [])
    if fmt == "geojson":
        return _download(json.dumps(risks_to_geojson(risks), ensure_ascii=False, indent=2).encode("utf-8"), "application/geo+json", "risk-markers.geojson")
    if fmt == "csv":
        return _download(risks_to_csv(risks).encode("utf-8-sig"), "text/csv; charset=utf-8", "risk-list.csv")
    if fmt == "xlsx":
        return _download(risks_to_xlsx(risks), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "risk-list.xlsx")
    if fmt == "docx":
        return _download(risks_to_docx(project), "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "review-report.docx")
    if fmt == "pdf":
        return _download(risks_to_pdf(project), "application/pdf", "review-report.pdf")
    if fmt == "html":
        return _download(risks_to_html(project).encode("utf-8"), "text/html; charset=utf-8", "review-report.html")
    if fmt == "log":
        return _download(json.dumps(project.get("execution_log", []), ensure_ascii=False, indent=2).encode("utf-8"), "application/json", "rule-execution-log.json")
    body = json.dumps({"project": project, "risk_geojson": risks_to_geojson(risks)}, ensure_ascii=False, indent=2).encode("utf-8")
    return Response(content=body, media_type="application/json; charset=utf-8")


def _download(body: bytes, content_type: str, filename: str) -> Response:
    return Response(
        content=body,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def run() -> None:
    import uvicorn

    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "8010"))
    print(f"ShenchaSystem FastAPI started: http://{host}:{port}")
    uvicorn.run("review_system.fastapi_app:app", host=host, port=port, reload=False)
