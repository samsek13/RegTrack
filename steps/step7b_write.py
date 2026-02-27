"""
Step 7B: 写入法规记录
将法规信息写入数据库
"""

import logging
from typing import Dict, Any
import sqlite3

import db

# 配置日志
logger = logging.getLogger(__name__)


def write_regulation(reg: Dict[str, Any], source_url: str, conn: sqlite3.Connection) -> int:
    """
    将法规信息写入数据库
    
    Args:
        reg: 法规信息字典，包含 全名, 发布机构, 发布日期, 生效日期, 国家/地区
        source_url: 来源链接
        conn: 数据库连接
    
    Returns:
        新记录的 id
    """
    reg_name = reg.get("全名", "")
    logger.info(f"写入法规: {reg_name}")
    
    # 调用数据库插入函数
    reg_id = db.insert_regulation(conn, reg, source_url)
    
    logger.info(f"法规写入成功，id={reg_id}: {reg_name}")
    return reg_id


if __name__ == "__main__":
    # 测试写入功能
    logging.basicConfig(level=logging.INFO)
    
    # 初始化数据库
    db.init_db()
    
    # 测试数据
    test_reg = {
        "全名": "数据安全管理条例",
        "发布机构": "国务院",
        "发布日期": "2025-03-01",
        "生效日期": "2025-06-01",
        "国家/地区": "中国",
    }
    
    with db.get_connection() as conn:
        reg_id = write_regulation(test_reg, "https://example.com/test", conn)
        print(f"\n写入成功，id={reg_id}")
        
        # 验证
        all_regs = db.get_all_regulations(conn)
        print(f"\n当前法规数量: {len(all_regs)}")
        for reg in all_regs:
            print(f"  - {reg['name_cn']} ({reg['publisher']})")