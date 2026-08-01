# 黄河生态方舟 ArcGIS 开发手册

> 面向对象：负责 ArcGIS 开发的队友，以及需要继续执行本任务的 AI Agent。  
> 当前分支：`competition/arcgis-server`  
> 工作目录：由每位开发者自行选择，以下统一记作 `<PROJECT_DIR>`。  
> 基线标签：`baseline-webgis-2026-07-30`  
> 本文目标：在**不破坏原有 Django + PostGIS + Leaflet 平台**的前提下，完成可演示、可部署、可复现的 ArcGIS Server / ArcGIS JavaScript API 集成版本。

---

## 0. 先读这一节

### 0.1 仓库中已经准备好的内容

以下内容已经提交到 GitHub 的 `competition/arcgis-server` 分支。队友不需要复制原开发者的电脑，只需要从 GitHub 克隆自己的副本：

| 项目 | 当前状态 | 说明 |
|---|---|---|
| 代码分支 | 已准备 | `origin/competition/arcgis-server`，基于 `baseline-webgis-2026-07-30` |
| Django 本地配置入口 | 已准备 | `config/settings.py` 支持被 Git 忽略的 `config/local_settings.py` |
| ArcGIS 开发手册 | 已准备 | 本文已提交到 `docs/ARCGIS_DEVELOPMENT_PLAYBOOK.md` |
| 原版保护 | 已准备 | 原版代码在 `master`，队友不需要也不应访问原开发者的本地路径 |
| 数据与数据库 | 由队友创建 | 每个开发者必须创建自己的 PostGIS 数据库并运行迁移/导入 |

### 0.2 队友从 GitHub 开始的完整流程

下面步骤是队友第一次接手时应执行的顺序。不要跳过数据库配置，也不要复制其他人的 `.venv` 或 `local_settings.py`。

#### Windows PowerShell

```powershell
# 1. 克隆自己的开发副本；目录可以自定义
git clone --branch competition/arcgis-server https://github.com/ANXU-CRAZY/xuan1203.git xuan1203-arcgis
cd xuan1203-arcgis

# 2. 使用 Python 3.11 或 3.12 创建独立虚拟环境
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

# 3. 复制环境模板（不要把真实密钥提交到 Git）
Copy-Item .env.local.example .env.local -ErrorAction SilentlyContinue

# 4. 配置 config/local_settings.py，见第 2.3 节
# 5. 迁移数据库、导入数据、生成首页缓存
python manage.py migrate
python manage.py refresh_map_observation_cache --batch-size 5000
python manage.py check
```

如果仓库中没有 `.env.local.example`，直接新建 `.env.local` 即可；该文件只保存本机配置，不要提交。

#### GitHub 克隆后不会自动获得的内容

当前仓库有意不提交以下内容：

- PostgreSQL/PostGIS 数据库本身。
- 含大量记录的 CSV、XLSX、SHP 和临时数据文件。
- `media/` 中的用户上传图像和图库资源。
- `.env.local`、API Key、Token 和本机密码。
- Python 虚拟环境、模型权重和发布缓存。

因此队友还需要向项目负责人索取一个**经过授权的数据包**或 PostgreSQL dump。推荐提供：

```text
arcgis-data-package/
  data/                         # CSV/XLSX/SHP 及所有 SHP 伴随文件
  media/                        # 可公开的图库/演示图片
  yellow_river_arcgis.dump     # 可选，PostgreSQL custom-format dump
  DATA_README.md                # 数据来源、日期、授权和导入顺序
```

如果没有 dump，就按第 2.4 节运行迁移，再使用获得的 CSV/SHP 导入。没有数据包时仍可以完成页面骨架和服务配置，但不能声称已经完成真实观测服务。

#### Linux/macOS Bash

```bash
git clone --branch competition/arcgis-server https://github.com/ANXU-CRAZY/xuan1203.git xuan1203-arcgis
cd xuan1203-arcgis
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.local.example .env.local 2>/dev/null || touch .env.local
python manage.py migrate
python manage.py refresh_map_observation_cache --batch-size 5000
python manage.py check
```

### 0.3 当前还没有完成的事情

### 0.2 当前还没有完成的事情

下列内容**尚未实现**。不要向队友或评委声称已经完成：

- 尚未配置 ArcGIS Server、ArcGIS Enterprise Portal 或 ArcGIS Pro 发布连接。
- 尚未发布 Map Service、Feature Service、Geoprocessing Service、Vector Tile Service。
- 尚未把 ArcGIS JavaScript API 接到网页中。
- 尚未创建 ArcGIS 专用的 PostGIS 只读视图或物化视图。
- 尚未配置 ArcGIS Server CORS、Token、反向代理或生产环境部署。
- 尚未做 ArcGIS 空间分析工具箱、地理处理服务或三维场景。

### 0.4 三条不可违反的规则

1. **PostGIS 是业务数据唯一事实来源。** 不要把 ArcGIS 服务层变成新的主数据库，也不要手工在 ArcGIS 服务中修改观测记录。
2. **不要退回旧的全量点位加载方式。** 首页数据逻辑必须继续使用 `MapObservationCache` 和 `/api/map-observations/`，不应重新让浏览器全量访问 `/api/observations/`。
3. **绝不提交密钥。** ArcGIS Token、Portal 密码、PostgreSQL 密码、DeepSeek Key 和 `.env.local` 都不得提交到 Git、截图或聊天记录。

---

## 1. 最终要交付什么

建议将 ArcGIS 比赛版做成以下六项成果。它们比“只把底图换成 ArcGIS”更有说服力。

1. **ArcGIS 服务目录**：至少一组可访问的地图服务和要素服务，包含观测点、监测点、监测样线、行政区界或热点专题图。
2. **ArcGIS 网页地图**：独立页面 `/arcgis/`，使用 ArcGIS JavaScript API 4.x，而不是替换原主页 Leaflet。
3. **专题表达**：保护等级分类渲染、数量热力渲染、日期和保护等级筛选、图例、图层控制、详情弹窗。
4. **空间分析**：至少实现一个真实分析闭环，例如圈选统计、缓冲区巡护建议、热点区域识别或时段对比。
5. **数据更新链路**：Django 导入/审核数据后，可按固定命令刷新 ArcGIS 服务数据；演示时能说清楚数据如何同步。
6. **可复现说明**：服务地址配置、发布步骤、数据库视图 SQL、启动命令、测试截图和故障排查记录齐全。

推荐验收演示流程：打开 ArcGIS 页面 -> 切换观测点/样线/行政区图层 -> 选择日期与保护等级 -> 点击点位查看属性 -> 开启热力图 -> 圈选区域 -> 看到服务端或前端统计结果 -> 打开 ArcGIS REST Services Directory 证明服务真实存在。

---

## 2. 开发前检查清单

### 2.1 必须向项目负责人确认的信息

不要猜测下面信息。缺少时可以先完成本地页面和数据准备，但不能完成真实服务发布。

| 需要确认的项 | 为什么需要 | 典型值 |
|---|---|---|
| ArcGIS 产品形态 | 发布路径和权限完全不同 | ArcGIS Server Standalone / ArcGIS Enterprise / Portal |
| 版本号 | JS API、Pro、Server 兼容性不同 | 10.9.1、11.x 等 |
| ArcGIS Pro 是否可用 | 最稳定的发布和样式配置工具 | 有授权的 ArcGIS Pro |
| Server/Portal 地址 | 配置服务 URL 与 CORS | `https://gis.example.com/arcgis` |
| 发布账号权限 | 必须能创建服务或 Web Layer | Publisher / Administrator |
| 数据库网络路径 | ArcGIS Server 需要能访问 PostGIS | IP、端口、数据库名、白名单 |
| 竞赛要求 | 决定优先做二维、三维、分析或移动端 | 评分表/主题/截止日期 |
| 是否允许公网服务 | 决定 Token、代理和部署方案 | 公网 / 校园网 / 内网 |

### 2.2 安装 PostgreSQL 和 PostGIS

队友必须在自己的电脑或开发服务器上安装 PostgreSQL 和 PostGIS。不要连接原开发者的数据库。

建议版本：PostgreSQL 14/15/16，PostGIS 3.x。安装完成后，使用 pgAdmin 或 `psql` 创建自己的数据库：

```sql
CREATE USER gis_app WITH PASSWORD '<your-local-password>';
CREATE DATABASE yellow_river_arcgis_dev OWNER gis_app;
\c yellow_river_arcgis_dev
CREATE EXTENSION postgis;
```

如果使用已有 `postgres` 用户，也可以不创建 `gis_app`，但密码不能写入 Git。

检查 PostGIS：

```sql
SELECT current_database(), postgis_full_version();
```

### 2.3 创建队友自己的本地配置

在项目根目录创建 `config/local_settings.py`。该文件已被 `.gitignore` 忽略，只存在于队友自己的电脑：

```python
# config/local_settings.py
# 这个文件绝不提交到 Git。
LOCAL_DATABASE_OVERRIDES = {
    'NAME': 'yellow_river_arcgis_dev',
    'USER': 'gis_app',
    'PASSWORD': '<your-local-password>',
    'HOST': '127.0.0.1',
    'PORT': '5432',
}
LOCAL_CACHE_LOCATION = 'yellow-river-arcgis-dev-cache'
```

远程 PostgreSQL 时，将 `HOST` 改成数据库服务器地址，并确认防火墙、`pg_hba.conf` 和 PostgreSQL `listen_addresses` 已允许连接。不要修改 `config/settings.py` 中的默认密码来临时解决连接问题。

也可以使用环境变量：

```python
import os

LOCAL_DATABASE_OVERRIDES = {
    'NAME': os.environ['GIS_DB_NAME'],
    'USER': os.environ['GIS_DB_USER'],
    'PASSWORD': os.environ['GIS_DB_PASSWORD'],
    'HOST': os.environ.get('GIS_DB_HOST', '127.0.0.1'),
    'PORT': os.environ.get('GIS_DB_PORT', '5432'),
}
LOCAL_CACHE_LOCATION = os.environ.get(
    'GIS_CACHE_LOCATION', 'yellow-river-arcgis-dev-cache'
)
```

### 2.4 初始化自己的数据库

激活虚拟环境后执行：

```powershell
# Windows PowerShell
python manage.py migrate
python manage.py check
```

```bash
# Linux/macOS
python manage.py migrate
python manage.py check
```

如果拿到的是 PostgreSQL custom-format dump，并且 dump 中包含表结构与数据，可使用：

```bash
pg_restore --clean --if-exists --no-owner \\
  --dbname=yellow_river_arcgis_dev \\
  yellow_river_arcgis.dump
```

恢复后仍要执行一次 `python manage.py check`，并确认 `SELECT current_database()` 返回队友自己的数据库。不要把 dump 恢复到不确定的数据库名。

如果需要演示数据，可使用项目负责人提供的 CSV：

```bash
python manage.py fast_import_observations data/bird_monitor_import_ready.csv \\
  --batch-size 5000 --replace
python manage.py normalize_protection_levels
python manage.py refresh_map_observation_cache --batch-size 5000
```

`--replace` 会清空当前开发库中的旧观测数据，只能对自己的数据库使用。首次不确定时先不加 `--replace`。

SHP 样线/点位导入：

```bash
python manage.py load_shp
```

该命令默认从 `data/水鸟监测点.shp` 和 `data/水鸟监测样线.shp` 读取数据。`.shp`、`.shx`、`.dbf`、`.prj`、`.cpg` 必须放在同一目录。

### 2.5 本机检查命令

在队友自己选择的项目目录执行：

```powershell
# Windows，虚拟环境激活后
git branch --show-current
git status --short
python manage.py check
```

```bash
# Linux/macOS，虚拟环境激活后
git branch --show-current
git status --short
python manage.py check
```

确认当前数据库：

```bash
python - <<'PY'
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute('SELECT current_database(), postgis_lib_version()')
    print(cursor.fetchone())
PY
```

预期显示队友自己的数据库名，例如 `yellow_river_arcgis_dev`。如果显示陌生数据库，立刻停止迁移和导入，检查 `config/local_settings.py`。

### 2.6 需要阅读的代码顺序

不要上来就改 `index.html`。按此顺序阅读：

1. `config/settings.py`：Django、PostGIS、静态文件和本地覆盖入口。
2. `config/urls.py`：现有页面和 API 路由。
3. `app_monitor/models.py`：空间模型、坐标字段与缓存表。
4. `app_monitor/views.py`：`map_observations`、统计逻辑和 JSON 输出。
5. `app_monitor/serializers.py`：监测点/样线/观测记录的现有输出格式。
6. `app_monitor/management/commands/refresh_map_observation_cache.py`：首页缓存刷新过程。
7. `app_monitor/templates/index.html`：现有 Leaflet 首页，不要贸然替换。
8. `docs/AI_TECHNICAL_HANDOVER.md`：如果项目负责人另行提供了原平台交接书，再阅读该文件；不要依赖其他电脑上的本地路径。

---

## 3. 当前平台空间架构

```mermaid
flowchart LR
    A[CSV / SHP / 后台录入] --> B[(PostgreSQL + PostGIS)]
    B --> C[ObservationRecord
真实观测记录]
    C --> D[refresh_map_observation_cache]
    D --> E[MapObservationCache
首页轻量缓存]
    E --> F[/api/map-observations/
bbox + 日期 + 保护等级]
    F --> G[现有 Leaflet 首页]
    B --> H[ArcGIS 专用只读视图
或物化视图]
    H --> I[ArcGIS Server / Enterprise 服务]
    I --> J[ArcGIS JavaScript API 页面]
```

### 3.1 重要数据模型

| 模型 | 几何/坐标 | ArcGIS 中的角色 |
|---|---|---|
| `ObservationRecord` | `location` 为 `PointField(srid=4326)`；同时有 `longitude`、`latitude` | 原始业务观测数据，不建议让 ArcGIS 直接编辑 |
| `MapObservationCache` | 无 PostGIS geometry 字段，但有经纬度 | 高性能展示源，可转换为 ArcGIS 点图层 |
| `WetlandZone` | `location` 为 `PointField(srid=4326)` | 监测点要素图层 |
| `MonitoringRoute` | `path_geom` 为 `MultiLineStringField(srid=4326)` | 监测样线要素图层 |
| 行政区界 | 现有 GeoJSON：`app_monitor/static/app_monitor/geo/region_boundary.geojson` | 行政区界图层；后续可发布为 ArcGIS 图层 |

### 3.2 坐标规则

当前项目统一使用地理坐标系 WGS 84，即 **EPSG:4326**。

- PostGIS Point 的顺序：`(x, y)` = `(longitude, latitude)`。
- GeoJSON 坐标顺序：`[longitude, latitude]`。
- Leaflet 构造点时常写 `[latitude, longitude]`。
- ArcGIS JavaScript API `Point` 使用 `{ longitude, latitude }` 或 `[longitude, latitude]`。

这是最容易出现“点跑到海里/非洲”的错误来源。每次新建图层都要确认坐标顺序和 SRID。

### 3.3 现有高性能地图接口

已有接口：

```text
GET /api/map-observations/
```

支持参数：

| 参数 | 示例 | 说明 |
|---|---|---|
| `start` 或 `start_date` | `2014-01-01` | 起始日期 |
| `end` 或 `end_date` | `2026-07-30` | 结束日期 |
| `protection` | `all` / `first` / `second` / `three` / `none` | 保护等级筛选 |
| `bbox` | `113.2,34.4,114.1,35.1` | `west,south,east,north`，仅取视野内点 |
| `west/south/east/north` | 单独传递 | 与 `bbox` 等价 |
| `stats` | `0` 或 `1` | `0` 不重复计算全量统计，地图拖动时使用 |

响应包含：

```json
{
  "results": [
    {
      "id": 1,
      "observation_time": "2025-05-01",
      "count": 12,
      "species_name": "示例物种",
      "species_protection": "国家二级重点保护野生动物",
      "longitude": 113.62,
      "latitude": 34.75,
      "zone_name": "示例区域",
      "transect_name": "示例样线"
    }
  ],
  "stats": {},
  "bbox": [113.2, 34.4, 114.1, 35.1],
  "count": 1
}
```

注意：接口当前最多返回 10,000 条视野记录，且缓存 5 分钟。ArcGIS 页面若直接使用该接口，可以复用这套逻辑；若使用 ArcGIS Feature Service，仍要保持同等的按视野查询原则。

---

## 4. 推荐技术路线

### 4.1 不推荐的做法

- 不要删除 Leaflet 首页再“全站改 ArcGIS”。这会破坏已经调过的移动端、热力图、智能体和比赛演示链路。
- 不要将 Django 业务表全部导出为 Shapefile 后手工维护两份数据。
- 不要让评委只能看到一个截图或公开底图；必须提供真实 ArcGIS 服务或可验证的 API。
- 不要在前端源码写 Portal 密码、长效 Token 或数据库连接串。
- 不要使用 ArcGIS 作为唯一数据源后再手动同步回 Django。

### 4.2 推荐的分阶段架构

第一阶段，新增独立页面：

```text
/arcgis/ -> ArcGIS JavaScript API 4.x 页面
```

第二阶段，发布只读服务：

```text
PostGIS 只读视图/物化视图 -> ArcGIS Feature Service + Map Service
```

第三阶段，增加分析能力：

```text
Feature Service -> ArcGIS JS 查询/渲染/圈选
可选：ArcGIS Geoprocessing Service -> 缓冲区、热点、巡护建议
```

第四阶段，整理比赛演示：

```text
服务目录 + Web 页面 + 数据更新命令 + 部署文档 + 截图/录像
```

---

## 5. 第一步：准备 ArcGIS Server 和 ArcGIS Pro

### 5.1 最低工具组合

优先使用下列组合：

- ArcGIS Pro：制图、连接 PostGIS、配置符号、发布服务。
- ArcGIS Server 或 ArcGIS Enterprise：承载 REST 服务。
- ArcGIS JavaScript API 4.x：网页前端。
- PostgreSQL/PostGIS：保持为 Django 主数据源。

如果只有 ArcGIS Server 而没有 Portal，也可以发布传统 Map Service；若要发布托管 Feature Layer、Web Map、Web Experience，通常需要 Enterprise Portal/Hosting Server。先确认实际产品形态，再选择发布按钮和服务类型。

### 5.2 ArcGIS Server 基础检查

在浏览器打开：

```text
https://<host>/<web-adaptor>/rest/services?f=pjson
```

可访问表示 REST Services Directory 正常。随后确认：

- 是否能打开 ArcGIS Server Manager。
- 是否有 Publisher 或 Administrator 角色。
- 服务器是否可访问 PostGIS 的 `5432` 端口。
- ArcGIS Server 主机是否有对应 PostgreSQL 客户端/数据库连接支持。
- Server 与浏览器页面是否为 HTTPS，避免混合内容。
- Server 的 CORS 是否允许 Django 站点域名、`http://127.0.0.1:8001`。

### 5.3 不要混淆三类服务

| 服务 | 适合做什么 | 本项目建议 |
|---|---|---|
| Map Service / Map Image Layer | 高性能地图展示、预设制图样式 | 作为行政区、样线、保护专题的展示层 |
| Feature Service / Feature Layer | 查询、筛选、弹窗、编辑、统计 | 观测点、监测点、样线；比赛版至少要有一个 |
| Geoprocessing Service | 缓冲区、叠加分析、热点分析、巡护路线 | 作为加分项；先完成前两类后再做 |

---

## 6. 第二步：为 ArcGIS 建立安全的数据服务层

### 6.1 为什么不能直接让 ArcGIS 随便连接业务表

Django 的数据库表属于应用内部实现。直接把 `app_monitor_*` 所有表交给 ArcGIS 编辑会造成：

- ArcGIS 字段/对象 ID 要求和 Django 迁移相互影响。
- 误编辑会损坏审核状态、关联关系和缓存表。
- 业务字段改名后发布服务容易崩溃。
- 无法保证只暴露已审核数据。

正确做法：使用**只读数据库账号 + 专用视图或物化视图**，只导出比赛需要的字段。

### 6.2 创建 ArcGIS 只读账号

以下 SQL 由数据库管理员执行。密码用真实强密码替换，且只保存到服务器安全配置中。

```sql
CREATE ROLE arcgis_reader LOGIN PASSWORD '<strong-password>';
GRANT CONNECT ON DATABASE "yellow_river_arcgis_dev" TO arcgis_reader;
GRANT USAGE ON SCHEMA public TO arcgis_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO arcgis_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO arcgis_reader;
```

生产环境建议把 ArcGIS 服务视图放入单独 schema，例如 `arcgis_export`，并只授权该 schema：

```sql
CREATE SCHEMA arcgis_export;
GRANT USAGE ON SCHEMA arcgis_export TO arcgis_reader;
```

### 6.3 创建观测点视图

在队友自己创建的数据库（例如 `yellow_river_arcgis_dev`）中执行。执行前在 pgAdmin 中核对表名；Django 默认表名通常为 `app_monitor_mapobservationcache`。

```sql
CREATE OR REPLACE VIEW arcgis_export.observation_points AS
SELECT
    cache.record_id::integer AS objectid,
    cache.record_id::integer AS record_id,
    cache.observation_time,
    cache.count AS bird_count,
    cache.species_id_cached AS species_id,
    cache.species_name,
    cache.species_latin,
    cache.species_protection,
    cache.zone_id_cached AS zone_id,
    cache.zone_name,
    cache.transect_name,
    cache.status,
    cache.description,
    cache.image_url,
    ST_SetSRID(ST_MakePoint(cache.longitude, cache.latitude), 4326)::geometry(Point, 4326) AS shape
FROM app_monitor_mapobservationcache AS cache
WHERE cache.status = 'approved'
  AND cache.longitude IS NOT NULL
  AND cache.latitude IS NOT NULL;

GRANT SELECT ON arcgis_export.observation_points TO arcgis_reader;
```

字段约定：

- `objectid` 必须唯一、稳定、整数；这里使用原记录 ID。
- `shape` 是 ArcGIS 使用的点几何字段，SRID 必须为 4326。
- `bird_count` 是数量权重，可用于 ArcGIS Heatmap Renderer。
- `status='approved'` 必须保留，不能把待审核记录公开。

### 6.4 创建监测点与样线视图

```sql
CREATE OR REPLACE VIEW arcgis_export.monitoring_zones AS
SELECT
    id::integer AS objectid,
    id::integer AS zone_id,
    name,
    is_hotspot,
    observation_tips,
    location::geometry(Point, 4326) AS shape
FROM app_monitor_wetlandzone
WHERE location IS NOT NULL;

CREATE OR REPLACE VIEW arcgis_export.monitoring_routes AS
SELECT
    id::integer AS objectid,
    id::integer AS route_id,
    name,
    description,
    path_geom::geometry(MultiLineString, 4326) AS shape
FROM app_monitor_monitoringroute
WHERE path_geom IS NOT NULL;

GRANT SELECT ON arcgis_export.monitoring_zones TO arcgis_reader;
GRANT SELECT ON arcgis_export.monitoring_routes TO arcgis_reader;
```

### 6.5 大数据量时使用物化视图

当观测记录有数万到十万级时，优先发布物化视图或由 ArcGIS Server 缓存地图，而不是让服务每次复杂联表。

```sql
CREATE MATERIALIZED VIEW arcgis_export.observation_points_mv AS
SELECT * FROM arcgis_export.observation_points;

CREATE UNIQUE INDEX observation_points_mv_objectid_uidx
  ON arcgis_export.observation_points_mv (objectid);

CREATE INDEX observation_points_mv_shape_gix
  ON arcgis_export.observation_points_mv USING GIST (shape);
```

刷新顺序必须是：

```text
导入/审核/更新数据
  -> normalize_protection_levels（如保护等级变化）
  -> refresh_map_observation_cache
  -> REFRESH MATERIALIZED VIEW arcgis_export.observation_points_mv
  -> ArcGIS 服务读取新数据
```

首次不要追求自动化。先手动执行并记录时间；验证无误后，再增加 Django 管理命令 `refresh_arcgis_exports`。

### 6.6 数据库验证 SQL

```sql
SELECT COUNT(*) FROM arcgis_export.observation_points;
SELECT COUNT(*) FROM arcgis_export.monitoring_zones;
SELECT COUNT(*) FROM arcgis_export.monitoring_routes;

SELECT objectid, species_name, bird_count, ST_AsText(shape)
FROM arcgis_export.observation_points
LIMIT 5;
```

应确认：点几何是 `POINT(经度 纬度)`，且经度约 110-115、纬度约 30-36；如果数值反过来，立即检查坐标顺序。

---

## 7. 第三步：在 ArcGIS Pro 中发布服务

### 7.1 建立 PostgreSQL 数据库连接

1. 打开 ArcGIS Pro，新建项目，例如 `YellowRiverArcGISDemo`。
2. 打开 Catalog Pane -> Databases -> Add Database Connection。
3. 选择 PostgreSQL，填写 ArcGIS Server 可访问的数据库地址。
4. 使用 `arcgis_reader`，不要使用 Django 的管理员账号。
5. 连接数据库后，确认能看到 `arcgis_export` schema 下的视图/物化视图。
6. 将 `observation_points`、`monitoring_zones`、`monitoring_routes` 加入地图。

如果 ArcGIS Pro 无法识别视图为可发布的空间图层：

- 确认 `objectid` 唯一且为整数。
- 确认 `shape` 是单一几何类型、SRID 为 4326。
- 不要使用复杂不稳定 SQL；先改用物化视图。
- 记录 ArcGIS Pro 的完整错误文本，再处理，不要随意修改 Django 表。

### 7.2 配置图层样式

建议使用三种可解释的图层样式：

| 图层 | 推荐样式 | 字段 |
|---|---|---|
| 观测点 | Unique Values | `species_protection` |
| 观测点热力图 | Heat Map | `bird_count` |
| 监测点 | 分类符号或热点图标 | `is_hotspot` |
| 监测样线 | 单线/分级线 | 可按路线类型扩展字段 |

保护等级颜色必须与原系统含义一致，不要在 ArcGIS 页面中改变业务定义：

- 国家一级：红色或深红。
- 国家二级：橙色。
- 三有保护：蓝/青色。
- 无危/其他：灰绿或低饱和色。

配置 Popup：物种中文名、拉丁名、数量、保护等级、日期、区域、样线、描述、图片 URL。不要把 Django 用户信息、内部 ID 以外的敏感字段直接公开。

### 7.3 发布前检查

1. 打开属性表，确认每行都有唯一 `objectid`。
2. 放大/缩小地图，确认点位不漂移。
3. 用日期和保护等级字段做 Definition Query 测试。
4. 在不同底图下检查颜色对比。
5. 使用 100%、125%、150% 显示缩放检查弹窗排版。
6. 确认发布数据源可由 ArcGIS Server 主机访问，而不只是开发电脑可访问。

### 7.4 发布服务

发布 UI 会因 Server/Enterprise 版本不同而变化，但原则不变：

1. 在 ArcGIS Pro 中添加目标 ArcGIS Server 或 Portal 连接。
2. 先发布 `YellowRiver/Monitoring` 文件夹下的 Map Service 或 Map Image Layer。
3. 发布/启用 Feature Access，得到 Feature Service。
4. 优先选择“引用注册数据”，避免每次发布复制业务数据库。
5. 服务初期使用受控访问或内部共享；公开前再审查字段和 Token 策略。
6. 保存服务 URL、图层编号、服务版本和发布日期到项目文档。

服务 URL 通常形如：

```text
https://<host>/<web-adaptor>/rest/services/YellowRiver/Monitoring/MapServer
https://<host>/<web-adaptor>/rest/services/YellowRiver/Monitoring/FeatureServer/0
```

先在 REST Services Directory 检查：

```text
.../FeatureServer/0?f=pjson
.../FeatureServer/0/query?where=1%3D1&returnCountOnly=true&f=pjson
```

必须确认查询返回计数且坐标系为 4326 或服务声明可正确投影。

---

## 8. 第四步：新增 ArcGIS 网页页面

### 8.1 页面策略

第一版只新增页面，不替换原首页：

```text
原首页 /          Leaflet，保持稳定
ArcGIS 页 /arcgis/ ArcGIS JavaScript API 4.x，比赛展示与 ArcGIS 功能入口
```

这样任何 ArcGIS 接入问题都不会影响原平台演示。

### 8.2 建议文件结构

```text
app_monitor/
  templates/
    arcgis_map.html
  static/
    app_monitor/
      js/
        arcgis-map.js
      css/
        arcgis-map.css
  views.py                 # 新增 arcgis_map_view
config/
  urls.py                  # 新增 /arcgis/
```

不要把几千行 ArcGIS JavaScript 全塞进 `index.html`。原首页已很大，ArcGIS 页面应独立维护。

### 8.3 最小路由实现

在 `app_monitor/views.py` 添加页面视图：

```python
from django.shortcuts import render

def arcgis_map_view(request):
    return render(request, 'arcgis_map.html')
```

在 `config/urls.py` 导入并新增：

```python
path('arcgis/', arcgis_map_view, name='arcgis_map'),
```

完成后先验证：

```powershell
python manage.py check
python manage.py runserver 8001
```

浏览器访问 `http://127.0.0.1:8001/arcgis/`。在服务 URL 未准备好前，页面也应展示清晰的“服务尚未配置”状态，而不是白屏。

### 8.4 ArcGIS JavaScript API 最小模板

在 `arcgis_map.html` 中使用 4.x API。版本应与服务环境兼容，发布前固定版本，避免使用不受控的“latest”。

```html
<link rel="stylesheet" href="https://js.arcgis.com/4.30/esri/themes/light/main.css">
<script src="https://js.arcgis.com/4.30/"></script>

<main class="arcgis-page">
  <header class="arcgis-toolbar">
    <a href="/">返回原平台</a>
    <label>起始日期 <input id="start-date" type="date"></label>
    <label>结束日期 <input id="end-date" type="date"></label>
    <select id="protection-filter">
      <option value="all">全部保护等级</option>
      <option value="first">国家一级</option>
      <option value="second">国家二级</option>
      <option value="three">三有保护</option>
      <option value="none">无危/其他</option>
    </select>
    <button id="apply-filter" type="button">应用筛选</button>
  </header>
  <div id="arcgis-view"></div>
</main>
<script src="{% static 'app_monitor/js/arcgis-map.js' %}"></script>
```

注意：模板使用 `{% static %}` 时需要模板顶部写 `{% load static %}`。

### 8.5 ArcGIS JS 核心实现示例

以下是结构示例，不要直接把私有服务地址写死。服务地址应由一个非敏感的配置对象提供。

```javascript
require([
  'esri/Map',
  'esri/views/MapView',
  'esri/layers/FeatureLayer',
  'esri/layers/MapImageLayer',
  'esri/widgets/LayerList',
  'esri/widgets/Legend',
  'esri/widgets/Home',
  'esri/widgets/Expand'
], (
  Map, MapView, FeatureLayer, MapImageLayer,
  LayerList, Legend, Home, Expand
) => {
  const services = window.ARCGIS_SERVICES;

  const observations = new FeatureLayer({
    url: services.observations,
    outFields: ['*'],
    title: '水鸟观测记录',
    popupTemplate: {
      title: '{species_name}',
      content: [
        { type: 'fields', fieldInfos: [
          { fieldName: 'species_latin', label: '拉丁名' },
          { fieldName: 'species_protection', label: '保护等级' },
          { fieldName: 'bird_count', label: '观测数量' },
          { fieldName: 'observation_time', label: '观测日期' },
          { fieldName: 'zone_name', label: '区域' },
          { fieldName: 'transect_name', label: '样线' }
        ] }
      ]
    }
  });

  const map = new Map({
    basemap: 'topo-vector',
    layers: [observations]
  });

  const view = new MapView({
    container: 'arcgis-view',
    map,
    center: [113.62, 34.75],
    zoom: 9
  });

  view.ui.add(new Home({ view }), 'top-left');
  view.ui.add(new Expand({ view, content: new LayerList({ view }) }), 'top-right');
  view.ui.add(new Expand({ view, content: new Legend({ view }) }), 'bottom-left');
});
```

页面中必须使用 `center: [longitude, latitude]`，不要照抄 Leaflet 的 `[lat, lng]`。

### 8.6 服务地址配置方式

服务地址不是秘密时，可在 Django 模板中注入：

```python
# settings.py 默认值；正式地址由 local_settings.py 或服务器环境覆盖
ARCGIS_SERVICES = {
    'observations': '',
    'zones': '',
    'routes': '',
    'monitoring_map': '',
}
```

模板中：

```html
<script>
window.ARCGIS_SERVICES = {{ arcgis_services_json|safe }};
</script>
```

若服务需要 Token，前端不能保存管理员 Token。应使用短期匿名访问、受限的应用身份，或增加 Django 后端代理接口。代理接口必须限制目标域名、日志脱敏并处理 Token 续期，不能做成任意 URL 转发器。

---

## 9. 第五步：实现筛选、热力图和空间分析

### 9.1 保护等级和日期筛选

ArcGIS `FeatureLayer` 可通过 `definitionExpression` 让服务端过滤。字段名必须与已发布服务的字段一致。

```javascript
function sqlQuote(value) {
  return String(value).replace(/'/g, "''");
}

function buildWhere({ startDate, endDate, protection }) {
  const clauses = ["status = 'approved'"];
  if (startDate) clauses.push(`observation_time >= DATE '${sqlQuote(startDate)}'`);
  if (endDate) clauses.push(`observation_time <= DATE '${sqlQuote(endDate)}'`);

  const groups = {
    first: "species_protection LIKE '%一级%'",
    second: "species_protection LIKE '%二级%'",
    three: "species_protection LIKE '%三有%'",
    none: "(species_protection IS NULL OR species_protection = '' OR species_protection LIKE '%无危%')"
  };
  if (groups[protection]) clauses.push(groups[protection]);
  return clauses.join(' AND ');
}

document.querySelector('#apply-filter').addEventListener('click', () => {
  observations.definitionExpression = buildWhere({
    startDate: document.querySelector('#start-date').value,
    endDate: document.querySelector('#end-date').value,
    protection: document.querySelector('#protection-filter').value
  });
});
```

注意：不同 ArcGIS 服务对日期 SQL 的方言可能不同。先在 REST Directory 的 Query 页面验证 `where` 语句，再写入前端。

### 9.2 热力图

优先使用 ArcGIS JS API 的 HeatmapRenderer，而不是重新实现 Canvas 热力图。数量字段应使用 `bird_count`：

```javascript
observations.renderer = {
  type: 'heatmap',
  field: 'bird_count',
  colorStops: [
    { ratio: 0, color: 'rgba(49, 130, 189, 0)' },
    { ratio: 0.25, color: '#3182bd' },
    { ratio: 0.5, color: '#38a169' },
    { ratio: 0.75, color: '#ecc94b' },
    { ratio: 1, color: '#e53e3e' }
  ],
  maxDensity: 0.08,
  minDensity: 0
};
```

必须保留“点图层”和“热力图层”两种展示模式；评委需要能看原始观测点，也需要能看空间密度。不要让热力图遮住点位后无法复原。

### 9.3 圈选统计：最优先实现的分析功能

推荐使用 ArcGIS `Sketch` 绘制矩形/多边形，然后用 `FeatureLayer.queryFeatures` 查询选区内要素。它直观、可验证、与项目的巡护业务匹配。

业务输出至少包括：记录数、鸟类数量总和、物种数、一级/二级重点物种数、日期范围和区域建议。

伪代码：

```javascript
const query = observations.createQuery();
query.geometry = selectedPolygon;
query.spatialRelationship = 'intersects';
query.where = observations.definitionExpression || '1=1';
query.outFields = ['species_name', 'species_protection', 'bird_count'];
query.returnGeometry = false;

const { features } = await observations.queryFeatures(query);
const summary = summarize(features);
renderAnalysisPanel(summary);
```

### 9.4 缓冲区分析：第二个加分功能

可做“距重点观测点 1 km/3 km 巡护缓冲区”。实现有两种层级：

| 方案 | 何时使用 | 说明 |
|---|---|---|
| ArcGIS JS `geometryEngine` 或 geometry service | 需要快速网页演示 | 前端生成缓冲区并统计 |
| Geoprocessing Service | 比赛强调服务化、后端分析 | 用 ArcGIS Pro ModelBuilder/Script Tool 发布为 GP 服务 |

先完成圈选统计，再做缓冲区。不要为了展示复杂算法而牺牲基础图层、弹窗和筛选的稳定性。

### 9.5 Geoprocessing Service 的建议任务

如果时间充足，建立“巡护优先区分析”工具：

输入：日期范围、保护等级、缓冲距离。  
处理：筛选重点观测点 -> 缓冲 -> 叠加统计 -> 输出优先巡护面/建议表。  
输出：Feature Set 或服务图层，以及可读摘要。

必须记录：工具参数名、单位、坐标系、输入服务 URL、输出字段、运行时长、失败信息。

---

## 10. 第六步：同步与自动化

### 10.1 当前数据更新流程

原平台数据变化后，至少执行：

```powershell
python manage.py normalize_protection_levels
python manage.py refresh_map_observation_cache --batch-size 10000
```

如果 ArcGIS 使用物化视图，再执行物化视图刷新。建议增加一个新命令，而不是靠人工记忆 SQL：

```text
python manage.py refresh_arcgis_exports
```

该命令应只连接队友自己的 ArcGIS 开发数据库，执行固定的 `REFRESH MATERIALIZED VIEW`，完成后输出行数和时间。实现前先确认数据库连接，避免误刷新其他环境。

### 10.2 同步验收

每次导入/刷新后按此顺序检查：

1. `MapObservationCache` 数量是否合理。
2. ArcGIS 视图/物化视图记录数是否与缓存一致。
3. ArcGIS REST Query 的 `returnCountOnly=true` 是否一致。
4. 网页日期筛选后数量是否变化合理。
5. 随机挑 3 个记录，核对物种、日期、经纬度、保护等级。

不要只看“地图能显示”，必须验证字段和值。

---

## 11. 测试清单

### 11.1 后端与数据

```powershell
cd <PROJECT_DIR>
python manage.py check
python manage.py showmigrations
```

必要验证：

- 当前连接的数据库必须是队友自己创建的开发库，不得误连生产库或其他队友的数据库。
- `refresh_map_observation_cache` 成功。
- `/api/map-observations/` 返回 200。
- 服务账户只能 `SELECT`，不能 `INSERT/UPDATE/DELETE`。

### 11.2 ArcGIS REST 服务

逐项检查：

- Services Directory 可打开。
- Feature Layer metadata 中有正确 `geometryType`、`objectIdField`、`spatialReference`。
- `query?where=1%3D1&returnCountOnly=true&f=pjson` 返回成功。
- `query?where=1%3D1&outFields=*&returnGeometry=true&resultRecordCount=5&f=pjson` 返回几何。
- 日期与保护等级 where 条件可用。
- 没有返回待审核记录、密码、用户隐私字段。

### 11.3 网页 UI

- `/arcgis/` 不白屏；ArcGIS CDN 加载失败时有错误提示。
- 点、线、面图层均可开关。
- 手机宽度 375px、桌面宽度 1440px 不溢出。
- Popup 字段可读，中文不乱码。
- 热力模式可开启/关闭，切换回点模式正常。
- 日期/保护等级筛选不会把服务拖到超时。
- 圈选分析结果和弹窗/图层同步。

### 11.4 代码质量

- 每个完成的小功能单独提交。
- 提交信息写清楚，例如 `Add ArcGIS observation feature layer`。
- 不提交 `config/local_settings.py`、`.env.local`、Token、ArcGIS Pro 用户缓存、服务缓存。
- 不把大体积临时 `.aprx`、`.sd`、`.zip` 直接塞进 Git；必要时放发布介质或 Releases，并在文档记录版本。

---

## 12. 部署建议

### 12.1 Django 比赛分支单独部署

不要将 ArcGIS 试验直接部署覆盖主站。建议使用独立目录、服务和域名/路径：

```text
/home/xuan1203-arcgis
yellowriver-arcgis.service
https://arcgis-demo.example.com/
```

部署顺序：

```bash
cd /home/xuan1203-arcgis
git fetch origin
git switch competition/arcgis-server
git pull --ff-only origin competition/arcgis-server

source venv/bin/activate
python manage.py check
python manage.py migrate
python manage.py refresh_map_observation_cache --batch-size 10000
python manage.py collectstatic --noinput

sudo systemctl restart yellowriver-arcgis
sudo systemctl reload nginx
```

这里的服务名、虚拟环境路径和数据库配置必须按服务器实际情况修改。不要复制命令到原站执行。

### 12.2 CORS、HTTPS 与 Token

- ArcGIS 服务和 Django 页面尽量都使用 HTTPS。
- 在 ArcGIS Server/Enterprise 配置允许来源时，只加入实际域名和本地开发地址，不要使用无限制 `*` 作为生产策略。
- 受保护服务需要 Token 时，优先走服务器端代理或短期 Token；不要把高权限 Token 放在 JS 文件。
- Django 的 `CORS_ALLOW_ALL_ORIGINS = True` 是现有兼容设置，不是生产安全最佳实践；ArcGIS 分支部署前应收紧允许来源。

---

## 13. Git 协作规则

### 13.1 只在自己的分支开发

```powershell
cd <PROJECT_DIR>
git branch --show-current
# 必须显示 competition/arcgis-server
```

不要在 `master` 分支上写 ArcGIS 功能；始终确认当前目录位于 `competition/arcgis-server`。

### 13.2 每次工作前后

```powershell
# 开始前
git pull --ff-only origin competition/arcgis-server
git status --short

# 修改后
python manage.py check
git diff
git add <明确的文件>
git commit -m "<清晰说明>"
git push origin competition/arcgis-server
```

永远不要使用 `git add .` 或 `git add -A`，因为 `data/`、`media/`、截图和本机配置可能是未跟踪文件。

### 13.3 推荐提交顺序

1. `Add ArcGIS page route and empty layout`
2. `Add configurable ArcGIS service endpoints`
3. `Render ArcGIS observation feature layer`
4. `Add ArcGIS filtering and popup details`
5. `Add heatmap renderer and layer controls`
6. `Add polygon selection analysis`
7. `Document ArcGIS service publishing workflow`
8. `Prepare ArcGIS competition deployment`

---

## 14. 常见故障与处理方式

| 现象 | 优先检查 | 不要做什么 |
|---|---|---|
| 页面白屏 | 浏览器控制台、ArcGIS JS API URL、服务 URL | 不要先重写整个页面 |
| 图层 403/499 | 服务共享权限、Token、Portal 登录状态 | 不要把管理员 Token 写进 JS |
| 图层 404 | 服务文件夹、服务名、图层编号 | 不要猜 URL，先在 REST Directory 复制 |
| 点跑偏 | EPSG:4326、经纬顺序、`shape` 字段 | 不要盲目做坐标转换 |
| 发布视图失败 | 唯一 `objectid`、单一 geometry、读权限 | 不要修改 Django 迁移表结构 |
| 筛选报 SQL 错 | 服务字段名、日期 SQL 方言、引号转义 | 不要直接拼接未转义用户输入 |
| 服务很慢 | 要素数、空间索引、视野查询、物化视图 | 不要让浏览器全量加载十万点 |
| 数据更新后服务不变 | 缓存表、物化视图、服务缓存、浏览器缓存 | 不要重复导入造成重复数据 |
| 原平台出现异常 | 是否误改 `master`、是否共用原库 | 不要继续改，先回到 ArcGIS worktree |

---

## 15. 里程碑计划

### M0：环境和数据确认

- [ ] ArcGIS Pro/Server/Portal 信息确认。
- [ ] 队友自己的 PostgreSQL/PostGIS 数据库连接确认。
- [ ] 只读账号创建。
- [ ] ArcGIS 服务视图 SQL 验证。

### M1：真实服务发布

- [ ] 发布观测点 Feature Service。
- [ ] 发布监测点和样线服务。
- [ ] REST Directory 查询验证。
- [ ] 记录服务 URL 和图层编号。

### M2：网页接入

- [ ] `/arcgis/` 页面可访问。
- [ ] 加载观测点、监测点、样线。
- [ ] Popup、图例、图层控制完成。
- [ ] 筛选与热力图完成。

### M3：分析和比赛表达

- [ ] 圈选统计完成。
- [ ] 缓冲区或 GP 服务完成。
- [ ] 数据刷新命令完成。
- [ ] 完成截图、演示录屏和技术说明。

### M4：部署与答辩

- [ ] 独立测试站部署。
- [ ] CORS/HTTPS/Token 配置检查。
- [ ] 用全新浏览器完成演练。
- [ ] 准备 3 分钟和 8 分钟两种讲解脚本。

---

## 16. 给 AI Agent 的任务提示词

将下面文本与具体任务一起提供给 Agent：

```text
你正在 `<PROJECT_DIR>` 的 `competition/arcgis-server` 分支工作。
先阅读 `docs/ARCGIS_DEVELOPMENT_PLAYBOOK.md`，再阅读：
1. config/settings.py
2. config/urls.py
3. app_monitor/models.py
4. app_monitor/views.py
5. app_monitor/templates/index.html

约束：
- 不修改 `master` 分支；ArcGIS 代码只提交到 `competition/arcgis-server`。
- 不连接、修改或删除其他人的数据库；只使用自己创建的开发数据库。
- 不提交 config/local_settings.py、.env.local、Token、密码或数据集。
- 保留现有 /api/map-observations/ 与 MapObservationCache 逻辑。
- 不替换原 Leaflet 首页；先新增 /arcgis/ 页面。
- 每个阶段先运行当前虚拟环境中的 `python manage.py check`。
- 修改前说明计划，修改后列出文件、验证结果、未解决风险。
```

---

## 17. 最后验收标准

当且仅当以下条件都满足时，ArcGIS 版本才可称为“完成”：

- [ ] 远端 `competition/arcgis-server` 分支包含全部 ArcGIS 代码和文档。
- [ ] `master` 分支和其他开发者的数据库未被 ArcGIS 开发污染。
- [ ] ArcGIS REST 服务真实可访问，不是截图或本地假数据。
- [ ] Django/PostGIS 数据更新后有明确、可复现的 ArcGIS 更新流程。
- [ ] ArcGIS 页面能完成图层加载、筛选、弹窗、热力图和至少一项空间分析。
- [ ] 页面在桌面和移动端可用，错误状态可见且可诊断。
- [ ] 密钥、Token、账号、机器路径均未提交。
- [ ] 有服务 URL 表、发布步骤、测试记录、部署说明和比赛演示材料。

做到上述标准，这一部分才是“ArcGIS 开发集成”，而不是只在页面中嵌入一个 ArcGIS 底图。
