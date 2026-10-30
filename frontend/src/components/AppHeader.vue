<template>
  <header class="app-header">
    <div class="header-context">
      <el-button class="sidebar-toggle" :icon="collapsed ? Expand : Fold" circle @click="$emit('toggle-sidebar')" />
      <div>
        <p class="header-eyebrow">通信基建 GIS 设计智能审查系统</p>
        <h1>{{ pageTitle }}</h1>
        <p class="header-project">{{ store.currentProject?.name || "尚未打开工程项目" }}</p>
      </div>
    </div>
    <div class="runtime-strip">
      <el-tag :type="localStatus.type" effect="dark">{{ localStatus.text }}</el-tag>
      <el-tag effect="plain">LLM：{{ local.llm_model || "qwen2.5:32b" }}</el-tag>
      <el-tag effect="plain">Embedding：{{ local.embed_model || "bge-m3" }}</el-tag>
      <el-tag effect="plain">Agent：{{ store.config?.agent_framework?.framework || "langgraph" }}</el-tag>
      <el-tag effect="plain">API：{{ store.config?.api_framework || "fastapi" }}</el-tag>
      <el-button :icon="Refresh" circle @click="refresh" :loading="store.loading.boot" />
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { Expand, Fold, Refresh } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { useRoute } from "vue-router";

import { useReviewStore } from "@/stores/review";
import { errorMessage } from "@/utils/error";

const store = useReviewStore();
const route = useRoute();
defineProps<{ collapsed: boolean }>();
defineEmits<{ (event: "toggle-sidebar"): void }>();
const local = computed(() => store.config?.local_llm || {});
const pageTitle = computed(() => String(route.meta.title || "智能审查工作台"));
const localStatus = computed(() => {
  if (local.value.available) return { type: "success", text: "本地 Ollama 在线" };
  return { type: "warning", text: "本地 Ollama 未连接" };
});

async function refresh() {
  try {
    await store.boot();
    ElMessage.success("已刷新");
  } catch (error) {
    ElMessage.error(errorMessage(error));
  }
}
</script>
