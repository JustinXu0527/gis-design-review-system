import axios, { type AxiosError } from "axios";

import type { AppConfig, Project, ProjectListItem, QgisPreviewStatus, ReviewJobStatus, StandardDoc } from "@/types";

export interface FileUploadPayload {
  filename: string;
  content_base64?: string;
  content?: string;
  files?: FileUploadPayload[];
}

export interface UploadResult {
  filename: string;
  object_count: number;
  total_objects: number;
  duplicate: boolean;
  message?: string;
}

export interface ReviewResult {
  risk_count: number;
  summary?: Record<string, unknown>;
  agent_review?: unknown;
  computed_risk_count?: number;
  risks?: unknown[];
  execution_log?: unknown[];
}

interface ListResponse<T> {
  items: T[];
}

interface ErrorPayload {
  error?: string;
  detail?: string | { error?: string };
}

export class ApiRequestError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

export const apiClient = axios.create({
  baseURL: "/api",
  timeout: 120000,
});

apiClient.interceptors.response.use(
  (response) => response.data,
  (error: AxiosError<ErrorPayload>) => {
    const data = error.response?.data;
    const message =
      data?.error ||
      (typeof data?.detail === "object" ? data.detail.error : "") ||
      (typeof data?.detail === "string" ? data.detail : "") ||
      error.message ||
      "请求失败";
    return Promise.reject(new ApiRequestError(message, error.response?.status));
  },
);

export function fetchConfig(): Promise<AppConfig> {
  return apiClient.get("/config");
}

export function fetchQgisPreviewStatus(projectId?: string): Promise<QgisPreviewStatus> {
  return apiClient.get("/qgis/status", { params: projectId ? { project_id: projectId } : undefined });
}

export function fetchStandards(): Promise<ListResponse<StandardDoc>> {
  return apiClient.get("/standards");
}

export function fetchProjects(): Promise<ListResponse<ProjectListItem>> {
  return apiClient.get("/projects");
}

export function fetchProject(projectId: string): Promise<Project> {
  return apiClient.get(`/projects/${projectId}`);
}

export function createProject(name: string): Promise<Project> {
  return apiClient.post("/projects", { name });
}

export function deleteProject(projectId: string): Promise<{ deleted: boolean; id: string }> {
  return apiClient.delete(`/projects/${projectId}`);
}

export function uploadProjectDocument(projectId: string, payload: FileUploadPayload): Promise<UploadResult> {
  return apiClient.post(`/projects/${projectId}/documents`, payload);
}

export function uploadProjectFile(projectId: string, file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file, file.name);
  return apiClient.post(`/projects/${projectId}/documents`, form, {
    timeout: 15 * 60 * 1000,
  });
}

export function runProjectReview(projectId: string): Promise<ReviewResult> {
  return apiClient.post(`/projects/${projectId}/review`, {}, { timeout: 30 * 60 * 1000 });
}

export function startProjectReview(projectId: string): Promise<ReviewJobStatus> {
  return apiClient.post(`/projects/${projectId}/review/start`, {});
}

export function fetchProjectReviewStatus(projectId: string): Promise<ReviewJobStatus> {
  return apiClient.get(`/projects/${projectId}/review/status`);
}

export function isNotFoundError(error: unknown): boolean {
  return error instanceof ApiRequestError && error.status === 404;
}

export function exportProjectUrl(projectId: string, format: string): string {
  return `/api/projects/${projectId}/export?format=${format}`;
}
