#!/usr/bin/env python3
"""
下载外部 CDN 资源到本地 static/vendor/ 目录
解决国内访问 Google Fonts、unpkg、cdnjs 等 CDN 缓慢或被墙的问题
"""

import os
import urllib.request
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent

# 目标目录
VENDOR_DIR = BASE_DIR / 'static' / 'vendor'
VENDOR_DIR.mkdir(parents=True, exist_ok=True)

# 需要下载的资源列表
ASSETS = [
    # Leaflet CSS
    {
        'url': 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
        'path': 'leaflet/leaflet.css',
    },
    # Leaflet JS
    {
        'url': 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
        'path': 'leaflet/leaflet.js',
    },
    # Leaflet images (需要单独下载)
    {
        'url': 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
        'path': 'leaflet/images/marker-icon.png',
    },
    {
        'url': 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
        'path': 'leaflet/images/marker-icon-2x.png',
    },
    {
        'url': 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
        'path': 'leaflet/images/marker-shadow.png',
    },
    {
        'url': 'https://unpkg.com/leaflet@1.9.4/dist/images/layers.png',
        'path': 'leaflet/images/layers.png',
    },
    {
        'url': 'https://unpkg.com/leaflet@1.9.4/dist/images/layers-2x.png',
        'path': 'leaflet/images/layers-2x.png',
    },
    # Font Awesome CSS
    {
        'url': 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
        'path': 'font-awesome/all.min.css',
    },
    # Font Awesome Webfonts (主要字体文件)
    {
        'url': 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-solid-900.woff2',
        'path': 'font-awesome/webfonts/fa-solid-900.woff2',
    },
    {
        'url': 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-regular-400.woff2',
        'path': 'font-awesome/webfonts/fa-regular-400.woff2',
    },
    {
        'url': 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-brands-400.woff2',
        'path': 'font-awesome/webfonts/fa-brands-400.woff2',
    },
    # Chart.js
    {
        'url': 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js',
        'path': 'chart.js/chart.umd.min.js',
    },
    # jQuery
    {
        'url': 'https://code.jquery.com/jquery-3.6.0.min.js',
        'path': 'jquery/jquery-3.6.0.min.js',
    },
]


def download_file(url, dest_path):
    """下载文件到指定路径"""
    dest_file = VENDOR_DIR / dest_path
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    
    if dest_file.exists():
        print(f"✓ 已存在: {dest_path}")
        return True
    
    try:
        print(f"⬇ 下载中: {url}")
        print(f"  → {dest_path}")
        
        # 添加 User-Agent 避免被某些 CDN 拒绝
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read()
            
        with open(dest_file, 'wb') as f:
            f.write(content)
            
        print(f"✓ 完成: {dest_path} ({len(content)} bytes)")
        return True
        
    except Exception as e:
        print(f"✗ 失败: {dest_path}")
        print(f"  错误: {e}")
        return False


def fix_font_awesome_css():
    """修复 Font Awesome CSS 中的字体路径"""
    css_file = VENDOR_DIR / 'font-awesome' / 'all.min.css'
    
    if not css_file.exists():
        return
    
    print("\n🔧 修复 Font Awesome CSS 字体路径...")
    
    with open(css_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换 CDN 路径为相对路径
    content = content.replace(
        '../webfonts/',
        'webfonts/'
    )
    
    with open(css_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✓ Font Awesome CSS 路径已修复")


def fix_leaflet_css():
    """修复 Leaflet CSS 中的图片路径"""
    css_file = VENDOR_DIR / 'leaflet' / 'leaflet.css'
    
    if not css_file.exists():
        return
    
    print("\n🔧 修复 Leaflet CSS 图片路径...")
    
    with open(css_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换图片路径
    content = content.replace('images/', 'images/')
    
    with open(css_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✓ Leaflet CSS 路径已修复")


def main():
    print("=" * 60)
    print("下载外部 CDN 资源到本地")
    print("=" * 60)
    print(f"\n目标目录: {VENDOR_DIR}\n")
    
    success_count = 0
    fail_count = 0
    
    for asset in ASSETS:
        if download_file(asset['url'], asset['path']):
            success_count += 1
        else:
            fail_count += 1
        print()
    
    # 修复路径
    fix_font_awesome_css()
    fix_leaflet_css()
    
    print("\n" + "=" * 60)
    print(f"下载完成: 成功 {success_count} 个, 失败 {fail_count} 个")
    print("=" * 60)
    
    if fail_count == 0:
        print("\n✓ 所有资源下载成功!")
        print("\n下一步:")
        print("1. 运行: python manage.py collectstatic --noinput")
        print("2. 修改模板文件，将 CDN 链接替换为本地路径")
        print("3. 重启 Gunicorn: sudo systemctl restart gunicorn")
    else:
        print(f"\n⚠ 有 {fail_count} 个资源下载失败，请检查网络连接后重试")


if __name__ == '__main__':
    main()
