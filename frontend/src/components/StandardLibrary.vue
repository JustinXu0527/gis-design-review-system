<template>
  <el-card class="module-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <h2>标准知识库</h2>
          <span>后端维护，只读展示</span>
        </div>
        <el-tag>{{ store.standards.length }} 个库</el-tag>
      </div>
    </template>

    <el-alert
      class="readonly-alert"
      type="info"
      :closable="false"
      title="标准知识库和规则库由后端维护，前端只负责调用和展示。"
    />

    <el-empty v-if="!store.standards.length" description="暂无标准库" :image-size="80" />
    <el-scrollbar v-else max-height="360px">
      <el-collapse class="standard-collapse" accordion>
        <el-collapse-item v-for="item in store.standards" :key="item.file" :name="item.file">
          <template #title>
            <div class="standard-title">
              <strong>{{ item.file }}</strong>
              <el-tag size="small" type="success">{{ item.clause_count || 0 }} 条款</el-tag>
            </div>
          </template>
          <div class="standard-meta">
            <p>{{ (item.standards || []).join("、") || item.source_file || "行业标准" }}</p>
            <dl>
              <dt>规则</dt>
              <dd>{{ item.rule_count || 0 }} 条，{{ item.computable_rule_count || 0 }} 条可计算</dd>
              <dt>风险</dt>
              <dd>{{ riskLevelText(item.risk_level_counts || {}) }}</dd>
              <dt>类型</dt>
              <dd>{{ (item.rule_types || []).map(ruleTypeLabel).join("、") || "未识别" }}</dd>
            </dl>
          </div>
        </el-collapse-item>
      </el-collapse>
    </el-scrollbar>
  </el-card>
</template>

<script setup lang="ts">
import { useReviewStore } from "@/stores/review";
import { ruleTypeLabel } from "@/utils/format";

const store = useReviewStore();

function riskLevelText(counts: Record<string, number>) {
  return `高 ${counts.high || 0} / 中 ${counts.medium || 0} / 低 ${counts.low || 0}`;
}
</script>
