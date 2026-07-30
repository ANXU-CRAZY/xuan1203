"""
下载所有外链物种图片到本地 media/species/gallery/ 目录
这样图片就不需要从国外服务器加载了
"""
import os, time, re
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()

from app_monitor.models import SpeciesInfo, SpeciesImage

MEDIA_DIR = Path('media/species/gallery')
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = "YellowRiverWetland/1.0 (image download)"

def safe_filename(name):
    """生成安全的文件名"""
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

def download_image(url, filepath):
    """下载图片到本地"""
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=15) as response:
            data = response.read()
            if len(data) < 1000:  # 太小可能不是有效图片
                return False
            with open(filepath, 'wb') as f:
                f.write(data)
            return True
    except (HTTPError, URLError, TimeoutError, OSError) as e:
        print(f"  ❌ 下载失败: {e}")
        return False

print("=" * 80)
print("下载外链物种图片到本地")
print("=" * 80)

# 找到所有使用外链图片的物种（没有本地图片的）
downloaded = 0
skipped = 0
failed = 0

for species in SpeciesInfo.objects.all().order_by('name_cn'):
    name = species.name_cn or '未知'
    
    # 检查是否已有本地图片
    local_path = MEDIA_DIR / f"{safe_filename(name)}.jpg"
    if local_path.exists():
        skipped += 1
        continue
    
    # 找到该物种的图片URL
    image_url = None
    
    # 优先从 SpeciesImage 表获取
    img_record = species.images.filter(is_featured=True).first()
    if not img_record:
        img_record = species.images.first()
    
    if img_record:
        if img_record.image and str(img_record.image) not in ('', 'False', 'None'):
            skipped += 1  # 已有本地文件
            continue
        image_url = img_record.image_url
    
    if not image_url:
        skipped += 1
        continue
    
    # 跳过已经是本地路径的
    if image_url.startswith('/media/') or image_url.startswith('media/'):
        skipped += 1
        continue
    
    print(f"📥 {name}: {image_url[:60]}...")
    
    if download_image(image_url, local_path):
        # 更新数据库记录，指向本地文件
        img_record.image = f"species/gallery/{safe_filename(name)}.jpg"
        img_record.save(update_fields=['image'])
        downloaded += 1
        print(f"  ✅ 已保存到 {local_path}")
    else:
        failed += 1
    
    time.sleep(0.1)  # 避免请求过快

print(f"\n{'=' * 80}")
print(f"✅ 完成！下载: {downloaded}, 跳过: {skipped}, 失败: {failed}")
print(f"{'=' * 80}")
