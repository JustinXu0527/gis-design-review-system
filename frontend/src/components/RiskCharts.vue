<template>
  <section class="chart-row">
    <el-card class="module-card chart-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h2>风险统计</h2>
            <span>
              规则命中 {{ ruleCounts.total }} 条；风险位置 {{ locationCounts.total }} 处（地图已定位 {{ mappedLocationCounts.total }} 处）
            </span>
          </div>
        </div>
      </template>
      <div class="risk-chart-pair">
        <section class="risk-donut-panel">
          <strong>规则命中</strong>
          <div ref="riskChartEl" class="risk-donut-chart"></div>
        </section>
        <section class="risk-donut-panel">
          <strong>风险位置</strong>
          <div ref="locationChartEl" class="risk-donut-chart"></div>
        </section>
      </div>
    </el-card>

    <el-card class="module-card chart-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h2>对象类型</h2>
            <span>GIS 图层对象构成</span>
          </div>
        </div>
      </template>
      <div ref="objectChartEl" class="chart-box"></div>
    </el-card>

    <el-card class="module-card chart-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h2>规则来源</h2>
            <span>点击来源筛选 GIS 风险地图</span>
          </div>
        </div>
      </template>
      <div ref="sourceChartEl" class="chart-box"></div>
    </el-card>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts";
import type { ECharts } from "echarts";
import { useRouter } from "vue-router";

import { useReviewStore } from "@/stores/review";
import { groupCount, objectTypeLabel, riskCounts } from "@/utils/format";
import { riskLocationCounts } from "@/utils/riskLocations";

const store = useReviewStore();
const router = useRouter();
const riskChartEl = ref<HTMLDivElement | null>(null);
const locationChartEl = ref<HTMLDivElement | null>(null);
const objectChartEl = ref<HTMLDivElement | null>(null);
const sourceChartEl = ref<HTMLDivElement | null>(null);
let riskChart: ECharts | undefined;
let locationChart: ECharts | undefined;
let objectChart: ECharts | undefined;
let sourceChart: ECharts | undefined;
const ruleCounts = computed(() => riskCounts(store.risks));
const locationCounts = computed(() => riskLocationCounts(store.risks));
const mappedLocationCounts = computed(() => riskLocationCounts(store.risks, true));
const objectTypeEntries = computed(() =>
  Object.entries(groupCount(store.objects, (item) => item.type || "unknown")).sort((a, b) => b[1] - a[1]).slice(0, 8),
);
const ruleSourceEntries = computed(() =>
  Object.entries(groupCount(store.risks, (risk) => risk.clause?.standard_name || "未注明来源"))
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8),
);

onMounted(() => {
  if (riskChartEl.value) riskChart = echarts.init(riskChartEl.value);
  if (locationChartEl.value) locationChart = echarts.init(locationChartEl.value);
  if (objectChartEl.value) objectChart = echarts.init(objectChartEl.value);
  if (sourceChartEl.value) sourceChart = echarts.init(sourceChartEl.value);
  riskChart?.on("click", (params) => openRiskLevel(String(params.name || "")));
  locationChart?.on("click", (params) => openRiskLevel(String(params.name || "")));
  objectChart?.on("click", (params) => openObjectType(params.dataIndex));
  sourceChart?.on("click", (params) => openRuleSource(params.dataIndex));
  renderCharts();
  window.addEventListener("resize", resizeCharts);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", resizeCharts);
  riskChart?.dispose();
  locationChart?.dispose();
  objectChart?.dispose();
  sourceChart?.dispose();
});

watch(
  () => [store.risks, store.objects],
  () => renderCharts(),
  { deep: true },
);

function resizeCharts(): void {
  riskChart?.resize();
  locationChart?.resize();
  objectChart?.resize();
  sourceChart?.resize();
}

function renderCharts(): void {
  const counts = ruleCounts.value;
  const pieOption = (data: Array<{ name: string; value: number }>) => ({
    color: ["#c0392b", "#b9770e", "#0f766e", "#8a94a6"],
    tooltip: { trigger: "item" },
    legend: { bottom: 0, itemWidth: 9, itemHeight: 9, textStyle: { fontSize: 10 } },
    series: [
      {
        type: "pie",
        radius: ["46%", "70%"],
        center: ["50%", "46%"],
        label: { show: false },
        data: data.filter((item) => item.value),
      },
    ],
  });
  riskChart?.setOption(
    pieOption([
      { name: "高风险", value: counts.high },
      { name: "中风险", value: counts.medium },
      { name: "低风险", value: counts.low },
      { name: "未定级", value: counts.unknown },
    ]),
  );
  const locations = locationCounts.value;
  locationChart?.setOption(
    pieOption([
      { name: "高风险", value: locations.high },
      { name: "中风险", value: locations.medium },
      { name: "低风险", value: locations.low },
      { name: "未定级", value: locations.unknown },
    ]),
  );

  const entries = objectTypeEntries.value;
  objectChart?.setOption({
    color: ["#147a72"],
    grid: { left: 12, right: 12, top: 16, bottom: 20, containLabel: true },
    tooltip: { trigger: "axis" },
    xAxis: { type: "value", splitLine: { lineStyle: { color: "#edf2f7" } } },
    yAxis: {
      type: "category",
      data: entries.map(([type]) => objectTypeLabel(type)),
      axisTick: { show: false },
      axisLabel: { width: 128, overflow: "truncate" },
    },
    series: [
      {
        type: "bar",
        data: entries.map(([, value]) => value),
        barWidth: 14,
        itemStyle: { borderRadius: [0, 6, 6, 0] },
      },
    ],
  });

  const sourceEntries = ruleSourceEntries.value;
  sourceChart?.setOption({
    color: ["#2f73b8"],
    grid: { left: 12, right: 18, top: 16, bottom: 20, containLabel: true },
    tooltip: { trigger: "axis" },
    xAxis: { type: "value", splitLine: { lineStyle: { color: "#edf2f7" } } },
    yAxis: {
      type: "category",
      inverse: true,
      data: sourceEntries.map(([name]) => name),
      axisTick: { show: false },
      axisLabel: { width: 118, overflow: "truncate" },
    },
    series: [
      {
        type: "bar",
        data: sourceEntries.map(([, value]) => value),
        barWidth: 14,
        itemStyle: { borderRadius: [0, 6, 6, 0] },
      },
    ],
  });
}

function openRiskLevel(name: string): void {
  const filters: Record<string, "high" | "medium" | "low"> = { 高风险: "high", 中风险: "medium", 低风险: "low" };
  store.setRiskFilter(filters[name] || "all");
  store.setMapStandardFilter("");
  store.setMapObjectTypeFilter("");
  router.push("/map");
}

function openObjectType(dataIndex?: number): void {
  const objectType = objectTypeEntries.value[dataIndex ?? -1]?.[0] || "";
  store.setRiskFilter("all");
  store.setMapStandardFilter("");
  store.setMapObjectTypeFilter(objectType);
  router.push("/map");
}

function openRuleSource(dataIndex?: number): void {
  const standardName = ruleSourceEntries.value[dataIndex ?? -1]?.[0] || "";
  store.setRiskFilter("all");
  store.setMapObjectTypeFilter("");
  store.setMapStandardFilter(standardName === "未注明来源" ? "" : standardName);
  router.push("/map");
}
</script>
