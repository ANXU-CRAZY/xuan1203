# 黄河生态方舟平台 - 性能优化修复指南

## 问题诊断总结

根据性能分析，平台存在以下关键问题：

### P0 级别（立即修复）
1. **DEBUG = True** - 导致内存泄漏和严重性能下降
2. **Gunicorn workers 配置不足** - 并发能力受限
3. **缺少 worker 自动重启机制** - 内存持续增长

### P1 级别（重要优化）
4. **外部 CDN 依赖** - 5 个境外 CDN 导致首屏加载缓慢
5. **缺少缓存机制** - 首页每次请求都重新计算
6. **数据库连接未持久化** - 每次请求新建连接

---

## 修复步骤（按优先级）

### 第一步：关闭 DEBUG 模式（5 分钟，立即见效）

**已修改文件：`config/settings.py`**

```python
# 修改前
DEBUG = True
ALLOWED_HOSTS = ['*']

# 修改后
DEBUG = False
ALLOWED_HOSTS = ['3.1415926.love', '8.130.88.229', 'localhost', '127.0.0.1']
```

**执行命令：**
```bash
cd /home/xuan1203
python manage.py check
python manage.py collectstatic --noinput
sudo systemctl restart gunicorn
```

**预期效果：**
- 内存不再无限增长
- TTFB 从波动的 300-1700ms 降到稳定 50-200ms
- 多设备登录不再卡顿

---

### 第二步：配置 Gunicorn（10 分钟，立即见效）

#### 方案 A：使用配置文件（推荐）

**已创建文件：`gunicorn_config.py`**

1. 复制 systemd service 模板：
```bash
sudo cp gunicorn.service.template /etc/systemd/system/gunicorn.service
```

2. 编辑 service 文件，修改路径：
```bash
sudo nano /etc/systemd/system/gunicorn.service
```

确保以下内容正确：
```ini
User=xuan1203
WorkingDirectory=/home/xuan1203
ExecStart=/home/xuan1203/venv/bin/gunicorn \
    -c /home/xuan1203/gunicorn_config.py \
    config.wsgi:application
```

3. 重新加载并启动：
```bash
sudo systemctl daemon-reload
sudo systemctl enable gunicorn
sudo systemctl restart gunicorn
sudo systemctl status gunicorn
```

#### 方案 B：直接修改现有 service 文件

如果你已有 `/etc/systemd/system/gunicorn.service`，修改 `ExecStart` 行：

```bash
sudo nano /etc/systemd/system/gunicorn.service
```

**2 核服务器配置：**
```ini
ExecStart=/home/xuan1203/venv/bin/gunicorn config.wsgi:application \
    --workers 5 \
    --threads 2 \
    --worker-class gthread \
    --timeout 60 \
    --graceful-timeout 30 \
    --max-requests 500 \
    --max-requests-jitter 50 \
    --bind unix:/run/gunicorn.sock \
    --access-logfile - \
    --error-logfile -
```

**4 核服务器配置：**
```ini
ExecStart=/home/xuan1203/venv/bin/gunicorn config.wsgi:application \
    --workers 9 \
    --threads 2 \
    --worker-class gthread \
    --timeout 60 \
    --graceful-timeout 30 \
    --max-requests 500 \
    --max-requests-jitter 50 \
    --bind unix:/run/gunicorn.sock \
    --access-logfile - \
    --error-logfile -
```

然后重启：
```bash
sudo systemctl daemon-reload
sudo systemctl restart gunicorn
```

**验证配置：**
```bash
# 查看进程数（应该是 workers + 1）
ps aux | grep gunicorn | grep -v grep | wc -l

# 查看详细信息
ps aux | grep gunicorn | grep -v grep
```

**预期效果：**
- 并发能力提升 3-5 倍
- 多设备同时访问不再排队
- Worker 每处理 500 个请求自动重启，释放内存

---

### 第三步：本地化外部 CDN 资源（30 分钟，立即见效）

**问题：** 首页依赖 5 个境外 CDN，国内访问缓慢或被墙

#### 3.1 下载资源到本地

```bash
cd /home/xuan1203
python download_vendor_assets.py
```

这会下载以下资源到 `static/vendor/`：
- Leaflet (地图库)
- Font Awesome (图标)
- Chart.js (图表)
- jQuery

#### 3.2 修改模板文件

编辑 `app_monitor/templates/index.html`：

**修改前：**
```html
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
```

**修改后：**
```html
{% load static %}
<link rel="stylesheet" href="{% static 'vendor/leaflet/leaflet.css' %}" />
<link rel="stylesheet" href="{% static 'vendor/font-awesome/all.min.css' %}">
<!-- Google Fonts 删除或替换为国内镜像 -->
<script src="{% static 'vendor/chart.js/chart.umd.min.js' %}"></script>
```

#### 3.3 收集静态文件并重启

```bash
python manage.py collectstatic --noinput
sudo systemctl restart gunicorn
sudo systemctl restart nginx
```

**预期效果：**
- 首屏加载时间从 5-15 秒降到 1-3 秒
- 不再出现白屏等待
- 多设备首次打开都很快

---

### 第四步：启用缓存（30 分钟，中等效果）

**已修改文件：**
- `config/settings.py` - 添加了缓存配置
- `app_monitor/views.py` - 为 `map_observations` 添加了缓存

#### 4.1 验证缓存配置

检查 `config/settings.py` 中是否有：
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'yellow-river-cache',
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
        }
    }
}
```

#### 4.2 重启服务

```bash
sudo systemctl restart gunicorn
```

**预期效果：**
- 首页 API 响应时间从 500-1700ms 降到 20-50ms
- 相同查询参数的请求直接返回缓存（30 秒内）

#### 4.3 进阶：安装 Redis（可选，推荐生产环境）

```bash
# 安装 Redis
sudo apt update
sudo apt install redis-server -y

# 启动 Redis
sudo systemctl start redis
sudo systemctl enable redis

# 安装 Python Redis 客户端
source venv/bin/activate
pip install redis

# 修改 settings.py
```

修改 `config/settings.py`：
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}
```

重启：
```bash
sudo systemctl restart gunicorn
```

---

## 验证修复效果

### 1. 运行诊断脚本

```bash
chmod +x diagnose_performance.sh
./diagnose_performance.sh
```

这会生成完整的诊断报告，包括：
- DEBUG 状态
- Gunicorn 配置
- Worker 数量
- 缓存状态
- 静态文件状态

### 2. 手动验证

#### 检查 DEBUG 状态
```bash
grep "^DEBUG = " config/settings.py
# 应该输出: DEBUG = False
```

#### 检查 Gunicorn 进程
```bash
ps aux | grep gunicorn | grep -v grep
# 应该看到多个 worker 进程
```

#### 检查静态文件
```bash
ls -lh static/vendor/
# 应该看到 leaflet, font-awesome, chart.js 等目录
```

#### 测试首页加载速度
```bash
curl -w "\nTime: %{time_total}s\n" -o /dev/null -s http://8.130.88.229/
# 应该在 0.5 秒以内
```

#### 测试 API 响应时间
```bash
time curl -s "http://8.130.88.229/api/map-observations/" > /dev/null
# 第一次可能慢，第二次应该很快（缓存命中）
```

---

## 预期性能提升

| 指标 | 修复前 | 修复后 | 提升 |
|------|--------|--------|------|
| 首页 TTFB | 300-1700ms | 50-200ms | **70-90%** |
| 首屏加载时间 | 5-15 秒 | 1-3 秒 | **80%** |
| API 响应时间（缓存命中） | 500-1700ms | 20-50ms | **95%** |
| 并发能力 | 1-3 请求/秒 | 10-30 请求/秒 | **5-10 倍** |
| 多设备卡顿 | 经常卡顿 | 基本不卡 | **显著改善** |

---

## 故障排查

### 问题 1：修改后网站无法访问

**检查步骤：**
```bash
# 1. 检查 Gunicorn 状态
sudo systemctl status gunicorn

# 2. 查看错误日志
sudo journalctl -u gunicorn -n 50

# 3. 检查 Nginx 状态
sudo systemctl status nginx

# 4. 检查 Nginx 错误日志
sudo tail -50 /var/log/nginx/error.log
```

**常见原因：**
- `ALLOWED_HOSTS` 配置错误 → 添加你的域名/IP
- 静态文件未收集 → 运行 `python manage.py collectstatic`
- Gunicorn socket 权限问题 → 检查 `/run/gunicorn.sock`

### 问题 2：Gunicorn 启动失败

```bash
# 查看详细错误
sudo journalctl -u gunicorn -n 100 --no-pager

# 手动测试启动
cd /home/xuan1203
source venv/bin/activate
gunicorn -c gunicorn_config.py config.wsgi:application
```

**常见原因：**
- 配置文件路径错误
- 虚拟环境路径错误
- Python 包缺失

### 问题 3：静态文件 404

```bash
# 检查 static_root
ls -lh static_root/

# 重新收集
python manage.py collectstatic --noinput --clear

# 检查 Nginx 配置
sudo nginx -t
```

### 问题 4：缓存不生效

```bash
# 检查缓存配置
python manage.py shell
>>> from django.core.cache import cache
>>> cache.set('test', 'value', 30)
>>> cache.get('test')
# 应该返回 'value'
```

---

## 持续监控

### 1. 设置日志监控

```bash
# 实时查看 Gunicorn 日志
sudo journalctl -u gunicorn -f

# 实时查看 Nginx 访问日志
sudo tail -f /var/log/nginx/access.log

# 实时查看 Nginx 错误日志
sudo tail -f /var/log/nginx/error.log
```

### 2. 性能监控命令

```bash
# 查看 Gunicorn 内存使用
ps aux | grep gunicorn | awk '{sum+=$6} END {print "Total Memory: " sum/1024 " MB"}'

# 查看数据库连接数
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"

# 查看系统负载
uptime
```

### 3. 定期检查

建议每周运行一次诊断脚本：
```bash
./diagnose_performance.sh > performance_report_$(date +%Y%m%d).txt
```

---

## 进一步优化（可选）

### 1. 启用 HTTP/2 和 Brotli 压缩

编辑 Nginx 配置：
```nginx
server {
    listen 443 ssl http2;
    
    # Brotli 压缩（需要安装模块）
    brotli on;
    brotli_comp_level 6;
    brotli_types text/plain text/css application/json application/javascript text/xml application/xml;
}
```

### 2. 添加 CDN

将静态文件上传到阿里云 OSS 或腾讯云 COS，配置 CDN 加速。

### 3. 数据库优化

```sql
-- 为常用查询添加索引
CREATE INDEX idx_observation_status_time ON app_monitor_observationrecord(status, observation_time DESC);
CREATE INDEX idx_observation_species ON app_monitor_observationrecord(species_id);

-- 定期清理
VACUUM ANALYZE;
```

### 4. 启用 Django Debug Toolbar（仅开发环境）

```bash
pip install django-debug-toolbar
```

在 `settings.py` 中配置，用于分析 SQL 查询和性能瓶颈。

---

## 联系支持

如果遇到问题，请提供以下信息：

1. 诊断脚本输出：`./diagnose_performance.sh`
2. Gunicorn 日志：`sudo journalctl -u gunicorn -n 100`
3. Nginx 错误日志：`sudo tail -100 /var/log/nginx/error.log`
4. 服务器配置：CPU 核心数、内存大小

---

## 总结

完成以上步骤后，你的平台性能应该有显著提升：

✅ DEBUG = False - 解决内存泄漏  
✅ Gunicorn 多 worker - 提升并发能力  
✅ Worker 自动重启 - 防止内存增长  
✅ 本地化 CDN - 加快首屏加载  
✅ 启用缓存 - 减少数据库查询  
✅ 连接持久化 - 减少连接开销  

**关键指标：多设备登录卡顿问题应该基本解决！**
