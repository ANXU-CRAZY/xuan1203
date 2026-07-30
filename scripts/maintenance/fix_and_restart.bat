@echo off
echo ========================================
echo 修复物种图片并重启服务器
echo ========================================

echo.
echo [1/4] 提交代码...
git add app_monitor/serializers.py
git commit -m "Add SPECIES_IMG fallback to SpeciesInfoSerializer for missing cover images"
git push origin master

echo.
echo [2/4] 检查重复物种...
python check_duplicate_species.py

echo.
echo [3/4] 本地已修复！请按以下步骤操作：
echo   1. 按 Ctrl+C 停止当前 Django 服务器
echo   2. 运行: python manage.py runserver
echo   3. 按 Ctrl+F5 刷新浏览器
echo   4. 测试物种百科、图库、科普文章

echo.
echo [4/4] 服务器部署命令：
echo   ssh root@8.130.88.229
echo   cd /home/xuan1203 ^&^& git pull ^&^& source venv/bin/activate ^&^& sudo systemctl restart gunicorn ^&^& sudo systemctl restart nginx

echo.
pause
