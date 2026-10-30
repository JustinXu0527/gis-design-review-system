<template>
  <el-card class="module-card results-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <h2>审查结果</h2>
          <span>{{ summaryText }}</span>
        </div>
        <div class="export-group">
          <el-button v-for="item in exports" :key="item.format" size="small" @click="store.exportCurrentProject(item.format)">
            {{ item.label }}
          </el-button>
        </div>
      </div>
    </template>

    <div class="result-toolbar">
      <el-segmented v-model="riskFilterModel" :options="filterOptions" />
      <el-tag type="danger">高风险位置 {{ locationCounts.high }}</el-tag>
      <el-tag type="warning">中风险位置 {{ locationCounts.medium }}</el-tag>
      <el-tag type="success">低风险位置 {{ locationCounts.low }}</el-tag>
    </div>

    <el-table
      class="risk-table"
      :data="filteredLocations"
      height="300"
      row-key="id"
      :current-row-key="selectedLocation?.id"
      highlight-current-row
      empty-text="暂无风险结果。上传 GIS 成果并执行审查后，这里会显示风险清单。"
      @row-click="selectLocation"
    >
      <el-table-column label="等级" width="92">
        <template #default="{ row }">
          <el-tag :type="levelType(row.level)" effect="light">{{ levelLabel(row.level) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="问题" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ locationTitle(row) }}</template>
      </el-table-column>
      <el-table-column label="对象" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ objectNames(row) }}</template>
      </el-table-column>
      <el-table-column label="规则数" width="88" align="center">
        <template #default="{ row }">{{ row.risks.length }}</template>
      </el-table-column>
      <el-table-column label="条款" min-width="170" show-overflow-tooltip>
        <template #default="{ row }">{{ locationClauseText(row) }}</template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!selectedLocation" description="请选择风险位置查看详情" :image-size="80" />
    <section v-else class="risk-detail-panel">
      <div class="detail-title">
        <el-tag :type="levelType(selectedLocation.level)">{{ levelLabel(selectedLocation.level) }}</el-tag>
        <strong>{{ objectNames(selectedLocation) }}</strong>
      </div>
      <p>{{ locationSummary(selectedLocation) }}</p>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="风险构成">{{ locationComposition(selectedLocation) }}</el-descriptions-item>
        <el-descriptions-item label="命中规则">{{ selectedLocation.risks.length }} 条</el-descriptions-item>
        <el-descriptions-item label="涉及条款" :span="2">{{ locationClauseText(selectedLocation) }}</el-descriptions-item>
      </el-descriptions>
      <el-alert
        v-if="knowledgeGraphSummary"
        class="kg-location-alert"
        :closable="false"
        :type="selectedLocationHasKnowledgeGraph ? 'success' : 'warning'"
        show-icon
      >
        <template #title>{{ knowledgeGraphSummary }}</template>
      </el-alert>
      <el-collapse class="location-rule-collapse">
        <el-collapse-item v-for="risk in selectedLocation.risks" :key="risk.id" :name="risk.id">
          <template #title>
            <el-tag :type="levelType(risk.level)" size="small">{{ levelLabel(risk.level) }}</el-tag>
            <span class="location-rule-title">{{ risk.title }}｜{{ clauseText(risk) }}</span>
          </template>
          <p>{{ risk.description || "规则命中该对象，需要进一步核查。" }}</p>
          <p><strong>计算证据：</strong>{{ evidenceText(risk) }}</p>
          <p><strong>整改建议：</strong>{{ risk.recommendation || "结合标准条款和现场资料进一步复核并整改。" }}</p>
          <div v-if="risk.knowledge_graph?.verified" class="kg-evidence">
            <div class="kg-evidence-title">
              <el-tag type="success" size="small">知识图谱</el-tag>
              <strong>标准证据链</strong>
            </div>
            <ol>
              <li v-for="item in risk.knowledge_graph.chain || []" :key="item">{{ item }}</li>
            </ol>
            <p v-if="risk.knowledge_graph.checked_properties?.length">
              <strong>检查字段：</strong>{{ risk.knowledge_graph.checked_properties.join("、") }}
            </p>
          </div>
          <div v-if="risk.mcp_remediation?.verified" class="mcp-remediation">
            <div class="mcp-remediation-title">
              <el-tag type="success" size="small">QGIS MCP 已验证</el-tag>
              <strong>工程定位整改路径</strong>
            </div>
            <p>
              QGIS 工程验证通过
              <template v-if="risk.mcp_remediation.layer_name">；当前对象可在工程图层“{{ risk.mcp_remediation.layer_name }}”中定位复核。</template>
            </p>
            <p><strong>操作：</strong>{{ risk.mcp_remediation.action }}</p>
          </div>
        </el-collapse-item>
      </el-collapse>
    </section>

    <el-collapse class="result-collapse">
      <el-collapse-item name="objects">
        <template #title>
          <span class="collapse-title">对象抽取</span>
          <el-tag size="small">{{ store.objects.length }} 个对象</el-tag>
        </template>
        <el-table :data="store.objects" height="240" size="small" empty-text="暂无 GIS 对象">
          <el-table-column prop="id" label="编号" min-width="160" show-overflow-tooltip />
          <el-table-column prop="name" label="名称" min-width="180" show-overflow-tooltip />
          <el-table-column label="类型" min-width="120">
            <template #default="{ row }">{{ objectTypeLabel(row.type) }}</template>
          </el-table-column>
          <el-table-column label="来源" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">{{ row.properties?.source_location || row.source }}</template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
      <el-collapse-item name="logs">
        <template #title>
          <span class="collapse-title">规则执行明细</span>
          <el-tag size="small">{{ store.executionLog.length }} 条日志</el-tag>
        </template>
        <el-table :data="store.executionLog" height="240" size="small" empty-text="暂无规则执行日志">
          <el-table-column label="规则类型" min-width="130">
            <template #default="{ row }">{{ ruleTypeLabel(row.rule_type) }}</template>
          </el-table-column>
          <el-table-column prop="clause_id" label="条款" min-width="120" />
          <el-table-column prop="standard_name" label="标准" min-width="220" show-overflow-tooltip />
          <el-table-column prop="finding_count" label="风险数" width="90" />
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="row.computable ? 'success' : 'info'" size="small">
                {{ row.computable ? "可计算" : "人工复核" }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from "vue";

import { useReviewStore } from "@/stores/review";
import { clauseText, evidenceText, levelLabel, levelType, objectTypeLabel, riskCounts, ruleTypeLabel } from "@/utils/format";
import { groupRisksByLocation, riskLocationCounts, type RiskLocation } from "@/utils/riskLocations";

const store = useReviewStore();
const exports = [
  { format: "pdf", label: "PDF" },
  { format: "docx", label: "Word" },
  { format: "xlsx", label: "Excel" },
  { format: "geojson", label: "GeoJSON" },
  { format: "log", label: "日志" },
];
const filterOptions = [
  { label: "全部", value: "all" },
  { label: "高风险", value: "high" },
  { label: "中风险", value: "medium" },
  { label: "低风险", value: "low" },
];

const locations = computed(() => groupRisksByLocation(store.risks));
const locationCounts = computed(() => riskLocationCounts(store.risks));
const riskFilterModel = computed({
  get: () => store.riskFilter,
  set: (filter: "all" | "high" | "medium" | "low") => store.setRiskFilter(filter),
});
const filteredLocations = computed(() => {
  if (store.riskFilter === "all") return locations.value;
  return locations.value.filter((location) => location.level === store.riskFilter);
});
const selectedLocation = computed(() => {
  return locations.value.find((location) => location.risks.some((risk) => risk.id === store.selectedRiskId)) || filteredLocations.value[0] || null;
});
const selectedLocationHasKnowledgeGraph = computed(() => Boolean(selectedLocation.value?.risks.some((risk) => risk.knowledge_graph?.verified)));
const knowledgeGraphSummary = computed(() => {
  if (!selectedLocation.value) return "";
  const graph = store.agentReview?.knowledge_graph;
  if (selectedLocationHasKnowledgeGraph.value) {
    const chainCount = selectedLocation.value.risks.filter((risk) => risk.knowledge_graph?.verified).length;
    return `该风险位置已关联 ${chainCount} 条知识图谱证据链，可在下方展开单条风险查看“标准-条款-对象-字段-风险等级”路径。`;
  }
  if (store.agentReview && !graph?.risk_chain_count) {
    return "当前审查结果未包含知识图谱证据链；重启服务并重新执行审查后会生成图谱证据。";
  }
  return "";
});
const summaryText = computed(() => {
  if (!store.currentProject) return "未打开项目";
  return `${store.objects.length} 个对象，${store.risks.length} 条规则命中，${locationCounts.value.total} 个风险位置`;
});

function selectLocation(row: RiskLocation): void {
  store.focusRisk(row.risks[0]?.id || "");
}

function objectNames(location: RiskLocation): string {
  const ids = location.objectIds;
  if (!ids.length) return "未绑定对象";
  const names = ids.map((id) => store.objects.find((obj) => obj.id === id)?.name || id);
  return names.join("、");
}

function locationTitle(location: RiskLocation): string {
  if (location.risks.length === 1) return location.risks[0]?.title || "规则问题";
  return `命中 ${location.risks.length} 条规则问题`;
}

function locationClauseText(location: RiskLocation): string {
  const clauses = [...new Set(location.risks.map((risk) => clauseText(risk)))];
  return clauses.join("；");
}

function locationComposition(location: RiskLocation): string {
  const composition = riskCounts(location.risks);
  return [
    composition.high && `高风险 ${composition.high} 条`,
    composition.medium && `中风险 ${composition.medium} 条`,
    composition.low && `低风险 ${composition.low} 条`,
    composition.unknown && `未定级 ${composition.unknown} 条`,
  ]
    .filter(Boolean)
    .join("，");
}

function locationSummary(location: RiskLocation): string {
  return `${objectNames(location)} 共命中 ${location.risks.length} 条规则，按最高等级归为${levelLabel(location.level)}。`;
}
</script>
