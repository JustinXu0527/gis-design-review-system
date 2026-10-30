<template>
  <div class="page-view knowledge-view">
    <section class="page-intro compact-intro">
      <div><span class="page-kicker">STANDARD INTELLIGENCE</span><h2>标准知识库与证据图谱</h2><p>查看后端维护的三类规则来源，以及标准、条款、规则、对象和风险之间的可追溯关系。</p></div>
    </section>
    <section class="knowledge-page-grid">
      <StandardLibrary />
      <el-card class="module-card knowledge-graph-card" shadow="never">
        <template #header><div class="card-header"><div><h2>知识图谱证据链</h2><span>{{ graphSummary }}</span></div><el-tag :type="riskChainCount ? 'success' : 'info'">{{ riskChainCount }} 条链路</el-tag></div></template>
        <div v-if="riskChains.length" class="graph-explorer-toolbar">
          <el-select v-model="selectedChainId" filterable placeholder="选择风险证据链" class="graph-chain-select">
            <el-option v-for="chain in riskChains" :key="chain.risk_id" :label="chainOptionLabel(chain)" :value="chain.risk_id" />
          </el-select>
          <el-button type="primary" plain :icon="View" @click="openRiskDetail">查看风险详情</el-button>
        </div>
        <div class="knowledge-chain-visual">
          <template v-for="(item, index) in graphPath" :key="item.label">
            <div class="knowledge-node" :class="item.class"><el-icon><component :is="item.icon" /></el-icon><strong>{{ item.label }}</strong><span>{{ item.note }}</span></div>
            <span v-if="index < graphPath.length - 1" class="knowledge-edge">→</span>
          </template>
        </div>
        <section v-if="selectedChain" class="knowledge-chain-detail">
          <div class="chain-detail-heading">
            <div>
              <el-tag :type="levelTagType(selectedChain.level)" size="small">{{ levelLabel(selectedChain.level) }}</el-tag>
              <strong>{{ selectedChain.title || '风险证据链' }}</strong>
            </div>
            <span>{{ selectedChain.clause_key || '未关联条款' }}</span>
          </div>
          <div class="chain-attribute-row">
            <span>检查字段</span>
            <el-tag v-for="field in selectedChain.checked_properties || []" :key="field" size="small" effect="plain">{{ field }}</el-tag>
            <span>规则类型</span>
            <el-tag v-for="rule in selectedChain.rule_types || []" :key="rule" size="small" type="warning" effect="plain">{{ rule }}</el-tag>
          </div>
          <ol class="chain-step-list">
            <li v-for="(step, index) in selectedChain.chain || []" :key="`${index}-${step}`">
              <span>{{ index + 1 }}</span><p>{{ step }}</p>
            </li>
          </ol>
        </section>
        <el-empty v-else description="完成智能审查后，可在此选择风险并查看真实证据链" :image-size="66" />
        <el-alert :closable="false" type="info" show-icon>
          <template #title>知识图谱用于组织和追溯证据，不替代确定性规则引擎的正式风险判定。</template>
        </el-alert>
      </el-card>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw } from "vue";
import { Collection, Document, Files, MapLocation, Search, View, Warning } from "@element-plus/icons-vue";
import { useRouter } from "vue-router";
import StandardLibrary from "@/components/StandardLibrary.vue";
import { useReviewStore } from "@/stores/review";
import type { KnowledgeGraphRiskChain } from "@/types";

const store = useReviewStore();
const router = useRouter();
const graph = computed(() => store.agentReview?.knowledge_graph);
const riskChainCount = computed(() => graph.value?.risk_chain_count || 0);
const riskChains = computed<KnowledgeGraphRiskChain[]>(() => graph.value?.risk_chains || []);
const selectedChainId = computed({
  get: () => riskChains.value.some((item) => item.risk_id === store.selectedRiskId)
    ? store.selectedRiskId
    : riskChains.value[0]?.risk_id || "",
  set: (riskId: string) => store.focusRisk(riskId),
});
const selectedChain = computed(() => riskChains.value.find((item) => item.risk_id === selectedChainId.value) || null);
const graphSummary = computed(() => graph.value ? `${graph.value.node_count || 0} 节点 / ${graph.value.edge_count || 0} 关系` : "等待审查生成图谱上下文");
const graphPath = [
  { label: "标准", note: "中德技术规范", class: "node-blue", icon: markRaw(Files) },
  { label: "条款", note: "结构化知识单元", class: "node-teal", icon: markRaw(Document) },
  { label: "规则", note: "可执行审查条件", class: "node-amber", icon: markRaw(Collection) },
  { label: "工程对象", note: "GIS 图层与要素", class: "node-blue", icon: markRaw(MapLocation) },
  { label: "检查字段", note: "属性、阈值与计算项", class: "node-teal", icon: markRaw(Search) },
  { label: "风险证据", note: "等级、位置与建议", class: "node-red", icon: markRaw(Warning) },
];

function chainOptionLabel(chain: KnowledgeGraphRiskChain): string {
  return `${levelLabel(chain.level)}｜${chain.title || '风险'}｜${chain.clause_key || '未关联条款'}`;
}

function levelLabel(level?: string): string {
  return { high: "高风险", medium: "中风险", low: "低风险" }[level || ""] || "待复核";
}

function levelTagType(level?: string): "danger" | "warning" | "success" | "info" {
  return { high: "danger", medium: "warning", low: "success" }[level || ""] as "danger" | "warning" | "success" || "info";
}

async function openRiskDetail(): Promise<void> {
  if (!selectedChain.value) return;
  store.focusRisk(selectedChain.value.risk_id);
  await router.push("/risks");
}
</script>
