# 最终修复步骤

## 当前状态
- ✅ 代码已修复（serializers.py 和 views.py）
- ❌ Django服务器可能还在使用旧缓存
- ❌ 浏览器可能还在使用旧缓存

## 立即执行的步骤

### 1. 停止Django服务器
在运行 `python manage.py runserver` 的终端中按 **Ctrl+C**

### 2. 清除Python缓存
```bash
# 删除所有 __pycache__ 目录
del /s /q app_monitor\__pycache__\*
```

### 3. 测试图片加载
```bash
python test_species_images.py
```

**预期输出：**
```
✅ 加载了 135 个物种图片映射

测试前10个物种的图片URL：

物种: 大天鹅
  直接查找: https://upload.wikimedia.org/wikipedia/commons/2/28/Cygnus_cygnus.jpg...
  API返回: https://upload.wikimedia.org/wikipedia/commons/2/28/Cygnus_cygnus.jpg...

物种: 白鹭
  直接查找: https://upload.wikimedia.org/wikipedia/commons/9/91/Egretta_garzetta.jpg...
  API返回: https://upload.wikimedia.org/wikipedia/commons/9/91/Egretta_garzetta.jpg...
```

### 4. 重启Django服务器
```bash
python manage.py runserver
```

### 5. 清除浏览器缓存
- 按 **Ctrl+Shift+Delete**
- 或者按 **Ctrl+F5** 强制刷新

### 6. 测试页面
访问以下页面，检查图片是否正确显示：
- http://127.0.0.1:8000/species/ （物种百科）
- http://127.0.0.1:8000/articles/ （科普文章）
- http://127.0.0.1:8000/gallery/ （图库）

### 7. 提交代码
```bash
git add app_monitor/serializers.py
git commit -m "Add SPECIES_IMG fallback to SpeciesInfoSerializer"
git push origin master
```

### 8. 部署到服务器
```bash
ssh root@8.130.88.229
cd /home/xuan1203
git pull
source venv/bin/activate
sudo systemctl restart gunicorn
sudo systemctl restart nginx
```

## 如果还有问题

### 问题A：图片还是显示不出来
**原因：** 数据库中的物种名称和 SPECIES_IMG 中的名称不匹配

**解决：**
```bash
python test_species_images.py
```
查看哪些物种找不到图片，然后在 `species.html` 的 `SPECIES_IMG` 中添加对应的映射。

### 问题B：科普文章图片都一样
**原因：** `_species_articles()` 函数返回的 `cover_image` 是 `None`

**解决：**
检查 `test_species_images.py` 的输出，确保 API 返回的 `cover_image_url` 不是 `None`。

### 问题C：图库有重复物种
**原因：** 数据库中有重复的物种记录

**解决：**
```bash
python check_duplicate_species.py
```
然后在 Django admin 后台删除重复的记录。

## 技术说明

### 图片加载优先级
1. 数据库 `SpeciesInfo.cover_image` 字段
2. 数据库 `SpeciesImage` 表（精选图片）
3. 数据库 `SpeciesImage` 表（第一张图片）
4. **前端模板 `SPECIES_IMG` 映射（fallback）** ← 新增
5. 占位图

### 为什么需要重启服务器
Python 的全局变量 `_SPECIES_IMG_CACHE` 在服务器启动时加载，如果不重启，它会一直使用旧的值（可能是空的或不完整的）。

### 为什么需要清除浏览器缓存
浏览器会缓存 API 响应，即使服务器返回了新的数据，浏览器可能还在使用旧的缓存。
