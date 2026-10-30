<template>
  <el-config-provider namespace="el">
    <div class="app-shell">
      <AppHeader :collapsed="false" />
      <main class="dashboard-grid" v-loading="store.loading.boot">
        <aside class="left-rail">
          <ProjectWorkbench />
          <StandardLibrary />
        </aside>

        <section class="main-stage">
          <RiskMap :map-height="mapHeight" />
          <div
            class="map-resizer"
            role="separator"
            aria-label="调整地图高度"
            aria-orientation="horizontal"
            title="拖动调整地图高度，双击恢复最小高度"
            @pointerdown="startMapResize"
            @dblclick="resetMapHeight"
          >
            <span></span>
          </div>
          <RiskCharts />
          <ReviewResults />
        </section>

        <aside class="right-rail">
          <ReviewSidePanel />
        </aside>
      </main>
    </div>
  </el-config-provider>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import AppHeader from "@/components/AppHeader.vue";
import ProjectWorkbench from "@/components/ProjectWorkbench.vue";
import ReviewResults from "@/components/ReviewResults.vue";
import ReviewSidePanel from "@/components/ReviewSidePanel.vue";
import RiskCharts from "@/components/RiskCharts.vue";
import RiskMap from "@/components/RiskMap.vue";
import StandardLibrary from "@/components/StandardLibrary.vue";
import { useReviewStore } from "@/stores/review";
import { errorMessage } from "@/utils/error";

const store = useReviewStore();
const minimumMapHeight = 338;
const mapHeight = ref(minimumMapHeight);
let resizeStartY = 0;
let resizeStartHeight = minimumMapHeight;

function maxMapHeight(): number {
  return Math.max(minimumMapHeight, window.innerHeight - 170);
}

function startMapResize(event: PointerEvent): void {
  resizeStartY = event.clientY;
  resizeStartHeight = mapHeight.value;
  document.body.classList.add("map-resizing");
  window.addEventListener("pointermove", resizeMap);
  window.addEventListener("pointerup", stopMapResize, { once: true });
}

function resizeMap(event: PointerEvent): void {
  mapHeight.value = Math.min(maxMapHeight(), Math.max(minimumMapHeight, resizeStartHeight + event.clientY - resizeStartY));
}

function stopMapResize(): void {
  document.body.classList.remove("map-resizing");
  window.removeEventListener("pointermove", resizeMap);
}

function resetMapHeight(): void {
  mapHeight.value = minimumMapHeight;
}

onMounted(async () => {
  try {
    await store.boot();
  } catch (error) {
    ElMessage.error(errorMessage(error));
  }
});

onBeforeUnmount(() => {
  stopMapResize();
});
</script>
