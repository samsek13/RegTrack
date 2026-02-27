"""
Step 1: RSS 源分页获取
从 RSS 源分页获取晚于指定日期的全部 item
"""

import logging
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import List, Dict, Any, Optional

import feedparser
import requests

from config import config

# 配置日志
logger = logging.getLogger(__name__)

# 分页参数
PAGE_SIZE = 30  # 每页获取的 item 数量


def fetch_items(cutoff_date: date) -> List[Dict[str, Any]]:
    """
    从 RSS 源分页获取晚于指定日期的全部 item
    
    Args:
        cutoff_date: 起始日期，获取 pubDate >= cutoff_date 的所有 item
    
    Returns:
        item 列表，每个 item 为字典：
        {
            "guid": str,
            "title": str,
            "description": str,
            "link": str,
            "pub_date": date | None,
            "content_encoded": str | None
        }
    """
    logger.info(f"开始获取 RSS 源，起始日期: {cutoff_date}")
    
    all_items: List[Dict[str, Any]] = []
    offset = 0
    should_continue = True
    
    while should_continue:
        # 构建分页 URL
        url = f"{config.rss_feed_url}?offset={offset}&limit={PAGE_SIZE}"
        logger.info(f"获取 RSS 页面: offset={offset}, limit={PAGE_SIZE}")
        
        try:
            # 解析 RSS feed
            feed = feedparser.parse(url)
            
            # 检查是否有错误
            if feed.bozo and feed.bozo_exception:
                logger.error(f"RSS 解析错误: {feed.bozo_exception}")
                raise Exception(f"RSS 解析失败: {feed.bozo_exception}")
            
            entries = feed.entries
            if not entries:
                logger.info("RSS 源无更多条目，停止获取")
                break
            
            # 处理当前页的 item
            page_added = 0
            page_skipped = 0
            for entry in entries:
                item = _parse_entry(entry)
                
                # 检查 pub_date 是否 >= 起始日期
                if item["pub_date"] is not None:
                    if item["pub_date"] >= cutoff_date:
                        all_items.append(item)
                        page_added += 1
                        logger.debug(f"添加 item: {item['title'][:50]}... (pub_date: {item['pub_date']})")
                    else:
                        # 当前 item pub_date < cutoff_date，但仍需继续翻页
                        # 因为 RSS 可能是时间倒序的，后面的可能更晚
                        page_skipped += 1
                        logger.debug(f"跳过 item (日期过早): {item['title'][:50]}... (pub_date: {item['pub_date']})")
                else:
                    # pub_date 解析失败，视为需处理（宁滥勿缺）
                    all_items.append(item)
                    page_added += 1
                    logger.warning(f"item pub_date 解析失败，默认添加: {item['title'][:50]}...")
            
            logger.info(f"本页处理结果: 添加 {page_added} 个, 跳过 {page_skipped} 个 (日期早于 {cutoff_date})")
            
            # 检查是否需要继续翻页
            # 终止条件：返回的 item 数量 < limit（已到末尾）
            # 或者当前批次中所有 item 的 pub_date 都 < cutoff_date（已经越过目标日期范围）
            if len(entries) < PAGE_SIZE:
                logger.info("已到达 RSS 源末尾，停止获取")
                break
            
            # 检查当前批次是否所有 item 的日期都早于 cutoff_date
            # 如果是，说明已经越过目标日期范围，可以停止
            all_items_before_cutoff = all(
                item["pub_date"] is not None and item["pub_date"] < cutoff_date
                for item in [_parse_entry(e) for e in entries]
            )
            if all_items_before_cutoff:
                logger.info("当前批次所有 item 日期均早于起始日期，停止获取")
                break
            
            # 继续翻页
            offset += PAGE_SIZE
            
        except requests.RequestException as e:
            logger.error(f"网络请求失败: {e}")
            raise Exception(f"RSS 源无法访问: {e}")
    
    logger.info(f"RSS 获取完成，共获取 {len(all_items)} 个 item")
    return all_items


def _parse_entry(entry) -> Dict[str, Any]:
    """
    解析 RSS feed entry
    
    Args:
        entry: feedparser 解析的 entry 对象
    
    Returns:
        解析后的 item 字典
    """
    # 提取 guid（优先 id，次选 link）
    guid = entry.get("id") or entry.get("guid") or entry.get("link", "")
    
    # 提取 title
    title = entry.get("title", "")
    
    # 提取 description
    description = entry.get("description", "")
    
    # 提取 link
    link = entry.get("link", "")
    
    # 解析 pub_date
    pub_date: Optional[date] = None
    pub_date_str = entry.get("published") or entry.get("pubDate")
    if pub_date_str:
        try:
            # 尝试解析 RFC 2822 格式的日期
            dt = parsedate_to_datetime(pub_date_str)
            pub_date = dt.date()
        except (ValueError, TypeError) as e:
            logger.warning(f"pub_date 解析失败: {pub_date_str}, 错误: {e}")
            pub_date = None
    
    # 提取 content:encoded
    # feedparser 将 content:encoded 映射为 entry.content[0].value
    content_encoded: Optional[str] = None
    if "content" in entry and len(entry.content) > 0:
        content_encoded = entry.content[0].get("value")
    # 也尝试通过命名空间直接获取
    elif "content_encoded" in entry:
        content_encoded = entry.get("content_encoded")
    
    return {
        "guid": guid,
        "title": title,
        "description": description,
        "link": link,
        "pub_date": pub_date,
        "content_encoded": content_encoded,
    }


if __name__ == "__main__":
    # 测试 RSS 获取功能
    import sys
    logging.basicConfig(level=logging.DEBUG)
    
    # 默认使用今天作为起始日期
    if len(sys.argv) > 1:
        cutoff = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
    else:
        cutoff = date.today()
    
    items = fetch_items(cutoff)
    print(f"\n获取到 {len(items)} 个 item:")
    for i, item in enumerate(items[:5]):
        print(f"\n--- Item {i+1} ---")
        print(f"Title: {item['title'][:60]}...")
        print(f"GUID: {item['guid']}")
        print(f"Pub Date: {item['pub_date']}")
        print(f"Link: {item['link']}")
        if item['content_encoded']:
            print(f"Content: {len(item['content_encoded'])} chars")