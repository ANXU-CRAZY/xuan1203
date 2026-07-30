#!/usr/bin/env python
"""诊断物种图片、图库和科普文章问题"""
import re
from pathlib import Path

print("=" * 80)
print("物种图片诊断")
print("=" * 80)

# 1. 检查 species.html 中的 SPECIES_IMG
species_html = Path('app_monitor/templates/species.html')
if species_html.exists():
    text = species_html.read_text(encoding='utf-8')
    
    # 查找 SPECIES_IMG 定义
    pattern = r"const\s+SPECIES_IMG\s*=\s*\{([^}]+)\};"
    matches = re.findall(pattern, text, re.DOTALL)
    
    if matches:
        # 提取所有键值对
        pairs = re.findall(r"'([^']+)'\s*:\s*'([^']+)'", matches[0])
        print(f"\n✅ species.html 中找到 SPECIES_IMG，包含 {len(pairs)} 个物种")
        print(f"前5个物种:")
        for i, (name, url) in enumerate(pairs[:5]):
            print(f"  {i+1}. {name}: {url[:60]}...")
    else:
        print(f"\n❌ species.html 中没有找到 SPECIES_IMG 定义！")
        print("正则表达式可能需要调整")
else:
    print(f"\n❌ 文件不存在: {species_html}")

# 2. 检查 species-gallery.html 中的 FALLBACK_IMAGES
gallery_html = Path('app_monitor/templates/species-gallery.html')
if gallery_html.exists():
    text = gallery_html.read_text(encoding='utf-8')
    
    pattern = r"const\s+FALLBACK_IMAGES\s*=\s*\{([^}]+)\};"
    matches = re.findall(pattern, text, re.DOTALL)
    
    if matches:
        pairs = re.findall(r"'([^']+)'\s*:\s*'([^']+)'", matches[0])
        print(f"\n✅ species-gallery.html 中找到 FALLBACK_IMAGES，包含 {len(pairs)} 个物种")
    else:
        print(f"\n❌ species-gallery.html 中没有找到 FALLBACK_IMAGES 定义！")
else:
    print(f"\n❌ 文件不存在: {gallery_html}")

print("\n" + "=" * 80)
print("建议修复方案：")
print("=" * 80)
print("1. 检查模板文件中的 JavaScript 常量格式是否正确")
print("2. 确保 SPECIES_IMG 和 FALLBACK_IMAGES 使用单引号")
print("3. 运行 python manage.py sync_species_gallery 同步图库")
print("4. 运行 python manage.py backfill_species_wikimedia_images 补全图片")
