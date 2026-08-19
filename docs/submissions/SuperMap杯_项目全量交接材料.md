# 黄河水鸟生态监测与三维可视化系统：队友交接材料

更新日期：2026-08-14  
适用场景：SuperMap 杯 GIS 开发竞赛、项目维护、答辩准备

## 1. 项目一句话

本项目是面向郑州黄河湿地水鸟保护的 GIS Web 系统。它把观鸟记录、空间数据库、生态评价结果、SuperMap 服务和三维场景连接起来，形成从“数据查看”到“空间研判”的演示闭环。

项目对外展示名称可使用：**黄河水鸟生态监测与三维可视化系统**。系统内品牌名为：**黄河生态方舟**；决策页标题为：**黄河生态方舟——郑州黄河湿地生态保护决策台**。

## 2. 项目能做什么

| 模块 | 现有能力 | 真实边界 |
|---|---|---|
| 二维监测大屏 | 天地图底图、图层开关、观鸟记录、热力图、时间和保护等级筛选、统计图表、缓冲分析入口 | 高缩放加载实际点，低缩放使用聚合，避免一次渲染全部 11.8 万点 |
| SuperMap 地图服务 | iClient for JavaScript（Leaflet）加载 iServer 发布地图 | 依赖 iServer 地图服务与本机网络/许可状态 |
| 决策平台 | InVEST 生境质量、四季保护优先度、核心区、热点、风险、巡护、模拟物联和简报 | “压力指数”为 PostGIS 运营排序，不等价于 InVEST 生境质量 |
| 水鸟识别 | 上传图片、目标检测、细分类、阈值设置和结果展示 | 是辅助识别，不取代人工鉴定；依赖模型文件与服务 |
| 三维场景 | SuperMap3D 读取 Realspace DEM 影像瓦片，叠加黄河、行政区、生态注记和受控数量的观测点 | 依赖本机 SDK、iServer Realspace REST、影像/地形缓存。三维缓存未稳定时，不可宣称已通过最终验收 |

## 3. 目录与代码定位

项目根目录：`D:\xuan1203-supermap`

| 路径 | 作用 |
|---|---|
| `config/urls.py` | 所有页面和 API 的 URL 路由 |
| `app_monitor/views.py` | 二维/决策/三维/报告页面、SuperMap 状态、专题点、缓冲、生态 API |
| `app_monitor/templates/index.html` | 二维监测大屏 |
| `app_monitor/templates/ecology_center.html` | 生态决策平台 |
| `app_monitor/templates/ecology_3d.html` | SuperMap3D 三维页面 |
| `app_monitor/templates/ecology_report.html` | 生态成果简报 |
| `app_monitor/templates/app_monitor/bird_recognition.html` | 水鸟识别页 |
| `app_monitor/static/app_monitor/eco/` | InVEST 与季节优先度 PNG、核心区 GeoJSON、成果目录 |
| `work/YellowRiverEcology3D/` | iDesktopX/Realspace 相关工作数据和缓存 |
| `docs/supermap/PHASE_1_PUBLISHING.md` | 首轮 iServer 发布说明 |
| `docs/submissions/` | 历史申报材料、接口文档和部署记录 |

## 4. 技术栈

### 后端与数据

- Django 5.2、Django REST Framework
- GeoDjango、PostgreSQL、PostGIS
- Python 虚拟环境：`D:\xuan1203\anxu`
- 主要发布视图/数据集：`YellowRiverSuperMap` 数据库中的 `supermap_observation_points`
- 几何字段：`geom`；坐标系：EPSG:4326

### SuperMap 技术链路

- SuperMap iDesktopX 2025：组织工作空间、地图和 Realspace 场景。
- SuperMap iServer 2025U1：发布地图服务、数据服务和 Realspace 三维服务。
- iClient for JavaScript（Leaflet）：二维地图服务瓦片加载。
- iClient3D for WebGL（SuperMap3D）：三维场景与 DEM 影像瓦片加载。
- REST / GeoJSON：页面与服务之间的数据交换。

## 5. 本机服务与入口

| 组件 | 地址 | 当前用途 |
|---|---|---|
| 二维监测大屏 | `http://127.0.0.1:8002/supermap/` | 主展示页 |
| 决策平台 | `http://127.0.0.1:8003/ecology/` | 生态评价与空间决策 |
| 三维场景 | `http://127.0.0.1:8003/ecology/3d/` | SuperMap3D 三维表达 |
| 成果简报 | `http://127.0.0.1:8003/ecology/report/` | 模型成果与统计汇报 |
| 水鸟识别 | `http://127.0.0.1:8003/bird-page/` | 图像识别界面 |
| iServer 服务目录 | `http://127.0.0.1:8090/iserver/services` | 服务可达性验证 |
| iServer 管理台 | `http://127.0.0.1:8090/iserver/iManager` | 发布与管理 |

已使用或约定的服务名称：`map-YellowRiverSuperMap`、`data-YellowRiverEcology3D`、`3D-YellowRiverEcology3D`。服务名和场景名可在 iServer 服务目录中复核；不要把密码提交到聊天、代码仓库或 PPT。

## 6. 数据与生态评价事实边界

### 6.1 可以用于竞赛材料的已核查事实

- 生态评价以 2014-2024 年水鸟记录和环境变量为基础，2025 年监测坐标用于外部时相验证。
- 工作流包括季节 MaxEnt 适宜性、Getis-Ord Gi* 集聚、PCA 核心区，以及全研究区 InVEST Habitat Quality。
- “高适宜—高集聚”核心区面积约 **103.10 km²**。
- 2025 年受限背景验证 AUC：春季 0.901、夏季 0.828、秋季 0.816、冬季 0.846。

以上结论来自现有 B79 作品资料和 2026052829 材料，应保持“模型成果”属性，不应用前端统计数字替换或扩大。

### 6.2 数据来源口径

- 中国观鸟记录中心：水鸟观测记录与时空验证数据。
- 天地图：基础底图和地名注记。
- OpenStreetMap（OSM）：道路、水系和开放地理要素参考。
- 地理空间数据云、Copernicus GLO-30：遥感影像、DEM 与基础环境数据。

### 6.3 不应夸大的内容

- 模拟物联站点不是实时真实设备流，页面已标记为演示数据。
- 压力指数用于区域运营排序，不是 InVEST 指标。
- 三维页加载成功的前提是 SDK、Realspace 场景 JSON、影像缓存和地形缓存均可用；任何一项不通时，不能声称三维 DEM 地形已稳定展示。
- 鸟类识别页面只有在模型文件加载和推理服务正常时才能输出结果；识别结果需要人工复核。

## 7. 核心接口

| 接口 | 用途 |
|---|---|
| `/api/supermap/status/` | 返回 iServer 服务状态和地图服务地址 |
| `/api/supermap/thematic-points/` | 返回视域内专题点或聚合单元 |
| `/api/supermap/pick/` | 点击地图后匹配 PostGIS 点位 |
| `/api/supermap/protected-buffer/` | 保护鸟类点缓冲区分析 |
| `/api/ecology/layers/` | 决策台生态评价图层目录 |
| `/api/ecology/capacity/` | 三市观测记录、物种数与运营压力汇总 |
| `/api/ecology/risk-alerts/` | 保护鸟类风险清单 |
| `/api/ecology/hotspots/` | 热点网格 GeoJSON |
| `/api/ecology/patrol-plan/` | 基于热点排序的巡护序列 |
| `/api/ecology/live-feed/` | 比赛演示用模拟物联状态 |
| `/bird/recognize/` | 水鸟图片识别 |

## 8. 日常启动与演示顺序

1. 启动 PostgreSQL/PostGIS。
2. 启动 SuperMap iServer，打开服务目录确认 8090 可访问。
3. 激活 `D:\xuan1203\anxu`，进入 `D:\xuan1203-supermap`。
4. 运行 `python manage.py check` 与 `python manage.py migrate`。
5. 分别启动两个 Django 端口：`python manage.py runserver 8002` 与 `python manage.py runserver 8003`。
6. 先打开二维大屏、决策台、成果简报、识别页和 iServer 服务目录。
7. 三维页必须最后验证。优先用 SuperMap 官方示例验证同一 Realspace 服务；官方示例失败时停止修改前端，转回 iDesktopX/iServer 处理缓存和发布。

## 9. 三维服务排查原则

这部分是项目最容易误判的地方。

1. 先确认 iServer 运行，再生成或重建缓存。生成缓存时应先停止 iServer，避免 Windows 文件锁导致半成品缓存。
2. 使用与 iServer 2025U1 配套的 iDesktopX 2025 生成**三维影像缓存和 DEM 地形缓存**，不要误用二维瓦片缓存。
3. 在 iServer 服务目录核对 Realspace 服务和场景路径；直接打开场景 JSON、layers.json，确认返回 200。
4. 用官方 WebGL/S3MTiles 示例加载。官方示例失败说明根因在服务端或数据端，不要继续改 Django 代理或前端相机参数。
5. 验收缓存：`.sci` 场景元数据应有正确命名空间、`StoreType`、`Levels`；Terrain 层应具备本地缓存标记。随后再接回 `ecology_3d.html`。

## 10. 答辩时的推荐展示顺序

1. 用二维大屏说明“11.8 万记录如何在一张图上被筛选、聚合和统计”。
2. 进入生态决策台，切换 InVEST 与春/夏/秋/冬保护优先度，展示核心区、热点和风险工具。
3. 打开成果简报，讲清核心区 103.10 km²、四季验证 AUC 和数据边界。
4. 展示水鸟识别的上传、阈值与识别闭环。
5. 打开 iServer 服务目录，说明 SuperMap iDesktopX—iServer—iClient 的服务化链路。
6. 三维页只有在当天机器的官方示例和业务页都成功时展示；否则用服务架构与缓存验收路线说明，不让白屏干扰主线。

## 11. 下一步开发优先级

1. 重建并验收三维影像与 DEM 地形缓存，完成 Realspace 官方示例加载。
2. 实现二维点选到三维飞行定位。
3. 以真实河道/湿地缓冲区与保护等级规则完善风险预警。
4. 引入网络约束的巡护路径，替换当前热点序列的演示型连线。
5. 连接真实物联/轨迹数据，并保留“模拟/真实”清晰标识。
6. 补充专题图布局和一键导出，实现正式业务报告输出。

## 12. 完整工程接手指南

### 12.1 项目要解决的问题

项目服务于郑州黄河湿地水鸟保护。传统观鸟数据以表格、照片和分散点位为主，存在“记录难汇总、空间格局难判断、生态模型成果难进入日常研判、三维表达难复用”的问题。系统以 SuperMap 服务化 GIS 为主线，将观测记录、生态评价、空间分析和三维场景连接为一条可演示、可扩展的流程：

```text
观测记录 / 环境栅格 / 行政区与河流 / DEM
                ↓
        PostGIS + GeoDjango 数据管理
                ↓
  iDesktopX 组织工作空间与场景 / iServer 发布 REST 服务
                ↓
二维监测大屏  ←→  生态决策台  ←→  Realspace 三维场景
                ↓
      识别、空间查询、缓冲、热点、风险和成果简报
```

答辩时要讲清楚：系统不是只把点位“画在地图上”，而是以 SuperMap iDesktopX—iServer—iClient 的服务化链路承载二维监测、生态研判和三维表达；Django/GeoDjango 负责业务 API 与 PostGIS 空间计算。

### 12.2 参赛作品的统一口径

- 作品名称：**黄河水鸟生态监测与三维可视化系统**。
- 决策平台品牌：**黄河生态方舟——郑州黄河湿地生态保护决策台**。
- 比赛技术主线：SuperMap iDesktopX 2025、SuperMap iServer 2025U1、iClient for JavaScript（Leaflet）、iClient3D for WebGL（SuperMap3D）、Realspace、REST、S3M、GeoJSON。
- 后端主线：Django 5.2、Django REST Framework、GeoDjango、PostgreSQL/PostGIS。
- 数据来源口径：中国观鸟记录中心、天地图、OpenStreetMap、地理空间数据云、Copernicus GLO-30。不要把这些来源扩展为没有实际使用过的数据集。

### 12.3 代码目录与责任边界

| 位置 | 主要内容 | 修改时的注意事项 |
|---|---|---|
| `config/urls.py` | 页面和 API 路由 | 新页面先挂路由，再确认 8002/8003 都能访问 |
| `app_monitor/views.py` | 地图点位、SuperMap 状态、缓冲、生态、识别等视图与 API | 空间查询优先使用 GeoDjango/PostGIS，不在前端遍历全量点 |
| `app_monitor/templates/index.html` | 二维监测大屏 | 当前主展示页；保持既有暗色监测大屏语言与 Logo |
| `app_monitor/templates/ecology_center.html` | 生态决策台 | 使用天地图底图开关，避免切回 OSM 作为默认底图 |
| `app_monitor/templates/ecology_report.html` | 成果简报 | 生态模型结论、平台统计、模拟物联必须分层表述 |
| `app_monitor/templates/ecology_3d.html` | 三维页 | 只能在官方示例验证通过后接 Realspace；不要继续用前端补丁掩盖服务端错误 |
| `app_monitor/templates/app_monitor/bird_recognition.html` | 鸟类识别页面 | 识别结果需保留“辅助识别、人工复核”的产品边界 |
| `app_monitor/static/app_monitor/eco/` | InVEST、四季优先度、核心区和热点等成果资源 | 成果资源变更后同步核对决策台的图层清单与图例 |
| `work/YellowRiverEcology3D/` | iDesktopX / Realspace 工作数据、缓存相关资源 | 服务运行时不要直接覆盖缓存；先停 iServer，再重建三维缓存 |
| `docs/supermap/PHASE_1_PUBLISHING.md` | 第一阶段 iServer 发布说明 | 发布地址、服务名变化时同步更新本材料和部署说明 |

### 12.4 数据与数据库

1. 主数据库为 `YellowRiverSuperMap`，主要观测点表为 `supermap_observation_points`，几何字段 `geom`，坐标参考系 `EPSG:4326`。
2. 二维页不应在低缩放级别直接回传约 11.8 万记录。当前策略是：低缩放使用网格或聚合表达，高缩放按视域和筛选条件返回真实点位；这是性能设计，不是数据缺失。
3. 已发布地图服务与业务 API 可以同时存在：地图服务承担地图图层展示，业务 API 用于点击拾取、属性弹窗、筛选、缓冲区和统计。
4. 若新增 GeoJSON、Shapefile 或 CSV 数据，先验证编码、坐标系、空几何和字段名；导入 iDesktopX 出现 0% 卡死时，优先转换为 UTF-8 无 BOM 或 Shapefile，再导入。
5. 栅格评价成果、核心区和热点资源应保留来源、生成日期、空间分辨率、投影和方法说明，答辩时不要只展示色带而无法说明口径。

### 12.5 SuperMap 工作空间与服务

#### 二维地图和数据服务

建议在 iDesktopX 中通过本机 PostGIS 连接建立工作空间，将 `supermap_observation_points` 加入地图并保存。当前约定服务包括：

| 服务 | 用途 | 典型入口 |
|---|---|---|
| `map-YellowRiverSuperMap` | 二维地图服务 | `http://127.0.0.1:8090/iserver/services/map-YellowRiverSuperMap/rest` |
| `data-YellowRiverEcology3D` | 数据服务 | iServer 服务目录中核对实际 REST 地址 |
| `3D-YellowRiverEcology3D` | Realspace 三维服务 | iServer 服务目录中核对场景名称、场景 JSON 与图层 JSON |

发布检查顺序：在 iDesktopX 保存工作空间和地图 → iServer 管理台发布地图/数据/三维服务 → 在服务目录直接打开 REST 根地址 → 再由 Web 页调用。遇到问题时，先确认服务目录返回 200，而不是先改前端。

#### 三维 Realspace 的正确验收路线

这部分是目前最容易出现误判的环节。下列顺序不可颠倒：

1. 先停止 iServer，避免 Windows 对 `output` 缓存文件的锁定。
2. 使用与 iServer 2025U1 配套的 iDesktopX 2025，生成**三维影像缓存**和**DEM 地形缓存**；不要误用二维瓦片缓存。
3. 生成后检查 `.sci` 元数据：应具备正确的 `xmlns:sml` 命名空间，以及 `StoreType`、`Levels` 等节点；Terrain 层应具备本地缓存标志。
4. 启动 iServer，重新发布或重载 Realspace 服务。
5. 在 iServer 服务目录直接确认场景 JSON、`layers.json` 返回 200。
6. 使用 SuperMap 官方 WebGL/S3MTiles 示例加载同一个场景。官方示例成功后，才允许接回 `ecology_3d.html`。

若官方示例仍然白屏、出现 `parseSci3dDoc`、场景 JSON 404、`layers.json` 404，根因在工作空间、缓存或 iServer 发布，**停止修改前端、Django 代理和相机参数**，回到第 1 步处理。浏览器中 `Immersive Translate`、`unload` 等扩展警告通常不是根因。

### 12.6 前端页面的功能现状

| 页面 | 地址 | 重点演示内容 | 当前边界 |
|---|---|---|---|
| 二维监测大屏 | `http://127.0.0.1:8002/supermap/` | 观鸟记录、时间和保护等级筛选、热力图、统计、点位拾取、缓冲分析、SuperMap 服务图层、进入决策平台入口 | 真实点位按缩放/视域受控加载；不要强制所有点同屏渲染 |
| 生态决策台 | `http://127.0.0.1:8003/ecology/` | 天地图开关、InVEST、季节优先度、热点、风险、巡护、行政承载和模拟物联 | 模拟物联只用于比赛演示，需清晰标识 |
| 成果简报 | `http://127.0.0.1:8003/ecology/report/` | 核心区、方法、AUC、平台统计和生态结论的可读化展示 | 压力指数不是 InVEST 生境质量结果 |
| 鸟类识别 | `http://127.0.0.1:8003/bird-page/` | 图片上传、检测、分类、阈值、识别展示 | 是辅助识别，结论须人工复核 |
| 三维场景 | `http://127.0.0.1:8003/ecology/3d/` | Realspace DEM 影像、黄河、行政区、生态注记、受控点位，后续二维三维联动 | 以官方示例和服务端缓存验收为前提；未稳定时不要将其作为答辩主展示 |

### 12.7 已核对的模型与事实边界

下列数值可用于材料和答辩，但必须按“模型结果/验证结果”表述：

- 评价流程：2014—2024 年水鸟记录和环境变量；2025 年监测坐标用于外部时相验证。
- 评价方法：季节 MaxEnt 适宜性、Getis-Ord Gi* 集聚、PCA 核心区、全研究区 InVEST Habitat Quality。
- “高适宜—高集聚”核心区面积约 **103.10 km²**。
- 2025 年受限背景验证 AUC：春 **0.901**、夏 **0.828**、秋 **0.816**、冬 **0.846**。

下列内容不可夸大：

- 模拟物联数据不是实时设备流。
- 平台压力指数是基于业务/空间统计的运营排序，不等同于 InVEST 值。
- 三维场景必须满足 SDK、许可、服务和缓存均可用，不能因页面有框架就说“DEM 三维地形已稳定验收”。
- 鸟类识别服务需要模型文件和推理服务正常，不应代替专家鉴定。

### 12.8 本机运行与排障

启动顺序：

```powershell
# 1. 启动 PostgreSQL/PostGIS
# 2. 启动 SuperMap iServer，确认 8090 服务目录可访问

Set-Location D:\xuan1203-supermap
& D:\xuan1203\anxu\Scripts\Activate.ps1
python manage.py check
python manage.py migrate

# 终端 A
python manage.py runserver 8002

# 终端 B
python manage.py runserver 8003
```

验证清单：

1. `http://127.0.0.1:8090/iserver/services` 可访问，地图、数据和三维服务名称与当前工作空间一致。
2. `http://127.0.0.1:8002/supermap/` 能加载二维页和统计内容。
3. `http://127.0.0.1:8003/ecology/` 能切换生态图层，天地图开关正常。
4. `http://127.0.0.1:8003/ecology/report/` 可显示模型证据和核心区结论。
5. `http://127.0.0.1:8003/bird-page/` 可打开；有模型时再验证识别闭环。
6. 三维服务先以官方示例确认，再检查业务页；不要仅用业务页白屏判断问题。

常见问题：

| 现象 | 优先检查 |
|---|---|
| 8002 或 8003 无法运行 | 端口占用、虚拟环境、`manage.py check`、是否启动了正确的 Django 工程 |
| 服务图层不显示 | 8090 服务目录、REST 地址、浏览器强制刷新 `Ctrl+F5`、iServer 许可和服务状态 |
| 点位放大后变少/消失 | 当前视域、筛选条件、缩放级别与服务端返回上限；不要直接改为全量加载 |
| iDesktopX 导入 GeoJSON 卡在 0% | UTF-8 无 BOM、空间参考、空几何、特殊字段；必要时转 Shapefile |
| 三维 404 / `parseSci3dDoc` | 停止改前端，按 Realspace 缓存与发布验收路线处理 |
| iServer 内存异常 | 维持合理 `javaopts.config` 内存设置，避免多浏览器并发拉取 DEM；三维缓存生成时先停 iServer |

### 12.9 比赛答辩建议与 10 分钟演示脚本

**0:00—1:00：问题与定位**  
“黄河湿地水鸟保护的数据来源多、时空异构，监测记录、生态评价和保护研判往往分离。我们以 SuperMap 服务化 GIS 为底座，构建面向郑州黄河湿地的水鸟生态监测与三维可视化系统。”

**1:00—2:00：技术架构**  
展示架构页，说明 iDesktopX 组织工作空间和场景，iServer 2025U1 发布地图、数据与 Realspace 服务，iClient/Leaflet 承担二维展示，SuperMap3D 承担三维接入，Django/GeoDjango/PostGIS 承担业务和空间计算。

**2:00—4:00：二维监测大屏**  
打开二维页。展示时间、保护等级筛选与统计；说明约 11.8 万记录采用低缩放聚合、高缩放真实点位的性能策略。点选一条记录，演示属性和缓冲分析入口；强调地图服务与 PostGIS 业务 API 协同。

**4:00—5:30：生态决策台**  
从二维页进入决策台。切换天地图、InVEST 生境质量与四季保护优先度，展示热点、保护鸟风险和巡护建议。说明模型成果、运营统计和模拟物联在页面上分层表达，避免混淆证据口径。

**5:30—6:30：成果简报和模型证据**  
打开成果简报，说明“高适宜—高集聚”核心区约 103.10 km²；2025 年验证 AUC 为春 0.901、夏 0.828、秋 0.816、冬 0.846。强调这些是模型与验证结论，不是前端临时统计。

**6:30—7:30：鸟类识别闭环**  
展示图片上传、目标检测和分类结果。说明该模块用于辅助审核与公众参与，识别结果需要人工复核后再进入可靠数据链路。

**7:30—8:30：SuperMap 服务化证据**  
打开 iServer 服务目录，指向地图、数据和三维服务。说明 iDesktopX—iServer—iClient 的发布链路，体现本作品不是单纯前端可视化。

**8:30—9:30：Realspace 三维与验收方法**  
只有在当日官方 WebGL 示例和业务三维页均成功时展示三维场景。否则展示“服务端先验收、页面后接入”的路线：三维影像缓存、DEM 地形缓存、场景 JSON 与 `layers.json`、官方示例验证。这比用白屏页面冒险更专业。

**9:30—10:00：收束与展望**  
“下一步将实现二维点选飞行定位到三维、真实河道湿地缓冲的风险规则、网络约束巡护路径以及真实物联数据接入。系统的价值在于把生态模型、空间数据和日常保护动作放在同一套 SuperMap 服务化工作流中。”

### 12.10 后续开发优先级与交接原则

1. **先稳定三维服务端**：重建并验收三维影像/DEM 地形缓存，官方示例通过后再恢复业务页开发。
2. **完成二维三维联动**：二维点选传递经纬度与属性，三维页飞行定位到相同区域。
3. **提高生态预警真实性**：以河道/湿地缓冲、保护等级、季节和观测置信度替换单纯前端排序。
4. **把演示巡护升级为网络分析**：准备道路/水系/阻力面和巡护约束，再做最小成本路径或网络分析。
5. **接入真实动态数据前保留模拟标签**：真实监测站、轨迹和设备元数据到位后再替换模拟物联。
6. **所有新功能先标证据边界**：数据来源、时间范围、模型版本、是否真实/模拟、服务依赖，均应在代码和材料中保持一致。
