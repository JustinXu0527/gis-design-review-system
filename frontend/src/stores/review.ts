import { ElMessage, ElMessageBox } from "element-plus";
import { defineStore } from "pinia";

import {
  createProject,
  deleteProject,
  exportProjectUrl,
  fetchConfig,
  fetchProject,
  fetchProjectReviewStatus,
  fetchProjects,
  fetchStandards,
  isNotFoundError,
  runProjectReview,
  startProjectReview,
  uploadProjectDocument,
  uploadProjectFile,
  type UploadResult,
} from "@/api/client";
import type { AgentReview, AppConfig, DesignObject, ExecutionLog, Project, ProjectListItem, ReviewJobStatus, RiskFinding, StandardDoc } from "@/types";
import { designUploadPayloads, fileSelectionKey, isShapefilePart, normalizeProjectName } from "@/utils/files";

type StatusType = "success" | "warning" | "info" | "error";
type RiskFilter = "all" | "high" | "medium" | "low";
const LAST_PROJECT_KEY = "review-last-project-id";
const RISK_FILTER_KEY = "review-risk-filter";
const RISK_SELECTION_PREFIX = "review-selected-risk:";
const MAP_STANDARD_FILTER_KEY = "review-map-standard-filter";
const MAP_OBJECT_TYPE_FILTER_KEY = "review-map-object-type-filter";

interface ReviewState {
  config: AppConfig | null;
  standards: StandardDoc[];
  projects: ProjectListItem[];
  currentProject: Project | null;
  reviewJob: ReviewJobStatus | null;
  selectedRiskId: string;
  selectedRiskFocusToken: number;
  riskFilter: RiskFilter;
  mapStandardFilter: string;
  mapObjectTypeFilter: string;
  selectedFileKey: string;
  selectedFileProjectId: string;
  uploadedFileKey: string;
  uploadedFileProjectId: string;
  loading: {
    boot: boolean;
    project: boolean;
    upload: boolean;
    review: boolean;
  };
  statusMessage: string;
  statusType: StatusType;
}

export const useReviewStore = defineStore("review", {
  state: (): ReviewState => ({
    config: null,
    standards: [],
    projects: [],
    currentProject: null,
    reviewJob: null,
    selectedRiskId: "",
    selectedRiskFocusToken: 0,
    riskFilter: storedRiskFilter(),
    mapStandardFilter: localStorage.getItem(MAP_STANDARD_FILTER_KEY) || "",
    mapObjectTypeFilter: localStorage.getItem(MAP_OBJECT_TYPE_FILTER_KEY) || "",
    selectedFileKey: "",
    selectedFileProjectId: "",
    uploadedFileKey: "",
    uploadedFileProjectId: "",
    loading: {
      boot: false,
      project: false,
      upload: false,
      review: false,
    },
    statusMessage: "等待执行审查",
    statusType: "info",
  }),
  getters: {
    objects: (state): DesignObject[] => state.currentProject?.objects || [],
    risks: (state): RiskFinding[] => state.currentProject?.risks || [],
    executionLog: (state): ExecutionLog[] => state.currentProject?.execution_log || [],
    agentReview: (state): AgentReview | null => state.currentProject?.agent_review || null,
    filteredRisks: (state): RiskFinding[] => {
      const risks = state.currentProject?.risks || [];
      if (state.riskFilter === "all") return risks;
      return risks.filter((risk) => risk.level === state.riskFilter);
    },
    mapFilteredRisks: (state): RiskFinding[] => {
      const objects = new Map((state.currentProject?.objects || []).map((item) => [item.id, item]));
      return (state.currentProject?.risks || []).filter((risk) => {
        if (state.riskFilter !== "all" && risk.level !== state.riskFilter) return false;
        if (state.mapStandardFilter && risk.clause?.standard_name !== state.mapStandardFilter) return false;
        if (state.mapObjectTypeFilter) {
          const objectIds = risk.evidence?.object_ids || [];
          if (!objectIds.some((objectId) => objects.get(objectId)?.type === state.mapObjectTypeFilter)) return false;
        }
        return true;
      });
    },
    selectedRisk: (state): RiskFinding | null => {
      const risks = state.currentProject?.risks || [];
      return risks.find((risk) => risk.id === state.selectedRiskId) || risks[0] || null;
    },
    standardClauseCount: (state): number => state.standards.reduce((sum, item) => sum + (item.clause_count || 0), 0),
  },
  actions: {
    selectRisk(riskId: string): void {
      this.selectedRiskId = riskId;
      if (this.currentProject?.id && riskId) {
        localStorage.setItem(`${RISK_SELECTION_PREFIX}${this.currentProject.id}`, riskId);
      }
    },
    focusRisk(riskId: string): void {
      this.selectRisk(riskId);
      this.selectedRiskFocusToken += 1;
    },
    setRiskFilter(filter: RiskFilter): void {
      this.riskFilter = filter;
      localStorage.setItem(RISK_FILTER_KEY, filter);
    },
    setMapStandardFilter(standardName: string): void {
      this.mapStandardFilter = standardName;
      localStorage.setItem(MAP_STANDARD_FILTER_KEY, standardName);
    },
    setMapObjectTypeFilter(objectType: string): void {
      this.mapObjectTypeFilter = objectType;
      localStorage.setItem(MAP_OBJECT_TYPE_FILTER_KEY, objectType);
    },
    clearMapFilters(): void {
      this.setRiskFilter("all");
      this.setMapStandardFilter("");
      this.setMapObjectTypeFilter("");
    },
    restoreRiskSelection(projectId: string): void {
      const risks = this.currentProject?.risks || [];
      const rememberedRiskId = localStorage.getItem(`${RISK_SELECTION_PREFIX}${projectId}`) || "";
      const nextRiskId = risks.some((risk) => risk.id === rememberedRiskId) ? rememberedRiskId : risks[0]?.id || "";
      this.selectedRiskId = nextRiskId;
      if (nextRiskId) localStorage.setItem(`${RISK_SELECTION_PREFIX}${projectId}`, nextRiskId);
    },
    async boot(): Promise<void> {
      this.loading.boot = true;
      try {
        const [config, standards, projects] = await Promise.all([fetchConfig(), fetchStandards(), fetchProjects()]);
        this.config = config;
        this.standards = standards.items || [];
        this.projects = projects.items || [];
        if (this.currentProject?.id) {
          await this.openProject(this.currentProject.id);
        } else {
          const rememberedProjectId = localStorage.getItem(LAST_PROJECT_KEY) || "";
          if (this.projects.some((project) => project.id === rememberedProjectId)) {
            await this.openProject(rememberedProjectId);
          }
        }
      } finally {
        this.loading.boot = false;
      }
    },
    async refreshProjectList(): Promise<void> {
      const projects = await fetchProjects();
      this.projects = projects.items || [];
    },
    async openProject(projectId: string): Promise<void> {
      if (!projectId) return;
      this.loading.project = true;
      try {
        this.currentProject = await fetchProject(projectId);
        this.reviewJob = null;
        try {
          const job = await fetchProjectReviewStatus(projectId);
          if (job.status !== "idle") this.reviewJob = job;
        } catch {
          this.reviewJob = null;
        }
        localStorage.setItem(LAST_PROJECT_KEY, projectId);
        this.restoreRiskSelection(projectId);
        this.statusMessage = this.currentProject?.risks?.length ? "已加载历史审查结果。" : "等待执行审查。";
        this.statusType = this.currentProject?.risks?.length ? "success" : "info";
      } finally {
        this.loading.project = false;
      }
    },
    async createNewProject(name: string): Promise<Project | null> {
      const cleanName = normalizeProjectName(name);
      const duplicate = this.projects.some((project) => normalizeProjectName(project.name).toLowerCase() === cleanName.toLowerCase());
      if (cleanName && duplicate) {
        ElMessage.warning(`项目名称“${cleanName}”已存在，请换一个名称。`);
        return null;
      }
      const project = await createProject(cleanName);
      this.currentProject = project;
      localStorage.setItem(LAST_PROJECT_KEY, project.id);
      this.projects.unshift({
        id: project.id,
        name: project.name,
        object_count: 0,
        risk_count: 0,
      });
      this.resetFileSelection();
      this.statusMessage = "项目已创建，请上传 GIS 设计成果。";
      this.statusType = "success";
      return project;
    },
    markSelectedFiles(files: File[]): void {
      this.selectedFileProjectId = this.currentProject?.id || "";
      this.selectedFileKey = fileSelectionKey(files);
      this.uploadedFileKey = "";
      this.uploadedFileProjectId = "";
    },
    resetFileSelection(): void {
      this.selectedFileKey = "";
      this.selectedFileProjectId = "";
      this.uploadedFileKey = "";
      this.uploadedFileProjectId = "";
    },
    async uploadDesignFiles(files: File[]): Promise<void> {
      if (!this.currentProject) throw new Error("请先创建或打开项目");
      const fileList = Array.from(files || []);
      if (!fileList.length) throw new Error("请先选择 GIS 设计成果文件");
      if (this.selectedFileProjectId && this.selectedFileProjectId !== this.currentProject.id) {
        throw new Error("文件是在其他项目下选择的，请重新选择当前项目的 GIS 设计成果");
      }
      this.loading.upload = true;
      try {
        const selectionKey = fileSelectionKey(fileList);
        const directFiles = fileList.filter((file) => !isShapefilePart(file.name));
        const payloads = await designUploadPayloads(fileList.filter((file) => isShapefilePart(file.name)));
        if (!directFiles.length && !payloads.length) {
          throw new Error("没有找到可读取的 GIS 成果。Shapefile 请至少选择 .shp，并同时选择同名 .shx/.dbf/.prj，或上传 ZIP/RAR 压缩包。");
        }
        const results: UploadResult[] = [];
        for (const file of directFiles) {
          results.push(await uploadProjectFile(this.currentProject.id, file));
        }
        for (const payload of payloads) {
          results.push(await uploadProjectDocument(this.currentProject.id, payload));
        }
        this.uploadedFileProjectId = this.currentProject.id;
        this.uploadedFileKey = selectionKey;
        await this.openProject(this.currentProject.id);
        await this.refreshProjectList();
        const skipped = results.filter((item) => item.duplicate).length;
        this.statusMessage = skipped
          ? `已跳过 ${skipped} 个重复文件；同一 GIS 成果不会重复读取图层。`
          : `已完成 GIS 图层读取，当前选择的 ${fileList.length} 个文件会保留显示，可直接执行审查。`;
        this.statusType = skipped ? "warning" : "success";
      } finally {
        this.loading.upload = false;
      }
    },
    async reviewCurrentProject(): Promise<void> {
      if (!this.currentProject) throw new Error("请先创建项目");
      if (!(this.currentProject.objects || []).length) {
        throw new Error("当前项目没有 GIS 工程对象。请先上传 GIS 成果并读取图层后再执行审查。");
      }
      this.loading.review = true;
      this.statusMessage = "正在启动 LangGraph 智能审查工作流。";
      this.statusType = "info";
      const projectId = this.currentProject.id;
      try {
        try {
          this.reviewJob = await startProjectReview(projectId);
        } catch (error) {
          if (!isNotFoundError(error)) throw error;
          this.reviewJob = null;
          this.statusMessage = "当前服务使用兼容审查模式，正在执行完整审查。";
          await runProjectReview(projectId);
          if (this.currentProject?.id === projectId) {
            this.currentProject = await fetchProject(projectId);
            this.restoreRiskSelection(projectId);
          }
          await this.refreshProjectList();
          const count = this.currentProject?.risks?.length || 0;
          this.statusMessage = `审查完成：固定规则库命中 ${count} 条正式风险，本地模型用于解释原因和生成建议。`;
          this.statusType = count ? "warning" : "success";
          return;
        }
        const deadline = Date.now() + 30 * 60 * 1000;
        while (["queued", "running"].includes(this.reviewJob.status)) {
          if (Date.now() >= deadline) throw new Error("智能审查等待超时，请稍后在项目记录中重新打开查看结果。");
          await wait(650);
          this.reviewJob = await fetchProjectReviewStatus(projectId);
          this.statusMessage = this.reviewJob.message || "LangGraph 工作流正在执行。";
        }
        if (this.reviewJob.status === "error") {
          throw new Error(this.reviewJob.error || this.reviewJob.message || "智能审查执行失败");
        }
        if (this.currentProject?.id === projectId) {
          this.currentProject = await fetchProject(projectId);
          this.restoreRiskSelection(projectId);
        }
        await this.refreshProjectList();
        const count = this.currentProject?.risks?.length || 0;
        this.statusMessage = `审查完成：固定规则库命中 ${count} 条正式风险，本地模型用于解释原因和生成建议。`;
        this.statusType = count ? "warning" : "success";
      } finally {
        this.loading.review = false;
      }
    },
    async removeProject(project: ProjectListItem): Promise<void> {
      await ElMessageBox.confirm(`确认删除项目“${project.name}”？项目资料、审查结果和上传文件都会删除。`, "删除项目", {
        type: "warning",
        confirmButtonText: "删除",
        cancelButtonText: "取消",
      });
      await deleteProject(project.id);
      if (this.currentProject?.id === project.id) {
        this.currentProject = null;
        this.reviewJob = null;
        this.selectedRiskId = "";
        localStorage.removeItem(LAST_PROJECT_KEY);
      }
      localStorage.removeItem(`${RISK_SELECTION_PREFIX}${project.id}`);
      await this.refreshProjectList();
      this.statusMessage = "项目已删除。";
      this.statusType = "info";
    },
    exportCurrentProject(format: string): void {
      if (!this.currentProject) {
        ElMessage.warning("请先创建或打开项目");
        return;
      }
      window.location.href = exportProjectUrl(this.currentProject.id, format);
    },
  },
});

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function storedRiskFilter(): RiskFilter {
  const value = localStorage.getItem(RISK_FILTER_KEY);
  return value === "high" || value === "medium" || value === "low" ? value : "all";
}
