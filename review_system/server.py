from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .local_llm_client import LocalOllamaClient
from .gis_tooling import enrich_risks_with_mcp_remediation
from .knowledge_graph import enrich_risks_with_knowledge_graph
from .reporting import risks_to_csv, risks_to_docx, risks_to_geojson, risks_to_html, risks_to_pdf, risks_to_xlsx
from .review_agent import LocalReviewAgent
from .rule_engine import RuleEngine
from .storage import ROOT, add_project_document, create_project, delete_project, delete_standard_doc, get_project, import_standard, list_projects, list_standard_docs, load_clauses, save_project


STATIC = ROOT / "static"


def standard_library_editable() -> bool:
    return os.getenv("ALLOW_STANDARD_LIBRARY_EDIT", "0").strip().lower() in {"1", "true", "yes", "on"}


class ReviewHandler(BaseHTTPRequestHandler):
    server_version = "ShenchaSystem/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self._send_file(STATIC / "index.html")
        if parsed.path.startswith("/static/"):
            relative = parsed.path.removeprefix("/static/")
            path = (STATIC / relative).resolve()
            if not path.is_relative_to(STATIC.resolve()):
                return self._json({"error": "not found"}, status=404)
            return self._send_file(path)
        if parsed.path == "/api/health":
            return self._json({"ok": True})
        if parsed.path == "/api/config":
            return self._json(
                {
                    "local_llm": LocalOllamaClient().status(),
                    "agent_framework": {
                        "framework": "langgraph",
                        "nodes": LocalReviewAgent.graph_nodes,
                    },
                    "standard_library": {
                        "source": "backend",
                        "editable": standard_library_editable(),
                        "directory": "data/standards",
                    },
                }
            )
        if parsed.path == "/api/standards":
            return self._json({"items": list_standard_docs()})
        if parsed.path == "/api/projects":
            return self._json({"items": list_projects()})
        if parsed.path.startswith("/api/projects/") and parsed.path.endswith("/export"):
            return self._export(parsed.path.split("/")[3], parse_qs(parsed.query).get("format", ["json"])[0])
        if parsed.path.startswith("/api/projects/"):
            project_id = parsed.path.split("/")[3]
            return self._json(get_project(project_id))
        return self._json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/standards/import" and not standard_library_editable():
                return self._json({"error": "standard library is backend-managed and read-only"}, status=403)
            payload = self._read_json()
            if parsed.path == "/api/projects":
                return self._json(create_project(payload.get("name", "")))
            if parsed.path == "/api/standards/import":
                return self._json(import_standard(payload))
            if parsed.path.startswith("/api/projects/") and parsed.path.endswith("/documents"):
                project_id = parsed.path.split("/")[3]
                return self._json(add_project_document(project_id, payload))
            if parsed.path.startswith("/api/projects/") and parsed.path.endswith("/review"):
                project_id = parsed.path.split("/")[3]
                project = get_project(project_id)
                if not project:
                    return self._json({"error": "project not found"}, status=404)
                if not project.get("objects"):
                    return self._json(
                        {
                            "error": "项目没有可审查的工程对象。请先上传工程资料并完成对象抽取后再执行审查。",
                            "code": "empty_project",
                        },
                        status=400,
                    )
                clauses = load_clauses()
                computed_risks, log = RuleEngine(clauses).review(project.get("objects", []))
                agent_review = run_local_review(project, clauses, computed_risks, log)
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
                project["risks"] = sorted(computed_risks, key=lambda item: item.get("priority", 9))
                project["execution_log"] = log
                project["agent_review"] = agent_review
                save_project(project)
                return self._json(
                    {
                        "risk_count": len(project["risks"]),
                        "summary": review_summary(project, log),
                        "agent_review": agent_review,
                        "computed_risk_count": len(computed_risks),
                        "risks": project["risks"],
                        "execution_log": log,
                    }
                )
        except ValueError as exc:
            return self._json({"error": str(exc)}, status=400)
        except Exception as exc:
            return self._json({"error": str(exc)}, status=500)
        return self._json({"error": "not found"}, status=404)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/standards/"):
                if not standard_library_editable():
                    return self._json({"error": "standard library is backend-managed and read-only"}, status=403)
                filename = unquote(parsed.path.removeprefix("/api/standards/"))
                return self._json(delete_standard_doc(filename))
            if parsed.path.startswith("/api/projects/"):
                project_id = unquote(parsed.path.split("/")[3])
                return self._json(delete_project(project_id))
        except FileNotFoundError as exc:
            return self._json({"error": str(exc)}, status=404)
        except Exception as exc:
            return self._json({"error": str(exc)}, status=500)
        return self._json({"error": "not found"}, status=404)

    def _export(self, project_id: str, fmt: str) -> None:
        project = get_project(project_id)
        if not project:
            return self._json({"error": "project not found"}, status=404)
        risks = project.get("risks", [])
        if fmt == "geojson":
            return self._download(json.dumps(risks_to_geojson(risks), ensure_ascii=False, indent=2).encode("utf-8"), "application/geo+json", "risk-markers.geojson")
        if fmt == "csv":
            return self._download(risks_to_csv(risks).encode("utf-8-sig"), "text/csv; charset=utf-8", "risk-list.csv")
        if fmt == "xlsx":
            return self._download(risks_to_xlsx(risks), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "risk-list.xlsx")
        if fmt == "docx":
            return self._download(risks_to_docx(project), "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "review-report.docx")
        if fmt == "pdf":
            return self._download(risks_to_pdf(project), "application/pdf", "review-report.pdf")
        if fmt == "html":
            return self._download(risks_to_html(project).encode("utf-8"), "text/html; charset=utf-8", "review-report.html")
        if fmt == "log":
            return self._download(json.dumps(project.get("execution_log", []), ensure_ascii=False, indent=2).encode("utf-8"), "application/json", "rule-execution-log.json")
        return self._json({"project": project, "risk_geojson": risks_to_geojson(risks)})

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw or "{}")

    def _json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _download(self, body: bytes, content_type: str, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            return self._json({"error": "not found"}, status=404)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run() -> None:
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "8010"))
    httpd = ThreadingHTTPServer((host, port), ReviewHandler)
    print(f"ShenchaSystem started: http://{host}:{port}")
    httpd.serve_forever()


def review_summary(project: dict, log: list[dict]) -> dict:
    objects = project.get("objects", [])
    object_types = sorted({obj.get("type", "unknown") for obj in objects})
    computable = [item for item in log if item.get("computable")]
    manual = [item for item in log if not item.get("computable")]
    agent = project.get("agent_review") or {}
    retrieval = agent.get("retrieval") or {}
    graph = agent.get("graph") or {}
    return {
        "object_count": len(objects),
        "object_types": object_types,
        "rule_count": len(log),
        "computable_rule_count": len(computable),
        "manual_rule_count": len(manual),
        "finding_count": len(project.get("risks", [])),
        "agent_status": agent.get("status", "unknown"),
        "agent_model": agent.get("model", ""),
        "retrieval_status": retrieval.get("status", "unknown"),
            "retrieval_model": retrieval.get("model", ""),
            "retrieved_clause_count": retrieval.get("selected_count", 0),
            "knowledge_graph_status": (agent.get("knowledge_graph") or {}).get("status", "unknown"),
            "knowledge_graph_risk_chain_count": (agent.get("knowledge_graph") or {}).get("risk_chain_count", 0),
            "agent_graph_framework": graph.get("framework", ""),
        }


def run_local_review(
    project: dict,
    clauses: list[dict],
    computed_risks: list[dict],
    log: list[dict],
    progress_callback=None,
) -> dict:
    try:
        return LocalReviewAgent(clauses, progress_callback=progress_callback).review(project, computed_risks, log)
    except Exception as exc:
        client = LocalOllamaClient()
        return {
            "enabled": client.enabled,
            "status": "error",
            "provider": "ollama",
            "model": client.llm_model,
            "summary": f"本地 Ollama 智能审查调用失败：{exc}",
            "overall_level": "unknown",
            "key_points": ["已回退显示本地规则引擎结果。"],
            "risks": [],
            "retrieval": {"enabled": False, "provider": "ollama", "model": client.embed_model, "status": "error", "selected_count": 0},
            "knowledge_graph": {"status": "error", "risk_chain_count": 0},
            "graph": {"framework": "langgraph", "nodes": LocalReviewAgent.graph_nodes, "status": "error"},
            "error": str(exc),
        }
