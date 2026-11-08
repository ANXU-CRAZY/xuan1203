# 方舟慧眼：识鸟 / 识别地物

## 入口与能力

监测大屏中间入口改为「AI识别」。点击后选择「识鸟」或「识别地物」；顶栏九宫格中的方舟慧眼也打开相同选择。

| 任务 | 地址 | 能力 | 运行方式 |
| --- | --- | --- | --- |
| 任务选择 | `/huiyan/choose/` | 无 JavaScript 时仍可选择 | Django 页面 |
| 识鸟 | `/huiyan/` | 现有鸟兽物种识别、计数与置信度 | 原 ONNX 识别器，保持原接口 |
| 识别地物 | `/huiyan/land/` | SAM 2 点/框提示分割、GroundingDINO 文字提示分割 | 独立轻量版 HTTP 子进程 |

地物工作台返回掩码、框、面积及分割分数，不负责物种分类；目标名称是人工标签。文字提示、中文词表及自动补冠词逻辑沿用轻量版本身。没有把两种模型或状态放进同一推理进程。

## 本地运行

当前提供的目录是 Windows PyInstaller onedir 成品，入口为 `E:\方舟慧眼-轻量版\方舟慧眼-轻量版.exe`，并没有 `web_demo.py` 源文件。

启动项目后访问 <http://127.0.0.1:8012/>，点「AI识别」→「识别地物」。宿主会在第一次打开地物工作台时启动本机 `127.0.0.1:8013` 的轻量版，默认 tiny / CPU。识鸟和监测大屏不会触发 SAM 或 GroundingDINO 加载。

```powershell
& .\anxu\Scripts\python.exe manage.py runserver 127.0.0.1:8012 --insecure --noreload
```

`config/settings.py` 中的设置均可通过同名环境变量覆盖：

| 配置 | 默认值 | 含义 |
| --- | --- | --- |
| `HUIYAN_LAND_SERVICE_URL` | `http://127.0.0.1:8013` | 仅接受本机 HTTP 地址，固定端口，不静默换端口 |
| `HUIYAN_LAND_EXECUTABLE` | 上述 E 盘 exe | 保留整个 onedir 目录，包括 `_internal`、checkpoints、models |
| `HUIYAN_LAND_AUTOSTART` | Windows 为 `1`，其他系统为 `0` | 是否按需启动 exe |
| `HUIYAN_LAND_MODEL` | `tiny` | 可选 tiny / small / base_plus / large |
| `HUIYAN_LAND_DEVICE` | `cpu` | cpu / cuda / auto |

宿主与服务在同一台机器，浏览器通过 Django 的 `/huiyan/land/workbench/` 访问，不需要跨域或开放 8013 到公网。已启动服务可直接复用。端口若是其他应用会明确报错，不会关闭或替换它。子进程日志在 `var/land-segmentation/service.log`；浏览器离开工作台时发送 CSRF 保护的释放请求，服务留待后续复用。原浏览器刷新可恢复图像；其他浏览器取得工作台后不能恢复前一用户的数据。

## 隔离与适配

- 提供的轻量版文件、模型权重、打包链路均未修改。原生三栏尺寸、模块顺序及控件位置保留；宿主在返回页面时改写接口/图像地址、注入同源 CSRF 请求头，并加载独立的 `huiyan/land-theme.css` 外观层。
- Django 不导入 SAM 2 / PyTorch / GroundingDINO，不向当前 requirements 添加重量依赖。
- 操作通过 OS 文件锁串行执行，线程和多个 WSGI worker 共用同一把锁；模型初次加载时，同一会话的图像请求排队等待。
- 单进程单图采用浏览器会话租约。其他浏览器收到占用提示，不能读取或覆盖当前图片、掩码或坐标。新会话载入图片前清理旧计数/历史；加载前不返回前一会话图像。20 分钟无请求可重新取得工作台。离开页面时自动释放，不要多人同时直接访问 8013。
- 原生配置接口改为浏览器 localStorage 保存，不读写宿主的私有配置文件。例图文件名及上传批次文件名不能包含路径；只代理明确允许的接口；请求/响应有大小上限，代理不跟随重定向。
- 当前打包程序 CSV 将经纬度列写反。宿主适配器以对象的 `lon` / `lat` 字段校正 CSV 中「经度」「纬度」，保留原文件名、其他字段及 BOM。
- `/platform/` 域名挂载和独立慧眼 WSGI URL 配置均可使用新入口。

会话锁文件是单机部署方案；扩展到多台宿主需要每用户独立分割实例或统一队列，不能直接增加多个访问同一个 STATE 的 worker。

## 验证

```powershell
& .\anxu\Scripts\python.exe manage.py check
& .\anxu\Scripts\python.exe manage.py test app_monitor.test_land_segmentation
& .\anxu\Scripts\python.exe scripts/check_land_segmentation.py --image 'E:\方舟慧眼-轻量版\input\truck.jpg' --box 250 250 1550 1100 --output tmp/land-overlay.png
```

脚本通过宿主自动启动服务，上传真实图片、框选、改名、设置坐标、保存叠加图、核对 CSV，再清空目标并释放工作会话。并非模拟模型结果。

2026-11-08 本机实测：1800×1200 卡车例图，tiny / CPU；框选分数 **0.9217**，bbox `[186,282,1608,852]`，面积 **519707 px**；命名/英文名/坐标写入成功；导出带 BOM；清空后 objects 为 0。浏览器原生处理函数实测点选产生掩码；`a truck` 文字提示通过 GroundingDINO + SAM 返回一个目标，分数 **0.8589**。CPU 文字提示完整处理约 45 秒，包含模型加载和推理时间，不能承诺实时返回。

原目录中没有 `verify_round40~75.py` 或 `verify_exe_module.py`，因此没有宣称运行其 376 项原工程回归；宿主测试覆盖的是路由、URL 重写、CSRF、跨会话隔离、跨进程锁、配置隔离、无服务提示及 CSV 坐标。

## 弹窗设计调整

产品是生态监测地图中的任务选择；气质取克制、清楚、可靠；视觉沿用方舟地图的青绿和实验室标识；颜色集中在两个任务图标，外层保持白底；方舟标识作为识别细节。

原版问题是标题/大图标块过重、纵向卡片和说明重复占据空间。调整为 464px 双列弹窗，细边框与中性阴影、20px 标题、短说明和统一的悬停/键盘焦点；窄屏保留两项并排，允许说明自然换行；原任务与顺序不变。设计检查参考 [unslop by Damir Sokolovsky (@heydamir)](https://heydamir.design/unslop)，CC BY 4.0。

## 地物页外观调整（2026-11-08）

移除宿主额外的「识别地物 · 智能分割 / 按点、框或文字提取目标轮廓」说明栏。通过独立外观层对齐识鸟页面的白底、青绿操作色、面板边框、字体和深浅色主题；没有直接引用包含网格和尺寸规则的鸟类工作区样式。

在 1440、1280、390px 三种宽度，逐项比较启用/禁用外观层时的顶栏、三栏容器、各列、Tab、图像模块及视窗位置尺寸，差异均为 0；验证深浅主题切换及与识鸟页面使用的 JSON 主题存储格式兼容。18 项适配测试通过，包含离开页面、刷新恢复和跨浏览器隔离。

## 部署边界

本次接通的是本地 Windows 成品。Linux 服务器无法直接运行这个 Windows exe；在线部署前需要取得分割项目的源码或 Linux 服务包，在服务器独立运行，并将本机服务地址配置到 Django。不要把 Windows 的 `_internal` 上传覆盖 Django 虚拟环境，也不要将数 GB 权重加入 Git。
