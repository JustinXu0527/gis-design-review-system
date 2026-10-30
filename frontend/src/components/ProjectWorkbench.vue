<template>
  <el-card class="module-card workbench-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <h2>GIS 设计成果</h2>
          <span>{{ store.currentProject?.name || "未创建项目" }}</span>
        </div>
        <el-tag :type="store.currentProject ? 'success' : 'info'">
          {{ store.currentProject ? "已打开" : "待创建" }}
        </el-tag>
      </div>
    </template>

    <el-form label-position="top" class="workbench-form">
      <el-form-item label="项目名称">
        <el-input v-model="projectName" clearable placeholder="例如：某区 FTTH 管道光缆设计审查">
          <template #append>
            <el-button type="primary" @click="createProject" :loading="creating">创建</el-button>
          </template>
        </el-input>
      </el-form-item>

      <el-form-item label="GIS 成果文件">
        <el-upload
          v-model:file-list="fileList"
          class="gis-upload"
          drag
          multiple
          :auto-upload="false"
          :accept="accept"
          :disabled="!store.currentProject || store.loading.upload"
          :on-change="onFileChange"
          :on-remove="onFileChange"
        >
          <el-icon class="upload-icon"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖拽 GIS 成果到此处，或 <em>点击选择</em></div>
          <template #tip>
            <div class="upload-tip">支持 .gpkg、.geojson、.zip、.rar，或同名 .shp/.shx/.dbf/.prj</div>
          </template>
        </el-upload>
      </el-form-item>

      <el-button
        class="full-button"
        type="success"
        :icon="Upload"
        :disabled="!canUpload"
        :loading="store.loading.upload"
        @click="uploadFiles"
      >
        {{ uploadButtonText }}
      </el-button>
    </el-form>

    <div class="metric-grid compact">
      <div>
        <strong>{{ store.objects.length }}</strong>
        <span>设计对象</span>
      </div>
      <div>
        <strong>{{ store.risks.length }}</strong>
        <span>风险结果</span>
      </div>
      <div>
        <strong>{{ store.standardClauseCount }}</strong>
        <span>标准条款</span>
      </div>
    </div>

    <el-alert class="status-alert" :type="store.statusType" :closable="false" show-icon>
      <template #title>{{ store.statusMessage }}</template>
    </el-alert>

    <el-button
      class="full-button review-button"
      type="primary"
      size="large"
      :icon="Cpu"
      :disabled="!store.currentProject || !store.objects.length"
      :loading="store.loading.review"
      @click="runReview"
    >
      开始全量审查
    </el-button>

  </el-card>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { Cpu, Upload, UploadFilled } from "@element-plus/icons-vue";
import { ElMessage, type UploadUserFile } from "element-plus";
import { useRouter } from "vue-router";

import { useReviewStore } from "@/stores/review";
import { errorMessage } from "@/utils/error";
import { fileSelectionKey } from "@/utils/files";

const store = useReviewStore();
const router = useRouter();
const projectName = ref("");
const fileList = ref<UploadUserFile[]>([]);
const creating = ref(false);
const accept = ".gpkg,.geojson,.shp,.shx,.dbf,.prj,.cpg,.qpj,.qgs,.qgz,.qml,.sld,.zip,.rar";

const files = computed<File[]>(() => fileList.value.flatMap((item) => (item.raw ? [item.raw as File] : [])));
const currentSelectionKey = computed(() => fileSelectionKey(files.value));
const canUpload = computed(() => {
  if (!store.currentProject || store.loading.upload || !files.value.length) return false;
  if (store.selectedFileProjectId && store.selectedFileProjectId !== store.currentProject.id) return false;
  if (store.uploadedFileProjectId === store.currentProject.id && store.uploadedFileKey === currentSelectionKey.value) return false;
  return true;
});
const uploadButtonText = computed(() => {
  if (!store.currentProject) return "请先创建或打开项目";
  if (!files.value.length) return "选择 GIS 成果后上传";
  if (!canUpload.value) return "已读取，可直接审查";
  return "上传 GIS 成果并读取图层";
});

async function createProject() {
  creating.value = true;
  try {
    const project = await store.createNewProject(projectName.value);
    if (project) {
      projectName.value = "";
      fileList.value = [];
      ElMessage.success("项目已创建");
    }
  } catch (error) {
    ElMessage.error(errorMessage(error));
  } finally {
    creating.value = false;
  }
}

function onFileChange() {
  store.markSelectedFiles(files.value);
}

async function uploadFiles() {
  try {
    await store.uploadDesignFiles(files.value);
    ElMessage.success("GIS 图层读取完成");
  } catch (error) {
    ElMessage.error(errorMessage(error));
  }
}

async function runReview() {
  try {
    await router.push("/agent");
    await store.reviewCurrentProject();
    ElMessage.success("审查完成");
  } catch (error) {
    ElMessage.error(errorMessage(error));
  }
}

</script>
