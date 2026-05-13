#!/bin/bash
# 性能诊断脚本 - 检查服务器配置和性能瓶颈

echo "=========================================="
echo "黄河生态方舟平台 - 性能诊断报告"
echo "=========================================="
echo ""

# 1. 系统信息
echo "【1. 系统信息】"
echo "操作系统: $(uname -s)"
echo "内核版本: $(uname -r)"
echo "CPU 核心数: $(nproc)"
echo "总内存: $(free -h | awk '/^Mem:/ {print $2}')"
echo "可用内存: $(free -h | awk '/^Mem:/ {print $7}')"
echo ""

# 2. Django 配置检查
echo "【2. Django 配置检查】"
if [ -f "config/settings.py" ]; then
    DEBUG_STATUS=$(grep "^DEBUG = " config/settings.py | head -1)
    echo "DEBUG 状态: $DEBUG_STATUS"
    
    if echo "$DEBUG_STATUS" | grep -q "True"; then
        echo "⚠️  警告: DEBUG = True 会导致严重性能问题!"
        echo "   建议: 立即改为 DEBUG = False"
    else
        echo "✓ DEBUG 已正确设置为 False"
    fi
    
    ALLOWED_HOSTS=$(grep "^ALLOWED_HOSTS = " config/settings.py | head -1)
    echo "ALLOWED_HOSTS: $ALLOWED_HOSTS"
    
    # 检查缓存配置
    if grep -q "CACHES" config/settings.py; then
        echo "✓ 已配置缓存系统"
    else
        echo "⚠️  未配置缓存系统，建议添加"
    fi
    
    # 检查数据库连接持久化
    if grep -q "CONN_MAX_AGE" config/settings.py; then
        echo "✓ 已启用数据库连接持久化"
    else
        echo "⚠️  未启用数据库连接持久化，建议添加 CONN_MAX_AGE"
    fi
else
    echo "✗ 未找到 config/settings.py"
fi
echo ""

# 3. Gunicorn 进程检查
echo "【3. Gunicorn 进程检查】"
GUNICORN_PROCS=$(ps aux | grep gunicorn | grep -v grep | wc -l)
echo "Gunicorn 进程数: $GUNICORN_PROCS"

if [ $GUNICORN_PROCS -gt 0 ]; then
    echo ""
    echo "进程详情:"
    ps aux | grep gunicorn | grep -v grep | awk '{printf "  PID: %-6s CPU: %-5s MEM: %-5s CMD: %s\n", $2, $3"%", $4"%", $11}'
    echo ""
    
    # 计算建议的 worker 数
    CPU_COUNT=$(nproc)
    RECOMMENDED_WORKERS=$((CPU_COUNT * 2 + 1))
    ACTUAL_WORKERS=$((GUNICORN_PROCS - 1))  # 减去 master 进程
    
    echo "建议 Worker 数: $RECOMMENDED_WORKERS (公式: 2*CPU+1 = 2*$CPU_COUNT+1)"
    echo "实际 Worker 数: $ACTUAL_WORKERS"
    
    if [ $ACTUAL_WORKERS -lt $RECOMMENDED_WORKERS ]; then
        echo "⚠️  Worker 数量偏少，可能导致并发性能不足"
    elif [ $ACTUAL_WORKERS -gt $((RECOMMENDED_WORKERS + 2)) ]; then
        echo "⚠️  Worker 数量过多，可能浪费内存"
    else
        echo "✓ Worker 数量配置合理"
    fi
else
    echo "✗ Gunicorn 未运行"
fi
echo ""

# 4. Gunicorn 配置文件检查
echo "【4. Gunicorn 配置检查】"
if [ -f "/etc/systemd/system/gunicorn.service" ]; then
    echo "✓ 找到 systemd service 文件"
    echo ""
    echo "配置内容:"
    grep "ExecStart" /etc/systemd/system/gunicorn.service | sed 's/^/  /'
    echo ""
    
    # 检查关键参数
    SERVICE_CONTENT=$(cat /etc/systemd/system/gunicorn.service)
    
    if echo "$SERVICE_CONTENT" | grep -q "\-\-workers"; then
        WORKERS=$(echo "$SERVICE_CONTENT" | grep -oP '\-\-workers\s+\K\d+' | head -1)
        echo "  配置的 workers: $WORKERS"
    else
        echo "  ⚠️  未显式配置 workers (默认为 1)"
    fi
    
    if echo "$SERVICE_CONTENT" | grep -q "\-\-max-requests"; then
        MAX_REQ=$(echo "$SERVICE_CONTENT" | grep -oP '\-\-max-requests\s+\K\d+' | head -1)
        echo "  配置的 max-requests: $MAX_REQ"
        echo "  ✓ 已启用 worker 自动重启"
    else
        echo "  ⚠️  未配置 max-requests，worker 不会自动重启释放内存"
    fi
    
    if echo "$SERVICE_CONTENT" | grep -q "gthread"; then
        echo "  ✓ 使用 gthread worker (支持多线程)"
    else
        echo "  ⚠️  未使用 gthread，建议添加 --worker-class gthread"
    fi
else
    echo "✗ 未找到 /etc/systemd/system/gunicorn.service"
    echo "  建议: 使用项目中的 gunicorn.service.template 创建"
fi
echo ""

# 5. Nginx 状态
echo "【5. Nginx 状态】"
if systemctl is-active --quiet nginx; then
    echo "✓ Nginx 正在运行"
    
    # 检查 Nginx 配置
    if [ -f "/etc/nginx/sites-available/yellow_river" ] || [ -f "/etc/nginx/conf.d/yellow_river.conf" ]; then
        echo "✓ 找到 Nginx 配置文件"
    fi
    
    # 检查最近的错误日志
    if [ -f "/var/log/nginx/error.log" ]; then
        ERROR_COUNT=$(tail -100 /var/log/nginx/error.log 2>/dev/null | wc -l)
        echo "最近 100 行错误日志: $ERROR_COUNT 条"
    fi
else
    echo "✗ Nginx 未运行"
fi
echo ""

# 6. 数据库连接检查
echo "【6. PostgreSQL 状态】"
if systemctl is-active --quiet postgresql; then
    echo "✓ PostgreSQL 正在运行"
    
    # 检查连接数
    if command -v psql &> /dev/null; then
        CONN_COUNT=$(sudo -u postgres psql -t -c "SELECT count(*) FROM pg_stat_activity;" 2>/dev/null | tr -d ' ')
        if [ ! -z "$CONN_COUNT" ]; then
            echo "当前数据库连接数: $CONN_COUNT"
        fi
    fi
else
    echo "✗ PostgreSQL 未运行"
fi
echo ""

# 7. 静态文件检查
echo "【7. 静态文件检查】"
if [ -d "static_root" ]; then
    STATIC_COUNT=$(find static_root -type f 2>/dev/null | wc -l)
    echo "✓ static_root 目录存在 ($STATIC_COUNT 个文件)"
else
    echo "⚠️  static_root 目录不存在"
    echo "   建议: 运行 python manage.py collectstatic --noinput"
fi

if [ -d "static/vendor" ]; then
    echo "✓ static/vendor 目录存在 (本地 CDN 资源)"
    
    # 检查关键文件
    if [ -f "static/vendor/leaflet/leaflet.js" ]; then
        echo "  ✓ Leaflet 已本地化"
    else
        echo "  ✗ Leaflet 未本地化"
    fi
    
    if [ -f "static/vendor/chart.js/chart.umd.min.js" ]; then
        echo "  ✓ Chart.js 已本地化"
    else
        echo "  ✗ Chart.js 未本地化"
    fi
    
    if [ -f "static/vendor/font-awesome/all.min.css" ]; then
        echo "  ✓ Font Awesome 已本地化"
    else
        echo "  ✗ Font Awesome 未本地化"
    fi
else
    echo "⚠️  static/vendor 目录不存在"
    echo "   建议: 运行 python download_vendor_assets.py"
fi
echo ""

# 8. 磁盘空间
echo "【8. 磁盘空间】"
df -h / | awk 'NR==1 {print "  " $0} NR==2 {print "  " $0; if (int($5) > 80) print "  ⚠️  磁盘使用率超过 80%"}'
echo ""

# 9. 最近的应用日志
echo "【9. 最近的应用日志 (journalctl)】"
if command -v journalctl &> /dev/null; then
    echo "最近 10 条 Gunicorn 日志:"
    sudo journalctl -u gunicorn -n 10 --no-pager 2>/dev/null | sed 's/^/  /' || echo "  无法读取日志"
else
    echo "  journalctl 不可用"
fi
echo ""

# 10. 性能建议总结
echo "=========================================="
echo "【性能优化建议总结】"
echo "=========================================="

ISSUES=0

# 检查 DEBUG
if [ -f "config/settings.py" ] && grep -q "^DEBUG = True" config/settings.py; then
    echo "🔴 P0: 立即将 DEBUG 改为 False"
    ISSUES=$((ISSUES + 1))
fi

# 检查 Gunicorn workers
if [ $GUNICORN_PROCS -gt 0 ]; then
    ACTUAL_WORKERS=$((GUNICORN_PROCS - 1))
    if [ $ACTUAL_WORKERS -lt 3 ]; then
        echo "🔴 P0: 增加 Gunicorn workers 数量 (当前: $ACTUAL_WORKERS, 建议: $RECOMMENDED_WORKERS)"
        ISSUES=$((ISSUES + 1))
    fi
fi

# 检查 max-requests
if [ -f "/etc/systemd/system/gunicorn.service" ]; then
    if ! grep -q "\-\-max-requests" /etc/systemd/system/gunicorn.service; then
        echo "🔴 P0: 添加 --max-requests 参数，启用 worker 自动重启"
        ISSUES=$((ISSUES + 1))
    fi
fi

# 检查本地 CDN
if [ ! -d "static/vendor" ]; then
    echo "🟡 P1: 下载外部 CDN 资源到本地 (运行 python download_vendor_assets.py)"
    ISSUES=$((ISSUES + 1))
fi

# 检查缓存
if [ -f "config/settings.py" ] && ! grep -q "CACHES" config/settings.py; then
    echo "🟡 P1: 配置 Django 缓存系统"
    ISSUES=$((ISSUES + 1))
fi

if [ $ISSUES -eq 0 ]; then
    echo "✓ 未发现明显性能问题"
else
    echo ""
    echo "发现 $ISSUES 个需要优化的问题"
fi

echo ""
echo "=========================================="
echo "诊断完成"
echo "=========================================="
