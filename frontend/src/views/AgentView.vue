<template>
  <div class="page-view agent-view">
    <section class="page-intro compact-intro">
      <div><span class="page-kicker">AGENT ORCHESTRATION</span><h2>智能体审查与工具执行</h2><p>观察 LangGraph 节点运行、QGIS MCP 外部调用和本地模型解释过程。</p></div>
      <el-tag v-if="store.currentProject" type="success" effect="plain">当前工程：{{ store.currentProject.name }}</el-tag>
    </section>
    <AgentWorkflow />
  </div>
</template>

<script setup lang="ts">
import AgentWorkflow from "@/components/AgentWorkflow.vue";
import { useReviewStore } from "@/stores/review";
const store = useReviewStore();
</script>
