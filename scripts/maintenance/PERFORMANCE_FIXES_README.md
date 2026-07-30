# 性能优化修复包 - 使用说明

## 📋 问题总结

你的平台存在以下性能问题：

1. **DEBUG = True** → 内存泄漏，每个请求的 SQL 都保存在内存中
2. **Gunicorn workers 不足** → 并发能力差，多设备登录排队
3. **缺少 worker 自动重启** → 内存持续增长不释放
4. **5 个境外 CDN** → 国内访问慢或被墙，首屏白屏
5. **无缓存机制** → 每次请求都重新计算统计数据
6. **数据库连接未持久化** → 每次请求新建连接

## 🎯 修复目标

- 首页加载时间从 5-15 秒降到 1-3 秒
- API 响应时间从 500-1700ms 降到 20-200ms
- 多设备登录不再卡顿
- 并发能力提升 5-10 倍

## 📦 修复包内容

### 已修改的文件
- `config/settings.py` - DEBUG=False, 缓存配置, 连接持久化
- `app_monitor/views.py` - 添加缓存逻辑

### 新增的文件
- `gunicorn_config.py` - Gunicorn 配置文件
- `gunicorn.service.template` - Systemd service 模板
- `download_vendor_assets.py` - 下载 CDN 资源到本地
- `update_templates_cdn.py` - 自动更新模板中的 CDN 链接
- `diagnose_performance.sh` - 性能诊断脚本
- `quick_fix.sh` - 一键快速修复脚本
- `PERFORMANCE_FIX_GUIDE.md` - 详细修复指南

## 🚀 快速开始（3 种方式）

### 方式 1：一键修复（推荐新手）

```bash
# 1. 上传所有文件到服务器项目根目录
cd /home/xuan1203

# 2. 给脚本添加执行权限
chmod +x quick_fix.sh diagnose_performance.sh

# 3. 运行一键修复脚本
./quick_fix.sh

# 4. 下载本地 CDN 资源
python download_vendor_assets.py

# 5. 更新模板文件
python update_templates_cdn.py

# 6. 收集静态文件
python manage.py collectstatic --noinput

# 7. 重启服务
sudo systemctl restart gunicorn
sudo systemctl restart nginx

# 8. 验证效果
./diagnose_performance.sh
```

### 方式 2：手动逐步修复（推荐有经验用户）

详见 `PERFORMANCE_FIX_GUIDE.md`

### 方式 3：仅修复关键问题

```bash
# 最小修复（5 分钟）
# 1. 修改 DEBUG
sed -i 's/^DEBUG = True/DEBUG = False/' config/settings.py

# 2. 收集静态文件
python manage.py collectstatic --noinput

# 3. 重启
sudo systemctl restart gunicorn
```

## 📊 验证修复效果

### 1. 运行诊断脚本

```bash
./diagnose_performance.sh
```

应该看到：
- ✓ DEBUG 已正确设置为 False
- ✓ Worker 数量配置合理
- ✓ 已配置缓存系统
- ✓ 已启用数据库连接持久化

### 2. 测试性能

```bash
# 测试首页加载时间
time curl -s http://8.130.88.229/ > /dev/null

# 测试 API 响应时间
time curl -s "http://8.130.88.229/api/map-observations/" > /dev/null

# 测试多次（第二次应该更快，因为缓存）
time curl -s "http://8.130.88.229/api/map-observations/" > /dev/null
```

### 3. 检查服务状态

```bash
# Gunicorn 状态
sudo systemctl status gunicorn

# 查看 worker 进程
ps aux | grep gunicorn | grep -v grep

# 查看内存使用
ps aux | grep gunicorn | awk '{sum+=$6} END {print "Total: " sum/1024 " MB"}'
```

## 🔧 Gunicorn 配置说明

### 当前配置（gunicorn_config.py）

```python
workers = multiprocessing.cpu_count() * 2 + 1  # 自动计算
worker_class = "gthread"  # 多线程支持
threads = 2  # 每个 worker 2 个线程
timeout = 60  # 60 秒超时
max_requests = 500  # 每 500 个请求自动重启 worker
max_requests_jitter = 50  # 随机抖动
```

### 不同服务器配置建议

| 服务器规格 | Workers | Threads | 并发能力 |
|-----------|---------|---------|---------|
| 1 核 2G | 3 | 2 | ~6 并发 |
| 2 核 4G | 5 | 2 | ~10 并发 |
| 4 核 8G | 9 | 2 | ~18 并发 |
| 8 核 16G | 17 | 2 | ~34 并发 |

## 📁 文件说明

### 配置文件
- **gunicorn_config.py** - Gunicorn 主配置，自动计算 workers
- **gunicorn.service.template** - Systemd service 模板，需要复制到 `/etc/systemd/system/`

### 脚本文件
- **download_vendor_assets.py** - 下载 Leaflet, Font Awesome, Chart.js, jQuery 到本地
- **update_templates_cdn.py** - 自动替换模板中的 CDN 链接为本地路径
- **diagnose_performance.sh** - 全面诊断系统配置和性能
- **quick_fix.sh** - 一键应用所有修复

### 文档文件
- **PERFORMANCE_FIX_GUIDE.md** - 详细的修复指南，包含故障排查
- **PERFORMANCE_FIXES_README.md** - 本文件

## ⚠️ 注意事项

### 1. 备份

所有脚本都会自动备份原文件：
- `config/settings.py.backup.YYYYMMDD_HHMMSS`
- `*.html.backup`

### 2. ALLOWED_HOSTS

修改 DEBUG=False 后，必须正确配置 ALLOWED_HOSTS：

```python
ALLOWED_HOSTS = [
    '3.1415926.love',      # 你的域名
    '8.130.88.229',        # 服务器 IP
    'localhost',
    '127.0.0.1',
]
```

### 3. 静态文件

每次修改后都要收集静态文件：

```bash
python manage.py collectstatic --noinput
```

### 4. 服务重启

修改配置后必须重启：

```bash
sudo systemctl restart gunicorn
sudo systemctl restart nginx
```

## 🐛 故障排查

### 问题 1：网站 500 错误

```bash
# 查看错误日志
sudo journalctl -u gunicorn -n 50

# 常见原因
# - ALLOWED_HOSTS 配置错误
# - 静态文件未收集
# - 数据库连接失败
```

### 问题 2：静态文件 404

```bash
# 重新收集
python manage.py collectstatic --noinput --clear

# 检查 Nginx 配置
sudo nginx -t
sudo systemctl reload nginx
```

### 问题 3：Gunicorn 启动失败

```bash
# 手动测试
cd /home/xuan1203
source venv/bin/activate
gunicorn -c gunicorn_config.py config.wsgi:application

# 查看详细错误
sudo journalctl -u gunicorn -n 100 --no-pager
```

### 问题 4：性能没有改善

```bash
# 1. 确认 DEBUG = False
grep "^DEBUG = " config/settings.py

# 2. 确认 workers 数量
ps aux | grep gunicorn | grep -v grep | wc -l

# 3. 确认缓存工作
python manage.py shell
>>> from django.core.cache import cache
>>> cache.set('test', 'value', 30)
>>> cache.get('test')

# 4. 查看慢查询
# 在 settings.py 添加:
LOGGING = {
    'version': 1,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

## 📈 性能监控

### 实时监控命令

```bash
# 实时查看日志
sudo journalctl -u gunicorn -f

# 监控内存
watch -n 1 'ps aux | grep gunicorn | awk "{sum+=\$6} END {print \"Memory: \" sum/1024 \" MB\"}"'

# 监控连接数
watch -n 1 'sudo -u postgres psql -t -c "SELECT count(*) FROM pg_stat_activity;"'

# 系统负载
watch -n 1 uptime
```

### 定期检查

建议每周运行：

```bash
./diagnose_performance.sh > report_$(date +%Y%m%d).txt
```

## 🎓 进阶优化

完成基础修复后，可以考虑：

1. **安装 Redis** - 替换 LocMemCache，支持多 worker 共享缓存
2. **启用 HTTP/2** - Nginx 配置 `listen 443 ssl http2;`
3. **添加 CDN** - 将静态文件上传到阿里云 OSS
4. **数据库索引** - 为常用查询添加索引
5. **异步任务** - 使用 Celery 处理耗时操作

详见 `PERFORMANCE_FIX_GUIDE.md` 的"进一步优化"章节。

## 📞 获取帮助

如果遇到问题，请提供：

1. 诊断报告：`./diagnose_performance.sh`
2. Gunicorn 日志：`sudo journalctl -u gunicorn -n 100`
3. Nginx 日志：`sudo tail -100 /var/log/nginx/error.log`
4. 服务器配置：CPU 核心数、内存大小

## ✅ 检查清单

修复完成后，确认以下项目：

- [ ] DEBUG = False
- [ ] ALLOWED_HOSTS 包含你的域名/IP
- [ ] Gunicorn workers >= 3
- [ ] Gunicorn 配置了 --max-requests
- [ ] 缓存系统已配置
- [ ] 数据库 CONN_MAX_AGE 已设置
- [ ] 静态文件已收集
- [ ] 外部 CDN 已本地化（可选但推荐）
- [ ] 服务已重启
- [ ] 诊断脚本无警告

## 📝 更新日志

- 2024-XX-XX: 初始版本
  - 修复 DEBUG=True 问题
  - 添加 Gunicorn 配置
  - 添加缓存系统
  - 本地化 CDN 资源
  - 添加诊断工具

---

**祝你的平台性能飞起！🚀**
