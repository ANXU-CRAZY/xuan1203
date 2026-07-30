import os
import django
import pandas as pd
from datetime import datetime

# 初始化 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from app_monitor.models import SpeciesInfo, WetlandZone, ObservationRecord


def run_import(csv_file_path):
    print(f"🔄 开始读取文件: {csv_file_path}")

    # 1. 读取 CSV (自动处理编码)
    try:
        df = pd.read_csv(csv_file_path, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(csv_file_path, encoding='gbk')

    df = df.fillna('')  # 填充空值
    success_count = 0

    for index, row in df.iterrows():
        try:
            # --- A. 导入/获取 物种信息 ---
            # 你的CSV表头是：中文名, species, 目, 科, 保护级别
            species_obj, _ = SpeciesInfo.objects.get_or_create(
                name_cn=row['中文名'],
                defaults={
                    'name_latin': row['species'],
                    'order': row['目'],
                    'family': row['科'],
                    'protection_level': str(row['保护级别'])
                }
            )

            # --- B. 导入/获取 监测点位 (矢量点层) ---
            # 你的CSV表头是：loc, x, y
            zone_obj, _ = WetlandZone.objects.get_or_create(
                name=row['loc'],
                defaults={
                    'longitude': float(row['x']),
                    'latitude': float(row['y'])
                }
            )

            # --- C. 处理日期 ---
            # 你的CSV日期格式可能是 2022/12/11
            date_str = str(row['date'])
            try:
                if '/' in date_str:
                    obs_date = datetime.strptime(date_str, '%Y/%m/%d').date()
                else:
                    obs_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                # 如果日期格式很乱，默认设为今天，防止报错
                obs_date = datetime.now().date()

            # --- D. 创建观测记录 ---
            ObservationRecord.objects.create(
                species=species_obj,
                zone=zone_obj,
                observation_time=obs_date,
                count=int(row['abundance']) if row['abundance'] else 1,
                status=1  # 历史数据默认审核通过
            )

            success_count += 1
            if success_count % 50 == 0:
                print(f"   已处理 {success_count} 条...")

        except Exception as e:
            print(f"❌ 第 {index + 1} 行出错: {e}")
            continue

    print(f"✅ 导入完成！共导入 {success_count} 条观测记录。")


if __name__ == '__main__':
    # 请确保csv文件就在当前目录下
    run_import('2021鸟类监测.csv')
