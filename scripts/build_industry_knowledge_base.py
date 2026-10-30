from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fitz
except ImportError:  # pragma: no cover - script dependency guard
    fitz = None


ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "行业标准"
TEXT_DIR = ROOT / "data" / "extracted_standards_text"
KB_DIR = ROOT / "data" / "knowledge_base"
STANDARDS_DIR = ROOT / "data" / "standards"
RULE_FILE = STANDARDS_DIR / "industry_standards_subtopic3_rules.json"
CATALOG_FILE = KB_DIR / "industry_standards_catalog.json"
CLAUSE_INDEX_FILE = KB_DIR / "industry_standard_clause_index.json"


STANDARD_META: dict[str, dict[str, str]] = {
    "工业企业厂内铁路、道路运输安装规程.pdf": {
        "standard_id": "GB-4387-2008",
        "standard_name": "工业企业厂内铁路、道路运输安全规程",
        "version": "GB 4387-2008",
        "relevance": "high",
    },
    "标准轨距铁路限界第二部分：建筑限界.pdf": {
        "standard_id": "GB-146.2-2020",
        "standard_name": "标准轨距铁路限界 第2部分：建筑限界",
        "version": "GB 146.2-2020",
        "relevance": "high",
    },
    "架空电力线路与调幅广播收音台的防护间距.pdf": {
        "standard_id": "GB-7495-1987",
        "standard_name": "架空电力线路与调幅广播收音台的防护间距",
        "version": "GB 7495-87",
        "relevance": "high",
    },
    "电信线路遭受强电线路危险影响的容许值.pdf": {
        "standard_id": "GB-6830-1986",
        "standard_name": "电信线路遭受强电线路危险影响的容许值",
        "version": "GB 6830-86",
        "relevance": "high",
    },
    "电力安全工作规程 电力线路部分.pdf": {
        "standard_id": "GB-26859-2011",
        "standard_name": "电力安全工作规程 电力线路部分",
        "version": "GB 26859-2011",
        "relevance": "high",
    },
    "系统接地的型式及安全技术要求.pdf": {
        "standard_id": "GB-14050-2008",
        "standard_name": "系统接地的型式及安全技术要求",
        "version": "GB 14050-2008",
        "relevance": "medium",
    },
    "爆炸性环境 第15部分：电气装置设计、选型、安装规范.pdf": {
        "standard_id": "GB-3836.15-2024",
        "standard_name": "爆炸性环境 第15部分：电气装置设计、选型、安装规范",
        "version": "GB 3836.15-2024",
        "relevance": "medium",
    },
    "隧道防火保护板.pdf": {
        "standard_id": "GB-28376-2012",
        "standard_name": "隧道防火保护板",
        "version": "GB 28376-2012",
        "relevance": "medium",
    },
    "煤矿低浓度瓦斯管道输送安全保障系统设计规范.pdf": {
        "standard_id": "GB-40881-2021",
        "standard_name": "煤矿低浓度瓦斯管道输送安全保障系统设计规范",
        "version": "GB 40881-2021",
        "relevance": "medium",
    },
    "施工升降机安全规程.pdf": {
        "standard_id": "GB-10055-2007",
        "standard_name": "施工升降机安全规程",
        "version": "GB 10055-2007",
        "relevance": "low",
    },
}


def stable_id(*parts: str) -> str:
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()


def clause(
    standard_id: str,
    standard_name: str,
    version: str,
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
    confidence: str = "medium",
) -> dict[str, Any]:
    return {
        "id": stable_id(standard_id, clause_id, title),
        "standard_id": standard_id,
        "standard_name": standard_name,
        "version": version,
        "is_placeholder": False,
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
        "rules": rules or [{"id": f"{standard_id}-{clause_id}-manual", "type": "manual_review", "params": {}}],
    }


def rule(rule_id: str, rule_type: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"id": rule_id, "type": rule_type, "params": params}


def min_distance_rule(
    rule_id: str,
    left_type: str,
    right_type: str,
    threshold_m: float,
    left_filters: dict[str, Any] | None = None,
    right_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return rule(
        rule_id,
        "min_distance",
        {
            "object_types": [
                {"type": left_type, "filters": left_filters or {}},
                {"type": right_type, "filters": right_filters or {}},
            ],
            "threshold_m": threshold_m,
        },
    )


def min_property_rule(
    rule_id: str,
    object_type: str,
    prop: str,
    threshold: float,
    unit: str = "",
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return rule(
        rule_id,
        "min_property",
        {"object_type": object_type, "property": prop, "threshold": threshold, "unit": unit, "filters": filters or {}},
    )


def max_property_rule(
    rule_id: str,
    object_type: str,
    prop: str,
    threshold: float,
    unit: str = "",
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return rule(
        rule_id,
        "max_property",
        {"object_type": object_type, "property": prop, "threshold": threshold, "unit": unit, "filters": filters or {}},
    )


def required_properties_rule(rule_id: str, object_type: str, properties: list[str]) -> dict[str, Any]:
    return rule(rule_id, "required_properties", {"object_type": object_type, "properties": properties})


def build_curated_clauses() -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []

    def meta(filename: str) -> tuple[str, str, str]:
        item = STANDARD_META[filename]
        return item["standard_id"], item["standard_name"], item["version"]

    filename = "工业企业厂内铁路、道路运输安装规程.pdf"
    sid, name, version = meta(filename)
    clauses.extend(
        [
            clause(
                sid,
                name,
                version,
                "4.2",
                "厂内铁路和道路建筑限界不得被侵入",
                "厂内建（构）筑物、设备和绿化物严禁侵入铁路线路和道路的建筑限界，并不得妨碍视线。",
                ["building", "equipment", "vegetation", "railway", "road"],
                "通信设施、管道、机柜、临时堆料或绿化物邻近厂内铁路/道路时，复核是否侵入限界或遮挡视线。",
                "high",
                "调整设施位置或清除侵限物；未拆除前设置有效安全措施和侵限警告标志。",
                [
                    required_properties_rule(
                        "GB4387-4.2-GAUGE-CHECK",
                        "railway_adjacent_object",
                        ["gauge_intrusion_checked", "sightline_checked", "mitigation_desc"],
                    )
                ],
                filename,
                "4.2 厂内建（构）筑物、设备和绿化物严禁侵入铁路线路和道路的建筑限界，并不得妨碍视线。",
            ),
            clause(
                sid,
                name,
                version,
                "4.9-4.10",
                "邻近运输线路施工和跨越敷设需审批并防护",
                "原有线路改造、邻近路基施工、跨越铁路线路和道路敷设电线、管道等设施时，必须事先经总图管理和运输部门批准；附近施工不得侵入限界。",
                ["construction_activity", "cable_route", "pipeline", "railway", "road"],
                "通信光缆、电缆、管道需要横穿或邻近厂内铁路、道路、路基、桥梁时。",
                "high",
                "补充审批记录、施工防护方案、限界复核结论和现场警示措施。",
                [
                    required_properties_rule(
                        "GB4387-4.9-APPROVAL-PROPS",
                        "construction_activity",
                        ["transport_department_approval", "protective_measure_desc", "gauge_check_result"],
                    )
                ],
                filename,
                "4.9 跨越铁路线路和道路或横穿路基和桥梁敷设电线、管道等设施时，必须事先经工厂总图管理和运输部门批准。",
            ),
            clause(
                sid,
                name,
                version,
                "5.1.2",
                "铁路路基边线外1m内禁止开挖取土蓄水",
                "厂内铁路线路路基在路堤护道边线外、路堑天沟边线外和平地侧沟边线外1m以内，严禁挖沟、蓄水、取土。",
                ["excavation", "railway_roadbed"],
                "通信管沟、顶管工作井、临时排水或土方工程靠近厂内铁路路基时。",
                "high",
                "避让路基保护范围；确需施工时应调整方案并取得专项审批。",
                [min_distance_rule("GB4387-5.1.2-ROADBED-1M", "excavation", "railway_roadbed", 1.0)],
                filename,
                "5.1.2 厂内铁路线路路基在路堤护道边线外、路堑天沟边线外和平地侧沟边线外1m以内，严禁挖沟、蓄水、取土。",
            ),
            clause(
                sid,
                name,
                version,
                "5.2.3",
                "通信、信号架空线最低点净空要求",
                "通信、信号架空线弛度最低点至地面/路面/钢轨顶面的距离应满足区间3m、站内3.5m、跨越道路5.5m、跨越铁路7m。",
                ["overhead_communication_line", "road", "railway"],
                "通信或信号架空线经过厂区、站内、道路或铁路上方时。",
                "high",
                "提高架设高度、改为地下敷设或调整跨越点，并复核最大弛度工况。",
                [
                    min_property_rule("GB4387-5.2.3-SECTION-3M", "overhead_communication_line", "clearance_m", 3.0, "m", {"location": "section"}),
                    min_property_rule("GB4387-5.2.3-STATION-3.5M", "overhead_communication_line", "clearance_m", 3.5, "m", {"location": "station"}),
                    min_property_rule("GB4387-5.2.3-ROAD-5.5M", "overhead_communication_line", "clearance_m", 5.5, "m", {"crossing_type": "road"}),
                    min_property_rule("GB4387-5.2.3-RAIL-7M", "overhead_communication_line", "clearance_m", 7.0, "m", {"crossing_type": "railway"}),
                ],
                filename,
                "5.2.3 通信、信号架空线弛度最低点：区间距地面不少于3m，站内不少于3.5m，跨越道路不小于5.5m，跨越铁路距钢轨顶面不小于7m。",
            ),
            clause(
                sid,
                name,
                version,
                "5.2.4",
                "电力线路与铁路接近或交叉距离",
                "电力线路接近、平行或跨越铁路时，电杆/塔与铁路中心线、导线最低点与钢轨顶面应满足最小距离。",
                ["power_line", "railway"],
                "通信工程涉及电力线路、铁路、通信线路三者共廊或交叉时，作为外部风险源约束。",
                "high",
                "调整电力/通信线路交叉位置，补充铁路与电力专业复核，必要时采用地下穿越。",
                [
                    min_property_rule("GB4387-5.2.4-POLE-UNDER10KV-3M", "power_line", "pole_to_rail_center_m", 3.0, "m", {"voltage_band": "<10"}),
                    min_property_rule("GB4387-5.2.4-CROSS-POLE-5M", "power_line", "pole_to_rail_center_m", 5.0, "m", {"crossing_type": "railway"}),
                    min_property_rule("GB4387-5.2.4-CROSS-110KV-7.5M", "power_line", "rail_crossing_vertical_clearance_m", 7.5, "m", {"voltage_band": "<=110"}),
                    min_property_rule("GB4387-5.2.4-CROSS-220KV-8.5M", "power_line", "rail_crossing_vertical_clearance_m", 8.5, "m", {"voltage_band": "154-220"}),
                    min_property_rule("GB4387-5.2.4-CROSS-330KV-9.5M", "power_line", "rail_crossing_vertical_clearance_m", 9.5, "m", {"voltage_band": "330"}),
                ],
                filename,
                "5.2.4 电力线路跨越铁路时，电杆内侧距铁路中心线不小于5m；导线最低点距钢轨顶面：110kV及以下不小于7.5m，154kV～220kV不小于8.5m，330kV不小于9.5m。",
            ),
            clause(
                sid,
                name,
                version,
                "5.3.4",
                "铁路通信光电缆埋设地点需设置警示保护标志",
                "铁路信号、通信光电（缆）埋设铺设地点，应按标准设置易于识别的警示保护标志。",
                ["railway_communication_cable", "fiber_cable"],
                "铁路沿线、厂内铁路附近敷设通信光缆或信号电缆。",
                "medium",
                "补充标石、警示牌、电子标识或竣工资料中的标志设置说明。",
                [required_properties_rule("GB4387-5.3.4-MARKER", "railway_communication_cable", ["warning_marker", "marker_desc"])],
                filename,
                "5.3.4 铁路信号、通信光电（缆）埋设铺设地点，铁路运输企业应按标准设置易于识别的警示保护标志。",
            ),
            clause(
                sid,
                name,
                version,
                "5.4.2",
                "铁路道口交叉角和两侧水平路段要求",
                "道路与铁路平面交叉一般应正交；受地形限制斜交时交叉角一般不小于45°；道口两侧从钢轨外侧算起各应有不小于16m水平路段。",
                ["railway_road_crossing"],
                "通信管线、道路改造或施工便道与铁路平面交叉处。",
                "medium",
                "优化交叉角和道口两侧线形；不满足时应专项论证并补充防护措施。",
                [
                    min_property_rule("GB4387-5.4.2-ANGLE-45", "railway_road_crossing", "crossing_angle_deg", 45, "deg"),
                    min_property_rule("GB4387-5.4.2-LEVEL-16M", "railway_road_crossing", "approach_level_length_m", 16, "m"),
                ],
                filename,
                "5.4.2 道路与铁路平面交叉，一般设计为正交；必须斜交时交叉角一般不小于45°；道口两侧各应有不小于16m的水平路段。",
            ),
        ]
    )

    filename = "标准轨距铁路限界第二部分：建筑限界.pdf"
    sid, name, version = meta(filename)
    clauses.extend(
        [
            clause(
                sid,
                name,
                version,
                "2.1-3.4",
                "铁路建筑限界侵入复核",
                "建筑限界为与线路中心线垂直的极限横断面轮廓，除规定设备外，其他设备或建筑物均不得侵入；曲线部分应按规定加宽。",
                ["railway_adjacent_object", "fiber_cable", "pipeline", "cabinet", "building"],
                "通信机柜、管线、桥架、标志杆、监控设备等布设在标准轨距铁路限界附近时。",
                "high",
                "按铁路建筑限界图和曲线加宽要求进行断面复核，侵限对象应迁改或专项审批。",
                [required_properties_rule("GB146.2-2.1-GAUGE-PROPS", "railway_adjacent_object", ["gauge_profile_checked", "curve_widening_checked"])],
                filename,
                "2.1 此轮廓内，除机车车辆和相关设备外，其他设备或建筑物均不得侵入；3.3 曲线部分相邻线路中心距离以及线路中心线至建筑物间的扩大距离应按规定计算。",
            ),
            clause(
                sid,
                name,
                version,
                "4.1.1-4.2.2",
                "电力牵引区段跨线桥、天桥、隧道最小高度",
                "适用于电力牵引区段的跨线桥、天桥、雨棚及隧道建筑限界，最大高度根据接触网结构高度计算确定，最小不应小于6550mm。",
                ["railway_overpass", "railway_tunnel", "bridge", "tunnel"],
                "通信桥架、管线或设备依附铁路跨线桥、隧道、天桥等结构布设时。",
                "high",
                "核对结构净高和接触网结构高度，低于限值时调整路由或结构方案。",
                [
                    min_property_rule("GB146.2-4.1-OVERPASS-6.55M", "railway_overpass", "clearance_height_m", 6.55, "m"),
                    min_property_rule("GB146.2-4.2-TUNNEL-6.55M", "railway_tunnel", "clearance_height_m", 6.55, "m"),
                ],
                filename,
                "图1/图4说明：适用于电力牵引区段的跨线桥、天桥及隧道建筑限界，最大高度根据接触网结构高度计算确定，最小不应小于6550mm。",
            ),
        ]
    )

    filename = "架空电力线路与调幅广播收音台的防护间距.pdf"
    sid, name, version = meta(filename)
    receiver_distances = {
        "1": {"35": 600, "63-110": 800, "220-330": 1000, "500": 1200},
        "2": {"35": 300, "63-110": 500, "220-330": 700, "500": 900},
        "3": {"35": 100, "63-110": 300, "220-330": 400, "500": 500},
    }
    monitoring_distances = {
        "1": {"35": 1000, "63-110": 1400, "220-330": 1600, "500": 2000},
        "2": {"35": 600, "63-110": 600, "220-330": 800, "500": 1000},
        "3": {"35": 100, "63-110": 300, "220-330": 400, "500": 500},
    }
    clauses.append(
        clause(
            sid,
            name,
            version,
            "3.1",
            "架空电力线路与调幅广播收音台防护间距",
            "不同电压等级架空电力线路与各级调幅广播收音台之间的防护间距应符合表1。",
            ["am_broadcast_station", "power_line"],
            "通信线路或基站选址靠近调幅广播收音台及架空电力线路时，用于识别电磁干扰外部约束。",
            "medium",
            "优先调整路由或站址；确有困难时按标准附录采取降低干扰或迁移天线等措施并专项论证。",
            [
                min_distance_rule(
                    f"GB7495-3.1-RX-L{level}-{voltage}",
                    "am_broadcast_station",
                    "power_line",
                    distance,
                    {"station_role": "receiver", "station_level": level},
                    {"voltage_band": voltage},
                )
                for level, voltage_map in receiver_distances.items()
                for voltage, distance in voltage_map.items()
            ],
            filename,
            "3.1 表1：一级台在35/63-110/220-330/500kV下防护间距为600/800/1000/1200m；二级台为300/500/700/900m；三级台为100/300/400/500m。",
        )
    )
    clauses.append(
        clause(
            sid,
            name,
            version,
            "3.2",
            "架空电力线路与监测台（站）防护间距",
            "不同电压等级架空电力线路与各级监测台（站）的防护间距应符合表2。",
            ["am_broadcast_station", "power_line"],
            "通信工程设施、广播监测台和架空电力线路同域布局时。",
            "medium",
            "站址与线路距离不足时，调整站址/线路或开展电磁干扰专项计算。",
            [
                min_distance_rule(
                    f"GB7495-3.2-MON-L{level}-{voltage}",
                    "am_broadcast_station",
                    "power_line",
                    distance,
                    {"station_role": "monitoring", "station_level": level},
                    {"voltage_band": voltage},
                )
                for level, voltage_map in monitoring_distances.items()
                for voltage, distance in voltage_map.items()
            ],
            filename,
            "3.2 表2：一级监测台在35/63-110/220-330/500kV下防护间距为1000/1400/1600/2000m；二级为600/600/800/1000m；三级为100/300/400/500m。",
        )
    )
    clauses.append(
        clause(
            sid,
            name,
            version,
            "A.1-A.2",
            "防护间距不足时的防护措施",
            "满足表1规定的防护间距确有困难时，可采取控制无线电干扰电平、保护导线金具绝缘子、改变电力线路路径、改进或迁移收音台天线等措施。",
            ["power_line", "am_broadcast_station"],
            "距离不足但工程受限，需要技术经济比较和部门协商时。",
            "medium",
            "形成专项计算、协商记录和防护措施清单，不得仅以经验说明替代。",
            [required_properties_rule("GB7495-A-PROTECTION", "power_line", ["emi_assessment", "protective_measure_desc"])],
            filename,
            "附录A：通过合理设计降低无线电干扰电平、保护导线金具和绝缘子、改变线路路径；广播部门可改进天线或迁移收音台。",
        )
    )

    filename = "电信线路遭受强电线路危险影响的容许值.pdf"
    sid, name, version = meta(filename)
    clauses.extend(
        [
            clause(
                sid,
                name,
                version,
                "2",
                "电感应引起的人体电流容许值",
                "在特定强电线路故障及正常运行状态下，人体碰触邻近通信导线时，由电感应引起的流经人体电流容许值为15mA（有效值）。",
                ["telecom_line", "power_line"],
                "通信明线、电缆或广播明线邻近交流电力线、电气铁道接触网等强电线路时。",
                "high",
                "开展强电影响计算，必要时增加屏蔽、接地、改用光缆或增设增音站等保护措施。",
                [max_property_rule("GB6830-2-BODY-CURRENT-15MA", "telecom_line", "body_current_ma", 15, "mA")],
                filename,
                "第2章：由电感应引起的流经人体的电流容许值为15mA（有效值）。",
            ),
            clause(
                sid,
                name,
                version,
                "3.1",
                "电信明线线路故障状态危险纵电动势容许值",
                "强电线路故障状态下，通信导线上的纵电动势容许值一般为430V；强电线路为高可靠电力线时为650V。",
                ["telecom_line", "power_line"],
                "电信明线与强电线路接近、平行或交叉，并可能受故障短路影响时。",
                "high",
                "若超过容许值，应优先调整间距、屏蔽、接地或改用光缆，并复核故障电流持续时间。",
                [
                    max_property_rule("GB6830-3.1-EMF-430V", "telecom_line", "longitudinal_emf_v_fault", 430, "V", {"power_line_reliability": "general"}),
                    max_property_rule("GB6830-3.1-EMF-650V", "telecom_line", "longitudinal_emf_v_fault", 650, "V", {"power_line_reliability": "reliable"}),
                ],
                filename,
                "3.1.1 通信导线上的纵电动势容许值为430V；3.1.2 强电线路为高可靠电力线时，通信导线上的纵电动势容许值为650V。",
            ),
            clause(
                sid,
                name,
                version,
                "3.2-4.2",
                "强电线路正常运行状态纵电动势容许值",
                "强电线路正常运行状态下，通信导线或电缆芯线上的纵电动势容许值为60V。",
                ["telecom_line", "telecom_cable", "power_line"],
                "通信明线或电缆邻近正常运行的交流电力线、交流电气铁道接触网时。",
                "high",
                "补充感应电压计算；超过60V时采取增距、屏蔽、接地、改用电缆/光缆等措施。",
                [
                    max_property_rule("GB6830-3.2-WIRE-NORMAL-60V", "telecom_line", "longitudinal_emf_v_normal", 60, "V"),
                    max_property_rule("GB6830-4.2-CABLE-NORMAL-60V", "telecom_cable", "longitudinal_emf_v_normal", 60, "V"),
                ],
                filename,
                "3.2 通信导线上的纵电动势容许值为60V；4.2 电缆芯线上的纵电动势容许值为60V。",
            ),
            clause(
                sid,
                name,
                version,
                "5.1-5.2",
                "危险影响超限时的防护措施",
                "当纵电动势和对地电压值超过容许值时，应从强电线路和电信线路两方面采取经济有效的保护措施。",
                ["telecom_line", "telecom_cable", "power_line"],
                "通信线路与强电线路危险影响评估结果超限或资料缺失时。",
                "high",
                "强电侧可增设屏蔽、限制短路电流、快速切断故障电流；电信侧可增距、迁改、改电缆/屏蔽电缆、采用光纤电缆、增设增音站或保护变压器。",
                [required_properties_rule("GB6830-5-PROTECTION-PROPS", "telecom_line", ["danger_influence_assessment", "protective_measure_desc"])],
                filename,
                "5.1 选择强电线路时应与电信线路保持合理间距；5.2 可加大距离、迁移电信线路、将架空明线改为电缆、采用光纤电缆等。",
            ),
        ]
    )

    filename = "电力安全工作规程 电力线路部分.pdf"
    sid, name, version = meta(filename)
    table1 = {"<=10": 0.7, "20-35": 1.0, "66-110": 1.5, "220": 3.0, "330": 4.0, "500": 5.0}
    table4 = {"<=10": 1.0, "20-35": 2.5, "66-110": 3.0, "220": 4.0, "330": 5.0, "500": 6.0}
    table5 = {"<1": 1.5, "1-10": 3.0, "35-66": 4.0, "110": 5.0, "220": 6.0, "330": 7.0, "500": 8.5}
    clauses.extend(
        [
            clause(
                sid,
                name,
                version,
                "5.3.2 表1",
                "带电线路杆塔作业最小安全距离",
                "带电线路杆塔上工作与带电导线应满足表1最小安全距离。",
                ["power_line_work"],
                "通信工程需在电力杆塔、同杆多回路或邻近带电导线处施工时。",
                "high",
                "距离不足时不得按普通停电/第二种工作票作业，应转为带电作业方案或停电隔离。",
                [
                    min_property_rule(f"GB26859-T1-{voltage}", "power_line_work", "distance_to_live_conductor_m", distance, "m", {"voltage_band": voltage})
                    for voltage, distance in table1.items()
                ],
                filename,
                "表1：10kV及以下0.7m，20/35kV 1.0m，66/110kV 1.5m，220kV 3.0m，330kV 4.0m，500kV 5.0m。",
            ),
            clause(
                sid,
                name,
                version,
                "7.5 表4",
                "邻近或交叉其他电力线工作安全距离",
                "砍剪靠近带电线路树木、锚固杆塔维修线路等邻近或交叉其他电力线工作，应满足表4安全距离。",
                ["near_power_line_work", "construction_activity"],
                "通信线路跨越、平行或临近其他电力线施工，或树障清理、拉线锚固作业。",
                "high",
                "距离不足时应停电、隔离或调整施工方法，不得直接接触可能带电对象。",
                [
                    min_property_rule(f"GB26859-T4-{voltage}", "near_power_line_work", "distance_to_power_line_m", distance, "m", {"voltage_band": voltage})
                    for voltage, distance in table4.items()
                ],
                filename,
                "表4：10kV及以下1.0m，20/35kV 2.5m，66/110kV 3.0m，220kV 4.0m，330kV 5.0m，500kV 6.0m。",
            ),
            clause(
                sid,
                name,
                version,
                "9.5 表5",
                "立撤杆等施工与架空输电线最小安全距离",
                "杆塔、拉线、临时拉线与架空输电线及其他带电体的最小安全距离应符合表5。",
                ["construction_activity", "power_line"],
                "通信杆塔立撤、吊装、拉线施工或大型机械邻近架空输电线时。",
                "high",
                "按电压等级设置施工控制线和警戒范围，距离不足时停电或调整施工组织。",
                [
                    min_property_rule(
                        f"GB26859-T5-{voltage}",
                        "construction_activity",
                        "distance_to_overhead_power_line_m",
                        distance,
                        "m",
                        {"voltage_band": voltage},
                    )
                    for voltage, distance in table5.items()
                ],
                filename,
                "表5：<1kV为1.5m，1~10kV为3.0m，35~66kV为4.0m，110kV为5.0m，220kV为6.0m，330kV为7.0m，500kV为8.5m。",
            ),
            clause(
                sid,
                name,
                version,
                "6.4.3-6.4.8",
                "验电后装设接地线及接地线截面要求",
                "线路验明确无电压后应立即装设接地线并三相短路；成套接地线截面不应小于25mm²并满足短路电流要求。",
                ["temporary_grounding_wire", "power_line_work"],
                "通信工程需要进入电力线路作业区或与停电电力线路联合施工时。",
                "high",
                "补充验电、接地线规格、接地顺序和现场确认记录；截面不足应更换合格接地线。",
                [
                    min_property_rule("GB26859-6.4-GROUND-WIRE-25", "temporary_grounding_wire", "cross_section_mm2", 25, "mm2"),
                    required_properties_rule("GB26859-6.4-GROUNDING-PROPS", "power_line_work", ["voltage_checked", "grounding_installed", "worker_confirmation"]),
                ],
                filename,
                "6.4.3 线路经验明确无电压后，应立即装设接地线并三相短路；6.4.6 接地线截面不应小于25mm²。",
            ),
        ]
    )

    filename = "系统接地的型式及安全技术要求.pdf"
    sid, name, version = meta(filename)
    clauses.extend(
        [
            clause(
                sid,
                name,
                version,
                "5.1.1-5.1.3",
                "接地系统自动切断、保护导体和等电位联结要求",
                "当发生故障时保护电器应自动切断故障部分供电，避免超过交流50V的预期接触电压持续存在；外露可导电部分应接入同一接地系统，并尽量实施总等电位联结。",
                ["electrical_installation", "equipment_room", "grounding_system"],
                "通信机房、室外机柜、供电系统、接地网和防雷接地设计。",
                "high",
                "核对接地型式、保护导体连续性、等电位联结和自动切断条件；无法满足时增设RCD或等电位措施。",
                [
                    max_property_rule("GB14050-5.1-TOUCH-50V", "electrical_installation", "expected_touch_voltage_v", 50, "V"),
                    required_properties_rule("GB14050-5.1-BONDING", "grounding_system", ["main_equipotential_bonding", "protective_conductor_continuity"]),
                ],
                filename,
                "5.1.1 一个超过交流50V的预期接触电压不应持续存在到足以对人体产生危险；5.1.2 系统中应尽量实施总等电位联结。",
            ),
            clause(
                sid,
                name,
                version,
                "5.1.5-5.1.9",
                "保护导体禁止事项和电气连续性",
                "不得在保护导体回路中装设保护电器和开关；严禁将煤气管道、金属构件用作保护导体；连接保护导体或PEN导体时必须保证良好的电气连续性。",
                ["grounding_system", "protective_conductor"],
                "通信接地、机房接地、机柜保护接地和PEN/PE导体设计审核。",
                "high",
                "补充保护导体路径、截面、连接方式、禁止替代材料和连续性测试记录。",
                [
                    required_properties_rule(
                        "GB14050-5.1-PE-PROPS",
                        "protective_conductor",
                        ["conductor_spec", "continuity_test_result", "no_switch_in_pe", "not_using_gas_pipe"],
                    )
                ],
                filename,
                "5.1.5 不得在保护导体回路中装设保护电器和开关；5.1.6 严禁将煤气管道、金属构件用作保护导体；5.1.9 必须保证良好的电气连续性。",
            ),
            clause(
                sid,
                name,
                version,
                "5.2.2-5.3.2",
                "TN/TT系统自动切断条件",
                "TN系统应满足Zs·Ia≤U0；TT系统应满足RA·Ia≤50V，以保证保护电器在规定时间内自动切断供电。",
                ["grounding_system", "electrical_installation"],
                "通信供配电、接地型式选择和保护电器整定审核。",
                "medium",
                "按接地型式提交阻抗、电流、接地电阻和保护动作时间计算书。",
                [
                    rule("GB14050-5.2-TN-FORMULA", "manual_review", {"formula": "Zs * Ia <= U0", "system_type": "TN"}),
                    rule("GB14050-5.3-TT-FORMULA", "manual_review", {"formula": "RA * Ia <= 50V", "system_type": "TT"}),
                ],
                filename,
                "5.2.2 TN系统保护条件：Zs·Ia≤U0；5.3.2 TT系统保护条件：RA·Ia≤50V。",
            ),
        ]
    )

    filename = "爆炸性环境 第15部分：电气装置设计、选型、安装规范.pdf"
    sid, name, version = meta(filename)
    clauses.extend(
        [
            clause(
                sid,
                name,
                version,
                "7.3.1.4.3",
                "本质安全电路电感电容参数限制",
                "本质安全电路中所有连接装置和任何电缆的总电感、总电容应小于或等于电源的Lo和Co。",
                ["intrinsically_safe_circuit", "cable"],
                "通信监测、传感、控制电缆进入爆炸性危险场所时。",
                "high",
                "提交本质安全系统描述文件，计算总电感/电容并核对设备类别、温度组别和保护等级。",
                [
                    rule(
                        "GB3836.15-7.3.1.4.3-LOCO",
                        "manual_review",
                        {"checks": ["sum_Li_and_cable_inductance <= Lo", "sum_Ci_and_cable_capacitance <= Co"]},
                    )
                ],
                filename,
                "7.3.1.4.3 系统中所有连接的装置和任何电缆的总电感和电容应小于或等于电源的Lo和Co。",
            ),
            clause(
                sid,
                name,
                version,
                "7.3.2",
                "EPL Ga/Da场所本质安全电路和电涌保护要求",
                "要求EPL Ga/Da级场所内的本质安全装置、关联装置和互连电缆应为ia等级；存在危险电位差风险时，电涌保护器应接近场所入口，且能转移最小10kA峰值放电电流。",
                ["intrinsically_safe_circuit", "surge_protector", "hazardous_area"],
                "通信传感、监控电缆进入石化、燃气、煤矿等爆炸危险区域时。",
                "high",
                "采用ia等级本质安全回路，入口处设置合格电涌保护器并提供接地连接截面证明。",
                [
                    max_property_rule("GB3836.15-7.3.2-SPD-DIST-1M", "surge_protector", "distance_to_zone_entry_m", 1.0, "m"),
                    min_property_rule("GB3836.15-7.3.2-SPD-10KA", "surge_protector", "peak_discharge_current_ka", 10.0, "kA"),
                    min_property_rule("GB3836.15-7.3.2-SPD-CU-4MM2", "surge_protector", "bonding_conductor_mm2", 4.0, "mm2"),
                    required_properties_rule("GB3836.15-7.3.2-IA", "intrinsically_safe_circuit", ["epl_level", "protection_level", "isolation_desc"]),
                ],
                filename,
                "7.3.2 在要求EPLGa级的场所安装本质安全电路时，电路应为ia等级；电涌保护器应合理地接近入口（例如1m范围内），峰值放电电流最小10kA，连接铜导体截面积至少4mm²。",
            ),
            clause(
                sid,
                name,
                version,
                "7.3.4",
                "本质安全接线盒防护等级和端子间距",
                "本质安全接线盒通常需要至少IP54外壳；本质安全端子与接地部件间距至少3mm；独立本质安全电路之间至少6mm；本质安全与非本质安全裸露导电部件之间至少50mm。",
                ["junction_box", "intrinsically_safe_circuit"],
                "通信接线盒、传感器箱、仪表箱安装在爆炸危险场所或连接本质安全回路时。",
                "high",
                "核对外壳IP等级、端子标识、端子间距、防爆认证及带电开盖警示。",
                [
                    min_property_rule("GB3836.15-7.3.4-IS-GROUND-3MM", "junction_box", "is_terminal_to_ground_clearance_mm", 3, "mm"),
                    min_property_rule("GB3836.15-7.3.4-IS-IS-6MM", "junction_box", "is_circuit_clearance_mm", 6, "mm"),
                    min_property_rule("GB3836.15-7.3.4-IS-NONIS-50MM", "junction_box", "is_to_non_is_clearance_mm", 50, "mm"),
                    required_properties_rule("GB3836.15-7.3.4-IP54", "junction_box", ["ip_rating", "terminal_marking", "explosion_protection_cert"]),
                ],
                filename,
                "7.3.4 接线盒通常需要至少IP54外壳；本质安全接线端子与接地部件之间至少3mm；独立本质安全电路之间至少6mm；本质安全与非本质安全电路之间至少50mm。",
            ),
        ]
    )

    filename = "隧道防火保护板.pdf"
    sid, name, version = meta(filename)
    clauses.extend(
        [
            clause(
                sid,
                name,
                version,
                "5.1-5.10",
                "隧道防火保护板外观、尺寸和理化性能",
                "隧道防火保护板应无裂纹、分层等缺陷；长宽厚不宜超过3000mm/1250mm/70mm；面密度不应超过25kg/m²；干态抗弯强度不低于6MPa；吸湿变形率不大于0.20%。",
                ["tunnel_fireproof_board"],
                "通信线缆、桥架或设备穿越隧道并使用防火保护板封护时。",
                "medium",
                "核对产品检验报告、规格尺寸、安装方式和材料性能。",
                [
                    max_property_rule("GB28376-5.2-LENGTH", "tunnel_fireproof_board", "length_mm", 3000, "mm"),
                    max_property_rule("GB28376-5.2-WIDTH", "tunnel_fireproof_board", "width_mm", 1250, "mm"),
                    max_property_rule("GB28376-5.2-THICKNESS", "tunnel_fireproof_board", "thickness_mm", 70, "mm"),
                    max_property_rule("GB28376-5.3-DENSITY", "tunnel_fireproof_board", "area_density_kg_m2", 25, "kg/m2"),
                    min_property_rule("GB28376-5.5-BENDING", "tunnel_fireproof_board", "dry_bending_strength_mpa", 6, "MPa"),
                    max_property_rule("GB28376-5.7-DEFORMATION", "tunnel_fireproof_board", "moisture_deformation_rate", 0.20, "%"),
                ],
                filename,
                "5.2 板材长不宜超过3000mm、宽不宜超过1250mm、厚度不宜超过70mm；5.3 面密度不应超过25kg/m²；5.5 干态抗弯强度不低于6MPa。",
            ),
            clause(
                sid,
                name,
                version,
                "5.16-5.18",
                "隧道防火保护板燃烧、吸水和耐火性能",
                "板材燃烧增长速率指数不大于250W/s，600s内总热释放量不大于15MJ，焰尖高度不大于150mm，吸水率不大于12.0%，耐火性能应满足表3。",
                ["tunnel_fireproof_board"],
                "通信设施隧道防火封护材料选型与验收。",
                "medium",
                "补充燃烧性能、吸水率、耐火极限型式检验报告，按隧道场景选择耐火曲线。",
                [
                    max_property_rule("GB28376-5.16-FIGRA", "tunnel_fireproof_board", "figra_w_s", 250, "W/s"),
                    max_property_rule("GB28376-5.16-THR600", "tunnel_fireproof_board", "thr600_mj", 15, "MJ"),
                    max_property_rule("GB28376-5.16-FS", "tunnel_fireproof_board", "flame_tip_height_mm", 150, "mm"),
                    max_property_rule("GB28376-5.17-WATER", "tunnel_fireproof_board", "water_absorption_rate", 12.0, "%"),
                    required_properties_rule("GB28376-5.18-FIRE-REPORT", "tunnel_fireproof_board", ["fire_resistance_report", "temperature_curve_type"]),
                ],
                filename,
                "表2：FIGRA0.4MJ≤250W/s，THR600s≤15MJ，焰尖高度≤150mm；5.17 吸水率不大于12.0%；5.18 耐火性能应满足表3。",
            ),
            clause(
                sid,
                name,
                version,
                "8.1-8.4",
                "隧道防火保护板标志、包装、运输和存放",
                "产品标志应注明生产厂、产品名称、规格、执行标准等；包装应防雨防潮并附合格证和说明书；运输防雨淋，存放通风干燥。",
                ["tunnel_fireproof_board"],
                "防火保护板采购、进场验收和现场存放。",
                "low",
                "补充产品标志、合格证、说明书和现场存放检查记录。",
                [required_properties_rule("GB28376-8-MARK-PACK", "tunnel_fireproof_board", ["product_mark", "certificate", "storage_condition"])],
                filename,
                "8.1 产品标志应注明生产厂名称、产品名称、型号规格、执行标准代号等；8.2 包装应防雨、防潮，并附合格证和说明书。",
            ),
        ]
    )

    filename = "煤矿低浓度瓦斯管道输送安全保障系统设计规范.pdf"
    sid, name, version = meta(filename)
    clauses.append(
        clause(
            sid,
            name,
            version,
            "人工复核",
            "瓦斯管道输送安全保障系统人工复核",
            "该PDF可抽文本质量较低，已纳入知识库目录。涉及通信设施邻近煤矿低浓度瓦斯管道、放散、防爆、防雷和防静电接地时，应按原文进行人工/OCR复核。",
            ["gas_pipeline", "communication_facility", "hazardous_area"],
            "通信光缆、设备箱、监测电缆与煤矿瓦斯输送系统同沟、交叉或近距离布设。",
            "high",
            "补充OCR文本或标准原文页码，重点复核防爆、防雷、防静电接地、管道泄漏和安全距离要求。",
            [required_properties_rule("GB40881-MANUAL-GAS", "gas_pipeline_adjacent_work", ["ocr_review_done", "explosion_protection_desc", "lightning_static_grounding_desc"])],
            filename,
            "PDF文本层乱码较多；目录和局部条款显示涉及低浓度瓦斯管道输送、安全保障系统、防雷防静电接地等内容。",
            "low",
        )
    )

    filename = "施工升降机安全规程.pdf"
    sid, name, version = meta(filename)
    clauses.append(
        clause(
            sid,
            name,
            version,
            "人工复核",
            "施工升降机邻近通信线路作业安全人工复核",
            "该PDF文本层质量较低，且与通信线路设计审查关联度较低。若通信施工与施工升降机安装、运行、拆卸区域交叉，应按原文进行机械安全和临边防护复核。",
            ["construction_hoist", "construction_activity", "fiber_cable"],
            "通信工程施工现场与施工升降机设备运行范围交叉或邻近。",
            "medium",
            "补充施工组织设计、机械设备合格资料、危险区域隔离和高处坠落/物体打击防护措施。",
            [required_properties_rule("GB10055-MANUAL-HOIST", "construction_activity", ["hoist_interference_checked", "site_isolation_desc"])],
            filename,
            "施工升降机安全规程已纳入目录；当前抽取文本乱码，适合作为人工复核类知识条目。",
            "low",
        )
    )

    return clauses


def extract_pdf_texts() -> list[dict[str, Any]]:
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    catalog = []
    for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
        meta = STANDARD_META.get(pdf_path.name, {})
        text = ""
        pages = 0
        if fitz is not None:
            doc = fitz.open(pdf_path)
            pages = len(doc)
            parts = []
            for index, page in enumerate(doc, start=1):
                page_text = page.get_text("text") or ""
                if page_text.strip():
                    parts.append(f"\n\n===== Page {index} =====\n{page_text}")
            text = "".join(parts)
            (TEXT_DIR / f"{pdf_path.stem}.txt").write_text(text, encoding="utf-8")
        catalog.append(
            {
                "file": pdf_path.name,
                "standard_id": meta.get("standard_id", pdf_path.stem),
                "standard_name": meta.get("standard_name", pdf_path.stem),
                "version": meta.get("version", ""),
                "relevance_to_subtopic3": meta.get("relevance", "unknown"),
                "pages": pages,
                "text_length": len(text),
                "text_path": str((TEXT_DIR / f"{pdf_path.stem}.txt").relative_to(ROOT)).replace("\\", "/"),
                "extraction_status": "text_extracted" if text.strip() else "image_or_unreadable_text_layer",
            }
        )
    return catalog


def main() -> None:
    KB_DIR.mkdir(parents=True, exist_ok=True)
    STANDARDS_DIR.mkdir(parents=True, exist_ok=True)

    catalog = extract_pdf_texts()
    clauses = build_curated_clauses()
    counts: dict[str, int] = {}
    for item in clauses:
        counts[item["source_file"]] = counts.get(item["source_file"], 0) + 1
    for item in catalog:
        item["curated_clause_count"] = counts.get(item["file"], 0)

    standard_doc = {
        "source_file": "行业标准/*.pdf",
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "parser": {
            "provider": "local_pdf_extraction_plus_curated_rules",
            "notes": "Rules are curated from extracted PDF text and rendered-image review for PDFs without text layers.",
        },
        "clauses": clauses,
    }
    clause_index = [
        {
            "id": item["id"],
            "standard_id": item["standard_id"],
            "standard_name": item["standard_name"],
            "version": item["version"],
            "clause_id": item["clause_id"],
            "title": item["title"],
            "summary": item["summary"],
            "applicable_objects": item["applicable_objects"],
            "risk_level": item["risk_level"],
            "rule_types": sorted({rule_item["type"] for rule_item in item["rules"]}),
            "source_file": item["source_file"],
            "source_excerpt": item["source_excerpt"],
            "confidence": item["confidence"],
        }
        for item in clauses
    ]

    CATALOG_FILE.write_text(json.dumps({"items": catalog}, ensure_ascii=False, indent=2), encoding="utf-8")
    CLAUSE_INDEX_FILE.write_text(json.dumps({"items": clause_index}, ensure_ascii=False, indent=2), encoding="utf-8")
    RULE_FILE.write_text(json.dumps(standard_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {CATALOG_FILE.relative_to(ROOT)}")
    print(f"Wrote {CLAUSE_INDEX_FILE.relative_to(ROOT)}")
    print(f"Wrote {RULE_FILE.relative_to(ROOT)}")
    print(f"Curated clauses: {len(clauses)}")


if __name__ == "__main__":
    main()
