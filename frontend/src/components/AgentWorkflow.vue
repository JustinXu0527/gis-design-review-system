<template>
  <div class="agent-workspace">
    <el-card class="module-card workflow-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div><h2>LangGraph 智能审查工作流</h2><span>真实节点状态与执行耗时</span></div>
        </div>
      </template>

      <div class="workflow-command-bar">
        <div class="workflow-progress">
          <div class="workflow-progress-label">
            <div>
              <el-tag :type="workflowTagType" effect="light">{{ workflowStatusText }}</el-tag>
              <strong>{{ progressMessage }}</strong>
            </div>
            <span>{{ progress }}%</span>
          </div>
          <el-progress :percentage="progress" :stroke-width="9" :show-text="false" :status="job?.status === 'error' ? 'exception' : undefined" />
        </div>
        <el-button class="workflow-run-button" type="primary" size="large" :icon="VideoPlay" :loading="store.loading.review" :disabled="!store.objects.length" @click="runReview">
          {{ store.risks.length ? '重新执行智能审查' : '开始智能审查' }}
        </el-button>
      </div>

      <section class="workflow-live-grid" aria-label="实时审查指标">
        <article>
          <span>工程对象</span>
          <strong>{{ liveMetrics.objectsRead.toLocaleString() }}</strong>
          <small>已读取并标准化</small>
        </article>
        <article>
          <span>规则执行</span>
          <strong>{{ liveMetrics.rulesCompleted }}/{{ liveMetrics.rulesTotal }}</strong>
          <small>{{ liveMetrics.riskCount.toLocaleString() }} 条当前命中</small>
        </article>
        <article>
          <span>标准证据</span>
          <strong>{{ liveMetrics.evidenceRecalled }}</strong>
          <small>{{ liveMetrics.knowledgeChains }} 条图谱链路</small>
        </article>
        <article class="live-mcp-metric" :class="`status-${liveMetrics.mcpStatus}`">
          <span><i></i>QGIS MCP</span>
          <strong>{{ liveMetrics.mcpCalls }} 次</strong>
          <small :title="liveMetrics.mcpCurrent">{{ liveMetrics.mcpCurrent }}</small>
        </article>
      </section>

      <div class="workflow-flow" aria-label="LangGraph 工作流节点">
        <template v-for="(node, index) in workflowNodes" :key="node.id">
          <article class="workflow-node" :class="`node-${node.status}`">
            <div class="node-state-icon">
              <el-icon v-if="node.status === 'running'" class="is-loading"><Loading /></el-icon>
              <el-icon v-else-if="node.status === 'completed'"><Check /></el-icon>
              <el-icon v-else-if="node.status === 'failed'"><Close /></el-icon>
              <span v-else>{{ String(index + 1).padStart(2, '0') }}</span>
            </div>
            <div class="node-copy">
              <strong>{{ node.label || nodeLabel(node.id) }}</strong>
              <code>{{ node.id }}</code>
              <p>{{ node.summary || statusLabel(node.status) }}</p>
            </div>
            <small v-if="node.duration_ms">{{ formatDuration(node.duration_ms) }}</small>
          </article>
          <span v-if="index < workflowNodes.length - 1" class="workflow-connector" :class="{ active: node.status === 'completed' }"></span>
        </template>
      </div>
      <p class="workflow-boundary">正式风险由确定性规则引擎产生；LangGraph 负责检索、工具调用、证据校验和智能解释。</p>
    </el-card>

    <section class="agent-detail-grid">
      <el-card class="module-card tool-log-card" shadow="never">
        <template #header><div class="card-header"><div><h2>GIS 工具调用记录</h2><span>QGIS MCP 与受控本地工具</span></div><el-tag>{{ toolCalls.length }} 次调用</el-tag></div></template>
        <el-empty v-if="!toolCalls.length" description="执行智能审查后显示真实工具调用" :image-size="72" />
        <el-timeline v-else class="tool-call-timeline">
          <el-timeline-item v-for="(call, index) in toolCalls" :key="`${call.tool}-${index}`" :type="call.status === 'ok' ? 'success' : 'danger'" :timestamp="formatDuration(call.duration_ms || 0)" placement="top">
            <article class="tool-call-item">
              <div class="tool-call-title">
                <el-tag :type="call.provider === 'qgis_mcp' ? 'success' : 'info'" size="small">{{ providerLabel(call.provider) }}</el-tag>
                <strong>{{ toolLabel(call.tool) }}</strong>
                <span>{{ call.status === 'ok' ? '调用成功' : '调用失败' }}</span>
              </div>
              <p>{{ call.reason || '补充 GIS 审查证据' }}</p>
              <small>{{ call.summary || `核验 ${call.object_count || 0} 个工程对象` }}</small>
              <dl v-if="call.provider === 'qgis_mcp' && (call.object_ids?.length || call.layer_name)" class="tool-call-evidence">
                <div><dt>对象编号</dt><dd>{{ call.object_ids?.join('、') || '-' }}</dd></div>
                <div><dt>来源图层</dt><dd>{{ call.layer_name || '-' }}</dd></div>
                <div><dt>QGIS 要素</dt><dd>{{ call.qgis_feature_id || call.source_feature_id || '-' }}</dd></div>
                <div><dt>定位结果</dt><dd><el-tag :type="call.location_verified ? 'success' : 'warning'" size="small">{{ call.location_verified ? '验证通过' : '未定位' }}</el-tag></dd></div>
              </dl>
              <div v-if="call.field_names?.length" class="tool-field-list">
                <span>读取字段</span>
                <el-tag v-for="field in call.field_names" :key="field" size="small" effect="plain" :title="fieldValue(call, field)">
                  {{ field }}：{{ fieldValue(call, field) }}
                </el-tag>
              </div>
            </article>
          </el-timeline-item>
        </el-timeline>
      </el-card>

      <el-card class="module-card model-conclusion-card" shadow="never">
        <template #header><div class="card-header"><div><h2>本地模型智能解释</h2><span>{{ agent?.model || store.config?.local_llm?.llm_model || 'qwen2.5:32b' }}</span></div></div></template>
        <el-empty v-if="!agent" description="尚未生成智能审查结论" :image-size="72" />
        <div v-else class="model-conclusion">
          <el-alert :closable="false" :type="agent.status === 'ok' ? 'success' : 'warning'" show-icon>
            <template #title>{{ agent.summary || '智能审查已完成' }}</template>
          </el-alert>
          <div class="agent-fact-grid">
            <div><strong>{{ agent.formal_risk_count ?? store.risks.length }}</strong><span>正式风险</span></div>
            <div><strong>{{ agent.retrieval?.selected_count || 0 }}</strong><span>召回证据</span></div>
            <div><strong>{{ agent.knowledge_graph?.risk_chain_count || 0 }}</strong><span>图谱证据链</span></div>
          </div>
          <el-timeline v-if="agent.key_points?.length" class="conclusion-points">
            <el-timeline-item v-for="(point, index) in agent.key_points" :key="index" type="primary">{{ point }}</el-timeline-item>
          </el-timeline>
        </div>
      </el-card>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { Check, Close, Loading, VideoPlay } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

import { useReviewStore } from "@/stores/review";
import type { ToolCallRecord, WorkflowNodeState } from "@/types";
import { errorMessage } from "@/utils/error";

const store = useReviewStore();
const agent = computed(() => store.agentReview);
const job = computed(() => store.reviewJob);
const defaultLabels: Record<string, string> = {
  runtime_status: "运行状态检查",
  data_profile: "工程数据画像",
  semantic_retrieval: "标准语义检索",
  knowledge_graph_context: "知识图谱检索",
  gis_tool_planning: "GIS 工具规划",
  mcp_gis_tools: "MCP 外部调用",
  evidence_validation: "工具证据校验",
  llm_review: "本地模型解释",
  fallback_review: "规则结果回退",
};

const workflowNodes = computed<WorkflowNodeState[]>(() => {
  if (job.value?.nodes?.length) return job.value.nodes;
  if (agent.value?.workflow_trace?.length) return agent.value.workflow_trace;
  return (store.config?.agent_framework?.nodes || Object.keys(defaultLabels)).map((id) => ({
    id,
    label: nodeLabel(id),
    status: "pending",
    summary: "等待执行",
  }));
});
const toolCalls = computed<ToolCallRecord[]>(() => {
  if (job.value?.tool_calls?.length) return job.value.tool_calls;
  if (agent.value?.mcp_call_log?.length) return agent.value.mcp_call_log;
  return (agent.value?.gis_tool_results || []).map((item) => ({
    ...item,
    object_count: item.object_count ?? item.object_ids?.length ?? 0,
    summary: item.summary || "工具调用完成",
  }));
});
const progress = computed(() => {
  if (job.value && job.value.status !== "idle") return job.value.progress || 0;
  return agent.value ? 100 : 0;
});
const progressMessage = computed(() => {
  if (job.value?.message) return job.value.message;
  if (store.loading.review) return store.statusMessage || "智能审查正在执行。";
  return agent.value ? "最近一次智能审查已完成" : "等待启动工作流";
});
const workflowStatusText = computed(() => {
  if (store.loading.review || job.value?.status === "running") return "工作流运行中";
  if (job.value?.status === "error") return "执行失败";
  if (agent.value) return "最近审查已完成";
  return "等待审查";
});
const workflowTagType = computed<"primary" | "success" | "danger" | "info">(() => {
  if (store.loading.review || job.value?.status === "running") return "primary";
  if (job.value?.status === "error") return "danger";
  return agent.value ? "success" : "info";
});
const liveMetrics = computed(() => {
  const metrics = job.value?.metrics;
  const qgisCalls = toolCalls.value.filter((call) => call.provider === "qgis_mcp");
  const runtime = agent.value?.gis_tool_runtime as (NonNullable<typeof agent.value>["gis_tool_runtime"] & {
    mcp_object_check_count?: number;
    mcp_object_success_count?: number;
  }) | undefined;
  const mcpCalls = metrics?.mcp_calls_completed ?? qgisCalls.length;
  const mcpCurrent = metrics?.mcp_current_call || runtime?.note || (mcpCalls ? "对象核验完成" : "等待对象级调用");
  return {
    objectsRead: metrics?.objects_read ?? agent.value?.data_profile?.object_count ?? store.objects.length,
    rulesCompleted: metrics?.rules_completed ?? store.executionLog.length,
    rulesTotal: metrics?.rules_total ?? store.executionLog.length,
    riskCount: metrics?.risk_count ?? store.risks.length,
    evidenceRecalled: metrics?.evidence_recalled ?? agent.value?.retrieval?.selected_count ?? 0,
    knowledgeChains: metrics?.knowledge_chains ?? agent.value?.knowledge_graph?.risk_chain_count ?? 0,
    mcpCalls,
    mcpCurrent,
    mcpStatus: metrics?.mcp_call_status || (runtime?.status === "connected" ? "completed" : "pending"),
  };
});

async function runReview(): Promise<void> {
  try {
    await store.reviewCurrentProject();
    ElMessage.success("智能审查完成");
  } catch (error) {
    ElMessage.error(errorMessage(error));
  }
}

function nodeLabel(id: string): string {
  return defaultLabels[id] || id;
}

function statusLabel(status: string): string {
  return { pending: "等待执行", running: "正在执行", completed: "执行完成", failed: "执行失败", skipped: "本次未经过" }[status] || status;
}

function formatDuration(duration: number): string {
  if (!duration) return "< 1 ms";
  return duration >= 1000 ? `${(duration / 1000).toFixed(1)} s` : `${duration} ms`;
}

function providerLabel(provider?: string): string {
  return provider === "qgis_mcp" ? "QGIS MCP" : "本地 GIS 工具";
}

function toolLabel(tool: string): string {
  return {
    get_project_capabilities: "工程能力验证",
    inspect_project_object: "对象图层与字段核验",
    inspect_object_context: "对象上下文读取",
    validate_geometry: "几何有效性核验",
    summarize_rule_evidence: "规则证据绑定",
  }[tool] || tool;
}

function fieldValue(call: ToolCallRecord, field: string): string {
  const value = call.fields?.[field];
  if (value === null || value === undefined || value === "") return "空";
  const text = typeof value === "object" ? JSON.stringify(value) : String(value);
  return text.length > 28 ? `${text.slice(0, 28)}...` : text;
}
</script>
