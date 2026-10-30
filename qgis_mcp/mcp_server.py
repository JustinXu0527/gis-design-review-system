from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import httpx
from mcp.server.fastmcp import FastMCP


QGIS_SERVER_URL = os.getenv(
    "QGIS_SERVER_URL",
    "http://qgis-server/ows/",
).rstrip("/") + "/"

# MCP 容器看到的工程目录
PROJECTS_ROOT = Path(
    os.getenv("QGIS_PROJECTS_ROOT", "/projects")
).resolve()

# QGIS Server 容器看到的工程目录
QGIS_CONTAINER_ROOT = os.getenv(
    "QGIS_CONTAINER_ROOT",
    "/io/data",
).rstrip("/")

MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "9877"))

PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
WEB_PROJECT_PREFIX = os.getenv("QGIS_WEB_PROJECT_PREFIX", "web_")


mcp = FastMCP(
    name="QGIS MCP Server",
    host=MCP_HOST,
    port=MCP_PORT,
    stateless_http=True,
    json_response=True,
)


def resolve_project(project_id: str) -> tuple[Path, str, str]:
    """
    根据 project_id 找到工程文件。

    返回：
    1. MCP 容器中的真实文件路径
    2. QGIS Server 容器使用的 MAP 路径
    3. 实际匹配的目录名（兼容网站的 web_<project_id> 目录）
    """
    if not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise ValueError(
            "project_id 只能包含字母、数字、下划线和连字符。"
        )

    directory_names = [project_id]
    if WEB_PROJECT_PREFIX and not project_id.startswith(WEB_PROJECT_PREFIX):
        directory_names.append(f"{WEB_PROJECT_PREFIX}{project_id}")

    project_directory: Path | None = None
    resolved_project_id = ""
    for directory_name in directory_names:
        candidate = (PROJECTS_ROOT / directory_name).resolve()
        if PROJECTS_ROOT not in candidate.parents:
            continue
        if candidate.is_dir():
            project_directory = candidate
            resolved_project_id = directory_name
            break

    if project_directory is None:
        raise FileNotFoundError(
            f"找不到工程目录：{project_id}"
        )

    project_files = sorted(
        list(project_directory.glob("*.qgz"))
        + list(project_directory.glob("*.qgs"))
    )

    if not project_files:
        raise FileNotFoundError(
            f"工程 {project_id} 中没有 .qgz 或 .qgs 文件。"
        )

    mcp_project_path = _select_project_file(project_files)

    qgis_map_path = (
        f"{QGIS_CONTAINER_ROOT}/"
        f"{resolved_project_id}/"
        f"{mcp_project_path.name}"
    )

    return mcp_project_path, qgis_map_path, resolved_project_id


def _select_project_file(project_files: list[Path]) -> Path:
    """Mirror the web application's preview preference for uploaded QGIS projects."""
    non_generated = [file for file in project_files if file.name.lower() != "auto_preview.qgs"]
    candidates = non_generated or project_files
    qgz_files = [file for file in candidates if file.suffix.lower() == ".qgz"]
    return sorted(qgz_files or candidates, key=lambda file: file.name.lower())[0]


def local_name(tag: str) -> str:
    """移除 XML 标签的命名空间。"""
    return tag.rsplit("}", 1)[-1]


def parse_capabilities(xml_text: str) -> dict[str, Any]:
    """解析 WMS GetCapabilities 返回的图层信息。"""
    root = ElementTree.fromstring(xml_text)

    layers: list[dict[str, str | None]] = []

    for element in root.iter():
        if local_name(element.tag) != "Layer":
            continue

        layer_name: str | None = None
        layer_title: str | None = None

        for child in element:
            child_name = local_name(child.tag)

            if child_name == "Name":
                layer_name = child.text
            elif child_name == "Title":
                layer_title = child.text

        if layer_name or layer_title:
            layers.append(
                {
                    "name": layer_name,
                    "title": layer_title,
                }
            )

    return {
        "xml_root": local_name(root.tag),
        "layer_count": len(layers),
        "layers": layers,
    }


def _feature_info_bbox(coordinate: list[float], radius: float) -> str:
    x, y = float(coordinate[0]), float(coordinate[1])
    safe_radius = min(max(float(radius), 0.5), 5000.0)
    return f"{x - safe_radius},{y - safe_radius},{x + safe_radius},{y + safe_radius}"


def _selected_fields(properties: dict[str, Any], requested_fields: list[str]) -> dict[str, Any]:
    if not requested_fields:
        return dict(list(properties.items())[:16])
    normalized = {str(key).casefold(): str(key) for key in properties}
    selected: dict[str, Any] = {}
    for requested in requested_fields[:16]:
        requested_key = str(requested).casefold()
        requested_token = re.sub(r"[^\w]", "", requested_key)
        actual = normalized.get(requested_key)
        if not actual and requested_token:
            actual = next(
                (
                    str(key)
                    for key in properties
                    if re.sub(r"[^\w]", "", str(key).casefold()).startswith(requested_token)
                ),
                None,
            )
        if actual:
            selected[actual] = properties.get(actual)
    for key, value in properties.items():
        if key not in selected:
            selected[key] = value
        if len(selected) >= 8:
            break
    return selected


@mcp.tool()
async def qgis_server_health() -> dict[str, Any]:
    """
    检查 MCP 容器是否能够连接 QGIS Server。
    """
    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
        ) as client:
            response = await client.get(QGIS_SERVER_URL)

        return {
            "reachable": True,
            "qgis_server_url": QGIS_SERVER_URL,
            "http_status": response.status_code,
            "message": "已经连接到 QGIS Server。",
        }

    except httpx.HTTPError as exc:
        return {
            "reachable": False,
            "qgis_server_url": QGIS_SERVER_URL,
            "error": str(exc),
        }


@mcp.tool()
def list_qgis_projects() -> dict[str, Any]:
    """
    列出已经挂载到 MCP 容器中的所有 QGIS 工程。
    """
    if not PROJECTS_ROOT.exists():
        return {
            "project_count": 0,
            "projects": [],
            "error": f"工程根目录不存在：{PROJECTS_ROOT}",
        }

    projects: list[dict[str, Any]] = []

    for directory in sorted(PROJECTS_ROOT.iterdir()):
        if not directory.is_dir():
            continue

        project_files = sorted(
            list(directory.glob("*.qgz"))
            + list(directory.glob("*.qgs"))
        )

        projects.append(
            {
                "project_id": directory.name,
                "project_files": [
                    file.name for file in project_files
                ],
                "project_file_count": len(project_files),
            }
        )

    return {
        "project_count": len(projects),
        "projects": projects,
    }


@mcp.tool()
async def get_project_capabilities(
    project_id: str,
) -> dict[str, Any]:
    """
    验证指定 QGIS 工程，并返回可发布的 WMS 图层。
    """
    try:
        mcp_path, qgis_map_path, resolved_project_id = resolve_project(project_id)
    except (ValueError, FileNotFoundError) as exc:
        return {
            "valid": False,
            "project_id": project_id,
            "error": str(exc),
        }

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetCapabilities",
        "MAP": qgis_map_path,
    }

    try:
        async with httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
        ) as client:
            response = await client.get(
                QGIS_SERVER_URL,
                params=params,
            )

        response.raise_for_status()

    except httpx.HTTPError as exc:
        return {
            "valid": False,
            "project_id": project_id,
            "error": f"调用 QGIS Server 失败：{exc}",
        }

    xml_text = response.text

    if (
        "ServerException" in xml_text
        or "ServiceException" in xml_text
    ):
        return {
            "valid": False,
            "project_id": project_id,
            "mcp_project_path": str(mcp_path),
            "qgis_map_path": qgis_map_path,
            "qgis_response": xml_text[:3000],
        }

    try:
        parsed = parse_capabilities(xml_text)
    except ElementTree.ParseError as exc:
        return {
            "valid": False,
            "project_id": project_id,
            "error": f"QGIS Server 没有返回有效 XML：{exc}",
            "response_preview": xml_text[:1000],
        }

    return {
        "valid": True,
        "project_id": project_id,
        "resolved_project_id": resolved_project_id,
        "mcp_project_path": str(mcp_path),
        "qgis_map_path": qgis_map_path,
        **parsed,
    }


@mcp.tool()
async def inspect_project_object(
    project_id: str,
    object_id: str,
    layer_name: str,
    coordinate: list[float],
    source_feature_id: str = "",
    requested_fields: list[str] | None = None,
    crs: str = "EPSG:25832",
    search_radius: float = 25.0,
) -> dict[str, Any]:
    """Use QGIS Server GetFeatureInfo to query one engineering object and read its fields."""
    if len(coordinate) < 2:
        return {
            "valid": False,
            "object_id": object_id,
            "layer_name": layer_name,
            "error": "coordinate 至少需要包含 x、y 两个数值。",
        }
    try:
        _, qgis_map_path, resolved_project_id = resolve_project(project_id)
    except (ValueError, FileNotFoundError) as exc:
        return {
            "valid": False,
            "project_id": project_id,
            "object_id": object_id,
            "layer_name": layer_name,
            "error": str(exc),
        }

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetFeatureInfo",
        "MAP": qgis_map_path,
        "LAYERS": layer_name,
        "QUERY_LAYERS": layer_name,
        "STYLES": "",
        "CRS": crs,
        "BBOX": _feature_info_bbox(coordinate, search_radius),
        "WIDTH": "256",
        "HEIGHT": "256",
        "I": "128",
        "J": "128",
        "INFO_FORMAT": "application/json",
        "FEATURE_COUNT": "10",
        "WITH_GEOMETRY": "TRUE",
    }
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(QGIS_SERVER_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        return {
            "valid": False,
            "project_id": project_id,
            "resolved_project_id": resolved_project_id,
            "object_id": object_id,
            "layer_name": layer_name,
            "source_feature_id": source_feature_id,
            "query_method": "QGIS Server WMS GetFeatureInfo",
            "error": f"QGIS 对象查询失败：{exc}",
        }

    features = payload.get("features") if isinstance(payload, dict) else []
    features = features if isinstance(features, list) else []
    feature = features[0] if features and isinstance(features[0], dict) else {}
    properties = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
    fields = _selected_fields(properties, requested_fields or [])
    return {
        "valid": bool(feature),
        "project_id": project_id,
        "resolved_project_id": resolved_project_id,
        "object_id": object_id,
        "layer_name": layer_name,
        "layer_found": bool(feature),
        "source_feature_id": source_feature_id,
        "qgis_feature_id": str(feature.get("id") or ""),
        "query_method": "QGIS Server WMS GetFeatureInfo",
        "requested_coordinate": [float(coordinate[0]), float(coordinate[1])],
        "crs": crs,
        "location_verified": bool(feature),
        "candidate_count": len(features),
        "field_count": len(properties),
        "field_names": list(fields),
        "fields": fields,
        "message": "QGIS 已定位对象并读取图层字段。" if feature else "QGIS 在指定位置未返回图层要素。",
    }


@mcp.tool()
def build_wms_getmap_url(
    project_id: str,
    layers: str,
    bbox: str,
    crs: str = "EPSG:3857",
    width: int = 1200,
    height: int = 800,
    image_format: str = "image/png",
) -> dict[str, str]:
    """
    为指定工程构造 WMS GetMap 地址。

    layers 示例：
    Pipes,Infrastructure

    bbox 示例：
    932000,6450000,938000,6456000
    """
    _, qgis_map_path, resolved_project_id = resolve_project(project_id)

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetMap",
        "MAP": qgis_map_path,
        "LAYERS": layers,
        "STYLES": "",
        "CRS": crs,
        "BBOX": bbox,
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": image_format,
        "TRANSPARENT": "TRUE",
    }

    request = httpx.Request(
        method="GET",
        url=QGIS_SERVER_URL,
        params=params,
    )

    return {
        "project_id": project_id,
        "resolved_project_id": resolved_project_id,
        "getmap_url": str(request.url),
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
