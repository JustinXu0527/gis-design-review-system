<template>
  <el-card class="module-card project-records-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div><h2>项目记录</h2><span>打开已有工程或清理历史项目</span></div>
        <el-tag type="info">{{ store.projects.length }} 个项目</el-tag>
      </div>
    </template>

    <el-collapse v-model="expanded" class="project-record-collapse">
      <el-collapse-item name="records">
        <template #title>
          <div class="record-collapse-title">
            <span>历史项目</span>
            <small>{{ expanded.includes('records') ? '收起列表' : '展开列表' }}</small>
          </div>
        </template>
        <el-empty v-if="!store.projects.length" description="暂无项目" :image-size="68" />
        <el-scrollbar v-else max-height="320px">
          <article
            v-for="project in store.projects"
            :key="project.id"
            class="project-row"
            :class="{ active: project.id === store.currentProject?.id }"
          >
            <button class="project-open-button" type="button" @click="openProject(project.id)">
              <strong>{{ project.name }}</strong>
              <small>{{ project.object_count || 0 }} 对象，{{ project.risk_count || 0 }} 风险</small>
            </button>
            <el-button text type="danger" size="small" @click="removeProject(project)">删除</el-button>
          </article>
        </el-scrollbar>
      </el-collapse-item>
    </el-collapse>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ElMessage } from "element-plus";

import { useReviewStore } from "@/stores/review";
import type { ProjectListItem } from "@/types";
import { errorMessage } from "@/utils/error";

const store = useReviewStore();
const expanded = ref<string[]>(["records"]);

async function openProject(projectId: string): Promise<void> {
  try {
    await store.openProject(projectId);
  } catch (error) {
    ElMessage.error(errorMessage(error));
  }
}

async function removeProject(project: ProjectListItem): Promise<void> {
  try {
    await store.removeProject(project);
    ElMessage.success("项目已删除");
  } catch (error) {
    const message = errorMessage(error);
    if (!message.includes("cancel")) ElMessage.error(message || "已取消");
  }
}
</script>
