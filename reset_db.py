#!/usr/bin/env python3
"""
一键重置数据库脚本
此脚本将清空所有数据并重新初始化数据库
"""

import sys
import os
from pathlib import Path

# 将当前目录添加到系统路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from clear_db import reset_database


def main():
    print("正在重置 RegTracker 数据库...")
    print("-" * 40)
    
    success = reset_database()
    
    if success:
        print("\n✓ 数据库重置成功！")
        print("项目状态已重置为初始状态。")
    else:
        print("\n✗ 数据库重置失败！")
        sys.exit(1)


if __name__ == "__main__":
    main()