import type { DesignObject, RiskFinding, RiskLevel } from "@/types";

type TagType = "success" | "warning" | "danger" | "info" | "primary";

export const levelMeta: Record<string, { label: string; type: TagType; color: string }> = {
  high: { label: "高风险", type: "danger", color: "#c0392b" },
  medium: { label: "中风险", type: "warning", color: "#b9770e" },
  low: { label: "低风险", type: "success", color: "#0f766e" },
};

export interface RiskCountSummary {
  total: number;
  high: number;
  medium: number;
  low: number;
  unknown: number;
  [key: string]: number;
}

export function levelLabel(level?: RiskLevel): string {
  return levelMeta[String(level || "")]?.label || "未定级";
}

export function levelType(level?: RiskLevel): TagType {
  return levelMeta[String(level || "")]?.type || "info";
}

export function riskCounts(risks: RiskFinding[] = []): RiskCountSummary {
  return risks.reduce<RiskCountSummary>(
    (acc, risk) => {
      const level = risk.level || "unknown";
      acc.total += 1;
      acc[level] = (acc[level] || 0) + 1;
      return acc;
    },
    { total: 0, high: 0, medium: 0, low: 0, unknown: 0 },
  );
}

export function groupCount<T>(items: T[] = [], getter: (item: T) => string = (item) => String(item)): Record<string, number> {
  return items.reduce<Record<string, number>>((acc, item) => {
    const key = getter(item) || "unknown";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

export function ruleTypeLabel(type?: string): string {
  const labels: Record<string, string> = {
    min_distance: "最小距离",
    min_property: "属性下限",
    max_property: "属性上限",
    required_properties: "属性完整性",
    required_any_property: "至少一项属性",
    allowed_values: "枚举值校验",
    unique_resource: "资源唯一性",
    max_ratio: "比例上限",
    capacity_check: "容量校核",
    topology_connectivity: "拓扑连通",
    required_geometry: "几何必填",
    geometry_validity: "几何有效性",
    min_feature_count: "最少要素数",
    must_be_within: "范围包含",
    forbidden_intersection: "禁止相交",
    crossing_requires_properties: "交叉资料校验",
    manual_review: "人工复核",
  };
  return labels[type || ""] || type || "未知规则";
}

export function objectTypeLabel(type?: string): string {
  const labels: Record<string, string> = {
    fiber_cable: "光缆",
    communication_cable: "通信光缆",
    telecom_cable: "通信电缆",
    telecom_line: "通信线路",
    communication_line: "通信线路",
    overhead_communication_line: "架空通信线路",
    railway_communication_cable: "铁路通信电缆",
    duct: "管道",
    duct_hole: "管孔",
    pipeline: "管线",
    communication_pipeline: "通信管道",
    telecom_duct_route: "通信管道路由",
    water_pipeline: "给水管线",
    gas_pipeline: "燃气管线",
    sewer_pipeline: "排水/污水管线",
    existing_telecom_line: "既有通信管线",
    third_party_utility: "第三方地下管线",
    gas_pipeline_adjacent_work: "燃气管线邻近作业",
    pole: "杆",
    pole_route: "杆路",
    manhole: "人孔/手孔",
    equipment_room: "机房",
    equipment: "设备",
    base_station: "基站",
    fiber_cabinet: "光交箱",
    fiber_distribution_cabinet: "光纤分配柜/NVT",
    telecom_central_node: "通信中心节点/HVT",
    splice_closure: "接头盒",
    telecom_infrastructure_node: "通信基础设施节点",
    communication_facility: "通信设施",
    power_line: "电力线路",
    power_line_work: "近电作业",
    road: "道路",
    building: "建筑物",
    project_boundary: "项目边界",
    project_area: "工程范围",
    redline_correction_area: "红线修正范围",
    forbidden_area: "禁建区",
    protected_area: "保护区",
    hazardous_area: "危险区域",
    railway: "铁路",
    railway_roadbed: "铁路路基",
    tunnel: "隧道",
    tunnel_fireproof_board: "隧道防火板",
    address_point: "地址点",
    house_connection: "入户连接",
    civil_pit_work: "施工坑点",
    surveyed_route: "测量线",
    construction_photo: "施工照片点",
    customer_status_record: "客户状态记录",
    material_reference: "材料参考记录",
    procurement_record: "采购记录",
    site_index_record: "站点索引记录",
  };
  return labels[type || ""] || humanizeObjectType(type) || "未知对象";
}

function humanizeObjectType(type?: string): string {
  if (!type) return "";
  if (/[\u4e00-\u9fa5]/.test(type)) return type;
  const tokenLabels: Record<string, string> = {
    communication: "通信",
    telecom: "通信",
    fiber: "光纤",
    cable: "光缆",
    line: "线路",
    route: "路由",
    overhead: "架空",
    railway: "铁路",
    water: "给水",
    gas: "燃气",
    sewer: "排水",
    pipeline: "管线",
    duct: "管道",
    project: "项目",
    boundary: "边界",
    area: "区域",
    base: "基",
    station: "站",
    manhole: "人孔/手孔",
    equipment: "设备",
    room: "机房",
    power: "电力",
    road: "道路",
    building: "建筑物",
    facility: "设施",
    hazardous: "危险",
    adjacent: "邻近",
    work: "作业",
    address: "地址",
    point: "点",
    house: "入户",
    connection: "连接",
    civil: "土建",
    pit: "坑点",
    surveyed: "测量",
    third: "第三方",
    utility: "管线",
    existing: "既有",
  };
  const translated = type
    .split(/[_\-\s]+/)
    .filter(Boolean)
    .map((token) => tokenLabels[token.toLowerCase()] || token)
    .join("");
  return translated === type ? type : translated;
}

export function clauseText(risk?: RiskFinding | null): string {
  const clause = risk?.clause || {};
  return [clause.standard_name, clause.clause_id].filter(Boolean).join(" / ") || "导入标准库";
}

export function evidenceText(risk?: RiskFinding | null): string {
  const evidence = risk?.evidence || {};
  const unit = evidence.unit || "";
  return `${evidence.calculation || "规则执行证据"}；实际值 ${evidence.actual_value ?? "-"}，阈值 ${evidence.threshold ?? "-"}${unit}`;
}

export function objectSource(object?: DesignObject): string {
  const props = object?.properties || {};
  const sourceLocation = props.source_location;
  return typeof sourceLocation === "string" && sourceLocation ? sourceLocation : object?.source || "";
}
