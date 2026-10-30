from __future__ import annotations

import base64
import csv
import io
import json
import re
import tempfile
import uuid
import zipfile
from html import unescape
from pathlib import Path
from typing import Any

from .archive_utils import ARCHIVE_SUFFIXES, safe_extract_archive
from .models import DesignObject


TYPE_ALIASES = {
    "光缆": "fiber_cable",
    "光缆段": "fiber_cable",
    "主干光缆": "fiber_cable",
    "楼宇分支光缆": "fiber_cable",
    "通信光缆": "fiber_cable",
    "通信电缆": "telecom_cable",
    "电信电缆": "telecom_cable",
    "通信线路": "telecom_line",
    "电信线路": "telecom_line",
    "管道": "duct",
    "通信管道": "duct",
    "主干通信管道": "duct",
    "主干管道": "duct",
    "管孔": "duct_hole",
    "杆路": "pole_route",
    "杆": "pole",
    "手孔": "manhole",
    "人孔": "manhole",
    "人井": "manhole",
    "机房": "equipment_room",
    "弱电机房": "equipment_room",
    "核心机房": "equipment_room",
    "核心弱电机房": "equipment_room",
    "基站": "base_station",
    "光交箱": "fiber_cabinet",
    "光交接箱": "fiber_cabinet",
    "交接箱": "fiber_cabinet",
    "电力线": "power_line",
    "电力线路": "power_line",
    "强电线路": "power_line",
    "强电电缆": "power_line",
    "近电作业": "power_line_work",
    "带电体作业": "power_line_work",
    "带电导体作业": "power_line_work",
    "电力线路作业": "power_line_work",
    "道路": "road",
    "建筑": "building",
    "建筑物": "building",
    "办公楼": "building",
    "厂房": "building",
    "研发中心": "building",
    "楼宇": "building",
    "端口": "port",
    "纤芯": "fiber_core",
    "ODF": "equipment",
    "ODF架": "equipment",
    "ODF配线架": "equipment",
    "设备": "equipment",
    "接地系统": "grounding_system",
    "接地": "grounding_system",
    "浪涌保护器": "surge_protector",
    "SPD": "surge_protector",
    "防雷器": "surge_protector",
    "危险区域": "hazardous_area",
    "爆炸危险区域": "hazardous_area",
    "瓦斯管道": "gas_pipeline",
    "隧道": "tunnel",
    "防火板": "tunnel_fireproof_board",
    "铁路": "railway",
    "铁路路基": "railway_roadbed",
    "开挖": "excavation",
    "施工升降机": "construction_hoist",
    "fiber_cable": "fiber_cable",
    "telecom_cable": "telecom_cable",
    "telecom_line": "telecom_line",
    "duct": "duct",
    "duct_hole": "duct_hole",
    "pole_route": "pole_route",
    "pole": "pole",
    "manhole": "manhole",
    "equipment_room": "equipment_room",
    "base_station": "base_station",
    "fiber_cabinet": "fiber_cabinet",
    "cabinet": "fiber_cabinet",
    "power_line": "power_line",
    "power_line_work": "power_line_work",
    "road": "road",
    "building": "building",
    "port": "port",
    "fiber_core": "fiber_core",
    # German official GIS deliverables used by the Dreieich FTTH test project.
    "address": "address_point",
    "bereich": "project_area",
    "einmessung": "surveyed_route",
    "fotos": "construction_photo",
    "fremdleitung": "third_party_utility",
    "gbgs": "customer_status_record",
    "hauseinführung": "house_connection",
    "hauseinfuehrung": "house_connection",
    "infrastructure": "telecom_infrastructure_node",
    "pipes": "telecom_duct_route",
    "pitwork": "civil_pit_work",
    "po_liste": "procurement_record",
    "rotberichtigung": "redline_correction_area",
    "site_nummer": "site_index_record",
    "dt_materials": "material_reference",
    "gas": "gas_pipeline",
    "wasser": "water_pipeline",
    "strom": "power_line",
    "tk": "existing_telecom_line",
    "kanal": "sewer_pipeline",
    "hvt": "telecom_central_node",
    "nvt": "fiber_distribution_cabinet",
    "muffe": "splice_closure",
}


GIS_LAYER_TYPE_ALIASES = {
    "address": "address_point",
    "bereich": "project_area",
    "dt_materials": "material_reference",
    "einmessung": "surveyed_route",
    "fotos": "construction_photo",
    "fremdleitung": "third_party_utility",
    "gbgs": "customer_status_record",
    "hauseinführung": "house_connection",
    "hauseinfuehrung": "house_connection",
    "infrastructure": "telecom_infrastructure_node",
    "pipes": "telecom_duct_route",
    "pitwork": "civil_pit_work",
    "po_liste": "procurement_record",
    "rotberichtigung": "redline_correction_area",
    "site_nummer": "site_index_record",
}


GERMAN_UTILITY_CLASS_ALIASES = {
    "gas": "gas_pipeline",
    "wasser": "water_pipeline",
    "strom": "power_line",
    "tk": "existing_telecom_line",
    "kanal": "sewer_pipeline",
}


GERMAN_INFRASTRUCTURE_TYPE_ALIASES = {
    "hvt": "telecom_central_node",
    "nvt": "fiber_distribution_cabinet",
    "muffe": "splice_closure",
}


TEXT_OBJECT_PATTERNS = [
    ("fiber_cabinet", ["光交接箱", "光交箱", "交接箱"]),
    ("equipment_room", ["核心弱电机房", "弱电机房", "核心机房", "机房"]),
    ("fiber_cable", ["楼宇分支光缆", "主干光缆", "通信光缆", "光缆"]),
    ("telecom_cable", ["通信电缆", "电信电缆"]),
    ("telecom_line", ["通信线路", "电信线路"]),
    ("duct_hole", ["管孔"]),
    ("duct", ["主干通信管道", "通信管道", "主干管道", "管道"]),
    ("manhole", ["手孔", "人孔", "人井"]),
    ("equipment", ["ODF配线架", "ODF架", "ODF", "机柜", "设备"]),
    ("power_line_work", ["近电作业", "带电体作业", "带电导体作业", "电力线路作业"]),
    ("power_line", ["电力线路", "电力线", "强电线路", "强电电缆"]),
    ("road", ["道路"]),
    ("building", ["综合服务楼", "办公楼", "厂房", "研发中心", "仓储用房", "楼宇", "建筑物", "建筑"]),
    ("port", ["端口"]),
    ("fiber_core", ["纤芯"]),
    ("grounding_system", ["防雷防静电接地", "接地系统", "接地"]),
    ("surge_protector", ["浪涌保护器", "防雷器", "SPD"]),
    ("hazardous_area", ["爆炸危险区域", "危险区域"]),
    ("gas_pipeline", ["瓦斯管道"]),
    ("tunnel_fireproof_board", ["防火板"]),
    ("tunnel", ["隧道"]),
    ("railway_roadbed", ["铁路路基"]),
    ("railway", ["铁路"]),
    ("construction_hoist", ["施工升降机"]),
    ("excavation", ["开挖"]),
]

GENERIC_NAMES = {
    "光缆",
    "通信光缆",
    "管道",
    "通信管道",
    "机房",
    "光交接箱",
    "光交箱",
    "设备",
    "道路",
    "楼宇",
    "建筑",
    "端口",
    "纤芯",
}

SUPPORTED_TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".json", ".geojson", ".csv", ".tsv", ".dxf"}
SUPPORTED_GIS_SUFFIXES = {".gpkg", ".shp", ".geojson"} | ARCHIVE_SUFFIXES
PREVIEW_ONLY_SUFFIXES = {".qgs", ".qgz", ".qml", ".sld"}
PDF_PAGE_MARKER = "__PDF_PAGE__:"
OBJECT_TYPE_FIELDS = ["object_type", "type", "layer", "category", "class", "对象类型", "类型", "类别", "图层"]
OBJECT_NAME_FIELDS = ["name", "title", "label", "display_name", "名称", "对象名称", "设施名称"]
OBJECT_ID_FIELDS = ["id", "object_id", "fid", "编号", "对象编号", "设施编号"]


def normalize_type(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown"
    return TYPE_ALIASES.get(text, text.lower().replace(" ", "_"))


def decode_upload(payload: dict[str, Any]) -> tuple[str, bytes]:
    if isinstance(payload.get("files"), list):
        filename = payload.get("filename") or f"upload-{uuid.uuid4().hex}.zip"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for item in payload["files"]:
                child_name = Path(str(item.get("filename") or f"file-{uuid.uuid4().hex}")).name
                if "content_base64" in item:
                    child_raw = base64.b64decode(item["content_base64"])
                else:
                    child_raw = str(item.get("content", "")).encode("utf-8")
                zf.writestr(child_name, child_raw)
        return filename, buffer.getvalue()
    filename = payload.get("filename") or f"upload-{uuid.uuid4().hex}.txt"
    if "content_base64" in payload:
        return filename, base64.b64decode(payload["content_base64"])
    return filename, str(payload.get("content", "")).encode("utf-8")


def extract_text(filename: str, raw: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in SUPPORTED_TEXT_SUFFIXES:
        return raw.decode("utf-8-sig", errors="replace")
    if suffix == ".docx":
        return _docx_text(raw)
    if suffix == ".xlsx":
        return _xlsx_text(raw)
    if suffix == ".pdf":
        return _pdf_text(raw)
    return raw.decode("utf-8", errors="replace")


def extract_marked_json(text: str, begin_marker: str, end_marker: str) -> Any | None:
    pattern = re.compile(
        rf"{re.escape(begin_marker)}\s*(.*?)\s*{re.escape(end_marker)}",
        flags=re.S,
    )
    match = pattern.search(text)
    if not match:
        return None
    return json.loads(match.group(1))


def extract_design_objects(filename: str, raw: bytes) -> list[DesignObject]:
    suffix = Path(filename).suffix.lower()
    if suffix in PREVIEW_ONLY_SUFFIXES:
        return []
    if suffix in SUPPORTED_GIS_SUFFIXES:
        return _objects_from_gis_upload(filename, raw)
    text = extract_text(filename, raw)
    embedded = extract_marked_json(text, "BEGIN_DESIGN_OBJECTS_JSON", "END_DESIGN_OBJECTS_JSON")
    if embedded is not None:
        return _objects_from_data(filename, embedded)
    if suffix in {".json", ".geojson"}:
        return _objects_from_json(filename, text)
    if suffix in {".csv", ".tsv"}:
        return _objects_from_table(filename, text, delimiter="\t" if suffix == ".tsv" else ",")
    if suffix == ".xlsx":
        return _objects_from_xlsx_text(filename, text)
    return _objects_from_markdown_like(filename, text)


def extract_design_objects_from_path(filename: str, path: Path, archive_password: str = "") -> list[DesignObject]:
    suffix = Path(filename).suffix.lower()
    if suffix in PREVIEW_ONLY_SUFFIXES:
        return []
    if suffix in SUPPORTED_GIS_SUFFIXES:
        return _objects_from_gis_file(filename, path, archive_password)
    return extract_design_objects(filename, path.read_bytes())


def _objects_from_gis_upload(filename: str, raw: bytes) -> list[DesignObject]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".geojson":
        try:
            return _objects_from_gis_bytes(filename, raw)
        except RuntimeError:
            return _objects_from_json(filename, raw.decode("utf-8-sig", errors="replace"))
    return _objects_from_gis_bytes(filename, raw)


def _objects_from_gis_bytes(filename: str, raw: bytes) -> list[DesignObject]:
    with tempfile.TemporaryDirectory(prefix="gis-upload-source-") as temp_dir:
        source = Path(temp_dir) / Path(filename).name
        source.write_bytes(raw)
        return _objects_from_gis_file(filename, source)


def _objects_from_gis_file(filename: str, source: Path, archive_password: str = "") -> list[DesignObject]:
    try:
        import geopandas as gpd
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("GIS 设计成果抽取需要安装 geopandas、shapely 和 pyogrio。") from exc

    suffix = Path(filename).suffix.lower()
    objects: list[DesignObject] = []
    if suffix in ARCHIVE_SUFFIXES:
        with tempfile.TemporaryDirectory(prefix="gis-archive-") as temp_dir:
            temp_root = Path(temp_dir)
            safe_extract_archive(source, temp_root, archive_password)
            candidates = sorted(
                path for path in temp_root.rglob("*") if path.is_file() and path.suffix.lower() in {".shp", ".gpkg", ".geojson"}
            )
            if not candidates:
                raise ValueError("压缩包中没有找到 .shp、.gpkg 或 .geojson GIS 成果文件。")
            for path in candidates:
                objects.extend(_objects_from_gis_path(gpd, filename, path))
            return objects
    objects.extend(_objects_from_gis_path(gpd, filename, source))
    return objects


def _objects_from_gis_path(gpd: Any, source_filename: str, path: Path) -> list[DesignObject]:
    layers = _gis_layers(path)
    objects: list[DesignObject] = []
    for layer in layers:
        try:
            frame = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
        except Exception as exc:
            raise RuntimeError(f"无法读取 GIS 图层 {path.name}{'/' + layer if layer else ''}：{exc}") from exc
        if frame.empty:
            continue
        for row_index, row in frame.iterrows():
            objects.append(_gis_row_to_object(source_filename, path, layer, row_index, row))
    return objects


def _gis_layers(path: Path) -> list[str | None]:
    if path.suffix.lower() != ".gpkg":
        return [None]
    try:
        import pyogrio

        return [str(item[0]) for item in pyogrio.list_layers(path)]
    except Exception:
        return [None]


def _gis_row_to_object(source_filename: str, path: Path, layer: str | None, row_index: Any, row: Any) -> DesignObject:
    props = _json_ready_properties({key: value for key, value in row.items() if key != "geometry"})
    layer_name = layer or props.get("layer") or path.stem
    obj_type = _gis_semantic_type(str(layer_name), props)
    row_id = _first_present(props, OBJECT_ID_FIELDS) or row_index
    obj_id = f"{Path(source_filename).stem}-{layer_name}-{row_id}"
    name = str(_first_present(props, OBJECT_NAME_FIELDS) or props.get("编号") or obj_id)
    geom = row.get("geometry")
    geometry = _geometry_to_mapping(geom)
    props.update(
        {
            "source_file": source_filename,
            "source_layer": str(layer_name),
            "source_feature_id": str(row_id),
            "source_field": "GIS 图层要素",
            "source_location": f"{Path(source_filename).name} / {layer_name} / FID {row_id}",
            "extraction_method": "geopandas_layer",
            "geometry_type": getattr(geom, "geom_type", "") if geom is not None else "",
        }
    )
    return DesignObject(
        id=str(obj_id),
        type=obj_type,
        name=name,
        geometry=geometry,
        properties=props,
        source=source_filename,
    )


def _geometry_to_mapping(geom: Any) -> dict[str, Any] | None:
    if geom is None or getattr(geom, "is_empty", False):
        return None
    try:
        from shapely.geometry import mapping

        return dict(mapping(geom))
    except Exception:
        return None


def _gis_semantic_type(layer_name: str, props: dict[str, Any]) -> str:
    layer_key = _alias_key(layer_name)
    if layer_key == "fremdleitung":
        utility_type = GERMAN_UTILITY_CLASS_ALIASES.get(_alias_key(props.get("Class")))
        if utility_type:
            return utility_type
    if layer_key == "infrastructure":
        infra_type = GERMAN_INFRASTRUCTURE_TYPE_ALIASES.get(_alias_key(props.get("Type")))
        if infra_type:
            return infra_type
    raw_type = _first_present(props, OBJECT_TYPE_FIELDS)
    if raw_type is not None and not _looks_like_numeric_code(raw_type):
        return normalize_type(raw_type)
    return GIS_LAYER_TYPE_ALIASES.get(layer_key, normalize_type(layer_name))


def _alias_key(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("ü", "ue")
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ß", "ss")
    )


def _looks_like_numeric_code(value: Any) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.0+)?", str(value or "").strip()))


def _json_ready_properties(props: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in props.items():
        if value is None:
            clean[key] = None
            continue
        if hasattr(value, "item"):
            try:
                value = value.item()
            except Exception:
                pass
        if isinstance(value, float) and (value != value):
            clean[key] = None
        elif isinstance(value, (str, int, float, bool)) or value is None:
            clean[key] = value
        else:
            clean[key] = str(value)
    return clean


def _objects_from_data(filename: str, data: Any) -> list[DesignObject]:
    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        objects = []
        for index, feature in enumerate(data.get("features", []), start=1):
            props = feature.get("properties") or {}
            obj_type = normalize_type(_first_present(props, ["object_type", "type", "layer", "对象类型", "类型", "图层"]))
            obj_id = str(_first_present(props, ["id", "object_id", "编号"]) or f"{Path(filename).stem}-{index}")
            objects.append(
                DesignObject(
                    id=obj_id,
                    type=obj_type,
                    name=str(_first_present(props, ["name", "名称", "对象名称"]) or obj_id),
                    geometry=feature.get("geometry"),
                    properties=props,
                    source=filename,
                )
            )
        return objects
    if isinstance(data, dict):
        items = data.get("objects", data.get("features", []))
    else:
        items = data if isinstance(data, list) else []
    return [
        DesignObject(
            id=str(_first_present(item, ["id", "object_id", "编号"]) or f"{Path(filename).stem}-{index}"),
            type=normalize_type(_first_present(item, ["object_type", "type", "对象类型", "类型"])),
            name=str(_first_present(item, ["name", "名称", "对象名称", "id"]) or f"对象{index}"),
            geometry=item.get("geometry"),
            properties={k: v for k, v in item.items() if k not in {"geometry"}},
            source=filename,
        )
        for index, item in enumerate(items, start=1)
        if isinstance(item, dict)
    ]


def _objects_from_json(filename: str, text: str) -> list[DesignObject]:
    data = json.loads(text)
    return _objects_from_data(filename, data)


def _objects_from_table(filename: str, text: str, delimiter: str = ",") -> list[DesignObject]:
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    objects = []
    for index, row in enumerate(reader, start=1):
        obj_type = normalize_type(_first_present(row, ["object_type", "type", "对象类型", "类型", "类别", "图层", "layer"]))
        obj_id = str(_first_present(row, ["id", "object_id", "编号", "对象编号"]) or f"{Path(filename).stem}-{index}")
        x = _first_present(row, ["x", "经度", "lon", "longitude"])
        y = _first_present(row, ["y", "纬度", "lat", "latitude"])
        geometry = None
        if x not in (None, "") and y not in (None, ""):
            geometry = {"type": "Point", "coordinates": [float(x), float(y)]}
        objects.append(
            DesignObject(
                id=obj_id,
                type=obj_type,
                name=str(_first_present(row, ["name", "名称", "对象名称"]) or obj_id),
                geometry=geometry,
                properties={k: v for k, v in row.items() if k},
                source=filename,
            )
        )
    return objects


def _objects_from_markdown_like(filename: str, text: str) -> list[DesignObject]:
    normalized = _normalize_text(text)
    table_objects = _objects_from_design_object_table(filename, normalized)
    if table_objects:
        return _dedupe_objects(table_objects)
    return _dedupe_objects(_objects_from_text_keywords(filename, normalized))


def _objects_from_design_object_table(filename: str, text: str) -> list[DesignObject]:
    lines, line_pages = _lines_with_pages(text)
    objects: list[DesignObject] = []
    for index, line in enumerate(lines):
        if not _looks_like_object_name(line):
            continue
        obj_type = _type_from_text(line)
        if obj_type == "unknown":
            continue
        quantity = lines[index + 1] if index + 1 < len(lines) and _looks_like_quantity(lines[index + 1]) else ""
        if not quantity:
            continue
        detail_lines = _collect_table_detail_lines(lines, index + 2)
        if len(detail_lines) > 1 and 0 < len(detail_lines[1]) <= 2:
            detail_lines = [detail_lines[0] + detail_lines[1], *detail_lines[2:]]
        location = detail_lines[0] if detail_lines else ""
        params = " ".join(detail_lines[1:]) if len(detail_lines) > 1 else ""
        source_page = line_pages.get(index)
        excerpt = _compact_source_excerpt([line, quantity, location, params])
        props = {
            "extraction_method": "design_object_table",
            "raw_name": line,
            "source_field": "设计对象表",
            "extracted_from_text": excerpt,
            "source_excerpt": excerpt,
        }
        if source_page:
            props["source_page"] = source_page
            props["source_location"] = f"第{source_page}页，设计对象表"
        if quantity:
            props.update(_parse_quantity(quantity))
        if location:
            props["location_or_range"] = location
        if params:
            props["description"] = params
            props.update(_parse_common_properties(params))
        obj_index = len(objects) + 1
        objects.append(
            DesignObject(
                id=f"{Path(filename).stem}-table-{obj_index}",
                type=obj_type,
                name=line,
                properties=props,
                source=filename,
            )
        )
    return objects


def _collect_table_detail_lines(lines: list[str], start_index: int) -> list[str]:
    details: list[str] = []
    for index in range(start_index, len(lines)):
        line = lines[index]
        if _is_table_noise_line(line):
            continue
        if line.isdigit() and index + 2 < len(lines) and _looks_like_object_name(lines[index + 1]) and _looks_like_quantity(lines[index + 2]):
            break
        if _looks_like_object_name(line) and index + 1 < len(lines) and _looks_like_quantity(lines[index + 1]):
            break
        if line.startswith(("六、", "七、", "八、", "九、", "十、", "十一、", "十二、", "十三、", "附表")):
            break
        details.append(line)
    return details


def _is_table_noise_line(line: str) -> bool:
    if _page_number_from_marker(line):
        return True
    if re.fullmatch(r"第\s*\d+\s*页", line):
        return True
    return line in {
        "一般常见通信接入工程设计方案",
        "序号",
        "设计对象",
        "数量",
        "建议位置或范围",
        "主要参数",
    }


def _objects_from_text_keywords(filename: str, text: str) -> list[DesignObject]:
    objects: list[DesignObject] = []
    seen_contexts: set[tuple[str, str]] = set()
    for sentence, source_page in _split_sentences_with_pages(text):
        if len(sentence) > 240:
            continue
        for obj_type, keywords in TEXT_OBJECT_PATTERNS:
            for keyword in keywords:
                if keyword not in sentence:
                    continue
                name = _extract_name_around_keyword(sentence, keyword)
                if name in GENERIC_NAMES and len(sentence) > 36:
                    name = keyword
                key = (obj_type, name)
                if key in seen_contexts:
                    continue
                seen_contexts.add(key)
                obj_index = len(objects) + 1
                props = {
                    "extraction_method": "text_keyword",
                    "keyword": keyword,
                    "extracted_from_text": sentence[:220],
                    "source_excerpt": sentence[:220],
                    "source_field": "文本段落",
                }
                if source_page:
                    props["source_page"] = source_page
                    props["source_location"] = f"第{source_page}页，文本段落"
                props.update(_parse_common_properties(sentence))
                objects.append(
                    DesignObject(
                        id=f"{Path(filename).stem}-text-{obj_index}",
                        type=obj_type,
                        name=name,
                        properties=props,
                        source=filename,
                    )
                )
    return objects


def _objects_from_xlsx_text(filename: str, text: str) -> list[DesignObject]:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    delimiter = "\t" if "\t" in lines[0] else ","
    return _objects_from_table(filename, "\n".join(lines), delimiter=delimiter)


def _docx_text(raw: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    xml = re.sub(r"<w:tab\s*/>", "\t", xml)
    xml = re.sub(r"</w:p>", "\n", xml)
    return unescape(re.sub(r"<[^>]+>", "", xml))


def _xlsx_text(raw: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            xml = zf.read("xl/sharedStrings.xml").decode("utf-8", errors="replace")
            shared = [unescape(re.sub(r"<[^>]+>", "", item)) for item in re.findall(r"<si.*?</si>", xml, flags=re.S)]
        sheets = [name for name in zf.namelist() if name.startswith("xl/worksheets/sheet")]
        rows = []
        for sheet in sheets[:3]:
            xml = zf.read(sheet).decode("utf-8", errors="replace")
            for row_xml in re.findall(r"<row.*?</row>", xml, flags=re.S):
                cells = []
                for cell_xml in re.findall(r"<c([^>]*)>(.*?)</c>", row_xml, flags=re.S):
                    attrs, inner = cell_xml
                    match = re.search(r"<v>(.*?)</v>", inner)
                    value = match.group(1) if match else ""
                    if 't="s"' in attrs and value.isdigit() and int(value) < len(shared):
                        value = shared[int(value)]
                    cells.append(value)
                if cells:
                    rows.append(",".join(cells))
        return "\n".join(rows)


def _pdf_text(raw: bytes) -> str:
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("PDF对象抽取需要安装 pymupdf") from exc

    with fitz.open(stream=raw, filetype="pdf") as doc:
        pages = [f"{PDF_PAGE_MARKER}{index}\n{page.get_text('text')}" for index, page in enumerate(doc, start=1)]
    return "\n".join(pages)


def _lines_with_pages(text: str) -> tuple[list[str], dict[int, int]]:
    lines: list[str] = []
    pages: dict[int, int] = {}
    current_page: int | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        marker_page = _page_number_from_marker(line)
        if marker_page:
            current_page = marker_page
            continue
        lines.append(line)
        if current_page:
            pages[len(lines) - 1] = current_page
    return lines, pages


def _split_sentences_with_pages(text: str) -> list[tuple[str, int | None]]:
    items: list[tuple[str, int | None]] = []
    current_page: int | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        marker_page = _page_number_from_marker(line)
        if marker_page:
            current_page = marker_page
            continue
        for sentence in _split_sentences(line):
            items.append((sentence, current_page))
    return items


def _page_number_from_marker(line: str) -> int | None:
    if not line.startswith(PDF_PAGE_MARKER):
        return None
    value = line.removeprefix(PDF_PAGE_MARKER).strip()
    return int(value) if value.isdigit() else None


def _compact_source_excerpt(parts: list[str]) -> str:
    text = "；".join(str(part).strip() for part in parts if str(part).strip())
    text = re.sub(r"\s+", " ", text)
    return text[:260]


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text


def _looks_like_object_name(line: str) -> bool:
    if not line or len(line) > 32:
        return False
    if line in {"序号", "设计对象", "数量", "建议位置或范围", "主要参数", "检查项", "常见问题"}:
        return False
    return _type_from_text(line) != "unknown"


def _looks_like_quantity(line: str) -> bool:
    return bool(re.fullmatch(r"约?\s*\d+(?:\.\d+)?\s*(?:km|m|米|公里|处|台|个|条|座|芯|孔|套)", line, flags=re.I))


def _parse_quantity(text: str) -> dict[str, Any]:
    match = re.search(r"约?\s*(\d+(?:\.\d+)?)\s*(km|m|米|公里|处|台|个|条|座|芯|孔|套)", text, flags=re.I)
    if not match:
        return {"quantity_text": text}
    value = float(match.group(1))
    unit = match.group(2).lower()
    props: dict[str, Any] = {"quantity": value, "quantity_unit": unit, "quantity_text": text}
    if unit in {"km", "公里"}:
        props["planned_length_m"] = value * 1000
    elif unit in {"m", "米"}:
        props["planned_length_m"] = value
    return props


def _parse_common_properties(text: str) -> dict[str, Any]:
    props: dict[str, Any] = {}
    core_counts = re.findall(r"(\d+)\s*芯", text)
    if core_counts:
        props["core_count_options"] = [int(item) for item in core_counts]
        props["core_count"] = max(props["core_count_options"])
    capacity = re.search(r"容量[为按约不少于]*\s*(\d+)", text)
    if capacity:
        props["capacity"] = int(capacity.group(1))
    voltage = re.search(r"(\d+(?:\.\d+)?)\s*kV", text, flags=re.I)
    if voltage:
        voltage_kv = float(voltage.group(1))
        props["voltage_kv"] = voltage_kv
        props.setdefault("voltage_band", _voltage_band(voltage_kv))
    distance = re.search(r"(\d+(?:\.\d+)?)\s*(km|m|米|公里)", text, flags=re.I)
    if distance:
        unit = distance.group(2).lower()
        value = float(distance.group(1))
        props["distance_text"] = distance.group(0)
        props["distance_m"] = value * 1000 if unit in {"km", "公里"} else value
    if body_current := re.search(r"人体电流(?:估算|约|为|是|：|:)?\s*(\d+(?:\.\d+)?)\s*mA", text, flags=re.I):
        props["body_current_ma"] = float(body_current.group(1))
    if normal_emf := re.search(r"(?:正常(?:运行)?(?:时)?(?:的)?(?:纵向?|纵)?电动势|正常(?:运行)?纵电动势|纵电动势)(?:约|为|是|：|:)?\s*(\d+(?:\.\d+)?)\s*V", text, flags=re.I):
        props["longitudinal_emf_v_normal"] = float(normal_emf.group(1))
    if fault_emf := re.search(r"(?:故障(?:时)?(?:的)?(?:纵向?|纵)?电动势|故障(?:运行)?纵电动势)(?:约|为|是|：|:)?\s*(\d+(?:\.\d+)?)\s*V", text, flags=re.I):
        props["longitudinal_emf_v_fault"] = float(fault_emf.group(1))
    if live_distance := re.search(r"距(?:离)?(?:邻近|附近|周边)?(?:\d+(?:\.\d+)?\s*kV)?(?:带电体|带电导体|带电线路|导体)(?:约|为|是|：|:)?\s*(\d+(?:\.\d+)?)\s*(m|米)", text, flags=re.I):
        props["distance_to_live_conductor_m"] = float(live_distance.group(1))
    if zone_distance := re.search(r"距(?:离)?(?:爆炸)?危险区入口(?:内侧|外侧)?(?:约|为|是|：|:)?\s*(\d+(?:\.\d+)?)\s*(m|米)", text, flags=re.I):
        props["distance_to_zone_entry_m"] = float(zone_distance.group(1))
    if discharge := re.search(r"(?:标称|峰值)?(?:放电电流|冲击电流)(?:约|为|是|：|:)?\s*(\d+(?:\.\d+)?)\s*kA", text, flags=re.I):
        props["peak_discharge_current_ka"] = float(discharge.group(1))
    if bonding := re.search(r"(?:连接|接地|等电位|铜)?(?:导体|导线|连接线)(?:截面|面积)?(?:约|为|是|：|:)?\s*(\d+(?:\.\d+)?)\s*(?:mm2|mm²|平方毫米)", text, flags=re.I):
        props["bonding_conductor_mm2"] = float(bonding.group(1))
    return props


def _voltage_band(voltage_kv: float) -> str:
    if voltage_kv <= 10:
        return "<=10"
    if 20 <= voltage_kv <= 35:
        return "20-35"
    if 66 <= voltage_kv <= 110:
        return "66-110"
    if voltage_kv == 220:
        return "220"
    if voltage_kv == 330:
        return "330"
    if voltage_kv == 500:
        return "500"
    return f"{voltage_kv:g}"


def _type_from_text(text: str) -> str:
    text = str(text or "").strip()
    for obj_type, keywords in TEXT_OBJECT_PATTERNS:
        if any(keyword in text for keyword in keywords):
            return obj_type
    return TYPE_ALIASES.get(text, "unknown")


def _extract_name_around_keyword(sentence: str, keyword: str) -> str:
    clean = sentence.strip(" ，。；;:：、")
    if len(clean) <= 24:
        return clean
    patterns = [
        rf"([\u4e00-\u9fa5A-Za-z0-9#\-（）()、]{{0,12}}{re.escape(keyword)}[\u4e00-\u9fa5A-Za-z0-9#\-（）()]{{0,8}})",
        rf"({re.escape(keyword)}[\u4e00-\u9fa5A-Za-z0-9#\-（）()]{{0,12}})",
    ]
    for pattern in patterns:
        match = re.search(pattern, clean)
        if match:
            name = match.group(1).strip(" ，。；;:：、")
            name = re.sub(r"^(采用|设置|配置|新建|既有|外部|通过|进入|对于|涉及|完成|核对|资料|本工程拟为|本工程设置|园区)", "", name)
            name = re.sub(r"约?\d+(?:\.\d+)?\s*(?:km|m|米|公里|处|台|个|条|座|芯|孔|套).*$", "", name, flags=re.I)
            name = re.sub(r"约?\d.*$", "", name)
            name = re.sub(r"[一二三四五六七八九十百千万]+(?:处|台|个|条|座|套)$", "", name)
            return name or keyword
    return keyword


def _split_sentences(text: str) -> list[str]:
    logical_lines = [line.strip() for line in text.splitlines() if line.strip()]
    chunks: list[str] = []
    buffer = ""
    for line in logical_lines:
        if _looks_like_object_name(line):
            if buffer:
                chunks.extend(_split_sentence_text(buffer))
                buffer = ""
            chunks.append(line)
            continue
        if len(line) <= 16 and line in {"项目名称", "建设地点", "建设单位", "设计阶段", "编制日期", "文档说明"}:
            continue
        buffer += line
        if re.search(r"[。；;]$", line):
            chunks.extend(_split_sentence_text(buffer))
            buffer = ""
    if buffer:
        chunks.extend(_split_sentence_text(buffer))
    return [chunk for chunk in chunks if chunk]


def _split_sentence_text(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[。；;])", text) if item.strip()]


def _dedupe_objects(objects: list[DesignObject]) -> list[DesignObject]:
    seen: set[tuple[str, str]] = set()
    deduped: list[DesignObject] = []
    for obj in objects:
        name = re.sub(r"\s+", "", obj.name or "")
        if not name:
            continue
        key = (obj.type, name)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(obj)
    return deduped


def _first_present(data: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None
