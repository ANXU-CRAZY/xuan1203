#!/usr/bin/env python
"""检查API返回的数据"""
import requests
import json

print("=" * 80)
print("检查 API 返回的物种数据")
print("=" * 80)

# 1. 检查物种API
response = requests.get('http://127.0.0.1:8000/api/species/')
data = response.json()

print(f"\n✅ API返回了 {len(data)} 个物种\n")

# 2. 检查前10个物种的 cover_image_url
print("前10个物种的封面图片：\n")
for i, species in enumerate(data[:10]):
    name = species.get('name_cn', '未知')
    cover_url = species.get('cover_image_url')
    
    if cover_url:
        print(f"{i+1}. ✅ {name}")
        print(f"   URL: {cover_url[:80]}...")
    else:
        print(f"{i+1}. ❌ {name} - 没有封面图片")
    print()

# 3. 统计有图片和没图片的物种数量
with_image = sum(1 for s in data if s.get('cover_image_url'))
without_image = len(data) - with_image

print("=" * 80)
print(f"统计：")
print(f"  有图片: {with_image} 个 ({with_image/len(data)*100:.1f}%)")
print(f"  无图片: {without_image} 个 ({without_image/len(data)*100:.1f}%)")
print("=" * 80)

# 4. 检查科普文章API
print("\n检查科普文章 API：\n")
response = requests.get('http://127.0.0.1:8000/api/articles/')
articles = response.json()

print(f"✅ API返回了 {len(articles)} 篇文章\n")

# 检查前5篇物种科普文章（ID > 100000）
species_articles = [a for a in articles if a.get('id', 0) > 100000][:5]
print(f"前5篇物种科普文章的封面图片：\n")
for i, article in enumerate(species_articles):
    title = article.get('title', '未知')
    cover = article.get('cover_image')
    
    if cover:
        print(f"{i+1}. ✅ {title}")
        print(f"   URL: {cover[:80]}...")
    else:
        print(f"{i+1}. ❌ {title} - 没有封面图片")
    print()

print("=" * 80)
