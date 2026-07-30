# 紧急修复：物种百科、图库、科普文章

## 问题总结
1. ❌ 物种百科图片显示不出来
2. ❌ 科普文章所有封面都是同一张图
3. ❌ 图库有重复物种（暗绿绣眼 vs 暗绿绣眼鸟）

## 根本原因
**SpeciesInfoSerializer 的 `get_cover_image_url` 方法没有使用前端模板中的 SPECIES_IMG 作为 fallback！**

数据库中很多物种没有上传图片，但前端模板 `species.html` 中有 135 个物种的 Wikimedia 图片映射。后端API应该使用这个映射作为fallback，但之前的代码没有这么做。

## 已修复内容

### 1. 修复 `app_monitor/serializers.py`
在 `SpeciesInfoSerializer.get_cover_image_url()` 方法中添加了 fallback 逻辑：

```python
# 4. Fallback: 从前端模板的 SPECIES_IMG 映射中查找
from .views import _load_species_image_map, _lookup_species_image
image_map = _load_species_image_map()
fallback_url = _lookup_species_image(image_map, obj.name_cn)
if fallback_url:
    return fallback_url
```

### 2. 修复 `app_monitor/views.py`
修复了 `_load_species_image_map()` 的正则表达式，从：
```python
pattern = rf"const\s+{const_name}\s*=\s*\{{([^}}]+)\}};"
```
改为：
```python
pattern = rf"const\s+{const_name}\s*=\s*\{{(.*?)\}};"
```

这样可以正确匹配多行的 JavaScript 对象（135个物种图片）。

## 需要手动操作

### 1. 提交代码
```bash
git add app_monitor/serializers.py
git commit -m "Add SPECIES_IMG fallback to SpeciesInfoSerializer for missing cover images"
git push origin master
```

### 2. 重启本地Django服务器
按 Ctrl+C 停止当前服务器，然后：
```bash
python manage.py runserver
```

### 3. 清除浏览器缓存
按 Ctrl+Shift+Delete 或 Ctrl+F5 强制刷新

### 4. 测试页面
- http://127.0.0.1:8000/species/ （物种百科 - 应该看到所有物种都有图片）
- http://127.0.0.1:8000/gallery/ （图库）
- http://127.0.0.1:8000/articles/ （科普文章 - 每篇应该有对应物种的图片）

### 5. 处理重复物种
运行检查脚本：
```bash
python check_duplicate_species.py
```

如果发现重复（如"暗绿绣眼"和"暗绿绣眼鸟"），在Django admin后台删除重复的记录：
1. 访问 http://127.0.0.1:8000/admin/
2. 进入"物种信息"
3. 搜索"暗绿绣眼"
4. 删除重复的记录（保留一个即可）

### 6. 部署到服务器
```bash
ssh root@8.130.88.229
cd /home/xuan1203
git pull
source venv/bin/activate
sudo systemctl restart gunicorn
sudo systemctl restart nginx
```

## 预期结果
- ✅ 物种百科：所有135个物种都有图片显示
- ✅ 科普文章：每个物种的科普文章有对应的物种图片
- ✅ 图库：没有重复的物种

## 技术说明
物种图片的优先级（从高到低）：
1. 数据库 `SpeciesInfo.cover_image` 字段
2. 数据库 `SpeciesImage` 表中的精选图片
3. 数据库 `SpeciesImage` 表中的第一张图片
4. **前端模板 `species.html` 中的 SPECIES_IMG 映射（新增）**
5. 占位图

这样即使数据库中没有图片，也能从前端模板的 Wikimedia 映射中获取图片URL。
