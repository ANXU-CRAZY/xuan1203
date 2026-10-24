# 2026-10-24：导航、底图与方舟实验室主题

实际修改目录：`D:\xuan1203`。本地访问：`http://127.0.0.1:8012/`。未提交、推送或部署线上。

## 完成内容

1. 图层选择器增加“不显示底图”，选中后移除天地图底图和注记瓦片，保留行政区、观鸟记录和热力图；切回电子地图或卫星影像后恢复对应注记。注记原有显隐状态保留。
2. 顶部六个游戏合并到“生态互动”：识鸟、闯关、修复、迁徙、侦探、浮岛。支持鼠标、触控、键盘、Esc、关闭按钮、点击外部收起，游客和登录用户共用同一入口。
3. 保留“黄河生态方舟”，补充“方舟实验室 · 郑州市自然保护地事务中心”。名称统一使用“方舟实验室”。
4. 实际读取实验室主页 https://3.1415926.love/arklb-geoai/ 及其 style.css / theme.css：字体为 Inter、苹方、微软雅黑；正文 #172B35，蓝绿 #287F89，雾白 #F7F9F7，生态绿 #789C86。使用本地共享主题应用到大屏、百科、科普、图库、登录、个人和上报页面；六个游戏共享字体，保留游戏内容的状态颜色。保护等级颜色保持其含义。
5. 顶部增加“访问方舟实验室”，在新标签打开指定实验室主页，设置 noopener noreferrer。

## 修改文件

- 大屏导航、底图选项、图表配色：`app_monitor/templates/index.html`。
- 公共主题入口：`app_monitor/templates/app_monitor/site_theme.html`。
- 公共主题与生态互动交互：`app_monitor/static/app_monitor/site-theme.css`、`app_monitor/static/app_monitor/site-shell.js`。
- 接入主题：`app_monitor/templates/` 下 species、species-detail、species-gallery、articles、article-detail、image-gallery 六个模板；`templates/` 下 login、profile、report 和六个游戏模板。每个模板只增加公共主题引用和页面类型标识，并移除公共页面不再使用的字体引用。
- 浏览器验证：`check_site_navigation.py`、`site-navigation-results.json`、`site-final-version.json` 和 `lab-theme-*.png`。

## 验证

- Django check、共享脚本语法、git diff --check 通过。
- 47 项浏览器断言通过：底图关闭和恢复、关闭底图后平移无新瓦片请求、数据图层保留、六游戏入口、展开/关闭/键盘、登录和游客导航、实验室名称与链接、公共页面主题渲染、计算后的字体和色调。
- 1536×850、1280×720、1024×768、768×1024、390×844 均检查菜单边界、顶部工具条与页面溢出；桌面概览仍位于右下角。
- 本次页面无 JS 错误，无新增 8090、/iserver/、/api/supermap/ 请求。
- 最终服务实际返回 `site-theme.css?v=20261024-2`，物种柱状图和趋势图使用 #287F89；初始视图仍代表 117911 条记录、1124 个不同坐标，概览底边距仍为 20px。

截图：`lab-theme-desktop.png`（完整桌面）、`lab-theme-games.png`（生态互动展开）、`lab-theme-basemap-off.png`（关闭底图）、`lab-theme-390-games.png`（手机展开）。


## 后续视觉调整：20261024-3

按用户确认，仅恢复顶栏按钮样式，各入口页面继续保留当前布局和字体。顶部恢复原版彩色渐变胶囊按钮、白色图标文字与描边入口，保留生态互动合集及访问方舟实验室。左上角单位说明更新为“方舟实验室 · 郑州大学地球科学与技术学院 · 郑州市自然保护地事务中心”。

主题强调色及图表调色板的 HSL 饱和度相对提高约20%，亮度提高2.5个百分点；底图瓦片使用 saturate(1.2) brightness(1.02)，点位与保护等级颜色不套全局滤镜。新样式版本为20261024-3。

本轮完成Django检查、diff检查及1536、1280、1024、390四种宽度的浏览器核对：导航彩色按钮、生态互动展开收起、页面无横向溢出、顶部工具条位置、右下角概览位置、全部117911条记录代表数量。无JS错误。结果和截图见vivid-navigation-results.json、vivid-navigation-desktop.png、vivid-navigation-mobile.png。
