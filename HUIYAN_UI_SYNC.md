# 方舟慧眼界面对齐验收

日期：2026-10-26。工程：`D:\xuan1203`。本次只调整慧眼页面的展示结构与样式，保留原 Django 接口、天地图配置、模型资源、例图识别和导出链路。

## 改动文件

- `app_monitor/templates/app_monitor/huiyan.html`
  - 将生态类群面板置于目标物种面板之前，统一面板标题行和编号样式。
  - 例图收纳到右侧操作说明，图像区保留一键跳转例图按钮。
  - 结果表使用独立空态覆盖层，目标物体与结果表按同一高度变量排版。
  - 空间定位标题、当前位置读数、署名位置和交互文案对齐新版慧眼，同时继续使用站点 `/huiyan/api/*` 接口和天地图。
  - 保留批量处理、历史记录、坐标编辑、重绘、Excel 导出和五张实景例图的原有行为。
- `app_monitor/static/app_monitor/huiyan/workspace.css`
  - 统一三栏工作区、顶栏、按钮、例图、空态、地图和移动端响应式布局；延续本站浅色纸白、青绿色和字体体系。
- `config/huiyan_wsgi.py`、`config/wsgi.py`
  - 保留已有路径挂载封装，供本地和部署入口复用。

## 未迁移项

没有迁入独立工程的本地 HTTP 服务、打包脚本、训练脚本、外部地图或新的后端接口。识别模型、物种库、分类向量和现有数据库未改写，也没有引入 iServer、SuperMap 或 8090 依赖。

## 验收截图与结果

当前版本六档截图位于 `tmp/huiyan-ui-sync/`：

- `local-1920.png`
- `local-1536.png`
- `local-1280.png`
- `local-1024.png`
- `local-768.png`
- `local-390.png`

`tmp/huiyan-ui-sync/layout-results.json` 记录了各档尺寸、主题、字体、色彩、三栏位置、滚动宽度和结果/裁剪区高度。桌面视口三栏底边一致，全部视口的文档滚动宽度等于视口宽度；移动端按上下顺序自然滚动。

## 复现命令

```powershell
.\anxu\Scripts\python.exe manage.py check
.\anxu\Scripts\python.exe -m unittest app_monitor.test_huiyan_catalog -v
.\anxu\Scripts\python.exe -m pip check
.\anxu\Scripts\python.exe tmp\huiyan-update\api_check.py
.\anxu\Scripts\python.exe tmp\huiyan-update\browser_check.py
.\anxu\Scripts\python.exe tmp\huiyan-ui-sync\snapshot.py
```

本轮实测：Django 检查通过，分类回归 3 项通过，依赖无冲突；慧眼状态、23 个类群/40 个细分组合、例图 TIFF 转换与识别、重绘、批量处理、三工作表 Excel 导出均返回 200；浏览器交互 13 项通过，天地图瓦片返回 200，页面无新增 JavaScript 异常。

本地预览地址：`http://127.0.0.1:8012/huiyan/`。
