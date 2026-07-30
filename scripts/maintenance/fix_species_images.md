# 修复物种图片、科普文章和图库问题

## 问题描述
1. 物种百科的鸟类图片丢失
2. 科普文章的物种图片不对应
3. 图库显示有问题
4. 加载速度很慢

## 根本原因
1. `_load_species_image_map()` 的正则表达式匹配有问题
2. Wikimedia Commons 图片在中国访问很慢
3. 服务器重启后全局缓存 `_SPECIES_IMG_CACHE` 被清空

## 修复步骤

### 1. SSH连接服务器
```bash
ssh root@8.130.88.229
```

### 2. 拉取最新代码
```bash
cd /home/xuan1203
git pull
```

### 3. 激活虚拟环境
```bash
source venv/bin/activate
```

### 4. 诊断图片加载（重要！）
```bash
python manage.py shell << 'EOF'
from app_monitor.views import _load_species_image_map
from app_monitor.models import SpeciesInfo

# 清除旧缓存
import app_monitor.views
app_monitor.views._SPECIES_IMG_CACHE = None

# 重新加载
img_map = _load_species_image_map()
print(f"✅ 加载了 {len(img_map)} 个物种图片映射")

# 检查前10个物种
for species in SpeciesInfo.objects.all()[:10]:
    name = species.name_cn
    has_img = name in img_map
    print(f"  {'✅' if has_img else '❌'} {name}")

exit()
EOF
```

### 5. 重启服务
```bash
sudo systemctl restart gunicorn
sudo systemctl restart nginx
```

### 6. 检查日志
```bash
sudo journalctl -u gunicorn -n 50 --no-pager | grep "加载了"
```

### 7. 测试API
```bash
# 测试物种API
curl -s "https://3.1415926.love/api/species/" | python3 -m json.tool | head -n 50

# 测试图库API
curl -s "https://3.1415926.love/api/species-images/" | python3 -m json.tool | head -n 50

# 测试科普文章API
curl -s "https://3.1415926.love/api/articles/" | python3 -m json.tool | head -n 50
```

## 如果图片还是加载慢

### 方案1：使用图片代理（推荐）
在Nginx配置中添加Wikimedia图片代理：

```nginx
# 编辑Nginx配置
sudo nano /etc/nginx/conf.d/xuan_project.conf

# 添加以下location块
location /wikimedia-proxy/ {
    proxy_pass https://upload.wikimedia.org/;
    proxy_cache_valid 200 7d;
    proxy_cache_bypass $http_pragma $http_authorization;
    add_header X-Cache-Status $upstream_cache_status;
}
```

然后修改views.py中的图片URL，将：
```python
'https://upload.wikimedia.org/...'
```
改为：
```python
'https://3.1415926.love/wikimedia-proxy/...'
```

### 方案2：下载图片到本地
```bash
# 运行图片同步命令
python manage.py sync_species_gallery
python manage.py backfill_species_wikimedia_images --skip-wikidata --sleep 0.05
```

### 方案3：使用CDN加速
使用阿里云OSS或腾讯云COS存储图片，然后配置CDN加速。

## 验证修复

访问以下页面检查：
1. https://3.1415926.love/species/ （物种百科）
2. https://3.1415926.love/gallery/ （图库）
3. https://3.1415926.love/articles/ （科普文章）

每个物种应该都有对应的图片显示。

## 性能优化建议

### 1. 启用浏览器缓存
在Nginx配置中添加：
```nginx
location ~* \.(jpg|jpeg|png|gif|ico|css|js)$ {
    expires 7d;
    add_header Cache-Control "public, immutable";
}
```

### 2. 启用Gzip压缩
```nginx
gzip on;
gzip_types text/plain text/css application/json application/javascript text/xml application/xml;
gzip_min_length 1000;
```

### 3. 使用HTTP/2
确保Nginx配置中有：
```nginx
listen 443 ssl http2;
```

## 快速重启命令
```bash
ssh root@8.130.88.229 "cd /home/xuan1203 && git pull && source venv/bin/activate && sudo systemctl restart gunicorn && sudo systemctl restart nginx && echo '✅ 部署完成'"
```
