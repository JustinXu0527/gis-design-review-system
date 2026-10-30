# 通信基建设计智能审查系统原型

这是一个可运行的 GIS 设计成果智能审查原型，用于验证“GIS 图层读取 + Pydantic 工程对象 + Shapely 空间计算 + 行业标准规则引擎 + LangGraph Agent + 向量检索 + 本地 32B 大模型解释 + 风险追溯 + WebGIS/QGIS 标注 + 报告导出”的核心流程。

## 技术路线

当前子课题三的直接审查对象是 GIS 设计成果：

1. 上传 `.gpkg`、`.geojson`，或 ZIP/RAR 打包的 GIS 成果。
2. 后端使用 GeoPandas/Pyogrio 读取图层和要素。
3. 使用 Pydantic 统一定义工程对象、审查证据和风险结果。
4. 使用 Shapely 计算距离、相交、包含、穿越等空间关系。
5. 规则引擎基于固定后端规则库判断是否违规。
6. 本地 `qwen2.5:32b` 只负责解释违规原因、生成整改建议和审查报告。
7. FastAPI 提供 Web 接口，风险可导出为 GeoJSON 后在 QGIS/WebGIS 中展示违规位置。

## 前端技术栈

前端已迁移为大众化 Vue 工程，源码位于 `frontend/`，构建产物输出到后端托管目录 `static/`。

- Vue 3 + TypeScript：页面、组件和前端数据结构开发。
- Vite：前端开发服务器和生产构建。
- Vue Router：页面路由，目前使用 hash 路由，便于 FastAPI 静态托管。
- Pinia：项目、标准库、审查结果和上传状态的全局状态管理。
- Axios：调用 FastAPI 后端接口。
- Element Plus：表格、表单、按钮、上传、弹窗、标签、折叠面板等 UI 组件。
- OpenLayers：GIS 对象和风险位置的矢量地图展示。
- ECharts：风险等级和对象类型统计图表。
- `frontend/src/types.ts`：集中定义项目、GIS 对象、风险、证据、标准库和模型审查结果类型。

前端由原单页工作台调整为七个业务页面，并共享当前项目和风险选择状态：

- `/overview`：系统概览、核心指标与统计图表。
- `/projects`：项目创建、GIS 成果上传和图层读取。
- `/agent`：LangGraph 节点进度、QGIS MCP 调用记录和模型结论。
- `/map`：GIS 风险地图、地图全屏与风险定位。
- `/risks`：风险位置清单、规则证据与整改建议。
- `/knowledge`：标准库和知识图谱证据链说明。
- `/reports`：多格式报告导出和执行日志。

侧栏支持折叠；统计图表、风险清单和地图通过 Pinia 中的风险筛选与当前风险状态联动。

前端开发：

```powershell
cd E:\pythondata\挑战杯课题三\frontend
npm install
npm run dev
```

生产构建：

```powershell
cd E:\pythondata\挑战杯课题三\frontend
npm run typecheck
npm run build
```

构建后继续通过 FastAPI 访问 `http://127.0.0.1:8010`，无需额外启动 Node 服务。

## 本地模型配置

项目已从外接 DeepSeek API 改为本地 Ollama 部署，不再需要云端 API Key。默认使用 `test_models.py` 中验证过的两个模型：

- `qwen2.5:32b`：用于中文智能审查、风险解释和整改建议生成。
- `bge-m3`：用于标准条款 embedding 检索，审查时从十个 PDF 标准构建的规则库中召回最相关条款证据。
- `langgraph`：用于编排本地智能审查 Agent。当前图包含 `runtime_status -> data_profile -> semantic_retrieval -> knowledge_graph_context -> gis_tool_planning -> mcp_gis_tools -> evidence_validation -> llm_review/fallback_review` 九个状态节点。其中 `gis_tool_planning` 使用本地 LLM 生成受控工具计划；`mcp_gis_tools` 优先调用已配置的 QGIS MCP Server，并以 GeoPandas/Shapely 只读工具作为受控回退。页面会分别展示调用来源、状态、耗时、原因和结果摘要。

环境变量见 `.env` 或 `config.example.env`：

```env
OLLAMA_BASE_URL=http://localhost:11435
OLLAMA_LLM_MODEL=qwen2.5:32b
OLLAMA_EMBED_MODEL=bge-m3
OLLAMA_ENABLE_EMBEDDING_RETRIEVAL=1
ALLOW_STANDARD_LIBRARY_EDIT=0
APP_HOST=127.0.0.1
APP_PORT=8010
```

## 运行

确保 Ollama 正在 `http://localhost:12000` 提供服务，并且本机已有模型：

```powershell
ollama pull qwen2.5:32b
ollama pull bge-m3
```

启动 FastAPI 服务：

```powershell
cd E:\pythondata\挑战杯课题三
conda activate ziketi3
python main.py
```

打开 `http://127.0.0.1:8010`。

全量审查同时提供异步接口，供智能体页面轮询真实执行状态：

- `POST /api/projects/{project_id}/review/start`：启动后台审查任务。
- `GET /api/projects/{project_id}/review/status`：读取总进度、当前节点、节点耗时和 GIS 工具调用记录。

## 标准库与 embedding 用法

- 结构化标准库位于 `data/standards/*.json`。
- 十个 PDF 的目录和条款索引位于 `data/knowledge_base/`。
- PDF 抽取文本位于 `data/extracted_standards_text/`。
- 网站端标准库为只读展示，普通用户不能上传、替换或删除标准。
- 标准知识库和规则库由后端维护人员通过脚本或离线流程发布到 `data/standards`。
- 如确需在开发环境临时开放标准库维护接口，可设置 `ALLOW_STANDARD_LIBRARY_EDIT=1`；正式部署保持 `0`。
- 审查时先执行本地规则引擎，再用 `bge-m3` 对工程对象、规则命中证据和标准条款做语义匹配。
- 条款向量缓存写入 `data/knowledge_base/ollama_clause_embeddings.json`，后续审查会复用缓存。
- 规则文件会同步解析为轻量知识图谱，缓存写入 `data/knowledge_base/standards_knowledge_graph.json`。
- 知识图谱用于表达“标准-条款-规则-工程对象-检查字段-空间关系-风险等级”的证据链，不替代正式规则引擎。
- 本地 LLM 最终只接收召回后的相关条款，减少上下文噪声并提升可追溯性。

## 支持资料

- GIS 设计成果：`.gpkg`、`.geojson`、`.shp` 及 ZIP/RAR 打包的 GIS 文件。大压缩包使用 multipart 流式上传；RAR 解压要求服务器安装 WinRAR/UnRAR（Windows）或 `unrar`（Linux）。
- 普通 PDF、DOCX、XLSX、CSV 等资料只作为历史兼容入口，不作为当前子课题三的主要审查对象。
- 标准知识库：JSON 结构化标准库优先；Markdown、TXT、DOCX、XLSX 可通过本地 Ollama 解析成结构化条款。
- 导出结果：PDF、Word、Excel、CSV、GeoJSON 风险标注文件和规则执行日志。

## 审查流程

点击“调用本地 Ollama 执行全量审查”后，系统会：

1. 读取 `data/standards` 中的条款和规则。
2. 对 GIS 图层要素执行本地规则引擎，形成可计算证据。
3. 使用 `bge-m3` 召回与当前工程最相关的标准条款。
4. 构建知识图谱上下文，为正式风险生成可追溯证据链。
5. 进入 LangGraph Agent：检查 Ollama 状态，采集 GIS 数据概况，执行 `semantic_retrieval` 和 `knowledge_graph_context`，由模型生成 GIS 工具计划，调用受控 GIS 工具并校验证据，最后走 `llm_review` 或 `fallback_review`。
6. 页面展示风险数量、等级分布、条款依据、计算证据、知识图谱证据链、WebGIS 风险标注和智能审查结果。
