# 保护区范围图层

输入：用户提供的 protectedArea.zip。坐标系：WGS84 经纬度，属性编码 UTF-8，源类型 PolygonZ，共31个面要素。转换时仅使用二维坐标，不简化边界；全部31个输出面通过GEOS有效性检查，范围与源文件一致。

范围：112.8049874915689—114.2061992407818°E，34.80031005241041—34.98883663624658°N。源Name字段为SYQ、HXQ、HCQ等图斑代号，界面沿用这些代号，不虚构保护区全名或面积单位。截断的HTML说明字段不进入前端。

修改文件：

- app_monitor/static/app_monitor/geo/protected_areas.geojson：静态边界数据。
- scripts/convert_protected_area.py：可重复执行的ZIP转换脚本，复用原行政区转换工具，无新增运行时依赖。
- app_monitor/templates/index.html：增加“保护区范围”图层、默认显示、开关、图斑信息和交互优先级。

显示与交互：绿色半透明填充位于点位下方，独立边界线位于热力图上方且不接收鼠标事件。地图空白位置点击按实际多边形及内环判断命中，避免点位画布覆盖后区域无法点选。点位点击、缓冲选点及热力圈选优先。

验证：Django check、git diff --check通过。浏览器检查全部通过：31面加载、填充和边线层级、关闭和重开、保护区内部真实记录详情、图斑弹窗、缓冲选中心、热力圈选、手机图层控件、无JS错误。详细结果见protected-area-results.json，截图见protected-area-initial.png、protected-area-detail.png、protected-area-mobile.png。

本地访问：http://127.0.0.1:8012/ 。未修改原数据库，未提交或部署线上。
