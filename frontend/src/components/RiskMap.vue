<template>
  <section ref="mapShell" class="map-shell" :class="{ 'map-shell-fullscreen': isFullscreen }">
  <el-card class="module-card map-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <h2>GIS 风险地图</h2>
          <span>{{ mapHint }}</span>
        </div>
        <div class="map-tools">
          <el-tag :type="!hasUploadedGisData ? 'info' : qgisAvailable ? 'success' : 'warning'">
            {{ !store.currentProject ? "等待项目" : !hasUploadedGisData ? "等待上传" : qgisAvailable ? "QGIS 原生渲染" : "矢量预览" }}
          </el-tag>
          <el-tag type="success">对象 {{ store.objects.length }}</el-tag>
          <el-tag type="danger">规则命中 {{ store.risks.length }}</el-tag>
          <el-tag type="warning">可定位风险位置 {{ riskLocationCount }}</el-tag>
          <el-switch v-model="showQgisBaseLayers" size="small" inline-prompt active-text="全图" inactive-text="快速" :disabled="!hasUploadedGisData" />
          <el-button size="small" :disabled="!hasUploadedGisData" @click="fitMap">定位全部</el-button>
          <el-button size="small" :disabled="!hasUploadedGisData" @click="reloadMap">刷新地图</el-button>
          <el-button size="small" :icon="isFullscreen ? CloseBold : FullScreen" @click="toggleFullscreen">
            {{ isFullscreen ? "退出全屏" : "全屏" }}
          </el-button>
        </div>
      </div>
    </template>
    <div class="map-filter-bar">
      <div class="map-level-filter">
        <span>风险等级</span>
        <el-segmented v-model="mapRiskFilter" :options="riskFilterOptions" size="small" />
      </div>
      <el-select v-model="mapStandardFilter" clearable filterable placeholder="全部规则来源" size="small">
        <el-option v-for="name in standardOptions" :key="name" :label="name" :value="name" />
      </el-select>
      <el-select v-model="mapObjectTypeFilter" clearable filterable placeholder="全部对象类型" size="small">
        <el-option v-for="item in objectTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <span class="map-filter-summary">当前显示 {{ store.mapFilteredRisks.length }} / {{ store.risks.length }} 条风险</span>
      <el-button size="small" text :disabled="!hasMapFilters" @click="store.clearMapFilters()">重置筛选</el-button>
      <el-button size="small" type="primary" plain :disabled="!store.selectedRisk" @click="openObjectDetails">对象详情</el-button>
    </div>
    <div v-if="qgisStatus?.error && !qgisAvailable" class="map-status">
      {{ qgisStatus.error }}
    </div>
    <div class="map-frame" :style="{ '--map-height': `${effectiveMapHeight}px` }">
      <div ref="mapEl" class="map-canvas"></div>
      <el-popover v-if="hasUploadedGisData" placement="top-end" :width="340" trigger="click" popper-class="map-legend-popper">
        <template #reference>
          <el-button class="map-legend-trigger" circle aria-label="查看审查图例" title="查看审查图例">
            <el-icon><InfoFilled /></el-icon>
          </el-button>
        </template>
        <div class="map-legend" aria-label="地图图例">
          <div class="legend-title">审查图例</div>
          <div class="legend-row"><i class="legend-base-line"></i><span>底图要素：按 .qgz 原始样式显示；图中已有的红线仍可能只是管线符号</span></div>
          <div class="legend-row"><i class="legend-risk-line"></i><span>风险线或风险面：边框按风险等级着色</span></div>
          <div class="legend-row"><i class="legend-dot high"></i><span>高风险</span></div>
          <div class="legend-row"><i class="legend-dot medium"></i><span>中风险</span></div>
          <div class="legend-row"><i class="legend-dot low"></i><span>低风险</span></div>
          <div class="legend-row"><i class="legend-cluster">2</i><span>数字表示聚合的风险位置数，不是规则命中总数</span></div>
        </div>
      </el-popover>
    </div>
  </el-card>
  <el-drawer v-model="detailDrawerOpen" class="map-object-drawer" title="风险对象详情" size="min(520px, 92vw)" append-to-body>
    <el-empty v-if="!selectedLocation" description="请在地图中选择风险位置" :image-size="72" />
    <div v-else class="map-object-detail">
      <div class="object-detail-heading">
        <div>
          <el-tag :type="selectedRiskTagType">{{ selectedRiskLabel }}</el-tag>
          <strong>{{ selectedLocation.risks.length }} 条规则命中</strong>
        </div>
        <span>{{ selectedLocation.objectIds.length }} 个关联对象</span>
      </div>
      <section v-for="object in selectedObjects" :key="object.id" class="object-detail-section">
        <h3>{{ object.name || object.id }}</h3>
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="对象编号">{{ object.id }}</el-descriptions-item>
          <el-descriptions-item label="来源图层">{{ object.properties?.source_layer || '-' }}</el-descriptions-item>
          <el-descriptions-item label="源要素编号">{{ object.properties?.source_feature_id ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="几何类型">{{ object.geometry?.type || object.properties?.geometry_type || '-' }}</el-descriptions-item>
        </el-descriptions>
      </section>
      <section class="object-detail-section">
        <div class="section-title-row"><h3>QGIS MCP 核验</h3><el-tag :type="mcpVerificationType">{{ mcpVerificationLabel }}</el-tag></div>
        <p class="object-detail-note">{{ selectedMcp?.query_method || '当前风险未包含在本轮对象级 MCP 抽检中，正式规则证据不受影响。' }}</p>
        <el-descriptions v-if="selectedMcp?.object_verified" :column="1" border size="small">
          <el-descriptions-item label="QGIS 要素">{{ selectedMcp.qgis_feature_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="验证图层">{{ selectedMcp.layer_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="读取字段">{{ selectedMcp.field_names?.join('、') || '-' }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="mcpFieldEntries.length" class="object-field-grid">
          <div v-for="item in mcpFieldEntries" :key="item.name"><span>{{ item.name }}</span><strong>{{ item.value }}</strong></div>
        </div>
      </section>
      <section class="object-detail-section">
        <h3>命中规则与空间证据</h3>
        <div v-for="risk in selectedLocation.risks" :key="risk.id" class="object-rule-item">
          <div><el-tag :type="riskTagType(risk.level)" size="small">{{ riskLevelLabel(risk.level) }}</el-tag><strong>{{ risk.title }}</strong></div>
          <p>{{ risk.evidence?.calculation || risk.description || '规则证据已绑定到当前对象。' }}</p>
          <small>{{ [risk.clause?.standard_name, risk.clause?.clause_id].filter(Boolean).join(' / ') }}</small>
        </div>
      </section>
    </div>
  </el-drawer>
  <el-dialog v-model="clusterDialogOpen" class="map-cluster-dialog" title="重叠风险位置" width="min(560px, 92vw)" append-to-body>
    <p class="cluster-dialog-note">该聚合点包含 {{ clusterLocations.length }} 个风险位置，请选择需要查看的对象。</p>
    <div class="cluster-location-list">
      <button v-for="location in clusterLocations" :key="location.id" type="button" @click="selectClusterLocation(location)">
        <div>
          <el-tag :type="riskTagType(location.level)" size="small">{{ riskLevelLabel(location.level) }}</el-tag>
          <strong>{{ location.objectIds.join("、") || "未绑定工程对象" }}</strong>
        </div>
        <span>{{ location.risks.length }} 条规则命中</span>
        <p>{{ location.risks.map((risk) => risk.title).filter((title, index, items) => items.indexOf(title) === index).join("；") }}</p>
      </button>
    </div>
  </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onActivated, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { CloseBold, FullScreen, InfoFilled } from "@element-plus/icons-vue";
import GeoJSON from "ol/format/GeoJSON";
import Feature from "ol/Feature";
import OlMap from "ol/Map";
import View from "ol/View";
import Point from "ol/geom/Point";
import ImageLayer from "ol/layer/Image";
import VectorLayer from "ol/layer/Vector";
import { defaults as defaultInteractions } from "ol/interaction/defaults";
import MouseWheelZoom from "ol/interaction/MouseWheelZoom";
import Projection from "ol/proj/Projection";
import { addProjection } from "ol/proj";
import ImageWMS from "ol/source/ImageWMS";
import Cluster from "ol/source/Cluster";
import VectorSource from "ol/source/Vector";
import { Circle as CircleStyle, Fill, Stroke, Style, Text } from "ol/style";
import type { FeatureLike } from "ol/Feature";
import { getCenter } from "ol/extent";
import type { Extent } from "ol/extent";

import { fetchQgisPreviewStatus } from "@/api/client";
import { useReviewStore } from "@/stores/review";
import type { DesignObject, QgisPreviewStatus, RiskFinding, RiskLevel } from "@/types";
import { levelLabel, levelMeta, levelType, objectTypeLabel } from "@/utils/format";
import { groupRisksByLocation, higherRiskLevel, type RiskLocation } from "@/utils/riskLocations";

const props = withDefaults(defineProps<{ mapHeight?: number }>(), {
  mapHeight: 338,
});

const store = useReviewStore();
const mapShell = ref<HTMLElement | null>(null);
const mapEl = ref<HTMLDivElement | null>(null);
const isFullscreen = ref(false);
const detailDrawerOpen = ref(false);
const clusterDialogOpen = ref(false);
const clusterLocations = ref<RiskLocation[]>([]);
const viewportHeight = ref(window.innerHeight);
const effectiveMapHeight = computed(() => (isFullscreen.value ? Math.max(420, viewportHeight.value - 92) : props.mapHeight));
const qgisStatus = ref<QgisPreviewStatus | null>(store.currentProject?.documents?.length ? store.currentProject.qgis_preview || null : null);
const riskLocationCount = ref(0);
let map: OlMap | undefined;
let qgisLayer: ImageLayer<ImageWMS> | undefined;
let objectLayer: VectorLayer<VectorSource> | undefined;
let riskShapeLayer: VectorLayer<VectorSource> | undefined;
let riskPointLayer: VectorLayer<Cluster> | undefined;
let riskPointSource: VectorSource | undefined;
let selectedRiskLayer: VectorLayer<VectorSource> | undefined;
let selectedRiskSource: VectorSource | undefined;

const hasUploadedGisData = computed(() => Boolean(store.currentProject?.documents?.length));
const qgisAvailable = computed(() => Boolean(hasUploadedGisData.value && qgisStatus.value?.available && qgisStatus.value?.wms_layers));
const showQgisBaseLayers = ref(false);
const riskFilterOptions = [
  { label: "全部", value: "all" },
  { label: "高", value: "high" },
  { label: "中", value: "medium" },
  { label: "低", value: "low" },
];
const mapRiskFilter = computed({
  get: () => store.riskFilter,
  set: (value: "all" | "high" | "medium" | "low") => store.setRiskFilter(value),
});
const mapStandardFilter = computed({
  get: () => store.mapStandardFilter,
  set: (value: string) => store.setMapStandardFilter(value || ""),
});
const mapObjectTypeFilter = computed({
  get: () => store.mapObjectTypeFilter,
  set: (value: string) => store.setMapObjectTypeFilter(value || ""),
});
const standardOptions = computed(() =>
  [...new Set(store.risks.map((risk) => risk.clause?.standard_name).filter((value): value is string => Boolean(value)))].sort(),
);
const objectTypeOptions = computed(() =>
  [...new Set(store.objects.map((object) => object.type).filter(Boolean))]
    .map((value) => ({ value, label: objectTypeLabel(value) }))
    .sort((a, b) => a.label.localeCompare(b.label, "zh-CN")),
);
const hasMapFilters = computed(() => store.riskFilter !== "all" || Boolean(store.mapStandardFilter || store.mapObjectTypeFilter));
const selectedLocation = computed(() =>
  groupRisksByLocation(store.risks).find((location) => location.risks.some((risk) => risk.id === store.selectedRiskId)) || null,
);
const selectedObjects = computed(() => {
  const ids = new Set(selectedLocation.value?.objectIds || []);
  return store.objects.filter((object) => ids.has(object.id));
});
const selectedMcp = computed(() => {
  const remediations = (selectedLocation.value?.risks || []).map((risk) => risk.mcp_remediation).filter(Boolean);
  return remediations.find((item) => item?.object_verified) || store.selectedRisk?.mcp_remediation || remediations[0] || null;
});
const selectedRiskLabel = computed(() => levelLabel(store.selectedRisk?.level));
const selectedRiskTagType = computed(() => levelType(store.selectedRisk?.level));
const mcpVerificationType = computed<"success" | "info">(() => (selectedMcp.value?.object_verified ? "success" : "info"));
const mcpVerificationLabel = computed(() => (selectedMcp.value?.object_verified ? "QGIS MCP 已验证" : "等待对象级核验"));
const mcpFieldEntries = computed(() =>
  Object.entries(selectedMcp.value?.fields || {}).map(([name, value]) => ({ name, value: displayFieldValue(value) })),
);
const activeWmsLayers = computed(() => {
  if (!qgisStatus.value) return "";
  return showQgisBaseLayers.value ? qgisStatus.value.wms_layers || "" : qgisStatus.value.render_wms_layers || qgisStatus.value.wms_layers || "";
});
const mapHint = computed(() => {
  if (!store.currentProject) return "请先创建或打开项目";
  if (!hasUploadedGisData.value) return "请上传 GIS 设计成果并读取图层";
  if (qgisAvailable.value) return "QGIS Server 按 .qgz 项目样式渲染，风险结果叠加显示";
  if (!store.objects.length) return "等待 GIS 图层";
  return "当前未连接 QGIS Server，使用前端矢量预览";
});

onMounted(async () => {
  document.addEventListener("fullscreenchange", handleFullscreenChange);
  window.addEventListener("resize", handleWindowResize);
  await loadQgisStatus();
  if (!mapEl.value) return;
  objectLayer = new VectorLayer({
    source: new VectorSource(),
    style: objectStyle,
    visible: !qgisAvailable.value,
  });
  riskShapeLayer = new VectorLayer({
    source: new VectorSource(),
    style: riskShapeStyle,
    declutter: true,
    zIndex: 20,
  });
  riskPointSource = new VectorSource();
  riskPointLayer = new VectorLayer({
    source: new Cluster({ distance: 42, minDistance: 18, source: riskPointSource }),
    style: riskClusterStyle,
    declutter: true,
    zIndex: 30,
  });
  selectedRiskSource = new VectorSource();
  selectedRiskLayer = new VectorLayer({
    source: selectedRiskSource,
    style: selectedRiskStyle,
    zIndex: 40,
  });
  qgisLayer = createQgisLayer();
  map = new OlMap({
    target: mapEl.value,
    layers: [qgisLayer, objectLayer, riskShapeLayer, riskPointLayer, selectedRiskLayer].filter(Boolean) as Array<
      ImageLayer<ImageWMS> | VectorLayer<VectorSource> | VectorLayer<Cluster>
    >,
    view: new View({
      projection: previewProjection(),
      center: [0, 0],
      zoom: 2,
      constrainResolution: true,
    }),
    controls: [],
    interactions: defaultInteractions({ mouseWheelZoom: false, zoomDuration: 0 }).extend([
      new MouseWheelZoom({ duration: 0, constrainResolution: true }),
    ]),
  });
  map.on("singleclick", selectRiskFromMap);
  renderLayers();
  if (store.selectedRiskFocusToken && store.selectedRisk) detailDrawerOpen.value = true;
});

onBeforeUnmount(() => {
  document.removeEventListener("fullscreenchange", handleFullscreenChange);
  window.removeEventListener("resize", handleWindowResize);
  if (map) map.setTarget(undefined);
});

onActivated(async () => {
  await nextTick();
  map?.updateSize();
  focusSelectedRisk(false);
});

watch(
  () => [store.objects, store.risks, store.riskFilter, store.mapStandardFilter, store.mapObjectTypeFilter],
  () => renderLayers(),
  { deep: true },
);

watch(qgisAvailable, () => {
  objectLayer?.setVisible(!qgisAvailable.value);
});

watch(showQgisBaseLayers, () => {
  refreshQgisLayer();
  fitMap();
});

watch(
  () => store.selectedRiskFocusToken,
  () => {
    focusSelectedRisk(true);
    if (store.selectedRisk) detailDrawerOpen.value = true;
  },
);

watch(
  () => store.selectedRiskId,
  () => focusSelectedRisk(false),
);

watch(
  () => props.mapHeight,
  async () => {
    await nextTick();
    map?.updateSize();
  },
);

watch(
  () => [
    store.currentProject?.id,
    store.currentProject?.documents?.length,
    store.currentProject?.qgis_preview?.updated_at,
    store.currentProject?.qgis_preview?.host_project_file,
  ],
  async () => {
    await loadQgisStatus();
    syncMapViewProjection();
    refreshQgisLayer();
    renderLayers();
  },
);

async function loadQgisStatus(): Promise<void> {
  const projectId = store.currentProject?.id;
  if (!projectId || !hasUploadedGisData.value) {
    qgisStatus.value = null;
    return;
  }
  try {
    const status = await fetchQgisPreviewStatus(projectId);
    if (store.currentProject?.id === projectId) qgisStatus.value = status;
  } catch (error) {
    if (store.currentProject?.id === projectId) {
      qgisStatus.value = { available: false, error: error instanceof Error ? error.message : "QGIS 预览状态读取失败" };
    }
  }
}

function refreshQgisLayer(): void {
  if (!map) return;
  if (qgisLayer) {
    map.removeLayer(qgisLayer);
    qgisLayer = undefined;
  }
  qgisLayer = createQgisLayer();
  if (qgisLayer) {
    map.getLayers().insertAt(0, qgisLayer);
  }
  objectLayer?.setVisible(!qgisAvailable.value);
}

function createQgisLayer(): ImageLayer<ImageWMS> | undefined {
  if (!store.currentProject || !qgisAvailable.value || !qgisStatus.value?.wms_proxy_url || !activeWmsLayers.value) return undefined;
  const params = {
    LAYERS: activeWmsLayers.value,
    FORMAT: "image/png",
    TRANSPARENT: true,
    VERSION: "1.3.0",
    PREVIEW_REVISION: qgisStatus.value.updated_at || qgisStatus.value.host_project_file || "base",
  };
  const source = new ImageWMS({
    url: qgisStatus.value.wms_proxy_url,
    params,
    ratio: 1,
    serverType: "qgis",
  });
  return new ImageLayer({
    source,
  });
}

function reloadMap(): void {
  refreshQgisLayer();
  fitMap();
}

async function toggleFullscreen(): Promise<void> {
  if (!document.fullscreenElement) {
    await mapShell.value?.requestFullscreen();
  } else {
    await document.exitFullscreen();
  }
}

function handleFullscreenChange(): void {
  isFullscreen.value = document.fullscreenElement === mapShell.value;
  nextTick(() => map?.updateSize());
}

function handleWindowResize(): void {
  viewportHeight.value = window.innerHeight;
  map?.updateSize();
}

function selectRiskFromMap(event: { pixel: number[] }): void {
  if (!map) return;
  const feature = map.forEachFeatureAtPixel(event.pixel, (candidate, layer) => {
    if (layer !== riskPointLayer && layer !== riskShapeLayer) return undefined;
    return candidate;
  }, { hitTolerance: 14 });
  if (!feature) return;
  const clusterItems = feature.get("features") as FeatureLike[] | undefined;
  const candidates = clusterItems?.length ? clusterItems : [feature];
  if (candidates.length > 1) {
    const riskIds = new Set(candidates.flatMap((candidate) => (candidate.get("risk_ids") as string[] | undefined) || []));
    clusterLocations.value = groupRisksByLocation(store.mapFilteredRisks).filter((location) =>
      location.risks.some((risk) => riskIds.has(risk.id)),
    );
    if (clusterLocations.value.length > 1) {
      clusterDialogOpen.value = true;
      return;
    }
  }
  const sourceFeature = candidates.find((candidate) => {
    const ids = candidate.get("risk_ids") as string[] | undefined;
    return Boolean(ids?.length && !ids.includes(store.selectedRiskId));
  }) || candidates[0];
  const riskIds = sourceFeature.get("risk_ids") as string[] | undefined;
  const riskId = riskIds?.[0] || sourceFeature.get("id");
  if (riskId) {
    store.selectRisk(String(riskId));
    detailDrawerOpen.value = true;
  }
}

function selectClusterLocation(location: RiskLocation): void {
  const riskId = location.risks[0]?.id;
  if (!riskId) return;
  store.selectRisk(riskId);
  clusterDialogOpen.value = false;
  detailDrawerOpen.value = true;
}

function openObjectDetails(): void {
  if (store.selectedRisk) detailDrawerOpen.value = true;
}

function riskTagType(level: RiskLevel) {
  return levelType(level);
}

function riskLevelLabel(level: RiskLevel): string {
  return levelLabel(level);
}

function displayFieldValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "空";
  const text = typeof value === "object" ? JSON.stringify(value) : String(value);
  return text.length > 52 ? `${text.slice(0, 52)}...` : text;
}

function previewProjection(): Projection | undefined {
  const code = qgisStatus.value?.crs;
  if (!code || code === "EPSG:3857") return undefined;
  const projection = new Projection({ code, units: "m" });
  addProjection(projection);
  return projection;
}

function syncMapViewProjection(): void {
  if (!map) return;
  const expectedCode = store.currentProject ? qgisStatus.value?.crs || "EPSG:3857" : "EPSG:3857";
  if (map.getView().getProjection().getCode() === expectedCode) return;
  map.setView(
    new View({
      projection: store.currentProject ? previewProjection() : undefined,
      center: [0, 0],
      zoom: 2,
      constrainResolution: true,
    }),
  );
}

function renderLayers(): void {
  if (!objectLayer || !riskShapeLayer || !riskPointSource) return;
  const objectSource = objectLayer.getSource();
  const riskSource = riskShapeLayer.getSource();
  if (!objectSource || !riskSource) return;
  objectSource.clear();
  riskSource.clear();
  riskPointSource.clear();
  selectedRiskSource?.clear();
  if (!store.currentProject) {
    riskLocationCount.value = 0;
    map?.getView().setCenter([0, 0]);
    map?.getView().setZoom(2);
    return;
  }
  if (!qgisAvailable.value) {
    objectSource.addFeatures(readFeatures(objectsToFeatureCollection(store.objects, "object")));
  }
  const groupedRisks = groupRisksByLocation(store.mapFilteredRisks);
  const locatedRisks = groupedRisks.filter((group) => group.geometry);
  riskLocationCount.value = locatedRisks.length;
  const riskFeatures = readFeatures(groupedRisksToFeatureCollection(locatedRisks));
  const shapeFeatures = riskFeatures.filter((feature) => feature.getGeometry()?.getType() !== "Point");
  const pointFeatures = riskFeatures.map(riskMarkerFeature);
  riskSource.addFeatures(shapeFeatures);
  riskPointSource.addFeatures(pointFeatures);
  fitMap();
  focusSelectedRisk(false);
}

function focusSelectedRisk(moveView = true): void {
  if (!map || !selectedRiskSource || !store.selectedRiskId) return;
  const location = groupRisksByLocation(store.risks).find((group) => group.risks.some((risk) => risk.id === store.selectedRiskId));
  selectedRiskSource.clear();
  if (!location?.geometry) return;
  const [feature] = readFeatures(groupedRisksToFeatureCollection([location]));
  if (!feature) return;
  selectedRiskSource.addFeature(riskMarkerFeature(feature));
  if (!moveView) return;
  const geometry = feature.getGeometry();
  if (!geometry) return;
  const extent = geometry.getExtent();
  const view = map.getView();
  if (extent[0] === extent[2] && extent[1] === extent[3]) {
    view.animate({ center: getCenter(extent), zoom: Math.max(view.getZoom() || 0, 17), duration: 350 });
    return;
  }
  view.fit(extent, { padding: [72, 72, 72, 72], maxZoom: 17, duration: 350 });
}

function readFeatures(collection: GeoJSON.FeatureCollection) {
  return new GeoJSON().readFeatures(collection);
}

function objectsToFeatureCollection(items: Array<DesignObject | RiskFinding>, kind: "object" | "risk"): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: (items || [])
      .filter((item) => item.geometry)
      .map((item) => ({
        type: "Feature",
        properties: featureProperties(item, kind),
        geometry: item.geometry as GeoJSON.Geometry,
      })),
  };
}

function featureProperties(item: DesignObject | RiskFinding, kind: "object" | "risk"): GeoJSON.GeoJsonProperties {
  if (kind === "object") {
    const object = item as DesignObject;
    return {
      id: object.id,
      name: object.name,
      type: object.type,
      kind,
    };
  }
  const risk = item as RiskFinding;
  return {
    id: risk.id,
    name: risk.title,
    type: risk.category,
    level: risk.level,
    kind,
  };
}

function groupedRisksToFeatureCollection(groups: RiskLocation[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: groups
      .filter((group) => group.geometry)
      .map((group) => ({
        type: "Feature",
        properties: {
          id: group.id,
          name: group.risks.length > 1 ? `${group.risks.length} 条规则问题` : group.risks[0]?.title || "风险位置",
          type: group.risks[0]?.category || "risk",
          level: group.level,
          kind: "risk",
          rule_count: group.risks.length,
          risk_ids: group.risks.map((risk) => risk.id),
        },
        geometry: group.geometry as GeoJSON.Geometry,
      })),
  };
}

function riskMarkerFeature(feature: Feature): Feature {
  const geometry = feature.getGeometry();
  if (!geometry || geometry.getType() === "Point") return feature;
  const marker = new Feature();
  marker.setProperties(feature.getProperties());
  marker.setGeometry(new Point(getCenter(geometry.getExtent())));
  return marker;
}

function fitMap(): void {
  if (!map || !objectLayer || !riskShapeLayer || !riskPointSource) return;
  const qgisExtent = qgisStatus.value?.extent;
  if (qgisAvailable.value && qgisExtent && qgisExtent.length === 4 && qgisExtent.every(Number.isFinite)) {
    map.getView().fit(qgisExtent as Extent, { padding: [28, 28, 28, 28], maxZoom: 18, duration: 0 });
    return;
  }
  const objectExtent = objectLayer.getSource()?.getExtent();
  const shapeExtent = riskShapeLayer.getSource()?.getExtent();
  const extent = mergeExtents(mergeExtents(objectExtent, shapeExtent), riskPointSource.getExtent());
  if (!extent) return;
  map.getView().fit(extent, { padding: [28, 28, 28, 28], maxZoom: 18, duration: 250 });
}

function mergeExtents(a?: Extent | null, b?: Extent | null): Extent | null {
  const validA = Number.isFinite(a?.[0]);
  const validB = Number.isFinite(b?.[0]);
  if (!validA && !validB) return null;
  if (!validA) return b || null;
  if (!validB) return a || null;
  const left = a as Extent;
  const right = b as Extent;
  return [
    Math.min(left[0], right[0]),
    Math.min(left[1], right[1]),
    Math.max(left[2], right[2]),
    Math.max(left[3], right[3]),
  ];
}

function objectStyle(feature: FeatureLike): Style {
  const geomType = feature.getGeometry()?.getType();
  const stroke = new Stroke({ color: "#146c67", width: 2 });
  const fill = new Fill({ color: "rgba(20, 108, 103, 0.12)" });
  if (geomType === "Point" || geomType === "MultiPoint") {
    return new Style({
      image: new CircleStyle({
        radius: 5,
        fill: new Fill({ color: "#146c67" }),
        stroke: new Stroke({ color: "#ffffff", width: 2 }),
      }),
    });
  }
  return new Style({ stroke, fill });
}

function riskShapeStyle(feature: FeatureLike): Style {
  const color = levelMeta[feature.get("level")]?.color || "#b9770e";
  return new Style({
    stroke: new Stroke({ color, width: 3 }),
    fill: new Fill({ color: `${color}1f` }),
  });
}

function riskClusterStyle(feature: FeatureLike): Style {
  const features = (feature.get("features") || []) as FeatureLike[];
  const count = features.length || 1;
  const level = features.reduce((current, item) => moreSevereLevel(current, item.get("level")), "low");
  const color = levelMeta[level]?.color || "#b9770e";
  const radius = count > 1 ? Math.min(17, 9 + Math.log2(count) * 3) : 7;
  return new Style({
    image: new CircleStyle({
      radius,
      fill: new Fill({ color }),
      stroke: new Stroke({ color: "#ffffff", width: 2 }),
    }),
    text: count > 1
      ? new Text({
          text: String(count),
          fill: new Fill({ color: "#ffffff" }),
          font: "600 11px Microsoft YaHei, sans-serif",
        })
      : undefined,
  });
}

function selectedRiskStyle(feature: FeatureLike): Style[] {
  const color = levelMeta[feature.get("level")]?.color || "#b9770e";
  return [
    new Style({
      image: new CircleStyle({
        radius: 16,
        fill: new Fill({ color: "rgba(255, 255, 255, 0.3)" }),
        stroke: new Stroke({ color: "#087f76", width: 3 }),
      }),
    }),
    new Style({
      image: new CircleStyle({
        radius: 8,
        fill: new Fill({ color }),
        stroke: new Stroke({ color: "#ffffff", width: 2 }),
      }),
    }),
  ];
}

function moreSevereLevel(current: string, candidate: string): string {
  return String(higherRiskLevel(current, candidate));
}
</script>
