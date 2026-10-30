<template>
  <div class="page-view reports-view">
    <section class="page-intro compact-intro">
      <div><span class="page-kicker">DELIVERABLE CENTER</span><h2>报告与审查成果</h2><p>统一导出风险清单、空间标注、规则日志与可归档审查报告。</p></div>
    </section>
    <section class="report-format-grid">
      <button v-for="item in formats" :key="item.format" class="report-format-card" :disabled="!store.currentProject" @click="store.exportCurrentProject(item.format)">
        <el-icon><component :is="item.icon" /></el-icon><strong>{{ item.title }}</strong><span>{{ item.description }}</span><small>{{ item.extension }}</small>
      </button>
    </section>
    <el-card class="module-card report-log-card" shadow="never">
      <template #header><div class="card-header"><div><h2>规则执行记录</h2><span>{{ store.executionLog.length }} 条规则日志</span></div></div></template>
      <el-table :data="store.executionLog" height="420" empty-text="执行审查后显示规则日志">
        <el-table-column prop="standard_name" label="标准来源" min-width="260" show-overflow-tooltip />
        <el-table-column prop="clause_id" label="条款" width="150" />
        <el-table-column label="规则类型" min-width="150"><template #default="{ row }">{{ ruleTypeLabel(row.rule_type) }}</template></el-table-column>
        <el-table-column prop="finding_count" label="风险数" width="100" align="center" />
        <el-table-column label="执行状态" width="120"><template #default="{ row }"><el-tag :type="row.computable ? 'success' : 'info'">{{ row.computable ? '已计算' : '人工复核' }}</el-tag></template></el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { markRaw } from "vue";
import { Document, Files, Location, Memo, Tickets } from "@element-plus/icons-vue";
import { useReviewStore } from "@/stores/review";
import { ruleTypeLabel } from "@/utils/format";

const store = useReviewStore();
const formats = [
  { format: "pdf", title: "综合审查报告", description: "适合归档、打印与正式提交", extension: "PDF", icon: markRaw(Document) },
  { format: "docx", title: "可编辑报告", description: "用于补充说明与人工复核", extension: "WORD", icon: markRaw(Memo) },
  { format: "xlsx", title: "风险数据表", description: "便于筛选、统计和问题闭环", extension: "EXCEL", icon: markRaw(Tickets) },
  { format: "geojson", title: "空间风险标注", description: "返回 QGIS 或 WebGIS 定位核查", extension: "GEOJSON", icon: markRaw(Location) },
  { format: "log", title: "规则执行日志", description: "追溯规则可执行性与命中数量", extension: "JSON", icon: markRaw(Files) },
];
</script>
