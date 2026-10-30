<template>
  <div class="page-view risks-view">
    <section class="page-intro compact-intro">
      <div><span class="page-kicker">RISK & EVIDENCE</span><h2>风险位置与证据链</h2><p>按位置聚合规则问题，查看计算证据、标准条款、知识图谱与整改路径。</p></div>
      <el-button type="primary" plain :icon="MapLocation" :disabled="!store.selectedRisk" @click="locateOnMap">在地图中定位</el-button>
    </section>
    <ReviewResults />
  </div>
</template>

<script setup lang="ts">
import { MapLocation } from "@element-plus/icons-vue";
import { useRouter } from "vue-router";
import ReviewResults from "@/components/ReviewResults.vue";
import { useReviewStore } from "@/stores/review";

const store = useReviewStore();
const router = useRouter();
function locateOnMap(): void {
  if (store.selectedRiskId) store.focusRisk(store.selectedRiskId);
  router.push("/map");
}
</script>
