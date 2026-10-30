from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fitz
except ImportError:  # pragma: no cover
    fitz = None


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
GERMAN_DIR = ROOT / "德国行业标准"
CHINA_DIR = ROOT / "中国行业标准"
TEST_DIR = ROOT / "test" / "PushPK_Dreieich Mitte_Handwerk"
DATA_DIR = ROOT / "data"
STANDARDS_DIR = DATA_DIR / "standards"
KB_DIR = DATA_DIR / "knowledge_base"
TEXT_DIR = DATA_DIR / "extracted_standards_text"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def rule(rule_id: str, rule_type: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"id": rule_id, "type": rule_type, "params": params}


def clause(
    standard_id: str,
    standard_name: str,
    clause_id: str,
    title: str,
    summary: str,
    applicable_objects: list[str],
    scenario: str,
    risk_level: str,
    recommendation: str,
    rules: list[dict[str, Any]],
    source_file: str,
    source_excerpt: str,
    version: str = "",
    confidence: str = "medium",
    is_placeholder: bool = False,
) -> dict[str, Any]:
    return {
        "id": stable_id(standard_id, clause_id, title),
        "standard_id": standard_id,
        "standard_name": standard_name,
        "version": version,
        "is_placeholder": is_placeholder,
        "clause_id": clause_id,
        "title": title,
        "summary": summary,
        "applicable_objects": applicable_objects,
        "scenario": scenario,
        "risk_level": risk_level,
        "recommendation": recommendation,
        "source_file": source_file,
        "source_excerpt": source_excerpt,
        "confidence": confidence,
        "rules": rules or [rule(f"{standard_id}-{clause_id}-manual", "manual_review", {})],
    }


def required(
    rule_id: str,
    object_type: str,
    properties: list[str],
    filters: dict[str, Any] | None = None,
    max_findings: int | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"object_type": object_type, "properties": properties, "filters": filters or {}}
    if max_findings:
        params["max_findings"] = max_findings
    return rule(rule_id, "required_properties", params)


def required_any(rule_id: str, object_type: str, properties: list[str], max_findings: int | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"object_type": object_type, "properties": properties}
    if max_findings:
        params["max_findings"] = max_findings
    return rule(rule_id, "required_any_property", params)


def min_prop(rule_id: str, object_type: str, prop: str, threshold: float, unit: str = "", max_findings: int | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"object_type": object_type, "property": prop, "threshold": threshold, "unit": unit}
    if max_findings:
        params["max_findings"] = max_findings
    return rule(rule_id, "min_property", params)


def allowed(rule_id: str, object_type: str, prop: str, values: list[str]) -> dict[str, Any]:
    return rule(rule_id, "allowed_values", {"object_type": object_type, "property": prop, "values": values})


def collect_standard_sources() -> tuple[list[dict[str, Any]], dict[str, str]]:
    sources: list[dict[str, Any]] = []
    texts: dict[str, str] = {}

    german_pdfs = sorted(GERMAN_DIR.glob("*.pdf"))
    china_pdfs: list[Path] = []
    for subdir in sorted(CHINA_DIR.iterdir() if CHINA_DIR.exists() else []):
        if subdir.is_dir() and re.match(r"0[1-3]", subdir.name):
            china_pdfs.extend(sorted(subdir.glob("*.pdf")))

    for path in german_pdfs:
        role = "rule_instruction" if path.name.startswith("00") else "de_standard"
        item, text = extract_pdf(path, "germany", role)
        sources.append(item)
        texts[path.name] = text

    for path in china_pdfs:
        item, text = extract_pdf(path, "china", "cn_standard")
        sources.append(item)
        texts[path.name] = text

    return sources, texts


def extract_pdf(path: Path, region: str, role: str) -> tuple[dict[str, Any], str]:
    output_dir = TEXT_DIR / region
    output_dir.mkdir(parents=True, exist_ok=True)
    text = ""
    pages = 0
    if fitz is not None:
        with fitz.open(path) as doc:
            pages = len(doc)
            parts = []
            for index, page in enumerate(doc, start=1):
                page_text = page.get_text("text") or ""
                if page_text.strip():
                    parts.append(f"\n\n===== Page {index} =====\n{page_text.strip()}")
            text = "\n".join(parts)
    text_path = output_dir / f"{path.stem}.txt"
    text_path.write_text(text, encoding="utf-8")
    return (
        {
            "file": path.name,
            "region": region,
            "role": role,
            "pages": pages,
            "text_length": len(text),
            "source_path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "text_path": str(text_path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "extraction_status": "text_extracted" if text.strip() else "image_or_unreadable_text_layer",
        },
        text,
    )


def build_project_profile() -> dict[str, Any]:
    profile: dict[str, Any] = {
        "project_name": "PushPK_Dreieich Mitte_Handwerk",
        "source_dir": str(TEST_DIR.relative_to(ROOT)).replace("\\", "/"),
        "generated_at": now_iso(),
        "layers": [],
        "semantic_type_counts": {},
        "field_dictionary": {},
    }
    try:
        import geopandas as gpd
        import pyogrio
        from review_system.extractors import extract_design_objects
    except Exception as exc:
        profile["error"] = f"geopandas/pyogrio unavailable: {exc}"
        return profile

    semantic_counter: Counter[str] = Counter()
    field_dictionary: dict[str, dict[str, Any]] = {}
    for gpkg in sorted(TEST_DIR.glob("*.gpkg")):
        for layer in [item[0] for item in pyogrio.list_layers(gpkg)]:
            layer_info: dict[str, Any] = {"file": gpkg.name, "layer": layer, "count": 0, "columns": [], "geometry_types": []}
            try:
                frame = gpd.read_file(gpkg, layer=layer)
                objects = extract_design_objects(gpkg.name, gpkg.read_bytes())
            except Exception as exc:
                layer_info["error"] = str(exc)
                profile["layers"].append(layer_info)
                continue
            layer_info["count"] = len(frame)
            layer_info["columns"] = [str(col) for col in frame.columns]
            if "geometry" in frame:
                layer_info["geometry_types"] = sorted({str(value) for value in frame.geometry.geom_type.dropna()})
            type_counts = Counter(obj.type for obj in objects if (obj.properties or {}).get("source_layer") == layer)
            if not type_counts and objects:
                type_counts = Counter(obj.type for obj in objects)
            layer_info["semantic_type_counts"] = dict(type_counts)
            semantic_counter.update(type_counts)
            for col in frame.columns:
                if col == "geometry":
                    continue
                key = f"{layer}.{col}"
                series = frame[col].dropna()
                samples = [str(value) for value in series.astype(str).unique()[:12]]
                field_dictionary[key] = {
                    "non_null_count": int(series.shape[0]),
                    "sample_values": samples,
                }
            profile["layers"].append(layer_info)
    profile["semantic_type_counts"] = dict(semantic_counter)
    profile["field_dictionary"] = field_dictionary
    return profile


def build_general_gis_rules() -> list[dict[str, Any]]:
    source = "系统内置：通用GIS数据质量规则"
    return [
        clause(
            "GIS-DQ",
            "通用GIS数据质量规则",
            "DQ-01",
            "关键GIS对象必须具备空间几何",
            "参与审查的工程对象应包含可解析的空间几何，否则无法计算距离、相交、包含和穿越关系。",
            ["*"],
            "所有从 GIS 成果读取的点、线、面对象。",
            "high",
            "补齐或修复缺失的几何，并确认上传文件包含完整图层。",
            [
                rule("GIS-DQ-01-ROUTES", "required_geometry", {"object_type": "telecom_duct_route", "geometry_types": ["LineString", "MultiLineString"]}),
                rule("GIS-DQ-01-UTILITIES", "required_geometry", {"object_type": "third_party_utility"}),
                rule("GIS-DQ-01-AREA", "required_geometry", {"object_type": "project_area", "geometry_types": ["Polygon", "MultiPolygon"]}),
                rule("GIS-DQ-01-NODES", "required_geometry", {"object_type": "fiber_distribution_cabinet", "geometry_types": ["Point", "MultiPoint"]}),
                rule("GIS-DQ-01-PIT", "required_geometry", {"object_type": "civil_pit_work", "geometry_types": ["Point", "MultiPoint"]}),
            ],
            source,
            "通用GIS数据质量要求：图层要素必须具备可解析几何。",
        ),
        clause(
            "GIS-DQ",
            "通用GIS数据质量规则",
            "DQ-02",
            "空间几何必须有效",
            "几何自相交、空几何或不可解析几何会导致空间分析结果不可靠。",
            ["*"],
            "所有带几何的 GIS 要素。",
            "medium",
            "在 QGIS/GeoPandas 中修复无效几何后重新上传。",
            [rule("GIS-DQ-02-VALIDITY", "geometry_validity", {"object_type": "*"})],
            source,
            "通用GIS数据质量要求：几何对象应满足有效性检查。",
        ),
        clause(
            "GIS-DQ",
            "通用GIS数据质量规则",
            "DQ-03",
            "工程范围图层必须存在",
            "工程范围或施工范围是后续空间适用性判断的边界依据。",
            ["project_area"],
            "德国测试项目中的 Bereich 图层和类似工程范围图层。",
            "medium",
            "补充项目边界、NVT/HK 工作区边界或红线范围图层。",
            [rule("GIS-DQ-03-AREA-COUNT", "min_feature_count", {"object_type": "project_area", "min_count": 1})],
            source,
            "通用GIS数据质量要求：工程范围图层至少应有一个面对象。",
        ),
        clause(
            "GIS-DQ",
            "通用GIS数据质量规则",
            "DQ-04",
            "抽取来源字段必须保留",
            "每个对象应保留来源文件、来源图层和来源要素ID，便于风险回溯到 GIS 成果。",
            ["*"],
            "所有由 GeoPandas/Pyogrio 读取的对象。",
            "medium",
            "保留 source_file、source_layer、source_feature_id 等抽取溯源字段。",
            [required("GIS-DQ-04-SOURCE", "*", ["source_file", "source_layer", "source_feature_id"])],
            source,
            "通用GIS数据质量要求：风险应可定位到来源图层与要素。",
        ),
    ]


def build_project_business_rules() -> list[dict[str, Any]]:
    source = "test/PushPK_Dreieich Mitte_Handwerk 官方GIS输入数据"
    return [
        clause(
            "PROJECT-DREIEICH",
            "Dreieich 光纤项目数据与业务规则",
            "PB-01",
            "管道/微管路由应保留区域、施工方式和长度信息",
            "Pipes 图层是本项目光纤管道和微管敷设的主线性成果，缺失区域、施工方式、长度或管孔数量会影响材料统计和审查。",
            ["telecom_duct_route"],
            "Pipes.gpkg/Pipes 图层。",
            "high",
            "补齐 HK_Area、NVT_Area、Bauweisen、Length、Pipe_Summe 等字段。",
            [required("PROJECT-DREIEICH-PB01-PIPES", "telecom_duct_route", ["HK_Area", "NVT_Area", "Bauweisen", "Length", "Pipe_Summe"], max_findings=80)],
            source,
            "Pipes 图层字段包括 HK_Area、NVT_Area、Bauweisen、Length、Pipe_Summe、Gräbensbreite、Gräbenstief 等。",
        ),
        clause(
            "PROJECT-DREIEICH",
            "Dreieich 光纤项目数据与业务规则",
            "PB-02",
            "管道应至少配置一种管孔或空管资源",
            "路由对象需要说明使用的 SNR/空管/微管资源，否则无法判断容量与材料方案。",
            ["telecom_duct_route"],
            "Pipes.gpkg/Pipes 图层中 SNRVe、SNR、Leerrohr 等资源字段。",
            "medium",
            "至少填写 SNRVe_7x12、SNRVe_22x7、SNR_1x7、SNR_1x10 或 Leerrohr 中的一项。",
            [required_any("PROJECT-DREIEICH-PB02-PIPE-RESOURCE", "telecom_duct_route", ["SNRVe_7x12", "SNRVe_22x7", "SNR_1x7", "SNR_1x10", "Leerrohr"])],
            source,
            "Pipes 图层包含 SNRVe_7x12、SNRVe_22x7、SNR_1x7、SNR_1x10、Leerrohr 等资源字段。",
        ),
        clause(
            "PROJECT-DREIEICH",
            "Dreieich 光纤项目数据与业务规则",
            "PB-03",
            "沟槽深度和宽度应满足项目最小记录要求",
            "沟槽深度和宽度是道路开挖、材料回填和竣工测量的关键参数，缺失或为0时需要复核。",
            ["telecom_duct_route"],
            "Pipes.gpkg/Pipes 图层中的 Gräbenstief 与 Gräbensbreite。",
            "high",
            "补充沟槽深度/宽度，或说明该段为非开挖、既有管孔利用等特殊施工方式。",
            [
                min_prop("PROJECT-DREIEICH-PB03-DEPTH", "telecom_duct_route", "Gräbenstief", 0.45, "m", max_findings=80),
                min_prop("PROJECT-DREIEICH-PB03-WIDTH", "telecom_duct_route", "Gräbensbreite", 0.15, "m", max_findings=80),
            ],
            source,
            "Pipes 图层样例显示 Gräbenstief 包含 0、0.45、0.6、0.8 等值，Gräbensbreite 包含 0、0.15、0.3 等值。",
        ),
        clause(
            "PROJECT-DREIEICH",
            "Dreieich 光纤项目数据与业务规则",
            "PB-04",
            "施工坑点应具备尺寸、深度、表面和施工方式信息",
            "PitWork 图层用于记录开挖坑位，缺失尺寸和深度会影响工程量和安全复核。",
            ["civil_pit_work"],
            "PitWork.gpkg/PitWork 图层。",
            "high",
            "补齐 Length、Width、Depth、Surface、Bauweisen 字段。",
            [
                required("PROJECT-DREIEICH-PB04-PIT-FIELDS", "civil_pit_work", ["Length", "Width", "Depth", "Surface", "Bauweisen"], max_findings=80),
                min_prop("PROJECT-DREIEICH-PB04-PIT-DEPTH", "civil_pit_work", "Depth", 0.5, "m", max_findings=80),
            ],
            source,
            "PitWork 图层字段包括 Length、Width、Depth、Surface、Bauweisen、Subco、Foto1 等。",
        ),
        clause(
            "PROJECT-DREIEICH",
            "Dreieich 光纤项目数据与业务规则",
            "PB-05",
            "地址点应保留可回访的门牌与施工状态信息",
            "Address 图层是入户接入、客户侧施工和开通状态的基础，缺失地址字段会影响业务闭环。",
            ["address_point"],
            "Address.gpkg/address 图层。",
            "medium",
            "补齐 Straße、Haus_Nr、PLZ、NVT_Area、HK_Area、Status_Tiefbau、Status_Kabel 等字段。",
            [required("PROJECT-DREIEICH-PB05-ADDRESS", "address_point", ["Straße", "Haus_Nr", "PLZ", "NVT_Area", "HK_Area", "Status_Tiefbau", "Status_Kabel"], max_findings=80)],
            source,
            "Address 图层字段包括 Straße、Haus_Nr、PLZ、NVT_Area、HK_Area、Status_Tiefbau、Status_Kabel。",
        ),
        clause(
            "PROJECT-DREIEICH",
            "Dreieich 光纤项目数据与业务规则",
            "PB-06",
            "交叉第三方管线的路由应具备穿越说明或文档记录",
            "当拟建通信管道与燃气、电力、给水、排水或既有通信管线发生空间交叉时，应能回溯施工保护或文档说明。",
            ["telecom_duct_route", "gas_pipeline", "power_line", "water_pipeline", "sewer_pipeline", "existing_telecom_line"],
            "Pipes 与 Fremdleitung 图层发生空间交叉或重叠。",
            "high",
            "补充 Dokumentation、Kommentar 或专项穿越保护说明，并在 QGIS 中标注交叉位置。",
            [
                rule(
                    "PROJECT-DREIEICH-PB06-CROSS-GAS",
                    "crossing_requires_properties",
                    {"object_types": ["telecom_duct_route", "gas_pipeline"], "properties": ["Dokumentation", "Kommentar"], "max_findings": 40},
                ),
                rule(
                    "PROJECT-DREIEICH-PB06-CROSS-POWER",
                    "crossing_requires_properties",
                    {"object_types": ["telecom_duct_route", "power_line"], "properties": ["Dokumentation", "Kommentar"], "max_findings": 40},
                ),
            ],
            source,
            "Fremdleitung 图层 Class 包含 Gas、Strom、Wasser、Kanal、TK；Pipes 图层包含 Dokumentation、Kommentar。",
        ),
    ]


def build_standards_rules(sources: list[dict[str, Any]], texts: dict[str, str]) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    german_standards = [item for item in sources if item["role"] == "de_standard"]
    china_standards = [item for item in sources if item["role"] == "cn_standard"]

    curated_by_file: dict[str, list[dict[str, Any]]] = {
        "01_德赖艾希市道路开挖规则_Aufgrabungsrichtlinie_2014.pdf": [
            clause(
                "DE-AUFGRABUNG",
                "德赖艾希市道路开挖规则",
                "DE-01",
                "道路开挖段应记录沟槽尺寸和恢复材料",
                "道路开挖相关路由应保留沟槽深度、宽度、表层材料和承载层材料，便于审查开挖与恢复质量。",
                ["telecom_duct_route", "civil_pit_work"],
                "通信管道位于道路或人行道开挖范围内。",
                "high",
                "补齐沟槽尺寸、路面类型、承载层材料和恢复做法；为非开挖段补充特殊施工说明。",
                [
                    min_prop("DE-AUFGRABUNG-DEPTH", "telecom_duct_route", "Gräbenstief", 0.45, "m", max_findings=80),
                    min_prop("DE-AUFGRABUNG-WIDTH", "telecom_duct_route", "Gräbensbreite", 0.15, "m", max_findings=80),
                    required("DE-AUFGRABUNG-PIT", "civil_pit_work", ["Depth", "Surface", "Tragschicht"], max_findings=80),
                ],
                "德国行业标准/01_德赖艾希市道路开挖规则_Aufgrabungsrichtlinie_2014.pdf",
                excerpt(texts.get("01_德赖艾希市道路开挖规则_Aufgrabungsrichtlinie_2014.pdf", "")),
            )
        ],
        "02_德国宽带资助GIS数据附加规定_GIS-Nebenbestimmungen_V5.1.pdf": [
            clause(
                "DE-GIS-NB",
                "德国宽带资助GIS数据附加规定",
                "DE-02",
                "GIS交付数据应可定位、可追溯、可统计",
                "GIS 成果应保留图层来源、要素ID、区域归属和几何信息，支撑资助项目验收和数据交换。",
                ["*"],
                "德国宽带资助项目 GIS 成果交付。",
                "high",
                "保留 source_layer、source_feature_id、NVT/HK 区域字段，并修复缺失几何。",
                [
                    required("DE-GIS-NB-SOURCE", "*", ["source_file", "source_layer", "source_feature_id"]),
                    rule("DE-GIS-NB-GEOMETRY", "geometry_validity", {"object_type": "*"}),
                ],
                "德国行业标准/02_德国宽带资助GIS数据附加规定_GIS-Nebenbestimmungen_V5.1.pdf",
                excerpt(texts.get("02_德国宽带资助GIS数据附加规定_GIS-Nebenbestimmungen_V5.1.pdf", "")),
            )
        ],
        "03_统一材料与被动基础设施容量方案_Materialkonzept_V5.0.2.pdf": [
            clause(
                "DE-MATERIAL",
                "统一材料与被动基础设施容量方案",
                "DE-03",
                "管孔与微管资源应能支撑材料统计",
                "路由对象应明确管孔、微管和空管资源配置，避免容量和材料统计无法闭合。",
                ["telecom_duct_route"],
                "Pipes 图层中的管孔、微管和空管字段。",
                "medium",
                "补齐 Pipe_Summe、SNRVe/SNR、Leerrohr 等资源字段。",
                [
                    min_prop("DE-MATERIAL-PIPE-SUM", "telecom_duct_route", "Pipe_Summe", 1, "孔", max_findings=80),
                    required_any("DE-MATERIAL-RESOURCE", "telecom_duct_route", ["SNRVe_7x12", "SNRVe_22x7", "SNR_1x7", "SNR_1x10", "Leerrohr"], max_findings=80),
                ],
                "德国行业标准/03_统一材料与被动基础设施容量方案_Materialkonzept_V5.0.2.pdf",
                excerpt(texts.get("03_统一材料与被动基础设施容量方案_Materialkonzept_V5.0.2.pdf", "")),
            )
        ],
        "04_技术设施与施工文档要求_Hinweisblatt_2022.pdf": [
            clause(
                "DE-HINWEISBLATT",
                "技术设施与施工文档要求",
                "DE-04",
                "施工与设施对象应保留照片或文档记录",
                "施工坑点、管道路由和基础设施节点应具备照片或文档记录，支撑现场复核与验收。",
                ["civil_pit_work", "telecom_duct_route", "fiber_distribution_cabinet", "splice_closure"],
                "施工过程、节点安装和管道路由验收。",
                "medium",
                "补充 Foto1/Foto2/Foto3 或 Dokumentation 字段。",
                [
                    required_any("DE-HINWEIS-PIT-PHOTO", "civil_pit_work", ["Foto1", "Foto2", "Foto3"], max_findings=80),
                    required_any("DE-HINWEIS-PIPE-DOC", "telecom_duct_route", ["Dokumentation", "Kommentar"], max_findings=80),
                ],
                "德国行业标准/04_技术设施与施工文档要求_Hinweisblatt_2022.pdf",
                excerpt(texts.get("04_技术设施与施工文档要求_Hinweisblatt_2022.pdf", "")),
            )
        ],
        "05_统一测量方案_Einheitliches_Messkonzept_2022.pdf": [
            clause(
                "DE-MESSKONZEPT",
                "统一测量方案",
                "DE-05",
                "测量线应保留长度和区域归属",
                "测量成果应明确测量长度、计算长度和区域归属，支撑竣工计量。",
                ["surveyed_route"],
                "Einmessung.gpkg/Einmessung 图层。",
                "medium",
                "补齐 Length、C_Length、NVT_Area 字段。",
                [required("DE-MESS-SURVEY", "surveyed_route", ["Length", "C_Length", "NVT_Area"], max_findings=80)],
                "德国行业标准/05_统一测量方案_Einheitliches_Messkonzept_2022.pdf",
                excerpt(texts.get("05_统一测量方案_Einheitliches_Messkonzept_2022.pdf", "")),
            )
        ],
        "06_OEW光纤网络规划与文档指南_V1.1_2025.pdf": [
            clause(
                "DE-OEW",
                "OEW光纤网络规划与文档指南",
                "DE-06",
                "入户连接和配线节点应具备地址与区域信息",
                "入户接入、NVT/HVT、接头盒等节点应保留地址、区域和状态字段，支撑网络规划闭环。",
                ["house_connection", "fiber_distribution_cabinet", "telecom_central_node", "splice_closure"],
                "光纤入户与配线节点规划成果。",
                "medium",
                "补齐地址、NVT/HK 区域和状态信息。",
                [
                    required("DE-OEW-HOUSE", "house_connection", ["Straße", "Haus_Nr", "NVT_Area", "HK_Area"], max_findings=80),
                    required("DE-OEW-INFRA", "fiber_distribution_cabinet", ["NVT_Area", "HK_Area", "Status"], max_findings=80),
                ],
                "德国行业标准/06_OEW光纤网络规划与文档指南_V1.1_2025.pdf",
                excerpt(texts.get("06_OEW光纤网络规划与文档指南_V1.1_2025.pdf", "")),
            )
        ],
        "07_德国电信电缆保护指令_Kabelschutzanweisung_2026.pdf": [
            clause(
                "DE-KABELSCHUTZ",
                "德国电信电缆保护指令",
                "DE-07",
                "与第三方管线交叉应有保护和文档说明",
                "通信管道与燃气、电力、给水等第三方管线交叉时，应具备施工保护、标识或文档记录。",
                ["telecom_duct_route", "gas_pipeline", "power_line", "water_pipeline"],
                "Pipes 与 Fremdleitung 的空间交叉。",
                "high",
                "补充交叉位置、保护措施、审批/协调记录和施工照片。",
                [
                    rule("DE-KABEL-CROSS-GAS", "crossing_requires_properties", {"object_types": ["telecom_duct_route", "gas_pipeline"], "properties": ["Dokumentation", "Kommentar"], "max_findings": 60}),
                    rule("DE-KABEL-CROSS-WATER", "crossing_requires_properties", {"object_types": ["telecom_duct_route", "water_pipeline"], "properties": ["Dokumentation", "Kommentar"], "max_findings": 60}),
                ],
                "德国行业标准/07_德国电信电缆保护指令_Kabelschutzanweisung_2026.pdf",
                excerpt(texts.get("07_德国电信电缆保护指令_Kabelschutzanweisung_2026.pdf", "")),
            )
        ],
        "08_DGUV地下管线附近施工安全指南_203-017_2019.pdf": [
            clause(
                "DE-DGUV-203-017",
                "DGUV地下管线附近施工安全指南",
                "DE-08",
                "地下管线附近施工应保留风险识别和保护措施",
                "靠近第三方地下管线的施工坑点和管道路由应具备风险识别、保护措施或现场记录。",
                ["civil_pit_work", "telecom_duct_route", "gas_pipeline", "power_line", "water_pipeline", "sewer_pipeline"],
                "施工坑点或路由靠近地下管线。",
                "high",
                "补充管线探测、人工试挖、保护距离、施工照片和安全交底记录。",
                [
                    required_any("DE-DGUV-PIT-PHOTO", "civil_pit_work", ["Foto1", "Foto2", "Foto3"], max_findings=80),
                    rule("DE-DGUV-CROSS-POWER", "crossing_requires_properties", {"object_types": ["telecom_duct_route", "power_line"], "properties": ["Dokumentation", "Kommentar"], "max_findings": 60}),
                ],
                "德国行业标准/08_DGUV地下管线附近施工安全指南_203-017_2019.pdf",
                excerpt(texts.get("08_DGUV地下管线附近施工安全指南_203-017_2019.pdf", "")),
            )
        ],
        "09_莱茵美因地下公用管线保护规范_NRM-N-A001_2023.pdf": [
            clause(
                "DE-NRM-N-A001",
                "莱茵美因地下公用管线保护规范",
                "DE-09",
                "第三方公用管线交叉应形成可追溯风险记录",
                "与燃气、电力、给排水等公用管线交叉的设计对象，应能定位交叉点并提供保护或协调资料。",
                ["telecom_duct_route", "gas_pipeline", "power_line", "water_pipeline", "sewer_pipeline"],
                "Fremdleitung 第三方管线与拟建通信管道路由重叠或交叉。",
                "high",
                "输出交叉风险清单，并补充协调记录、保护措施和现场核验信息。",
                [
                    rule("DE-NRM-CROSS-GAS", "crossing_requires_properties", {"object_types": ["telecom_duct_route", "gas_pipeline"], "properties": ["Dokumentation", "Kommentar"], "max_findings": 80}),
                    rule("DE-NRM-CROSS-SEWER", "crossing_requires_properties", {"object_types": ["telecom_duct_route", "sewer_pipeline"], "properties": ["Dokumentation", "Kommentar"], "max_findings": 80}),
                ],
                "德国行业标准/09_莱茵美因地下公用管线保护规范_NRM-N-A001_2023.pdf",
                excerpt(texts.get("09_莱茵美因地下公用管线保护规范_NRM-N-A001_2023.pdf", "")),
            )
        ],
    }

    for item in german_standards:
        clauses.extend(curated_by_file.get(item["file"], []))
        if item["file"] not in curated_by_file:
            clauses.append(manual_standard_clause(item, texts.get(item["file"], "")))

    for item in china_standards:
        clauses.append(china_standard_clause(item, texts.get(item["file"], "")))
    return clauses


def manual_standard_clause(item: dict[str, Any], text: str) -> dict[str, Any]:
    return clause(
        f"STD-{stable_id(item['file'])}",
        Path(item["file"]).stem,
        "MANUAL",
        "标准条文人工复核",
        "该标准已纳入知识库，可用于语义召回和报告引用；可执行规则需后续专家校准。",
        ["*"],
        "当设计对象语义与该标准主题匹配时召回。",
        "medium",
        "结合原文条款进行人工复核，并逐步固化为可计算规则。",
        [rule(f"STD-{stable_id(item['file'])}-MANUAL", "manual_review", {})],
        item["source_path"],
        excerpt(text),
        is_placeholder=True,
    )


def china_standard_clause(item: dict[str, Any], text: str) -> dict[str, Any]:
    name = Path(item["file"]).stem
    rules = [rule(f"CN-{stable_id(item['file'])}-MANUAL", "manual_review", {})]
    applicable = ["telecom_duct_route", "house_connection", "fiber_distribution_cabinet"]
    if "地下管线数据规范" in item["file"]:
        rules = [
            required("CN-PIPELINE-DATA-SOURCE", "*", ["source_file", "source_layer", "source_feature_id"], max_findings=80),
            rule("CN-PIPELINE-DATA-GEOM", "geometry_validity", {"object_type": "*"}),
        ]
        applicable = ["*"]
    elif "通信管道与通道工程设计标准" in item["file"]:
        rules = [
            required("CN-COMM-DUCT-FIELDS", "telecom_duct_route", ["Length", "HK_Area", "NVT_Area"], max_findings=80),
            min_prop("CN-COMM-DUCT-DEPTH", "telecom_duct_route", "Gräbenstief", 0.45, "m", max_findings=80),
        ]
    elif "通信管道工程施工及验收" in item["file"]:
        rules = [required_any("CN-COMM-DUCT-ACCEPTANCE-DOC", "telecom_duct_route", ["Dokumentation", "Kommentar"], max_findings=80)]
    elif "建筑物配建" in item["file"] or "家庭光纤" in item["file"]:
        rules = [required("CN-HOUSE-CONNECTION", "house_connection", ["Straße", "Haus_Nr", "NVT_Area"], max_findings=80)]
        applicable = ["house_connection", "address_point"]
    return clause(
        f"CN-{stable_id(item['file'])}",
        name,
        "CN",
        "中国通信/GIS规范参考规则",
        "该中国规范暂作为补充数据源，用于通信管道、地下管线数据和建筑物配建通信基础设施的参考审查。",
        applicable,
        "德国项目中出现相同或相近对象语义时作为参考规则召回。",
        "medium",
        "优先以德国项目标准为准；中国规范用于补充字段完整性、管线数据质量和通信工程经验检查。",
        rules,
        item["source_path"],
        excerpt(text),
        is_placeholder=False,
    )


def excerpt(text: str, limit: int = 360) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    return clean[:limit] if clean else "PDF文本层为空或需OCR；已纳入目录，后续可结合原文或OCR结果校准。"


def write_standard_doc(filename: str, source_file: str, clauses: list[dict[str, Any]]) -> None:
    write_json(
        STANDARDS_DIR / filename,
        {
            "source_file": source_file,
            "imported_at": now_iso(),
            "parser": {
                "provider": "project_data_source_rebuild",
                "notes": "规则库按 通用GIS数据质量 / 项目业务 / 德国与中国标准规范 三类重建。",
            },
            "clauses": clauses,
        },
    )


def archive_old_standard_docs() -> None:
    STANDARDS_DIR.mkdir(parents=True, exist_ok=True)
    archive_dir = STANDARDS_DIR / "_archive_replaced"
    archive_dir.mkdir(parents=True, exist_ok=True)
    keep = {
        "general_gis_data_quality_rules.json",
        "project_dreieich_business_rules.json",
        "de_cn_standards_technical_rules.json",
    }
    for path in STANDARDS_DIR.glob("*.json"):
        if path.name in keep:
            path.unlink()
            continue
        target = archive_dir / path.name
        if target.exists():
            target = archive_dir / f"{path.stem}-{stable_id(path.read_text(encoding='utf-8', errors='ignore'))}{path.suffix}"
        path.replace(target)


def archive_old_knowledge_artifacts() -> None:
    KB_DIR.mkdir(parents=True, exist_ok=True)
    kb_archive = KB_DIR / "_archive_replaced"
    kb_archive.mkdir(parents=True, exist_ok=True)
    for name in ["industry_standards_catalog.json", "industry_standard_clause_index.json"]:
        path = KB_DIR / name
        if path.exists():
            target = kb_archive / name
            if target.exists():
                target = kb_archive / f"{path.stem}-{stable_id(path.read_text(encoding='utf-8', errors='ignore'))}{path.suffix}"
            path.replace(target)

    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    text_archive = TEXT_DIR / "_archive_replaced"
    text_archive.mkdir(parents=True, exist_ok=True)
    for path in TEXT_DIR.glob("*.txt"):
        target = text_archive / path.name
        if target.exists():
            target = text_archive / f"{path.stem}-{stable_id(path.read_text(encoding='utf-8', errors='ignore'))}{path.suffix}"
        path.replace(target)
    rendered_pages = TEXT_DIR / "rendered_pages"
    if rendered_pages.exists():
        target_dir = text_archive / "rendered_pages"
        if target_dir.exists():
            target_dir = text_archive / f"rendered_pages-{stable_id(str(rendered_pages.stat().st_mtime_ns))}"
        rendered_pages.replace(target_dir)


def build_clause_index(all_clauses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": item["id"],
            "standard_id": item["standard_id"],
            "standard_name": item["standard_name"],
            "version": item.get("version", ""),
            "clause_id": item["clause_id"],
            "title": item["title"],
            "summary": item["summary"],
            "applicable_objects": item["applicable_objects"],
            "risk_level": item["risk_level"],
            "rule_types": sorted({rule_item.get("type", "manual_review") for rule_item in item.get("rules", [])}),
            "source_file": item.get("source_file", ""),
            "source_excerpt": item.get("source_excerpt", ""),
            "confidence": item.get("confidence", "medium"),
        }
        for item in all_clauses
    ]


def main() -> None:
    if not GERMAN_DIR.exists():
        raise FileNotFoundError(f"German standard folder not found: {GERMAN_DIR}")
    if not CHINA_DIR.exists():
        raise FileNotFoundError(f"Chinese standard folder not found: {CHINA_DIR}")

    KB_DIR.mkdir(parents=True, exist_ok=True)
    STANDARDS_DIR.mkdir(parents=True, exist_ok=True)

    sources, texts = collect_standard_sources()
    project_profile = build_project_profile()

    general_rules = build_general_gis_rules()
    project_rules = build_project_business_rules()
    standards_rules = build_standards_rules(sources, texts)
    all_clauses = [*general_rules, *project_rules, *standards_rules]

    archive_old_knowledge_artifacts()
    archive_old_standard_docs()
    write_standard_doc("general_gis_data_quality_rules.json", "系统内置：通用GIS数据质量规则", general_rules)
    write_standard_doc("project_dreieich_business_rules.json", "test/PushPK_Dreieich Mitte_Handwerk", project_rules)
    write_standard_doc("de_cn_standards_technical_rules.json", "德国行业标准/*.pdf + 中国行业标准/01-03/*.pdf", standards_rules)

    standard_counts = defaultdict(int)
    for clause_item in all_clauses:
        standard_counts[clause_item["standard_name"]] += 1
    catalog = {
        "generated_at": now_iso(),
        "source_summary": {
            "german_pdf_count": sum(1 for item in sources if item["region"] == "germany"),
            "german_rule_instruction_count": sum(1 for item in sources if item["role"] == "rule_instruction"),
            "german_standard_pdf_count": sum(1 for item in sources if item["role"] == "de_standard"),
            "china_standard_pdf_count": sum(1 for item in sources if item["role"] == "cn_standard"),
        },
        "sources": sources,
        "rule_documents": [
            "data/standards/general_gis_data_quality_rules.json",
            "data/standards/project_dreieich_business_rules.json",
            "data/standards/de_cn_standards_technical_rules.json",
        ],
        "clause_count_by_standard": dict(standard_counts),
    }
    write_json(KB_DIR / "multinational_standards_catalog.json", catalog)
    write_json(KB_DIR / "multinational_clause_index.json", {"items": build_clause_index(all_clauses)})
    write_json(KB_DIR / "project_dreieich_input_profile.json", project_profile)

    cache_path = KB_DIR / "ollama_clause_embeddings.json"
    if cache_path.exists():
        cache_path.unlink()

    print(f"Sources: {len(sources)} PDFs")
    print(f"Clauses: {len(all_clauses)}")
    print("Wrote data/standards/general_gis_data_quality_rules.json")
    print("Wrote data/standards/project_dreieich_business_rules.json")
    print("Wrote data/standards/de_cn_standards_technical_rules.json")
    print("Wrote data/knowledge_base/multinational_standards_catalog.json")
    print("Wrote data/knowledge_base/project_dreieich_input_profile.json")


if __name__ == "__main__":
    main()
