from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .extractors import decode_upload, extract_design_objects, extract_design_objects_from_path
from .standard_parser import StandardParser


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STANDARDS = DATA / "standards"
PROJECTS = DATA / "projects"
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def ensure_dirs() -> None:
    STANDARDS.mkdir(parents=True, exist_ok=True)
    PROJECTS.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_standard_docs() -> list[dict[str, Any]]:
    ensure_dirs()
    docs = []
    for path in sorted(STANDARDS.glob("*.json")):
        data = read_json(path, {})
        clauses = data.get("clauses", [])
        rules = [rule for clause in clauses for rule in clause.get("rules", [])]
        rule_types = [str(rule.get("type") or "manual_review") for rule in rules]
        risk_levels = [str(clause.get("risk_level") or "medium") for clause in clauses]
        computable_rules = [rule for rule in rules if rule.get("type") != "manual_review"]
        manual_rules = [rule for rule in rules if rule.get("type") == "manual_review"]
        docs.append(
            {
                "file": path.name,
                "source_file": data.get("source_file") or path.name,
                "imported_at": data.get("imported_at", ""),
                "clause_count": len(clauses),
                "placeholder_count": sum(1 for c in clauses if c.get("is_placeholder")),
                "standards": sorted({c.get("standard_name", "") for c in clauses}),
                "rule_count": len(rules),
                "computable_rule_count": len(computable_rules),
                "manual_rule_count": len(manual_rules),
                "rule_types": sorted(set(rule_types)),
                "risk_level_counts": {level: risk_levels.count(level) for level in sorted(set(risk_levels))},
                "sample_clauses": [
                    {
                        "clause_id": clause.get("clause_id"),
                        "title": clause.get("title"),
                        "risk_level": clause.get("risk_level"),
                        "rule_types": sorted({rule.get("type") for rule in clause.get("rules", []) if rule.get("type")}),
                    }
                    for clause in clauses[:3]
                ],
            }
        )
    return docs


def delete_standard_doc(filename: str) -> dict[str, Any]:
    ensure_dirs()
    if Path(filename).name != filename or not filename.endswith(".json"):
        raise ValueError("invalid standard filename")
    path = (STANDARDS / filename).resolve()
    if path.parent != STANDARDS.resolve() or not path.exists():
        raise FileNotFoundError(f"standard not found: {filename}")
    path.unlink()
    return {"deleted": True, "file": filename}


def load_clauses() -> list[dict[str, Any]]:
    clauses = []
    for path in sorted(STANDARDS.glob("*.json")):
        clauses.extend(read_json(path, {}).get("clauses", []))
    return clauses


def import_standard(payload: dict[str, Any]) -> dict[str, Any]:
    filename, raw = decode_upload(payload)
    parsed = StandardParser().parse_upload(filename, raw)
    target = STANDARDS / f"{Path(filename).stem}-{uuid.uuid4().hex[:8]}.json"
    parsed["imported_at"] = now_iso()
    write_json(target, parsed)
    return {"file": target.name, "clause_count": len(parsed.get("clauses", []))}


def normalize_project_name(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "")).strip()


def project_name_exists(name: str) -> bool:
    normalized = normalize_project_name(name).casefold()
    if not normalized:
        return False
    ensure_dirs()
    for path in sorted(PROJECTS.glob("*/project.json")):
        project = read_json(path, {})
        if normalize_project_name(project.get("name", "")).casefold() == normalized:
            return True
    return False


def create_project(name: str) -> dict[str, Any]:
    project_id = uuid.uuid4().hex[:12]
    clean_name = normalize_project_name(name)
    if project_name_exists(clean_name):
        raise ValueError(f"项目名称“{clean_name}”已存在，请换一个名称。")
    project = {
        "id": project_id,
        "name": clean_name or f"通信设计审查项目-{project_id}",
        "created_at": now_iso(),
        "documents": [],
        "objects": [],
        "risks": [],
        "execution_log": [],
        "agent_review": None,
        "qgis_preview": None,
    }
    write_json(PROJECTS / project_id / "project.json", project)
    return project


def get_project(project_id: str) -> dict[str, Any]:
    project = read_json(PROJECTS / project_id / "project.json", {})
    if project:
        project = normalize_project(project_id, project)
    return project


def delete_project(project_id: str) -> dict[str, Any]:
    ensure_dirs()
    if not SAFE_NAME.match(project_id):
        raise ValueError("invalid project id")
    path = (PROJECTS / project_id).resolve()
    if path.parent != PROJECTS.resolve() or not path.exists():
        raise FileNotFoundError(f"project not found: {project_id}")
    shutil.rmtree(path)
    try:
        from .qgis_rendering import qgis_project_host_root

        preview_dir = (qgis_project_host_root() / f"web_{project_id}").resolve()
        preview_root = qgis_project_host_root().resolve()
        if preview_dir.parent == preview_root and preview_dir.exists():
            shutil.rmtree(preview_dir)
    except Exception:
        pass
    return {"deleted": True, "id": project_id}


def save_project(project: dict[str, Any]) -> None:
    write_json(PROJECTS / project["id"] / "project.json", project)


def list_projects() -> list[dict[str, Any]]:
    projects = []
    for path in sorted(PROJECTS.glob("*/project.json")):
        project = read_json(path, {})
        if project:
            project_id = str(project.get("id") or path.parent.name)
            project = normalize_project(project_id, project)
        projects.append(
            {
                "id": project.get("id"),
                "name": project.get("name"),
                "created_at": project.get("created_at"),
                "document_count": len(project.get("documents", [])),
                "object_count": len(project.get("objects", [])),
                "risk_count": len(project.get("risks", [])),
            }
        )
    return projects


def add_project_document(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    project = get_project(project_id)
    if not project:
        raise KeyError(f"project not found: {project_id}")
    filename, raw = decode_upload(payload)
    digest = file_sha256(raw)
    for doc in project.get("documents", []):
        if doc.get("sha256") == digest:
            return {
                "filename": filename,
                "object_count": 0,
                "total_objects": len(project.get("objects", [])),
                "duplicate": True,
                "message": "该 GIS 成果已经在当前项目中读取过图层，已跳过重复读取。",
            }
    upload_dir = PROJECTS / project_id / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex[:8]}-{Path(filename).name}"
    stored_path = upload_dir / stored_name
    stored_path.write_bytes(raw)
    try:
        objects = extract_design_objects(filename, raw)
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
    return _commit_project_document(project, filename, stored_name, digest, len(raw), objects)


def add_project_document_from_path(project_id: str, filename: str, source_path: Path) -> dict[str, Any]:
    project = get_project(project_id)
    if not project:
        raise KeyError(f"project not found: {project_id}")
    clean_filename = Path(filename or source_path.name).name
    digest = file_sha256_path(source_path)
    for doc in project.get("documents", []):
        if doc.get("sha256") == digest:
            return {
                "filename": clean_filename,
                "object_count": 0,
                "total_objects": len(project.get("objects", [])),
                "duplicate": True,
                "message": "该 GIS 成果已经在当前项目中读取过图层，已跳过重复读取。",
            }

    upload_dir = PROJECTS / project_id / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex[:8]}-{clean_filename}"
    stored_path = upload_dir / stored_name
    shutil.copy2(source_path, stored_path)
    try:
        objects = extract_design_objects_from_path(clean_filename, stored_path)
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
    return _commit_project_document(project, clean_filename, stored_name, digest, stored_path.stat().st_size, objects)


def _commit_project_document(
    project: dict[str, Any],
    filename: str,
    stored_name: str,
    digest: str,
    size: int,
    objects: list[Any],
) -> dict[str, Any]:
    existing_ids = {str(obj.get("id")) for obj in project.get("objects", [])}
    new_objects = []
    for obj in objects:
        item = obj.to_dict()
        item["id"] = unique_object_id(str(item.get("id") or f"{Path(filename).stem}-{len(new_objects) + 1}"), existing_ids)
        existing_ids.add(item["id"])
        new_objects.append(item)
    project["documents"].append(
        {
            "filename": filename,
            "stored_name": stored_name,
            "uploaded_at": now_iso(),
            "sha256": digest,
            "size": size,
            "object_count": len(new_objects),
        }
    )
    project["objects"].extend(new_objects)
    project["risks"] = []
    project["execution_log"] = []
    project["agent_review"] = None
    try:
        from .qgis_rendering import ensure_project_qgis_preview

        ensure_project_qgis_preview(str(project["id"]), project)
    except Exception as exc:
        current_preview = project.get("qgis_preview") if isinstance(project.get("qgis_preview"), dict) else {}
        project["qgis_preview"] = {**current_preview, "error": str(exc)}
    save_project(project)
    return {"filename": filename, "object_count": len(new_objects), "total_objects": len(project["objects"]), "duplicate": False}


def file_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique_object_id(base_id: str, existing_ids: set[str]) -> str:
    if base_id not in existing_ids:
        return base_id
    index = 2
    while f"{base_id}-{index}" in existing_ids:
        index += 1
    return f"{base_id}-{index}"


def normalize_project(project_id: str, project: dict[str, Any]) -> dict[str, Any]:
    changed = False
    upload_dir = PROJECTS / project_id / "uploads"

    docs = []
    seen_hashes: set[str] = set()
    for doc in project.get("documents", []):
        if not isinstance(doc, dict):
            changed = True
            continue
        item = dict(doc)
        stored_name = item.get("stored_name")
        path = upload_dir / stored_name if stored_name else None
        if not item.get("sha256") and path and path.exists():
            raw = path.read_bytes()
            item["sha256"] = file_sha256(raw)
            item["size"] = len(raw)
            changed = True
        digest = item.get("sha256")
        if digest and digest in seen_hashes:
            changed = True
            continue
        if digest:
            seen_hashes.add(digest)
        docs.append(item)
    if len(docs) != len(project.get("documents", [])):
        changed = True
    project["documents"] = docs

    objects = []
    seen_objects: set[str] = set()
    for obj in project.get("objects", []):
        if not isinstance(obj, dict):
            changed = True
            continue
        key = str(obj.get("id") or json.dumps(obj, ensure_ascii=False, sort_keys=True))
        if key in seen_objects:
            changed = True
            continue
        seen_objects.add(key)
        objects.append(obj)
    if len(objects) != len(project.get("objects", [])):
        changed = True
        project["risks"] = []
        project["execution_log"] = []
        project["agent_review"] = None
    project["objects"] = objects

    if backfill_object_source_evidence(project, upload_dir):
        changed = True
    if migrate_legacy_model_risks(project):
        changed = True

    if changed:
        save_project(project)
    return project


def migrate_legacy_model_risks(project: dict[str, Any]) -> bool:
    agent = project.get("agent_review") or {}
    if agent.get("formal_risk_source") == "rule_engine":
        return False
    risks = project.get("risks", [])
    has_legacy_model_risks = any((risk.get("source") or "") == "ollama-langgraph" for risk in risks if isinstance(risk, dict))
    if not has_legacy_model_risks:
        return False
    from .rule_engine import RuleEngine

    computed_risks, log = RuleEngine(load_clauses()).review(project.get("objects", []))
    model_suggestions = agent.get("risks") or risks
    agent["model_risk_count"] = len(model_suggestions)
    agent["formal_risk_count"] = len(computed_risks)
    agent["formal_risk_source"] = "rule_engine"
    agent["risks_are_suggestions"] = True
    project["agent_review"] = agent
    project["risks"] = sorted(computed_risks, key=lambda item: item.get("priority", 9))
    project["execution_log"] = log
    return True


def backfill_object_source_evidence(project: dict[str, Any], upload_dir: Path) -> bool:
    wanted_fields = {"source_page", "source_location", "source_field", "source_excerpt", "extracted_from_text"}
    objects = project.get("objects", [])
    if not objects or all(wanted_fields.intersection((obj.get("properties") or {}).keys()) for obj in objects if isinstance(obj, dict)):
        return False

    changed = False
    extracted_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    extracted_by_id: dict[str, dict[str, Any]] = {}
    for doc in project.get("documents", []):
        stored_name = doc.get("stored_name")
        filename = doc.get("filename") or stored_name
        if not stored_name or not filename:
            continue
        path = upload_dir / stored_name
        if not path.exists():
            continue
        try:
            extracted = [obj.to_dict() for obj in extract_design_objects(filename, path.read_bytes())]
        except Exception:
            continue
        for item in extracted:
            props = item.get("properties") or {}
            if not wanted_fields.intersection(props.keys()):
                continue
            extracted_by_id[str(item.get("id"))] = item
            extracted_by_key[(str(item.get("source")), str(item.get("type")), str(item.get("name")))] = item

    for obj in objects:
        if not isinstance(obj, dict):
            continue
        props = obj.setdefault("properties", {})
        if wanted_fields.intersection(props.keys()):
            continue
        source = str(obj.get("source"))
        match = extracted_by_id.get(str(obj.get("id"))) or extracted_by_key.get((source, str(obj.get("type")), str(obj.get("name"))))
        if not match:
            continue
        match_props = match.get("properties") or {}
        for field in wanted_fields:
            value = match_props.get(field)
            if value and not props.get(field):
                props[field] = value
                changed = True
    return changed
