@echo off
echo ========================================
echo 部署到服务器
echo ========================================

ssh root@8.130.88.229 "cd /home/xuan1203 && git pull && source venv/bin/activate && python manage.py collectstatic --noinput && sudo systemctl restart gunicorn && sudo systemctl restart nginx"

echo.
echo 部署完成！
pause
