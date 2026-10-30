<template>
  <div class="page-view map-view">
    <section class="page-intro compact-intro">
      <div><span class="page-kicker">SPATIAL EVIDENCE</span><h2>GIS 风险地图</h2><p>按 QGIS 工程样式查看设计成果，并将规则风险聚合到可定位的工程位置。</p></div>
      <el-button type="primary" plain :icon="Warning" :disabled="!store.risks.length" @click="router.push('/risks')">查看风险清单</el-button>
    </section>
    <RiskMap :map-height="mapHeight" />
    <el-card v-if="store.selectedRisk" class="module-card map-selection-bar" shadow="never">
      <div class="map-selection-content">
        <div class="map-selection-heading">
          <span class="map-selection-eyebrow">当前选中风险</span>
          <div><el-tag :type="levelType(store.selectedRisk.level)">{{ levelLabel(store.selectedRisk.level) }}</el-tag><strong>{{ store.selectedRisk.title }}</strong></div>
          <small>{{ store.selectedRisk.evidence?.object_ids?.join("、") || "未绑定工程对象" }}</small>
        </div>
        <p>{{ store.selectedRisk.description || '已在地图中突出显示当前风险位置。' }}</p>
        <el-button type="primary" text @click="router.push('/risks')">查看证据与整改建议</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { Warning } from "@element-plus/icons-vue";
import { useRouter } from "vue-router";

import RiskMap from "@/components/RiskMap.vue";
import { useReviewStore } from "@/stores/review";
import { levelLabel, levelType } from "@/utils/format";

const store = useReviewStore();
const router = useRouter();
const mapHeight = ref(Math.max(500, window.innerHeight - 255));

function resizeMap(): void {
  mapHeight.value = Math.max(500, window.innerHeight - 255);
}

onMounted(() => window.addEventListener("resize", resizeMap));
onBeforeUnmount(() => window.removeEventListener("resize", resizeMap));
</script>
