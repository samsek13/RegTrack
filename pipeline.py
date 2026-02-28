"""
流程编排模块
将步骤 1–9 编排为完整流程
"""

import logging
from datetime import date, timedelta
from typing import Optional
import sqlite3

import db
from steps import (
    fetch_items,
    filter_by_title,
    extract_content,
    extract_regulations,
    is_duplicate,
    write_regulation,
    step7c_summary,
    enrich_regulations,
    classify_regulations,
)

# 配置日志
logger = logging.getLogger(__name__)


def run_pipeline(cutoff_date: date, manual_url: Optional[str] = None):
    """
    运行完整的处理流程
    
    Args:
        cutoff_date: 截止日期，获取 pubDate <= cutoff_date 的所有 item
        manual_url: 手动传入的链接，非空时跳过步骤 1-2
    """
    logger.info(f"开始运行 pipeline，截止日期: {cutoff_date}")
    
    # 使用单个数据库连接
    with db.get_connection() as conn:
        if manual_url:
            # 手动链接模式：跳过步骤 1-2，直接从步骤 3 开始
            logger.info(f"手动链接模式，处理 URL: {manual_url}")
            _run_manual_url_pipeline(conn, manual_url)
        else:
            # 标准模式：运行步骤 1-9
            _run_standard_pipeline(conn, cutoff_date)
        
        # 步骤 8：字段补全（每次 pipeline 结束时统一执行）
        logger.info("=== 步骤 8: 字段补全 ===")
        try:
            enrich_regulations(conn)
        except Exception as e:
            logger.error(f"步骤 8 执行失败: {e}")
        
        # 步骤 9：法规分类（每次 pipeline 结束时统一执行）
        logger.info("=== 步骤 9: 法规分类 ===")
        try:
            classify_regulations(conn)
        except Exception as e:
            logger.error(f"步骤 9 执行失败: {e}")
    
    logger.info("Pipeline 执行完成")


def _run_standard_pipeline(conn: sqlite3.Connection, cutoff_date: date):
    """
    标准模式：运行步骤 1-7B
    """
    # 步骤 1：从 RSS 获取 item
    logger.info("=== 步骤 1: 获取 RSS items ===")
    try:
        items = fetch_items(cutoff_date)
        logger.info(f"获取到 {len(items)} 个 item")
    except Exception as e:
        logger.error(f"步骤 1 执行失败: {e}")
        raise
    
    if not items:
        logger.info("没有需要处理的 item")
        return
    
    # 步骤 2：标题过滤
    logger.info("=== 步骤 2: 标题过滤 ===")
    try:
        items = filter_by_title(items, conn)
        logger.info(f"过滤后剩余 {len(items)} 个 item")
    except Exception as e:
        logger.error(f"步骤 2 执行失败: {e}")
        raise
    
    if not items:
        logger.info("过滤后没有需要处理的 item")
        return
    
    # 处理每个 item（步骤 3-7B）
    for idx, item in enumerate(items, 1):
        logger.info(f"=== 处理 item {idx}/{len(items)}: {item.get('title', '')[:50]}... ===")
        try:
            _process_item(conn, item)
        except Exception as e:
            logger.error(f"处理 item 失败: {e}，跳过继续处理下一个")
            continue


def _run_manual_url_pipeline(conn: sqlite3.Connection, url: str):
    """
    手动链接模式：从步骤 3 开始处理
    """
    import requests
    from bs4 import BeautifulSoup
    
    # 从链接抓取标题
    logger.info(f"抓取链接: {url}")
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        title = soup.find("title")
        title_text = title.get_text().strip() if title else "未知标题"
        logger.info(f"获取到标题: {title_text}")
    except Exception as e:
        logger.error(f"抓取链接失败: {e}")
        raise
    
    # 构造伪 item
    item = {
        "guid": url,
        "title": title_text,
        "description": "",
        "link": url,
        "pub_date": None,
        "content_encoded": None,
    }
    
    # 处理 item
    _process_item(conn, item)


def _process_item(conn: sqlite3.Connection, item: dict):
    """
    处理单个 item（步骤 3-7B）
    注：跳过步骤4和5，直接将整篇文章连同标题传递给步骤6进行法规提取
    """
    guid = item["guid"]
    
    # 步骤 3：提取内容
    logger.info("步骤 3: 提取内容")
    try:
        item = extract_content(item, conn)
    except Exception as e:
        logger.warning(f"步骤 3 失败: {e}，跳过该 item")
        return
    
    # 跳过步骤4和5，直接将整篇文章作为单个 segment 处理
    # 使用文章标题作为 segment 的 small_title
    segment = {"small_title": item.get("title"), "content": item.get("content_md", "")}
    
    # 步骤 6：提取法规信息
    logger.info("步骤 6: 提取法规信息")
    try:
        regulations = extract_regulations(segment, guid, 0, conn)
        logger.info(f"提取到 {len(regulations)} 条法规")
    except Exception as e:
        logger.warning(f"步骤 6 失败: {e}，跳过该 item")
        return
    
    if not regulations:
        logger.info("该 item 未提取到法规信息")
        return
    
    # 步骤 7A-7C：去重、写入主记录、写入 summary
    for reg in regulations:
        reg_name = reg.get("全名", "")
        
        # 步骤 7A：去重判断
        logger.info(f"步骤 7A: 去重判断 - {reg_name[:30]}...")
        try:
            dup = is_duplicate(reg, conn)
            if dup:
                logger.info(f"法规重复，跳过: {reg_name}")
                continue
        except Exception as e:
            logger.warning(f"步骤 7A 失败: {e}，保守处理为不重复")
        
        # 步骤 7B：写入数据库
        logger.info(f"步骤 7B: 写入法规 - {reg_name[:30]}...")
        try:
            reg_id = write_regulation(reg, item.get("link", ""), conn)
            logger.info(f"法规写入成功: {reg_name}, id={reg_id}")
            
            # 步骤 7C：将 summary 持久化（仅在 7B 成功后执行）
            step7c_summary.write_summary(reg_id, reg.get('summary', ''), conn)
            
        except Exception as e:
            logger.error(f"步骤 7B/7C 失败: {e}")


if __name__ == "__main__":
    # 测试 pipeline
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # 初始化数据库
    db.init_db()
    
    if len(sys.argv) > 1:
        # 手动链接模式
        url = sys.argv[1]
        run_pipeline(date.today(), manual_url=url)
    else:
        # 标准模式
        cutoff = date.today() - timedelta(days=1)
        run_pipeline(cutoff)