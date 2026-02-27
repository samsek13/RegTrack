"""
数据库备份模块
负责执行数据库备份和管理备份文件数量
"""

import os
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import List

from config import config

# 配置日志
logger = logging.getLogger(__name__)

# 备份文件保留数量
MAX_BACKUPS = 30


def backup_db() -> str:
    """
    执行数据库备份
    
    Returns:
        备份文件路径
    
    Raises:
        Exception: 备份失败时抛出异常
    """
    # 确保备份目录存在
    backup_dir = Path(config.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # 检查数据库文件是否存在
    db_path = Path(config.db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"数据库文件不存在: {db_path}")
    
    # 生成备份文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"regtracker_backup_{timestamp}.db"
    backup_path = backup_dir / backup_filename
    
    # 复制数据库文件
    logger.info(f"正在备份数据库: {db_path} -> {backup_path}")
    shutil.copy2(db_path, backup_path)
    logger.info(f"数据库备份成功: {backup_path}")
    
    # 清理旧备份
    _cleanup_old_backups(backup_dir)
    
    return str(backup_path)


def _cleanup_old_backups(backup_dir: Path):
    """
    清理旧备份文件，保留最近 MAX_BACKUPS 个
    
    Args:
        backup_dir: 备份目录路径
    """
    # 获取所有备份文件
    backup_files = list(backup_dir.glob("regtracker_backup_*.db"))
    
    # 如果备份数量未超过限制，无需清理
    if len(backup_files) <= MAX_BACKUPS:
        return
    
    # 按文件名排序（文件名包含时间戳，排序后旧文件在前）
    backup_files.sort()
    
    # 删除超出的旧备份
    files_to_delete = backup_files[:-MAX_BACKUPS]
    for old_file in files_to_delete:
        logger.info(f"删除旧备份: {old_file}")
        old_file.unlink()
    
    logger.info(f"清理完成，保留最近 {MAX_BACKUPS} 个备份")


def list_backups() -> List[str]:
    """
    列出所有备份文件
    
    Returns:
        备份文件路径列表（按时间降序）
    """
    backup_dir = Path(config.backup_dir)
    if not backup_dir.exists():
        return []
    
    backup_files = list(backup_dir.glob("regtracker_backup_*.db"))
    # 按文件名降序排序（最新的在前）
    backup_files.sort(reverse=True)
    
    return [str(f) for f in backup_files]


if __name__ == "__main__":
    # 测试备份功能
    logging.basicConfig(level=logging.INFO)
    
    try:
        path = backup_db()
        print(f"备份成功: {path}")
        
        backups = list_backups()
        print(f"当前备份数: {len(backups)}")
        for b in backups:
            print(f"  - {b}")
    except FileNotFoundError as e:
        print(f"错误: {e}")
        print("提示: 请先运行应用创建数据库，或手动创建 data 目录")