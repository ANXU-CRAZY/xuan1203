#!/bin/bash
# 快速修复脚本 - 一键应用所有性能优化

set -e  # 遇到错误立即退出

echo "=========================================="
echo "黄河生态方舟平台 - 快速性能修复"
echo "=========================================="
echo ""

# 检查是否在项目根目录
if [ ! -f "manage.py" ]; then
    echo "错误: 请在项目根目录运行此脚本"
    exit 1
fi

# 检查是否有虚拟环境
if [ ! -d "venv" ]; then
    echo "错误: 未找到虚拟环境 venv/"
    echo "请先创建虚拟环境: python3 -m venv venv"
    exit 1
fi

echo "【步骤 1/6】检查 DEBUG 设置..."
if grep -q "^DEBUG = True" config/settings.py; then
    echo "⚠️  发现 DEBUG = True，正在修改..."
    
    # 备份原文件
    cp config/settings.py config/settings.py.backup.$(date +%Y%m%d_%H%M%S)
    
    # 修改 DEBUG
    sed -i 's/^DEBUG = True/DEBUG = False/' config/settings.py
    
    # 修改 ALLOWED_HOSTS（如果是 ['*']）
    if grep -q "^ALLOWED_HOSTS = \['\*'\]" config/settings.py; then
        # 获取服务器 IP
        SERVER_IP=$(hostname -I | awk '{print $1}')
        sed -i "s/^ALLOWED_HOSTS = \['\*'\]/ALLOWED_HOSTS = ['3.1415926.love', '8.130.88.229', 'localhost', '127.0.0.1', '$SERVER_IP']/" config/settings.py
    fi
    
    echo "✓ DEBUG 已设置为 False"
else
    echo "✓ DEBUG 已经是 False"
fi
echo ""

echo "【步骤 2/6】检查数据库连接持久化..."
if ! grep -q "CONN_MAX_AGE" config/settings.py; then
    echo "正在添加 CONN_MAX_AGE..."
    
    # 在 DATABASES 配置中添加 CONN_MAX_AGE
    sed -i "/^DATABASES = {/,/^}/ s/'PORT': '5432',/'PORT': '5432',\n        'CONN_MAX_AGE': 60,  # 连接持久化/" config/settings.py
    
    echo "✓ 已添加数据库连接持久化"
else
    echo "✓ 数据库连接持久化已配置"
fi
echo ""

echo "【步骤 3/6】检查缓存配置..."
if ! grep -q "^CACHES = {" config/settings.py; then
    echo "正在添加缓存配置..."
    
    cat >> config/settings.py << 'EOF'

# === 缓存配置 (性能优化) ===
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'yellow-river-cache',
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
        }
    }
}
EOF
    
    echo "✓ 已添加缓存配置"
else
    echo "✓ 缓存配置已存在"
fi
echo ""

echo "【步骤 4/6】收集静态文件..."
source venv/bin/activate
python manage.py collectstatic --noinput
echo "✓ 静态文件收集完成"
echo ""

echo "【步骤 5/6】检查 Gunicorn 配置..."
if [ -f "/etc/systemd/system/gunicorn.service" ]; then
    echo "找到 Gunicorn service 文件"
    
    # 检查是否配置了 max-requests
    if ! grep -q "\-\-max-requests" /etc/systemd/system/gunicorn.service; then
        echo ""
        echo "⚠️  警告: Gunicorn 未配置 --max-requests"
        echo "建议手动编辑 /etc/systemd/system/gunicorn.service"
        echo "添加以下参数:"
        echo "  --workers 5"
        echo "  --threads 2"
        echo "  --worker-class gthread"
        echo "  --max-requests 500"
        echo "  --max-requests-jitter 50"
        echo ""
        echo "或使用项目中的 gunicorn_config.py:"
        echo "  ExecStart=/path/to/venv/bin/gunicorn -c /path/to/gunicorn_config.py config.wsgi:application"
        echo ""
        
        read -p "是否现在编辑 Gunicorn service 文件? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo nano /etc/systemd/system/gunicorn.service
        fi
    else
        echo "✓ Gunicorn 已配置 max-requests"
    fi
else
    echo "⚠️  未找到 /etc/systemd/system/gunicorn.service"
    echo "请使用 gunicorn.service.template 创建"
fi
echo ""

echo "【步骤 6/6】重启服务..."
echo "正在重启 Gunicorn..."
if sudo systemctl restart gunicorn; then
    echo "✓ Gunicorn 重启成功"
else
    echo "✗ Gunicorn 重启失败，请检查日志:"
    echo "  sudo journalctl -u gunicorn -n 50"
fi

echo ""
echo "正在重启 Nginx..."
if sudo systemctl restart nginx; then
    echo "✓ Nginx 重启成功"
else
    echo "✗ Nginx 重启失败，请检查配置:"
    echo "  sudo nginx -t"
fi

echo ""
echo "=========================================="
echo "修复完成!"
echo "=========================================="
echo ""
echo "已完成的优化:"
echo "  ✓ DEBUG = False"
echo "  ✓ 数据库连接持久化"
echo "  ✓ 缓存系统配置"
echo "  ✓ 静态文件收集"
echo ""
echo "建议继续完成:"
echo "  1. 下载本地 CDN 资源: python download_vendor_assets.py"
echo "  2. 修改模板文件，替换外部 CDN 链接"
echo "  3. 优化 Gunicorn 配置（如果尚未完成）"
echo "  4. 运行诊断脚本: ./diagnose_performance.sh"
echo ""
echo "查看服务状态:"
echo "  sudo systemctl status gunicorn"
echo "  sudo systemctl status nginx"
echo ""
echo "查看日志:"
echo "  sudo journalctl -u gunicorn -f"
echo ""
