#!/usr/bin/env python3
"""
自动更新模板文件，将外部 CDN 链接替换为本地静态文件
"""

import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# 需要处理的模板文件
TEMPLATE_FILES = [
    'app_monitor/templates/index.html',
    'app_monitor/templates/species.html',
    'app_monitor/templates/species-gallery.html',
    'app_monitor/templates/articles.html',
    'app_monitor/templates/article-detail.html',
    'app_monitor/templates/image-gallery.html',
    'app_monitor/templates/species-detail.html',
    'app_monitor/templates/app_monitor/bird_recognition.html',
]

# CDN 替换规则
CDN_REPLACEMENTS = [
    # Leaflet CSS
    {
        'pattern': r'<link\s+rel="stylesheet"\s+href="https://unpkg\.com/leaflet@[\d.]+/dist/leaflet\.css"\s*/?>',
        'replacement': '{% load static %}\n    <link rel="stylesheet" href="{% static \'vendor/leaflet/leaflet.css\' %}" />',
    },
    # Leaflet JS
    {
        'pattern': r'<script\s+src="https://unpkg\.com/leaflet@[\d.]+/dist/leaflet\.js"[^>]*></script>',
        'replacement': '<script src="{% static \'vendor/leaflet/leaflet.js\' %}"></script>',
    },
    # Font Awesome
    {
        'pattern': r'<link\s+rel="stylesheet"\s+href="https://cdnjs\.cloudflare\.com/ajax/libs/font-awesome/[\d.]+/css/all\.min\.css"[^>]*>',
        'replacement': '<link rel="stylesheet" href="{% static \'vendor/font-awesome/all.min.css\' %}">',
    },
    # Google Fonts - 删除或注释
    {
        'pattern': r'<link\s+href="https://fonts\.googleapis\.com/css2\?[^"]*"\s+rel="stylesheet"[^>]*>',
        'replacement': '<!-- Google Fonts removed for performance (blocked in China) -->',
    },
    # Chart.js
    {
        'pattern': r'<script\s+src="https://cdn\.jsdelivr\.net/npm/chart\.js@[\d.]+/dist/chart\.umd\.min\.js"[^>]*></script>',
        'replacement': '<script src="{% static \'vendor/chart.js/chart.umd.min.js\' %}"></script>',
    },
    # jQuery
    {
        'pattern': r'<script\s+src="https://code\.jquery\.com/jquery-[\d.]+\.min\.js"[^>]*></script>',
        'replacement': '<script src="{% static \'vendor/jquery/jquery-3.6.0.min.js\' %}"></script>',
    },
]


def ensure_load_static(content):
    """确保模板顶部有 {% load static %}"""
    if '{% load static %}' not in content:
        # 在第一个 <head> 标签后添加
        content = re.sub(
            r'(<head[^>]*>)',
            r'\1\n{% load static %}',
            content,
            count=1
        )
    return content


def update_template(file_path):
    """更新单个模板文件"""
    if not file_path.exists():
        print(f"⚠️  文件不存在: {file_path}")
        return False
    
    print(f"\n处理文件: {file_path}")
    
    # 读取原文件
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    changes_made = 0
    
    # 应用所有替换规则
    for rule in CDN_REPLACEMENTS:
        pattern = rule['pattern']
        replacement = rule['replacement']
        
        matches = re.findall(pattern, content)
        if matches:
            print(f"  找到 {len(matches)} 处匹配: {pattern[:50]}...")
            content = re.sub(pattern, replacement, content)
            changes_made += len(matches)
    
    # 确保有 {% load static %}
    if changes_made > 0:
        content = ensure_load_static(content)
    
    # 如果有修改，保存文件
    if content != original_content:
        # 备份原文件
        backup_path = file_path.with_suffix(file_path.suffix + '.backup')
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_content)
        print(f"  ✓ 已备份到: {backup_path}")
        
        # 保存修改后的文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✓ 已更新，共 {changes_made} 处修改")
        return True
    else:
        print(f"  - 无需修改")
        return False


def main():
    print("=" * 60)
    print("更新模板文件 - 替换外部 CDN 为本地静态文件")
    print("=" * 60)
    
    # 检查 static/vendor 目录是否存在
    vendor_dir = BASE_DIR / 'static' / 'vendor'
    if not vendor_dir.exists():
        print("\n⚠️  警告: static/vendor/ 目录不存在")
        print("请先运行: python download_vendor_assets.py")
        print("")
        response = input("是否继续更新模板? (y/n): ")
        if response.lower() != 'y':
            print("已取消")
            return
    
    updated_count = 0
    skipped_count = 0
    
    for template_path in TEMPLATE_FILES:
        file_path = BASE_DIR / template_path
        if update_template(file_path):
            updated_count += 1
        else:
            skipped_count += 1
    
    print("\n" + "=" * 60)
    print(f"处理完成: 更新 {updated_count} 个文件, 跳过 {skipped_count} 个文件")
    print("=" * 60)
    
    if updated_count > 0:
        print("\n✓ 模板文件已更新!")
        print("\n下一步:")
        print("1. 检查修改是否正确")
        print("2. 运行: python manage.py collectstatic --noinput")
        print("3. 重启服务: sudo systemctl restart gunicorn")
        print("4. 测试网站是否正常")
        print("\n如果出现问题，可以从 .backup 文件恢复")
    else:
        print("\n所有模板文件都已是最新状态")


if __name__ == '__main__':
    main()
