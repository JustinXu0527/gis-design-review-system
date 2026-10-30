<template>
  <div class="side-stack">
    <el-card class="module-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h2>风险定位与证据</h2>
            <span>{{ locationCounts.total }} 个风险位置</span>
          </div>
        </div>
      </template>
      <el-empty v-if="!selectedLocation" description="点击审查结果查看风险位置" :image-size="72" />
      <div v-else class="evidence-card">
        <div class="detail-title">
          <el-tag :type="levelType(selectedLocation.level)">{{ levelLabel(selectedLocation.level) }}</el-tag>
          <strong>{{ locationObjectNames(selectedLocation) }}</strong>
        </div>
        <p>{{ locationSummary(selectedLocation) }}</p>
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="风险构成">{{ locationComposition(selectedLocation) }}</el-descriptions-item>
          <el-descriptions-item label="命中规则">{{ selectedLocation.risks.length }} 条</el-descriptions-item>
          <el-descriptions-item label="涉及条款" :span="2">{{ locationClauses(selectedLocation) }}</el-descriptions-item>
          <el-descriptions-item v-if="selectedKnowledgeChain" label="图谱证据" :span="2">{{ selectedKnowledgeChain }}</el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>

    <el-card class="module-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h2>本地 Ollama 智能审查</h2>
            <span>{{ agentStatusText }}</span>
          </div>
        </div>
      </template>
      <el-empty v-if="!agent" description="尚未执行智能审查" :image-size="72" />
      <div v-else class="agent-box">
        <el-alert :closable="false" :type="agentAlertType" show-icon>
          <template #title>{{ agent.summary || "本地 Ollama 已完成智能审查。" }}</template>
        </el-alert>
        <div class="tag-row">
          <el-tag>正式风险 {{ agent.formal_risk_count ?? store.risks.length }}</el-tag>
          <el-tag type="info">模型建议 {{ agent.model_risk_count ?? 0 }}</el-tag>
          <el-tag :type="agent?.retrieval?.selected_count ? 'success' : 'info'">召回 {{ agent.retrieval?.selected_count ?? 0 }} 条证据</el-tag>
          <el-tag :type="agent?.knowledge_graph?.risk_chain_count ? 'success' : 'info'">
            图谱链 {{ agent.knowledge_graph?.risk_chain_count ?? 0 }} 条
          </el-tag>
          <el-tag :type="agent.gis_tool_runtime?.status === 'connected' ? 'success' : 'info'">
            QGIS MCP {{ agent.gis_tool_runtime?.status === 'connected' ? '已验证工程' : '未接入' }}
          </el-tag>
        </div>
        <el-alert
          v-if="agent.gis_tool_runtime?.status === 'connected'"
          class="mcp-status-alert"
          :closable="false"
          type="success"
          show-icon
        >
          <template #title>
            QGIS MCP 已完成工程验证：{{ agent.evidence_validation?.external_evidence_count ?? 1 }} 项外部工程证据已纳入整改路径。
          </template>
        </el-alert>
        <el-alert class="kg-status-alert" :closable="false" :type="agent.knowledge_graph?.risk_chain_count ? 'success' : 'warning'" show-icon>
          <template #title>
            {{
              agent.knowledge_graph?.risk_chain_count
                ? `知识图谱已生成 ${agent.knowledge_graph.risk_chain_count} 条风险证据链，图谱规模 ${agent.knowledge_graph.node_count || 0} 节点 / ${agent.knowledge_graph.edge_count || 0} 关系。`
                : "当前审查记录未包含知识图谱证据链，请重新执行审查生成。"
            }}
          </template>
        </el-alert>
        <el-descriptions v-if="agent.status !== 'ok'" :column="1" size="small" border>
          <el-descriptions-item label="调用状态">{{ agent.status || "unknown" }}</el-descriptions-item>
          <el-descriptions-item label="模型">{{ agent.model || store.config?.local_llm?.llm_model || "-" }}</el-descriptions-item>
          <el-descriptions-item label="错误">{{ agent.error || "未记录详细错误" }}</el-descriptions-item>
        </el-descriptions>
        <el-timeline>
          <el-timeline-item v-for="(item, index) in agent.key_points || []" :key="index" type="primary">
            {{ item }}
          </el-timeline-item>
        </el-timeline>
      </div>
    </el-card>

    <el-card class="module-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h2>标准来源提示</h2>
            <span>{{ store.standards.length }} 个标准库</span>
          </div>
        </div>
      </template>
      <el-scrollbar max-height="260px">
        <div v-for="item in store.standards" :key="item.file" class="source-item">
          <strong>{{ item.file }}</strong>
          <p>{{ (item.standards || []).join("、") || item.source_file }}</p>
          <el-progress
            :percentage="ruleRate(item)"
            :stroke-width="8"
            :show-text="false"
            status="success"
          />
          <small>{{ item.computable_rule_count || 0 }} / {{ item.rule_count || 0 }} 条规则可计算</small>
        </div>
      </el-scrollbar>
    </el-card>

    <el-card class="module-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h2>设计方案维度评估</h2>
            <span>{{ store.objects.length }} 对象，{{ store.risks.length }} 风险</span>
          </div>
        </div>
      </template>
      <div class="dimension-list">
        <div v-for="item in dimensions" :key="item.name" class="dimension-item">
          <div>
            <strong>{{ item.name }}</strong>
            <span>{{ item.comment }}</span>
          </div>
          <el-tag :type="item.score === 100 ? 'success' : item.score >= 80 ? 'warning' : 'danger'">
            {{ item.score }}
          </el-tag>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

import { useReviewStore } from "@/stores/review";
import type { StandardDoc } from "@/types";
import { clauseText, levelLabel, levelType, riskCounts } from "@/utils/format";
import { groupRisksByLocation, riskLocationCounts, type RiskLocation } from "@/utils/riskLocations";

const store = useReviewStore();
const locations = computed(() => groupRisksByLocation(store.risks));
const locationCounts = computed(() => riskLocationCounts(store.risks));
const selectedLocation = computed(() => {
  const selectedRiskId = store.selectedRiskId;
  return locations.value.find((location) => location.risks.some((risk) => risk.id === selectedRiskId)) || locations.value[0] || null;
});
const selectedKnowledgeChain = computed(() => selectedLocation.value?.risks.find((risk) => risk.knowledge_graph?.chain?.length)?.knowledge_graph?.chain?.join(" → ") || "");
const agent = computed(() => store.agentReview);
const agentAlertType = computed<"success" | "warning" | "error" | "info">(() => {
  if (!agent.value) return "info";
  if (agent.value.status === "ok") return "success";
  if (agent.value.status === "disabled") return "warning";
  if (agent.value.status === "error") return "error";
  return "info";
});
const agentStatusText = computed(() => {
  if (!agent.value) return "等待调用";
  if (agent.value.status === "ok") return `已完成｜${agent.value.model || store.config?.local_llm?.llm_model || "本地模型"}`;
  if (agent.value.status === "disabled") return "未就绪｜已回退规则引擎";
  if (agent.value.status === "error") return "调用失败｜已回退规则引擎";
  return agent.value.model || "等待调用";
});
const dimensions = computed(() => {
  const high = store.risks.filter((item) => item.level === "high").length;
  const medium = store.risks.filter((item) => item.level === "medium").length;
  return [
    {
      name: "空间冲突",
      score: high ? Math.max(0, 100 - high * 12) : 100,
      comment: high ? "存在高风险空间或属性冲突" : "未发现高风险空间冲突",
    },
    {
      name: "资料完整性",
      score: medium ? Math.max(70, 100 - medium * 5) : 100,
      comment: medium ? "部分 GIS 字段或证明材料需补充" : "未发现明显资料缺口",
    },
    {
      name: "规则可执行性",
      score: store.executionLog.length ? Math.round((store.executionLog.filter((item) => item.computable).length / store.executionLog.length) * 100) : 0,
      comment: store.executionLog.length ? "来自规则执行日志" : "等待审查执行",
    },
  ];
});

function ruleRate(item: StandardDoc): number {
  if (!item.rule_count) return 0;
  return Math.round(((item.computable_rule_count || 0) / item.rule_count) * 100);
}

function locationObjectNames(location: RiskLocation): string {
  if (!location.objectIds.length) return "未绑定对象";
  return location.objectIds.map((id) => store.objects.find((object) => object.id === id)?.name || id).join("、");
}

function locationComposition(location: RiskLocation): string {
  const counts = riskCounts(location.risks);
  return [
    counts.high && `高风险 ${counts.high} 条`,
    counts.medium && `中风险 ${counts.medium} 条`,
    counts.low && `低风险 ${counts.low} 条`,
    counts.unknown && `未定级 ${counts.unknown} 条`,
  ]
    .filter(Boolean)
    .join("，");
}

function locationClauses(location: RiskLocation): string {
  return [...new Set(location.risks.map((risk) => clauseText(risk)))].join("；");
}

function locationSummary(location: RiskLocation): string {
  return `${locationObjectNames(location)} 共命中 ${location.risks.length} 条规则，按最高等级归为${levelLabel(location.level)}。`;
}
</script>
