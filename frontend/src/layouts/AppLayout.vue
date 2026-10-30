<template>
  <el-config-provider namespace="el">
    <div class="application-frame" :class="{ 'sidebar-collapsed': collapsed }">
      <aside class="app-sidebar">
        <router-link class="sidebar-brand" to="/overview" aria-label="返回系统概览">
          <span class="sidebar-mark">GIS</span>
          <span v-show="!collapsed" class="sidebar-brand-copy">
            <strong>智审平台</strong>
            <small>ENGINEERING REVIEW</small>
          </span>
        </router-link>

        <el-menu :default-active="route.path" router :collapse="collapsed" class="sidebar-menu">
          <el-menu-item v-for="item in navigation" :key="item.path" :index="item.path">
            <el-icon><component :is="item.icon" /></el-icon>
            <template #title>{{ item.label }}</template>
          </el-menu-item>
        </el-menu>

        <div class="sidebar-footer">
          <span class="service-dot"></span>
          <span v-show="!collapsed">本地化智能审查</span>
        </div>
      </aside>

      <section class="application-main">
        <AppHeader :collapsed="collapsed" @toggle-sidebar="toggleSidebar" />
        <main class="page-stage" v-loading="store.loading.boot">
          <router-view v-slot="{ Component, route: currentRoute }">
            <transition name="page-fade" mode="out-in">
              <keep-alive>
                <component :is="Component" :key="currentRoute.name" />
              </keep-alive>
            </transition>
          </router-view>
        </main>
      </section>
    </div>
  </el-config-provider>
</template>

<script setup lang="ts">
import { markRaw, onMounted, ref } from "vue";
import {
  Connection,
  DataAnalysis,
  Document,
  FolderOpened,
  MapLocation,
  Share,
  Warning,
} from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { useRoute } from "vue-router";

import AppHeader from "@/components/AppHeader.vue";
import { useReviewStore } from "@/stores/review";
import { errorMessage } from "@/utils/error";

const store = useReviewStore();
const route = useRoute();
const collapsed = ref(localStorage.getItem("review-sidebar-collapsed") === "1");
const navigation = [
  { path: "/overview", label: "系统概览", icon: markRaw(DataAnalysis) },
  { path: "/projects", label: "项目管理", icon: markRaw(FolderOpened) },
  { path: "/agent", label: "智能体审查", icon: markRaw(Connection) },
  { path: "/map", label: "GIS 风险地图", icon: markRaw(MapLocation) },
  { path: "/risks", label: "风险与证据", icon: markRaw(Warning) },
  { path: "/knowledge", label: "标准与图谱", icon: markRaw(Share) },
  { path: "/reports", label: "报告中心", icon: markRaw(Document) },
];

function toggleSidebar(): void {
  collapsed.value = !collapsed.value;
  localStorage.setItem("review-sidebar-collapsed", collapsed.value ? "1" : "0");
  window.dispatchEvent(new Event("resize"));
}

onMounted(async () => {
  try {
    await store.boot();
  } catch (error) {
    ElMessage.error(errorMessage(error));
  }
});
</script>
