export type RiskLevel = "high" | "medium" | "low" | "unknown" | string;

export interface Geometry {
  type: string;
  coordinates?: unknown;
  geometries?: Geometry[];
}

export interface DesignObject {
  id: string;
  type: string;
  name: string;
  geometry?: Geometry | null;
  properties?: Record<string, unknown>;
  source?: string;
}

export interface ReviewEvidence {
  calculation?: string;
  actual_value?: number | string | null;
  threshold?: number | string | null;
  unit?: string;
  object_ids?: string[];
}

export interface RiskFinding {
  id: string;
  title: string;
  category?: string;
  level: RiskLevel;
  description?: string;
  impact?: string;
  recommendation?: string;
  priority?: number;
  clause?: {
    standard_name?: string;
    version?: string;
    clause_id?: string;
    summary?: string;
    is_placeholder?: boolean;
    applicable_reason?: string;
  };
  evidence?: ReviewEvidence;
  geometry?: Geometry | null;
  mcp_remediation?: McpRemediation;
  knowledge_graph?: RiskKnowledgeGraphEvidence;
}

export interface RiskKnowledgeGraphEvidence {
  verified?: boolean;
  chain?: string[];
  checked_properties?: string[];
  applicable_objects?: string[];
  rule_types?: string[];
}

export interface KnowledgeGraphRiskChain extends RiskKnowledgeGraphEvidence {
  risk_id: string;
  title?: string;
  level?: string;
  clause_key?: string;
}

export interface McpRemediation {
  verified?: boolean;
  provider?: string;
  project_id?: string;
  project_available?: boolean;
  layer_count?: number;
  layer_name?: string;
  layer_published?: boolean;
  object_reference?: string;
  source?: string;
  object_verified?: boolean;
  source_feature_id?: string;
  qgis_feature_id?: string;
  query_method?: string;
  field_names?: string[];
  fields?: Record<string, unknown>;
  action?: string;
}

export interface ExecutionLog {
  rule_id?: string;
  rule_type?: string;
  clause_id?: string;
  standard_name?: string;
  finding_count?: number;
  computable?: boolean;
}

export interface AgentReview {
  enabled?: boolean;
  status?: string;
  provider?: string;
  model?: string;
  summary?: string;
  overall_level?: string;
  key_points?: string[];
  risks?: unknown[];
  data_profile?: {
    object_count?: number;
    object_types?: Record<string, number>;
    source_layers?: Record<string, number>;
  };
  retrieval?: {
    enabled?: boolean;
    provider?: string;
    model?: string;
    status?: string;
    selected_count?: number;
  };
  knowledge_graph?: {
    status?: string;
    graph_path?: string;
    node_count?: number;
    edge_count?: number;
    selected_clause_count?: number;
    risk_chain_count?: number;
    node_type_counts?: Record<string, number>;
    risk_chains?: KnowledgeGraphRiskChain[];
  };
  gis_tool_runtime?: {
    status?: string;
    provider?: string;
    note?: string;
    error?: string;
    mcp_object_check_count?: number;
    mcp_object_success_count?: number;
  };
  evidence_validation?: {
    valid?: boolean;
    planned_tool_count?: number;
    executed_tool_count?: number;
    external_evidence_count?: number;
  };
  graph?: Record<string, unknown>;
  gis_tool_results?: GisToolResult[];
  workflow_trace?: WorkflowNodeState[];
  mcp_call_log?: ToolCallRecord[];
  error?: string;
  model_risk_count?: number;
  formal_risk_count?: number;
  formal_risk_source?: string;
  risks_are_suggestions?: boolean;
}

export type WorkflowNodeStatus = "pending" | "running" | "completed" | "failed" | "skipped";

export interface WorkflowNodeState {
  id: string;
  label: string;
  status: WorkflowNodeStatus;
  duration_ms?: number;
  summary?: string;
  started_at?: string;
  completed_at?: string;
}

export interface ToolCallRecord {
  tool: string;
  provider?: string;
  reason?: string;
  status?: string;
  duration_ms?: number;
  object_count?: number;
  object_ids?: string[];
  layer_name?: string;
  source_feature_id?: string;
  qgis_feature_id?: string;
  field_names?: string[];
  fields?: Record<string, unknown>;
  location_verified?: boolean;
  query_method?: string;
  summary?: string;
}

export interface GisToolResult extends ToolCallRecord {
  object_ids?: string[];
  result?: Record<string, unknown>;
  error?: string;
}

export interface ReviewJobStatus {
  project_id: string;
  status: "idle" | "queued" | "running" | "completed" | "error" | string;
  progress: number;
  current_node?: string;
  message?: string;
  nodes: WorkflowNodeState[];
  tool_calls: ToolCallRecord[];
  metrics?: {
    objects_read?: number;
    rules_total?: number;
    rules_completed?: number;
    risk_count?: number;
    current_rule?: string;
    evidence_recalled?: number;
    knowledge_chains?: number;
    mcp_calls_completed?: number;
    mcp_objects_verified?: number;
    mcp_current_call?: string;
    mcp_call_status?: string;
  };
  error?: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
}

export interface Project {
  id: string;
  name: string;
  created_at?: string;
  documents?: unknown[];
  objects?: DesignObject[];
  risks?: RiskFinding[];
  execution_log?: ExecutionLog[];
  agent_review?: AgentReview | null;
  qgis_preview?: QgisPreviewStatus | null;
}

export interface ProjectListItem {
  id: string;
  name: string;
  created_at?: string;
  document_count?: number;
  object_count?: number;
  risk_count?: number;
}

export interface StandardDoc {
  file: string;
  source_file?: string;
  imported_at?: string;
  clause_count?: number;
  placeholder_count?: number;
  standards?: string[];
  rule_count?: number;
  computable_rule_count?: number;
  manual_rule_count?: number;
  rule_types?: string[];
  risk_level_counts?: Record<string, number>;
  sample_clauses?: Array<Record<string, unknown>>;
}

export interface AppConfig {
  local_llm?: {
    available?: boolean;
    enabled?: boolean;
    llm_model?: string;
    embed_model?: string;
  };
  qgis_preview?: QgisPreviewStatus;
  agent_framework?: {
    framework?: string;
    nodes?: string[];
  };
  api_framework?: string;
  geometry_engine?: Record<string, unknown>;
  standard_library?: Record<string, unknown>;
}

export interface QgisPreviewLayer {
  name: string;
  checked?: boolean;
  source?: string;
}

export interface QgisPreviewStatus {
  mode?: string;
  available?: boolean;
  project_id?: string;
  project_exists?: boolean;
  project_file?: string;
  host_project_file?: string;
  container_project_file?: string;
  server_url_configured?: boolean;
  wms_proxy_url?: string;
  layers?: QgisPreviewLayer[];
  wms_layers?: string;
  render_wms_layers?: string;
  excluded_wms_layers?: string[];
  extent?: [number, number, number, number] | number[] | null;
  crs?: string;
  title?: string;
  generated?: boolean;
  updated_at?: string;
  error?: string;
}
