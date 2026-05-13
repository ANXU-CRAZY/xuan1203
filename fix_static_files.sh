#!/bin/bash
# ============================================
# 修复静态文件 404 问题
# ============================================

echo "=========================================="
echo "修复静态文件配置"
echo "=========================================="

# 1. 拉取最新代码
echo ""
echo "【步骤 1】拉取最新代码..."
cd /home/xuan1203
git pull origin master

# 2. 激活虚拟环境
echo ""
echo "【步骤 2】激活虚拟环境..."
source venv/bin/activate

# 3. 检查 static/vendor 目录
echo ""
echo "【步骤 3】检查 vendor 文件..."
if [ -d "static/vendor" ]; then
    echo "✓ static/vendor 目录存在"
    echo "文件列表:"
    ls -lh static/vendor/
else
    echo "✗ static/vendor 目录不存在，需要重新下载"
    python3 download_vendor_assets.py
fi

# 4. 重新收集静态文件
echo ""
echo "【步骤 4】收集静态文件到 static_root..."
python manage.py collectstatic --noinput --clear

# 5. 验证文件已复制
echo ""
echo "【步骤 5】验证 vendor 文件已复制到 static_root..."
if [ -d "static_root/vendor" ]; then
    echo "✓ static_root/vendor 目录存在"
    echo "文件数量:"
    find static_root/vendor -type f | wc -l
    echo ""
    echo "目录结构:"
    tree -L 2 static_root/vendor/ 2>/dev/null || ls -R static_root/vendor/
else
    echo "✗ static_root/vendor 目录不存在，收集失败！"
    exit 1
fi

# 6. 设置正确的权限
echo ""
echo "【步骤 6】设置文件权限..."
sudo chown -R www-data:www-data static_root/
sudo chmod -R 755 static_root/

# 7. 重启 Gunicorn
echo ""
echo "【步骤 7】重启 Gunicorn..."
sudo systemctl restart gunicorn
sleep 2

# 8. 检查服务状态
echo ""
echo "【步骤 8】检查服务状态..."
sudo systemctl status gunicorn --no-pager -l

# 9. 测试静态文件访问
echo ""
echo "【步骤 9】测试静态文件访问..."
echo ""
echo "测试 Leaflet CSS:"
curl -I https://3.1415926.love/static/vendor/leaflet/leaflet.css 2>&1 | head -1

echo "测试 Font Awesome CSS:"
curl -I https://3.1415926.love/static/vendor/font-awesome/all.min.css 2>&1 | head -1

echo "测试 Chart.js:"
curl -I https://3.1415926.love/static/vendor/chart.js/chart.umd.min.js 2>&1 | head -1

echo "测试 jQuery:"
curl -I https://3.1415926.love/static/vendor/jquery/jquery-3.6.0.min.js 2>&1 | head -1

echo ""
echo "=========================================="
echo "修复完成！"
echo "=========================================="
echo ""
echo "如果所有测试都返回 HTTP/2 200，说明静态文件已正常工作"
echo "请访问 https://3.1415926.love 测试网站"
