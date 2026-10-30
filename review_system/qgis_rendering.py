from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree

from .archive_utils import ARCHIVE_SUFFIXES, safe_extract_archive

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT_DIR = ROOT / "test" / "PushPK_Dreieich Mitte_Handwerk"
DEFAULT_PROJECT_FILE = DEFAULT_PROJECT_DIR / "PushPK_Dreieich Mitte_Handwerk.qgz"
QGIS_PROJECT_SUFFIXES = {".qgs", ".qgz"}
GIS_DATA_SUFFIXES = {".gpkg", ".shp", ".geojson", ".json"}
QGIS_STYLE_SUFFIXES = {".qml", ".sld"}
QGIS_PREVIEW_SUFFIXES = QGIS_PROJECT_SUFFIXES | GIS_DATA_SUFFIXES | QGIS_STYLE_SUFFIXES | ARCHIVE_SUFFIXES
_WMS_CACHE: OrderedDict[str, tuple[float, bytes, str]] = OrderedDict()
_WMS_CACHE_LOCK = threading.Lock()


def qgis_preview_status(project_id: str | None = None) -> dict[str, Any]:
    """Return QGIS Server rendering status for either a web project or fallback project."""

    preview = _project_preview(project_id)
    host_project = Path(preview["host_project_file"]) if preview.get("host_project_file") else qgis_project_file()
    container_project = preview.get("container_project_file") or qgis_container_project_file(host_project)
    server_url = qgis_server_url()
    metadata = read_qgis_project_metadata(host_project)
    status: dict[str, Any] = {
        "mode": "qgis_server_wms",
        "available": False,
        "project_id": project_id or "",
        "project_exists": host_project.exists(),
        "project_file": str(host_project),
        "container_project_file": container_project,
        "server_url_configured": bool(server_url),
        "wms_proxy_url": f"/api/qgis/wms?project_id={urllib.parse.quote(project_id)}" if project_id else "/api/qgis/wms",
        "layers": metadata.get("layers", []),
        "wms_layers": metadata.get("wms_layers", ""),
        "render_wms_layers": metadata.get("render_wms_layers", ""),
        "excluded_wms_layers": metadata.get("excluded_wms_layers", []),
        "extent": None,
        "crs": metadata.get("crs") or os.getenv("QGIS_PREVIEW_CRS", "EPSG:25832"),
        "title": metadata.get("title") or "QGIS 项目预览",
        "generated": bool(preview.get("generated")),
        "error": "",
    }
    if preview.get("error"):
        status["error"] = str(preview["error"])
        return status
    if not host_project.exists():
        status["error"] = "QGIS project file not found."
        return status
    if not server_url:
        status["error"] = "QGIS_SERVER_URL is not configured."
        return status

    try:
        body, content_type = request_qgis_server(
            {
                "SERVICE": "WMS",
                "REQUEST": "GetCapabilities",
                "VERSION": "1.3.0",
            },
            map_path=container_project,
        )
        text = body[:1200].decode("utf-8", errors="ignore")
        if "ServiceException" in text or "ExceptionReport" in text:
            status["error"] = text
            return status
        status["available"] = "xml" in content_type.lower() or b"WMS_Capabilities" in body[:400] or b"WMT_MS_Capabilities" in body[:400]
        if not status["available"]:
            status["error"] = f"Unexpected QGIS Server response content type: {content_type}"
        else:
            status["extent"] = _wms_extent_from_capabilities(
                body,
                metadata.get("render_wms_layers", "").split(","),
                status["crs"],
            )
    except Exception as exc:
        status["error"] = str(exc)
    return status


def ensure_project_qgis_preview(project_id: str, project: dict[str, Any]) -> dict[str, Any]:
    """Sync uploaded files to QGIS Server data root and prepare a project file."""

    if not project_id or not project:
        return {}
    preview_dir = qgis_project_host_root() / f"web_{project_id}"
    preview_dir.mkdir(parents=True, exist_ok=True)
    upload_dir = ROOT / "data" / "projects" / project_id / "uploads"
    copied: list[dict[str, str]] = []

    for doc in project.get("documents", []):
        if not isinstance(doc, dict):
            continue
        stored_name = doc.get("stored_name")
        original_name = _safe_upload_name(str(doc.get("filename") or stored_name or "upload"))
        if not stored_name:
            continue
        source = upload_dir / stored_name
        if not source.exists():
            continue
        suffix = Path(original_name).suffix.lower()
        if suffix in ARCHIVE_SUFFIXES:
            archive_copy = preview_dir / original_name
            if archive_copy.exists() and archive_copy.stat().st_size == source.stat().st_size:
                copied.append({"filename": original_name, "path": str(archive_copy)})
                continue
            extracted = safe_extract_archive(source, preview_dir)
            copied.extend({"filename": item.name, "path": str(item)} for item in extracted)
            shutil.copy2(source, archive_copy)
            copied.append({"filename": original_name, "path": str(archive_copy)})
            continue
        target = preview_dir / original_name
        shutil.copy2(source, target)
        copied.append({"filename": original_name, "path": str(target)})

    host_project = _find_project_file(preview_dir, include_generated=False)
    generated = False
    error = ""
    if host_project is None and any(path.suffix.lower() in GIS_DATA_SUFFIXES for path in preview_dir.rglob("*")):
        host_project = preview_dir / "auto_preview.qgs"
        try:
            generate_qgis_project_with_docker(preview_dir, host_project)
            generated = True
        except Exception as exc:
            error = str(exc)

    preview = {
        "project_dir_host": str(preview_dir),
        "project_dir_container": qgis_host_to_container(preview_dir),
        "host_project_file": str(host_project) if host_project else "",
        "container_project_file": qgis_host_to_container(host_project) if host_project else "",
        "copied_files": copied,
        "generated": generated,
        "updated_at": _now_iso(),
        "error": error,
    }
    project["qgis_preview"] = preview
    return preview


def generate_qgis_project_with_docker(project_dir: Path, output_project: Path) -> None:
    script_dir = ROOT / "docker" / "qgis-server"
    image = os.getenv("QGIS_DOCKER_IMAGE", "qgis/qgis-server:ltr")
    command = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{_docker_path(project_dir)}:/work",
        "-v",
        f"{_docker_path(script_dir)}:/scripts:ro",
        "-e",
        "QT_QPA_PLATFORM=offscreen",
        image,
        "python3",
        "/scripts/create_preview_project.py",
        "/work",
        f"/work/{output_project.name}",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=int(os.getenv("QGIS_PROJECT_BUILD_TIMEOUT", "120")))
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "QGIS project generation failed").strip())
    if not output_project.exists():
        raise RuntimeError("QGIS project generation finished but output project was not created.")


def request_qgis_server(params: dict[str, Any] | Iterable[tuple[str, Any]], map_path: str | None = None) -> tuple[bytes, str]:
    server_url = qgis_server_url()
    if not server_url:
        raise RuntimeError("QGIS_SERVER_URL is not configured.")

    query_items = list(params.items()) if isinstance(params, dict) else list(params)
    query = _merge_qgis_params(query_items, map_path=map_path)
    url = _append_query(server_url, query)
    timeout = float(os.getenv("QGIS_SERVER_TIMEOUT", "20"))
    request = urllib.request.Request(url, headers={"User-Agent": "gis-review-qgis-preview/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(), response.headers.get("content-type", "application/octet-stream")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"QGIS Server HTTP {exc.code}: {body[:800]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"QGIS Server request failed: {exc}") from exc


def request_qgis_map(params: dict[str, Any] | Iterable[tuple[str, Any]], map_path: str | None = None) -> tuple[bytes, str]:
    """Fetch a WMS map image with a small, short-lived cache for map navigation."""

    query_items = list(params.items()) if isinstance(params, dict) else list(params)
    request_name = next((str(value).upper() for key, value in query_items if str(key).upper() == "REQUEST"), "")
    if request_name != "GETMAP":
        return request_qgis_server(query_items, map_path=map_path)

    cache_key = _wms_cache_key(query_items, map_path)
    now = time.monotonic()
    ttl = max(0, int(os.getenv("QGIS_WMS_CACHE_TTL", "90")))
    if ttl:
        with _WMS_CACHE_LOCK:
            cached = _WMS_CACHE.get(cache_key)
            if cached and now - cached[0] <= ttl:
                _WMS_CACHE.move_to_end(cache_key)
                return cached[1], cached[2]
            if cached:
                _WMS_CACHE.pop(cache_key, None)

    body, content_type = request_qgis_server(query_items, map_path=map_path)
    if ttl and content_type.lower().startswith("image/"):
        limit = max(1, int(os.getenv("QGIS_WMS_CACHE_SIZE", "96")))
        with _WMS_CACHE_LOCK:
            _WMS_CACHE[cache_key] = (now, body, content_type)
            _WMS_CACHE.move_to_end(cache_key)
            while len(_WMS_CACHE) > limit:
                _WMS_CACHE.popitem(last=False)
    return body, content_type


def qgis_project_map_path(project_id: str | None = None) -> str:
    preview = _project_preview(project_id)
    if preview.get("container_project_file"):
        return str(preview["container_project_file"])
    return qgis_container_project_file(qgis_project_file())


def qgis_project_file() -> Path:
    configured = os.getenv("QGIS_PROJECT_FILE", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_PROJECT_FILE.resolve()


def qgis_container_project_file(host_project: Path) -> str:
    configured = os.getenv("QGIS_PROJECT_FILE_CONTAINER", "").strip()
    return configured or qgis_host_to_container(host_project)


def qgis_server_url() -> str:
    return os.getenv("QGIS_SERVER_URL", "").strip()


def qgis_project_host_root() -> Path:
    configured = os.getenv("QGIS_SERVER_DATA_ROOT_HOST", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    default = Path("E:/QGIS_Server/projects")
    return default if default.exists() else (ROOT / "data" / "qgis_server_projects")


def qgis_project_container_root() -> str:
    return os.getenv("QGIS_SERVER_DATA_ROOT_CONTAINER", "/io/data").strip().rstrip("/")


def qgis_host_to_container(path: Path | None) -> str:
    if path is None:
        return ""
    root = qgis_project_host_root()
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return str(path).replace("\\", "/")
    return f"{qgis_project_container_root()}/{relative.as_posix()}"


def read_qgis_project_metadata(project_file: Path) -> dict[str, Any]:
    if not project_file.exists():
        return {"layers": [], "wms_layers": "", "crs": os.getenv("QGIS_PREVIEW_CRS", "EPSG:25832")}
    try:
        xml_text = _read_qgis_project_xml(project_file)
        root = ElementTree.fromstring(xml_text)
    except Exception:
        return {"layers": [], "wms_layers": "", "crs": os.getenv("QGIS_PREVIEW_CRS", "EPSG:25832")}

    layer_tree = _layer_tree_layers(root)
    map_layers = _map_layers(root)
    layers = layer_tree or map_layers
    crs = _project_crs(root) or os.getenv("QGIS_PREVIEW_CRS", "EPSG:25832")
    title = root.findtext(".//title") or project_file.stem
    wms_layers = [layer["name"] for layer in layers if layer.get("checked", True)]
    render_layers = [name for name in wms_layers if not _is_slow_preview_layer(name)]
    return {
        "layers": layers,
        "wms_layers": ",".join(wms_layers),
        "render_wms_layers": ",".join(render_layers),
        "excluded_wms_layers": [name for name in wms_layers if name not in render_layers],
        "crs": crs,
        "title": title,
    }


def _is_slow_preview_layer(name: str) -> bool:
    """Keep external/base maps out of the interactive engineering preview by default."""

    configured = os.getenv(
        "QGIS_PREVIEW_EXCLUDE_LAYERS",
        "OpenStreetMap-DE,Liegenschaftskarte,Liegenschaftskarte Graustufen",
    )
    excluded = {item.strip().casefold() for item in configured.split(",") if item.strip()}
    return name.casefold() in excluded


def _wms_extent_from_capabilities(body: bytes, layer_names: list[str], crs: str) -> list[float] | None:
    """Read the engineering-layer bounds from WMS capabilities, excluding wide base maps."""

    wanted = {name.strip() for name in layer_names if name.strip()}
    if not wanted:
        return None
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return None

    bounds: list[tuple[float, float, float, float]] = []
    for layer in root.iter():
        if not layer.tag.endswith("Layer"):
            continue
        name = next((child.text or "" for child in layer if child.tag.endswith("Name")), "")
        if name not in wanted:
            continue
        for box in layer:
            if not box.tag.endswith("BoundingBox") or box.attrib.get("CRS", "").upper() != crs.upper():
                continue
            try:
                bounds.append(
                    (
                        float(box.attrib["minx"]),
                        float(box.attrib["miny"]),
                        float(box.attrib["maxx"]),
                        float(box.attrib["maxy"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
            break
    if not bounds:
        return None
    return [
        min(item[0] for item in bounds),
        min(item[1] for item in bounds),
        max(item[2] for item in bounds),
        max(item[3] for item in bounds),
    ]


def _project_preview(project_id: str | None) -> dict[str, Any]:
    if not project_id:
        host = qgis_project_file()
        return {
            "host_project_file": str(host),
            "container_project_file": qgis_container_project_file(host),
            "generated": False,
            "error": "",
        }
    try:
        from .storage import get_project, save_project

        project = get_project(project_id)
        if not project:
            return {"error": f"project not found: {project_id}"}
        preview = project.get("qgis_preview") or {}
        host_project = Path(str(preview.get("host_project_file") or ""))
        if not preview or not host_project.exists():
            preview = ensure_project_qgis_preview(project_id, project)
            save_project(project)
        return preview
    except Exception as exc:
        return {"error": str(exc)}


def _read_qgis_project_xml(project_file: Path) -> str:
    if project_file.suffix.lower() == ".qgz":
        with zipfile.ZipFile(project_file) as archive:
            qgs_names = [name for name in archive.namelist() if name.lower().endswith(".qgs")]
            if not qgs_names:
                raise RuntimeError("No .qgs project XML found inside .qgz")
            return archive.read(qgs_names[0]).decode("utf-8", errors="replace")
    return project_file.read_text(encoding="utf-8", errors="replace")


def _layer_tree_layers(root: ElementTree.Element) -> list[dict[str, Any]]:
    layers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in root.findall(".//layer-tree-layer"):
        name = node.attrib.get("name") or node.attrib.get("source") or ""
        if not name or name in seen:
            continue
        seen.add(name)
        checked = node.attrib.get("checked", "Qt::Checked") != "Qt::Unchecked"
        layers.append({"name": name, "checked": checked, "source": "layer_tree"})
    return layers


def _map_layers(root: ElementTree.Element) -> list[dict[str, Any]]:
    layers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in root.findall(".//maplayer"):
        name = node.findtext("shortname") or node.findtext("layername") or node.findtext("id") or ""
        if name and name not in seen:
            seen.add(name)
            layers.append({"name": name, "checked": True, "source": "maplayer"})
    return layers


def _project_crs(root: ElementTree.Element) -> str:
    candidates = [
        ".//projectCrs/spatialrefsys/authid",
        ".//projectlayers/maplayer/srs/spatialrefsys/authid",
        ".//destinationsrs/spatialrefsys/authid",
    ]
    for xpath in candidates:
        value = root.findtext(xpath)
        if value and value.upper().startswith("EPSG:"):
            return value.upper()
    return ""


def _find_project_file(directory: Path, include_generated: bool = True) -> Path | None:
    for suffix in ("*.qgz", "*.qgs"):
        matches = sorted(directory.rglob(suffix))
        if not include_generated:
            matches = [path for path in matches if path.name != "auto_preview.qgs"]
        if matches:
            return matches[0]
    return None


def _merge_qgis_params(items: list[tuple[str, Any]], map_path: str | None = None) -> str:
    merged = [
        (key, value)
        for key, value in items
        if str(value) != "" and key.lower() not in {"project_id", "map", "preview_revision"}
    ]
    seen = {key.upper() for key, _ in merged}
    merged.append(("MAP", map_path or qgis_container_project_file(qgis_project_file())))
    if "SERVICE" not in seen:
        merged.append(("SERVICE", "WMS"))
    return urllib.parse.urlencode(merged, doseq=True)


def _wms_cache_key(items: list[tuple[str, Any]], map_path: str | None) -> str:
    normalized = sorted(
        (str(key).upper(), str(value))
        for key, value in items
        if str(key).lower() not in {"project_id", "map", "preview_revision"}
    )
    return repr((map_path or qgis_container_project_file(qgis_project_file()), normalized))


def _append_query(url: str, query: str) -> str:
    separator = "&" if urllib.parse.urlsplit(url).query else "?"
    return f"{url}{separator}{query}"


def _safe_upload_name(filename: str) -> str:
    parts = [part for part in Path(filename).parts if part not in {"", ".", ".."}]
    name = Path(*parts).name if parts else "upload"
    return re_sub_unsafe_filename(name)


def re_sub_unsafe_filename(name: str) -> str:
    return "".join(char if char not in '<>:"|?*' else "_" for char in name).strip() or "upload"


def _docker_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
