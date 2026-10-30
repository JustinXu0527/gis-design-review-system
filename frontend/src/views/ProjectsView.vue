<template>
  <div class="page-view projects-view">
    <section class="page-intro compact-intro">
      <div><span class="page-kicker">PROJECT WORKSPACE</span><h2>项目与 GIS 成果管理</h2><p>创建工程项目，上传设计成果并完成图层读取。</p></div>
    </section>
    <section class="project-page-grid">
      <ProjectWorkbench />
      <el-card class="module-card project-process-card" shadow="never">
        <template #header><div class="card-header"><div><h2>工程接入流程</h2><span>四步进入智能审查</span></div></div></template>
        <el-steps direction="vertical" :active="activeStep" finish-status="success">
          <el-step title="创建或打开项目" description="每个项目独立保存工程文件、对象和审查记录" />
          <el-step title="上传 GIS 设计成果" description="支持 GPKG、GeoJSON、Shapefile、ZIP 与 RAR 工程包" />
          <el-step title="读取并标准化图层" description="统一工程对象、属性字段、坐标系与几何信息" />
          <el-step title="执行智能审查" description="运行规则引擎、LangGraph、知识图谱与 QGIS MCP" />
        </el-steps>
      </el-card>
      <div class="project-side-stack">
        <el-card class="module-card" shadow="never">
          <template #header><div class="card-header"><div><h2>当前数据状态</h2><span>{{ store.currentProject?.name || '尚未选择项目' }}</span></div></div></template>
          <div class="data-readiness-grid">
            <div><strong>{{ store.currentProject?.documents?.length || 0 }}</strong><span>工程文件</span></div>
            <div><strong>{{ store.objects.length }}</strong><span>标准对象</span></div>
            <div><strong>{{ store.risks.length }}</strong><span>规则命中</span></div>
          </div>
          <el-alert :closable="false" :type="store.statusType" show-icon><template #title>{{ store.statusMessage }}</template></el-alert>
        </el-card>
        <ProjectRecords />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import ProjectWorkbench from "@/components/ProjectWorkbench.vue";
import ProjectRecords from "@/components/ProjectRecords.vue";
import { useReviewStore } from "@/stores/review";

const store = useReviewStore();
const activeStep = computed(() => {
  if (store.risks.length) return 4;
  if (store.objects.length) return 3;
  if (store.currentProject?.documents?.length) return 2;
  return store.currentProject ? 1 : 0;
});
</script>
