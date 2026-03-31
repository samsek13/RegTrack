"""
重新生成缺失 summary 的脚本
遍历 regulations 表中 summary 为空的记录，调用 LLM 生成并写入
"""

import logging
import sqlite3

import db
from regulation_utils import generate_and_save_summary

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_regulations_without_summary(conn: sqlite3.Connection) -> list[dict]:
    """获取 summary 为空的法规记录"""
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, name_cn, publisher, jurisdiction, publish_date, effective_date
           FROM regulations
           WHERE summary IS NULL OR summary = '';"""
    )
    return [dict(row) for row in cursor.fetchall()]


def regenerate_summaries():
    """主函数：遍历缺失 summary 的记录，重新生成"""
    # 初始化数据库
    db.init_db()

    with db.get_connection() as conn:
        # 查询缺失 summary 的记录
        regs = get_regulations_without_summary(conn)

        if not regs:
            logger.info("没有缺失 summary 的记录")
            return

        logger.info(f"发现 {len(regs)} 条缺失 summary 的记录")

        success_count = 0
        fail_count = 0

        for reg in regs:
            reg_id = reg["id"]
            name_cn = reg["name_cn"]

            logger.info(f"正在处理: [{reg_id}] {name_cn}")

            # 构造 reg_info（有啥用啥，不填充）
            reg_info = {
                "name_cn": name_cn,
                "publisher": reg.get("publisher"),
                "jurisdiction": reg.get("jurisdiction"),
                "publish_date": reg.get("publish_date"),
                "effective_date": reg.get("effective_date"),
            }

            try:
                # 调用现有的 summary 生成函数
                # reg_id 非 None，生成成功后会自动写入数据库
                summary = generate_and_save_summary(reg_info, conn, reg_id=reg_id)

                if summary and summary != name_cn:
                    logger.info(f"  ✓ 生成成功: {summary[:50]}...")
                    success_count += 1
                elif summary == name_cn:
                    # 回退值，说明生成失败
                    logger.warning(f"  ⚠ 生成失败，使用 name_cn 作为回退值")
                    fail_count += 1
                else:
                    logger.warning(f"  ⚠ 生成返回空值")
                    fail_count += 1

            except Exception as e:
                logger.error(f"  ✗ 处理失败: {e}")
                fail_count += 1

        logger.info(f"完成！成功: {success_count}, 失败: {fail_count}")


if __name__ == "__main__":
    regenerate_summaries()