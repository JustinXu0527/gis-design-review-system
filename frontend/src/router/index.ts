import { createRouter, createWebHashHistory } from "vue-router";

import AppLayout from "@/layouts/AppLayout.vue";

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: "/",
      component: AppLayout,
      children: [
        { path: "", redirect: "/overview" },
        { path: "overview", name: "overview", component: () => import("@/views/OverviewView.vue"), meta: { title: "系统概览" } },
        { path: "projects", name: "projects", component: () => import("@/views/ProjectsView.vue"), meta: { title: "项目管理" } },
        { path: "map", name: "map", component: () => import("@/views/MapView.vue"), meta: { title: "GIS 风险地图" } },
        { path: "agent", name: "agent", component: () => import("@/views/AgentView.vue"), meta: { title: "智能体审查" } },
        { path: "risks", name: "risks", component: () => import("@/views/RisksView.vue"), meta: { title: "风险与证据" } },
        { path: "knowledge", name: "knowledge", component: () => import("@/views/KnowledgeView.vue"), meta: { title: "标准与知识图谱" } },
        { path: "reports", name: "reports", component: () => import("@/views/ReportsView.vue"), meta: { title: "报告中心" } },
      ],
    },
    { path: "/:pathMatch(.*)*", redirect: "/overview" },
  ],
});

router.afterEach((to) => {
  document.title = `${to.meta.title || "GIS 智能审查"} - 通信基建`;
});

export default router;
