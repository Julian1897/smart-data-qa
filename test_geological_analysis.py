#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import sys
import os
sys.path.append('./backend')

# 导入我们的分析函数
from main import analyze_geological_time

def test_geological_analysis():
    """测试地质时间分析功能"""

    # 读取测试数据
    df = pd.read_excel('testdata3-paleo_taxonomy.xlsx', engine='openpyxl')

    print("=== 地质时间分析测试 ===")
    print("\n测试数据概览：")
    print(df.to_string())

    # 测试1：地质存续时间最长的属
    print("\n" + "="*50)
    print("测试1: 哪个属（GenusName）的地质存续时间最长？")
    question1 = "哪个属（GenusName）的地质存续时间最长？"
    result1 = analyze_geological_time(question1, df)
    print(f"分析结果: {result1}")

    # 验证手工计算
    print("\n手工验证:")
    for idx, row in df.iterrows():
        genus = row.iloc[1]  # GenusName
        first = row.iloc[5]  # FirstAppearance_Ma
        last = row.iloc[6]   # LastAppearance_Ma
        duration = first - last
        print(f"{genus}: {first:.1f}Ma - {last:.1f}Ma = {duration:.1f}百万年")

    # 测试2：奥陶纪筛选
    print("\n" + "="*50)
    print("测试2: 找出所有在奥陶纪（Ordovician）出现，但在晚奥陶世（Late Ordovician）之前就已经绝迹的属")
    question2 = "找出所有在奥陶纪（Ordovician）出现，但在晚奥陶世（Late Ordovician）之前就已经绝迹的属。"
    result2 = analyze_geological_time(question2, df)
    print(f"分析结果: {result2}")

    print("\n手工验证:")
    print("奥陶纪时间范围：485.4-443.8 Ma")
    print("晚奥陶世时间范围：458.4-445.2 Ma")
    print("条件：在奥陶纪出现(FirstAppearance <= 485.4) 且在晚奥陶世前绝迹(LastAppearance > 458.4)")

    for idx, row in df.iterrows():
        genus = row.iloc[1]
        first = row.iloc[5]
        last = row.iloc[6]
        period = row.iloc[3]
        epoch = row.iloc[4]

        in_ordovician = first <= 485.4
        extinct_before_late_ordovician = last > 458.4

        print(f"{genus}: 出现{first:.1f}Ma, 绝迹{last:.1f}Ma, {period}-{epoch}")
        print(f"  - 在奥陶纪出现: {in_ordovician}")
        print(f"  - 在晚奥陶世前绝迹: {extinct_before_late_ordovician}")
        print(f"  - 符合条件: {in_ordovician and extinct_before_late_ordovician}")
        print()

if __name__ == "__main__":
    test_geological_analysis()