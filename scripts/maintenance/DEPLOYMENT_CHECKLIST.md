# 部署检查清单

## 📋 修复前准备

- [ ] 备份数据库
  ```bash
  sudo -u postgres pg_dump "Yellow River" > backup_$(date +%Y%m%d).sql
  ```

- [ ] 备份当前代码
  ```bash
  tar -czf backup_code_$(date +%Y%m%d).tar.gz /home/xuan1203
  ```

- [ ] 记录当前配置
  ```bash
  cp config/settings.py config/settings.py.original
  cp /etc/systemd/system/gunicorn.service gunicorn.service.original
  ```

- [ ] 确认服务器信息
  ```bash
  nproc  # CPU 核心数
  free -h  # 内存大小
  df -h  # 磁盘空间
  ```

## 🔧 核心修复步骤

### 步骤 1：关闭 DEBUG（必须）

- [ ] 修改 `config/settings.py`
  ```python
  DEBUG = False
  ALLOWED_HOSTS = ['3.1415926.love', '8.130.88.229', 'localhost', '127.0.0.1']
  ```

- [ ] 验证修改
  ```bash
  grep "^DEBUG = " config/settings.py
  grep "^ALLOWED_HOSTS" config/settings.py
  ```

### 步骤 2：添加数据库连接持久化（必须）

- [ ] 在 `config/settings.py` 的 DATABASES 配置中添加
  ```python
  'CONN_MAX_AGE': 60,
  ```

- [ ] 验证修改
  ```bash
  grep "CONN_MAX_AGE" config/settings.py
  ```

### 步骤 3：配置缓存系统（必须）

- [ ] 在 `config/settings.py` 末尾添加
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

- [ ] 验证修改
  ```bash
  grep "CACHES" config/settings.py
  ```

### 步骤 4：更新视图缓存（必须）

- [ ] 确认 `app_monitor/views.py` 已更新
  - 导入了 `cache` 和 `cache_page`
  - `map_observations` 函数添加了缓存逻辑

- [ ] 验证修改
  ```bash
  grep "from django.core.cache import cache" app_monitor/views.py
  grep "cache.get(cache_key)" app_monitor/views.py
  ```

### 步骤 5：配置 Gunicorn（必须）

- [ ] 复制配置文件
  ```bash
  cp gunicorn_config.py /home/xuan1203/
  ```

- [ ] 更新或创建 systemd service
  ```bash
  sudo cp gunicorn.service.template /etc/systemd/system/gunicorn.service
  sudo nano /etc/systemd/system/gunicorn.service
  ```

- [ ] 修改 service 文件中的路径
  - User=xuan1203
  - WorkingDirectory=/home/xuan1203
  - ExecStart=/home/xuan1203/venv/bin/gunicorn ...

- [ ] 重新加载 systemd
  ```bash
  sudo systemctl daemon-reload
  ```

### 步骤 6：收集静态文件（必须）

- [ ] 运行 collectstatic
  ```bash
  cd /home/xuan1203
  source venv/bin/activate
  python manage.py collectstatic --noinput
  ```

- [ ] 验证静态文件
  ```bash
  ls -lh static_root/
  ```

### 步骤 7：重启服务（必须）

- [ ] 重启 Gunicorn
  ```bash
  sudo systemctl restart gunicorn
  ```

- [ ] 检查 Gunicorn 状态
  ```bash
  sudo systemctl status gunicorn
  ```

- [ ] 重启 Nginx
  ```bash
  sudo systemctl restart nginx
  ```

- [ ] 检查 Nginx 状态
  ```bash
  sudo systemctl status nginx
  ```

## 🎯 可选优化步骤

### 步骤 8：本地化 CDN 资源（强烈推荐）

- [ ] 下载 CDN 资源
  ```bash
  python download_vendor_assets.py
  ```

- [ ] 验证下载
  ```bash
  ls -lh static/vendor/
  ```

- [ ] 更新模板文件
  ```bash
  python update_templates_cdn.py
  ```

- [ ] 收集静态文件
  ```bash
  python manage.py collectstatic --noinput
  ```

- [ ] 重启服务
  ```bash
  sudo systemctl restart gunicorn
  sudo systemctl restart nginx
  ```

### 步骤 9：安装 Redis（推荐）

- [ ] 安装 Redis
  ```bash
  sudo apt update
  sudo apt install redis-server -y
  ```

- [ ] 启动 Redis
  ```bash
  sudo systemctl start redis
  sudo systemctl enable redis
  ```

- [ ] 安装 Python 客户端
  ```bash
  source venv/bin/activate
  pip install redis
  ```

- [ ] 更新 settings.py 缓存配置
  ```python
  CACHES = {
      'default': {
          'BACKEND': 'django.core.cache.backends.redis.RedisCache',
          'LOCATION': 'redis://127.0.0.1:6379/1',
      }
  }
  ```

- [ ] 重启 Gunicorn
  ```bash
  sudo systemctl restart gunicorn
  ```

## ✅ 验证步骤

### 验证 1：配置检查

- [ ] 运行诊断脚本
  ```bash
  chmod +x diagnose_performance.sh
  ./diagnose_performance.sh
  ```

- [ ] 检查输出，确认：
  - ✓ DEBUG 已正确设置为 False
  - ✓ Worker 数量配置合理
  - ✓ 已配置缓存系统
  - ✓ 已启用数据库连接持久化

### 验证 2：服务状态

- [ ] Gunicorn 正常运行
  ```bash
  sudo systemctl status gunicorn
  ps aux | grep gunicorn | grep -v grep
  ```

- [ ] Worker 数量正确（应该 >= 3）
  ```bash
  ps aux | grep gunicorn | grep -v grep | wc -l
  ```

- [ ] Nginx 正常运行
  ```bash
  sudo systemctl status nginx
  ```

- [ ] PostgreSQL 正常运行
  ```bash
  sudo systemctl status postgresql
  ```

### 验证 3：功能测试

- [ ] 网站可以访问
  ```bash
  curl -I http://8.130.88.229/
  ```

- [ ] 首页加载正常
  ```bash
  curl -s http://8.130.88.229/ | grep "<title>"
  ```

- [ ] API 响应正常
  ```bash
  curl -s "http://8.130.88.229/api/species/" | head -20
  ```

- [ ] 管理后台可以访问
  ```bash
  curl -I http://8.130.88.229/admin/
  ```

### 验证 4：性能测试

- [ ] 首页加载时间 < 3 秒
  ```bash
  time curl -s http://8.130.88.229/ > /dev/null
  ```

- [ ] API 响应时间 < 500ms（第一次）
  ```bash
  time curl -s "http://8.130.88.229/api/map-observations/" > /dev/null
  ```

- [ ] API 响应时间 < 100ms（第二次，缓存命中）
  ```bash
  time curl -s "http://8.130.88.229/api/map-observations/" > /dev/null
  ```

- [ ] 多设备同时访问不卡顿
  - 用手机打开网站
  - 用电脑打开网站
  - 用平板打开网站
  - 都应该流畅加载

### 验证 5：缓存测试

- [ ] 缓存系统工作正常
  ```bash
  python manage.py shell
  >>> from django.core.cache import cache
  >>> cache.set('test', 'value', 30)
  >>> cache.get('test')
  # 应该返回 'value'
  >>> exit()
  ```

### 验证 6：日志检查

- [ ] Gunicorn 无错误
  ```bash
  sudo journalctl -u gunicorn -n 50 --no-pager
  ```

- [ ] Nginx 无错误
  ```bash
  sudo tail -50 /var/log/nginx/error.log
  ```

- [ ] 数据库连接正常
  ```bash
  sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"
  ```

## 📊 性能指标检查

### 修复前基线（记录）

- [ ] 首页 TTFB: _______ ms
- [ ] 首屏加载时间: _______ 秒
- [ ] API 响应时间: _______ ms
- [ ] Worker 进程数: _______
- [ ] 内存使用: _______ MB

### 修复后指标（应该达到）

- [ ] 首页 TTFB < 200ms
- [ ] 首屏加载时间 < 3 秒
- [ ] API 响应时间 < 500ms（首次）
- [ ] API 响应时间 < 100ms（缓存）
- [ ] Worker 进程数 >= 3
- [ ] 内存使用稳定（不持续增长）

## 🐛 故障排查清单

### 如果网站无法访问

- [ ] 检查 ALLOWED_HOSTS 配置
  ```bash
  grep "^ALLOWED_HOSTS" config/settings.py
  ```

- [ ] 检查 Gunicorn 日志
  ```bash
  sudo journalctl -u gunicorn -n 50
  ```

- [ ] 检查 Nginx 日志
  ```bash
  sudo tail -50 /var/log/nginx/error.log
  ```

- [ ] 检查端口占用
  ```bash
  sudo netstat -tlnp | grep :8000
  sudo netstat -tlnp | grep :80
  ```

### 如果静态文件 404

- [ ] 检查 static_root 目录
  ```bash
  ls -lh static_root/
  ```

- [ ] 重新收集静态文件
  ```bash
  python manage.py collectstatic --noinput --clear
  ```

- [ ] 检查 Nginx 配置
  ```bash
  sudo nginx -t
  ```

- [ ] 重启 Nginx
  ```bash
  sudo systemctl restart nginx
  ```

### 如果性能没有改善

- [ ] 确认 DEBUG = False
  ```bash
  grep "^DEBUG = " config/settings.py
  ```

- [ ] 确认 workers 数量
  ```bash
  ps aux | grep gunicorn | grep -v grep | wc -l
  ```

- [ ] 确认缓存工作
  ```bash
  python manage.py shell
  >>> from django.core.cache import cache
  >>> cache.set('test', 'value', 30)
  >>> cache.get('test')
  ```

- [ ] 查看慢查询
  ```bash
  sudo -u postgres psql "Yellow River" -c "SELECT query, calls, total_time, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"
  ```

## 📝 文档记录

### 修复完成后记录

- [ ] 修复日期: __________
- [ ] 修复人员: __________
- [ ] DEBUG 状态: False
- [ ] Workers 数量: __________
- [ ] 缓存类型: LocMemCache / Redis
- [ ] CDN 本地化: 是 / 否
- [ ] 性能提升: __________%

### 保存诊断报告

- [ ] 生成诊断报告
  ```bash
  ./diagnose_performance.sh > performance_report_$(date +%Y%m%d).txt
  ```

- [ ] 保存配置文件
  ```bash
  cp config/settings.py config/settings.py.$(date +%Y%m%d)
  cp /etc/systemd/system/gunicorn.service gunicorn.service.$(date +%Y%m%d)
  ```

## 🎯 后续维护

### 每日检查

- [ ] 查看服务状态
  ```bash
  sudo systemctl status gunicorn nginx postgresql
  ```

- [ ] 查看系统负载
  ```bash
  uptime
  ```

### 每周检查

- [ ] 运行诊断脚本
  ```bash
  ./diagnose_performance.sh > weekly_report_$(date +%Y%m%d).txt
  ```

- [ ] 检查磁盘空间
  ```bash
  df -h
  ```

- [ ] 检查日志大小
  ```bash
  du -sh /var/log/nginx/
  sudo journalctl --disk-usage
  ```

### 每月检查

- [ ] 数据库维护
  ```bash
  sudo -u postgres psql "Yellow River" -c "VACUUM ANALYZE;"
  ```

- [ ] 清理旧日志
  ```bash
  sudo journalctl --vacuum-time=30d
  ```

- [ ] 更新系统
  ```bash
  sudo apt update
  sudo apt upgrade
  ```

## ✅ 最终确认

- [ ] 所有核心修复步骤已完成
- [ ] 所有验证步骤已通过
- [ ] 性能指标达到预期
- [ ] 多设备登录不再卡顿
- [ ] 文档已记录
- [ ] 团队已通知

---

**签字确认：**

修复人员：____________  日期：____________

验收人员：____________  日期：____________

---

**备注：**
