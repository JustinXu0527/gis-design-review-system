# QGIS Server 原生预览接入说明

当前网站仍由 `ziketi3` 虚拟环境中的 FastAPI 提供业务接口，GIS 预览由本机 Docker Desktop 中的 `qgis/qgis-server:ltr` 镜像负责渲染。

## 当前部署路径

你已经准备好的 QGIS Server 目录为：

```text
E:\QGIS_Server
```

其中关键文件结构为：

```text
E:\QGIS_Server
├─ docker-compose.yml
└─ projects
   ├─ projects_001
   │  ├─ PushPK_Dreieich Mitte_Handwerk.qgz
   │  └─ *.gpkg
   └─ web_<项目ID>
      ├─ 用户上传的 GIS 文件
      └─ auto_preview.qgs
```

`projects_001` 是固定示例工程；`web_<项目ID>` 是网站在用户上传 GIS 文件后自动创建的项目预览目录。

## QGIS Server 启动

在 PowerShell 中运行：

```powershell
cd E:\QGIS_Server
docker compose up -d
```

检查服务：

```powershell
docker ps
```

直接验证 WMS：

```text
http://127.0.0.1:8080/ows/?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0&MAP=/io/data/projects_001/PushPK_Dreieich%20Mitte_Handwerk.qgz
```

## 网站配置

项目根目录 `.env` 中使用：

```env
QGIS_SERVER_URL=http://127.0.0.1:8080/ows/
QGIS_PROJECT_FILE=E:\QGIS_Server\projects\projects_001\PushPK_Dreieich Mitte_Handwerk.qgz
QGIS_PROJECT_FILE_CONTAINER=/io/data/projects_001/PushPK_Dreieich Mitte_Handwerk.qgz
QGIS_SERVER_DATA_ROOT_HOST=E:\QGIS_Server\projects
QGIS_SERVER_DATA_ROOT_CONTAINER=/io/data
QGIS_DOCKER_IMAGE=qgis/qgis-server:ltr
QGIS_PREVIEW_CRS=EPSG:25832
QGIS_SERVER_TIMEOUT=20
```

## 用户上传后的预览方式

网站支持两种预览路径：

1. 上传 `.qgz/.qgs` 工程文件及其引用的数据文件：QGIS Server 尽量按工程中的图层顺序、样式、标注和透明度渲染，效果最接近 QGIS Desktop。
2. 只上传 `.gpkg/.shp/.geojson/.zip` 数据文件：后端会调用 Docker 中的 PyQGIS 自动生成 `auto_preview.qgs`，再交给 QGIS Server 渲染。此时可以显示真实 GIS 图层，但样式主要使用 QGIS 默认样式或同名 `.qml/.sld`，不会凭空恢复桌面工程里的复杂制图效果。

## 网站启动

```powershell
cd E:\pythondata\挑战杯课题三
E:\conda_envs\ziketi3\python.exe main.py
```

打开：

```text
http://127.0.0.1:8010
```

## 接口验证

全局示例工程状态：

```text
http://127.0.0.1:8010/api/qgis/status
```

某个网页项目的 QGIS 预览状态：

```text
http://127.0.0.1:8010/api/qgis/status?project_id=<项目ID>
```

如果返回：

```json
{
  "available": true,
  "mode": "qgis_server_wms"
}
```

说明前端地图正在使用 QGIS Server 原生 WMS 渲染。

## 注意事项

- 如果希望网页效果与 QGIS Desktop 尽量一致，最好上传 `.qgz/.qgs` 工程文件，并同时上传工程引用的 `.gpkg/.shp` 等数据文件。
- 如果 QGIS 工程内部使用 Windows 绝对路径，Docker 容器可能无法读取，需要在 QGIS Desktop 中改成相对路径后保存。
- 当前方案是 QGIS Server 渲染服务，不是浏览器内嵌 QGIS Desktop。它能复用 QGIS 工程样式，但交互仍由 OpenLayers 提供。
