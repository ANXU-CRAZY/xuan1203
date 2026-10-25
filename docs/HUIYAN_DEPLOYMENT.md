# 方舟慧眼服务部署

方舟慧眼使用黄河生态方舟现有 Django 项目、数据库配置及域名。模型资源位于 `app_monitor/huiyan_runtime/model/`，不放进 Nginx 静态目录。

## 依赖

- Python 3.11 / 3.12；`onnxruntime==1.20.1`、`numpy>=1.24,<3`，以及主项目现有依赖。
- Linux 标注图中文字体：Ubuntu 包 `fonts-noto-cjk`。Windows 使用微软雅黑。
- 首次慧眼请求加载模型，模型采用 2 个 CPU 线程；大图分块检测后统一去重。

## 生产进程

主站已有 5 个 Gunicorn 工作进程。为避免每个进程都加载一份模型，`/huiyan/` 交给单独的 `fangzhou-huiyan.service`，使用 `config.huiyan_wsgi:application`，仍运行同一份 Django 代码，只绑定 `/run/fangzhou-huiyan.sock`。该入口复用主站设置及慧眼路由，避免载入原有水鸟识别页面的 PyTorch 运行库。公网没有新增端口。

- 识别进程：1 个工作进程、2 个线程、CPU 配额 150%、内存软限制 640MB、硬限制 900MB。
- 主站 `gunicorn` 配置、数据库、天地图 key 与小舟密钥保持原值。
- Nginx 的慧眼 location 连接该 Unix socket；静态文件仍通过原来的 `/static/` 服务。客户端请求体上限 20MB，满足现有 TIFF 例图上传。
- 图片由本站处理，不向第三方识别服务发送、不保存用户原图。

## 更新与回退

只打包本次提交涉及的应用文件，逐个计算 SHA-256。发布前保存在 `/root/backups/huiyan-时间戳/`：原文件、原 Nginx 配置、原发布清单、Python 依赖清单。原数据库不执行迁移或数据写入。

先在暂存目录验证 Linux 模型推理与中文绘图，再替换文件、执行 Django 检查和 collectstatic。启动识别工作进程后先通过 Unix socket 验证，再切换 Nginx 路由。主站以 HUP 平滑加载新导航和 URL。

失败时恢复备份中的应用文件及 Nginx 配置、重新 collectstatic，停止新增识别服务，并平滑重载主站。

查看运行状态：

```bash
systemctl status fangzhou-huiyan gunicorn nginx
journalctl -u fangzhou-huiyan --since '10 minutes ago'
```

上线验收：首页、`/huiyan/`、模型状态、五张例图、TIFF 转换、识别与 XLSX 导出、天地图、手机布局及主站小舟智能体。发布完成后记录提交和备份路径，不将环境文件或账号推送到 Git。
