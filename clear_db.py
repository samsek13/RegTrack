#!/usr/bin/env python3
"""
清空数据库脚本
此脚本将清空所有表的数据，但保留表结构
"""

import sqlite3
import os
from datetime import datetime

from config import config


def clear_database():
    """
    清空数据库中所有表的数据
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始清空数据库...")
    
    # 检查数据库文件是否存在
    if not os.path.exists(config.db_path):
        print(f"数据库文件不存在: {config.db_path}")
        return False
    
    # 连接到数据库
    conn = sqlite3.connect(config.db_path)
    cursor = conn.cursor()
    
    try:
        # 获取所有表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        # 排除 sqlite 系统表
        user_tables = [table for table in tables if not table.startswith('sqlite_')]
        
        print(f"发现 {len(user_tables)} 个用户表: {', '.join(user_tables)}")
        
        # 清空每个表的数据
        for table in user_tables:
            cursor.execute(f"DELETE FROM {table};")
            print(f"  - 已清空表: {table}")
        
        # 重置自增计数器
        cursor.execute("DELETE FROM sqlite_sequence;")
        
        # 提交更改
        conn.commit()
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 数据库清空完成!")
        print(f"共清空了 {len(user_tables)} 个表的数据")
        
        return True
        
    except Exception as e:
        print(f"清空数据库时发生错误: {str(e)}")
        conn.rollback()
        return False
    finally:
        conn.close()


def reset_database():
    """
    重置数据库：清空数据并重新初始化
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始重置数据库...")
    
    # 先清空数据库
    if not clear_database():
        return False
    
    # 重新初始化数据库（创建表结构）
    try:
        from db import init_db
        init_db()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 数据库重置完成!")
        return True
    except Exception as e:
        print(f"重置数据库时发生错误: {str(e)}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("RegTracker 数据库清空工具")
    print("=" * 50)
    
    print("\n请选择操作:")
    print("1. 清空数据（保留表结构）")
    print("2. 重置数据库（清空数据并重新初始化表结构）")
    print("3. 取消")
    
    choice = input("\n请输入选项 (1/2/3): ").strip()
    
    if choice == "1":
        success = clear_database()
        if success:
            print("\n✓ 数据库清空成功!")
        else:
            print("\n✗ 数据库清空失败!")
    elif choice == "2":
        success = reset_database()
        if success:
            print("\n✓ 数据库重置成功!")
        else:
            print("\n✗ 数据库重置失败!")
    elif choice == "3":
        print("操作已取消")
    else:
        print("无效选项，操作已取消")
    
    print("\n按 Enter 键退出...")
    input()