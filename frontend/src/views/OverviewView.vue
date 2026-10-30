<template>
  <div class="page-view overview-view">
    <section class="page-intro">
      <div>
        <span class="page-kicker">ENGINEERING INTELLIGENCE</span>
        <h2>工程审查态势总览</h2>
        <p>从 GIS 工程对象到规则风险、空间证据与智能解释，集中查看当前项目的审查状态。</p>
      </div>
      <div class="page-actions">
        <el-button :icon="FolderOpened" @click="router.push('/projects')">管理项目</el-button>
        <el-button type="primary" :icon="Cpu" :disabled="!store.objects.length" @click="router.push('/agent')">进入智能审查</el-button>
      </div>
    </section>

    <section class="overview-metrics">
      <button class="overview-metric metric-teal" @click="router.push('/map')">
        <span>工程对象</span>
        <strong>{{ store.objects.length.toLocaleString() }}</strong>
        <small>已标准化 GIS 要素</small>
      </button>
      <button class="overview-metric metric-red" @click="router.push('/risks')">
        <span>规则命中</span>
        <strong>{{ store.risks.length.toLocaleString() }}</strong>
        <small>确定性规则正式风险</small>
      </button>
      <button class="overview-metric metric-amber" @click="router.push('/risks')">
        <span>风险位置</span>
        <strong>{{ locationCounts.total.toLocaleString() }}</strong>
        <small>同位置规则聚合结果</small>
      </button>
      <button class="overview-metric metric-blue" @click="router.push('/knowledge')">
        <span>标准条款</span>
        <strong>{{ store.standardClauseCount.toLocaleString() }}</strong>
        <small>{{ store.standards.length }} 类后端标准库</small>
      </button>
    </section>

    <RiskCharts />

    <section class="overview-bottom-grid">
      <el-card class="module-card" shadow="never">
        <template #header>
          <div class="card-header">
            <div><h2>当前工程</h2><span>项目上下文与执行入口</span></div>
            <el-tag :type="store.currentProject ? 'success' : 'info'">{{ store.currentProject ? '已打开' : '等待项目' }}</el-tag>
          </div>
        </template>
        <el-empty v-if="!store.currentProject" description="请在项目管理中创建或打开工程" :image-size="72" />
        <div v-else class="current-project-summary">
          <strong>{{ store.currentProject.name }}</strong>
          <p>{{ store.currentProject.documents?.length || 0 }} 份工程资料，{{ store.objects.length }} 个设计对象。</p>
          <el-progress :percentage="reviewCompletion" :stroke-width="9" :show-text="false" />
          <div class="project-summary-actions">
            <span>{{ store.risks.length ? '已形成可追溯审查结果' : '等待执行智能审查' }}</span>
            <el-button text type="primary" @click="router.push(store.risks.length ? '/risks' : '/agent')">查看详情</el-button>
          </div>
        </div>
      </el-card>

      <el-card class="module-card" shadow="never">
        <template #header>
          <div class="card-header"><div><h2>系统能力</h2><span>当前运行链路</span></div></div>
        </template>
        <div class="capability-strip">
          <div><b>01</b><span>GIS 数据适配</span><small>GeoPandas / Pydantic</small></div>
          <div><b>02</b><span>确定性规则审查</span><small>Shapely / 三类规则库</small></div>
          <div><b>03</b><span>智能体证据组织</span><small>LangGraph / bge-m3</small></div>
          <div><b>04</b><span>专业工具验证</span><small>QGIS Server / MCP</small></div>
        </div>
      </el-card>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { Cpu, FolderOpened } from "@element-plus/icons-vue";
import { useRouter } from "vue-router";

import RiskCharts from "@/components/RiskCharts.vue";
import { useReviewStore } from "@/stores/review";
import { riskLocationCounts } from "@/utils/riskLocations";

const store = useReviewStore();
const router = useRouter();
const locationCounts = computed(() => riskLocationCounts(store.risks));
const reviewCompletion = computed(() => (store.risks.length ? 100 : store.objects.length ? 58 : 12));
</script>
