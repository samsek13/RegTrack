"""
Step 7C: 写入法规 Summary
将 Step 6 在内存中暂存的 summary 持久化到数据库
"""

import logging
import sqlite3

import db

# 配置日志
logger = logging.getLogger(__name__)


def write_summary(reg_id: int, summary: str, conn: sqlite3.Connection):
    """
    将 Step 6 生成的 summary 写入 regulations 表。
    
    参数：
        reg_id:  Step 7B 成功写入后返回的 regulations.id
        summary: Step 6 生成的主旨文本（非空字符串）
        conn:    数据库连接（由 pipeline.py 统一管理）
    
    失败处理：
        写入失败时仅记录警告日志，不向上抛出异常。
        法规主记录（Step 7B）已正常写入，summary 缺失不影响法规可用性。
    """
    try:
        db.update_regulation_summary(conn, reg_id, summary)
        logger.debug(f"summary 写入成功，regulation_id={reg_id}")
    except Exception as e:
        logger.warning(f"summary 写入失败，regulation_id={reg_id}，原因：{e}")


if __name__ == "__main__":
    # 测试写入功能
    logging.basicConfig(level=logging.INFO)
    
    # 初始化数据库
    db.init_db()
    
    with db.get_connection() as conn:
        # 先插入一条测试法规
        test_reg = {
            "全名": "测试法规",
            "国家/地区": "中国",
        }
        reg_id = db.insert_regulation(conn, test_reg, "https://example.com/test")
        print(f"插入测试法规，id={reg_id}")
        
        # 测试写入 summary
        write_summary(reg_id, "该法规是测试用法规，主要用于验证 summary 写入功能。", conn)
        print("summary 写入完成")
        
        # 验证
        regs = db.get_all_regulations(conn)
        target = next((r for r in regs if r['id'] == reg_id), None)
        if target and target.get('summary'):
            print(f"验证成功，summary: {target['summary']}")
        else:
            print("验证失败，summary 未写入")
