#!/bin/bash
# 快速重启服务器脚本

echo "=========================================="
echo "重启 Gunicorn 和 Nginx 服务"
echo "=========================================="

# 重启 Gunicorn
echo "正在重启 Gunicorn..."
sudo systemctl restart gunicorn
if [ $? -eq 0 ]; then
    echo "✅ Gunicorn 重启成功"
else
    echo "❌ Gunicorn 重启失败"
fi

# 重启 Nginx
echo "正在重启 Nginx..."
sudo systemctl restart nginx
if [ $? -eq 0 ]; then
    echo "✅ Nginx 重启成功"
else
    echo "❌ Nginx 重启失败"
fi

# 检查服务状态
echo ""
echo "=========================================="
echo "服务状态检查"
echo "=========================================="

echo "Gunicorn 状态:"
sudo systemctl status gunicorn --no-pager | head -n 10

echo ""
echo "Nginx 状态:"
sudo systemctl status nginx --no-pager | head -n 10

echo ""
echo "=========================================="
echo "最近的 Gunicorn 日志:"
echo "=========================================="
sudo journalctl -u gunicorn -n 20 --no-pager

echo ""
echo "重启完成！"
