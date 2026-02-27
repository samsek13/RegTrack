"""
Step 3: 内容提取
提取文章正文，清洗并转换为 Markdown 格式
"""

import logging
from typing import Dict, Any, Optional
import sqlite3

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

import db

# 配置日志
logger = logging.getLogger(__name__)

# 请求超时时间（秒）
REQUEST_TIMEOUT = 15


def extract_content(item: Dict[str, Any], conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    提取并清洗文章正文，转为 Markdown
    
    Args:
        item: item 字典，需包含 guid, title, link, content_encoded
        conn: 数据库连接
    
    Returns:
        附加了 content_md 字段的 item 字典
    
    Raises:
        Exception: 内容提取失败时抛出异常
    """
    guid = item["guid"]
    title = item["title"]
    link = item.get("link", "")
    content_encoded = item.get("content_encoded")
    
    content_md: Optional[str] = None
    
    # 路径一：优先使用 content:encoded
    if content_encoded:
        logger.info(f"[content:encoded] 从 RSS 提取正文: {title[:50]}...")
        content_md = _html_to_markdown(content_encoded)
    else:
        # 路径二：抓取 link 页面
        logger.info(f"[link] 抓取页面正文: {link}")
        content_md = _fetch_and_extract(link)
    
    if not content_md:
        raise Exception(f"内容提取失败: {title[:50]}...")
    
    # 清洗 Markdown
    content_md = _clean_markdown(content_md)
    
    # 写入缓存
    db.insert_cached_article(conn, guid, title, content_md, link)
    logger.info(f"内容提取完成，长度: {len(content_md)} 字符")
    
    # 返回附加了 content_md 的 item
    result = item.copy()
    result["content_md"] = content_md
    return result


def _html_to_markdown(html_content: str) -> str:
    """
    将 HTML 内容转换为 Markdown
    
    Args:
        html_content: HTML 内容
    
    Returns:
        Markdown 文本
    """
    # 使用 BeautifulSoup 解析 HTML
    soup = BeautifulSoup(html_content, "lxml")
    
    # 提取主体内容（优先 body 或 article）
    body = soup.find("body") or soup.find("article") or soup
    
    # 转换为 Markdown
    markdown_text = md(str(body), heading_style="ATX")
    
    return markdown_text


def _fetch_and_extract(url: str) -> str:
    """
    抓取网页并提取正文内容
    
    针对微信公众号文章优化，添加了反爬绕过措施：
    - 模拟真实浏览器的 User-Agent
    - 设置微信相关的 Referer
    - 添加必要的请求头
    
    Args:
        url: 网页 URL
    
    Returns:
        Markdown 格式的正文
    
    Raises:
        requests.RequestException: 网络请求失败
    """
    # 模拟真实浏览器的请求头
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://mp.weixin.qq.com/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-site",
        "Cache-Control": "max-age=0",
    }
    
    try:
        # 使用 session 保持连接状态
        session = requests.Session()
        
        # 首先访问微信主页获取 cookies（如果需要）
        if "mp.weixin.qq.com" in url:
            try:
                session.get("https://mp.weixin.qq.com", headers=headers, timeout=5)
            except:
                pass  # 忽略预访问的错误
        
        # 实际请求目标页面
        response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        # 检查是否被反爬拦截
        if "环境异常" in response.text or "完成验证后即可继续访问" in response.text:
            logger.error(f"遇到反爬验证页面: {url}")
            raise Exception(f"微信公众号文章需要验证，无法自动抓取: {url}")
        
        # 解析 HTML
        soup = BeautifulSoup(response.text, "lxml")
        
        # 针对微信公众号文章的特殊处理
        if "mp.weixin.qq.com" in url:
            # 微信文章的正文通常在 id="js_content" 的 div 中
            wechat_content = soup.find("div", id="js_content")
            if wechat_content:
                logger.info(f"使用微信专用选择器提取正文: {url}")
                # 移除微信特有的元素
                for elem in wechat_content.find_all(["script", "style"]):
                    elem.decompose()
                # 转换为 Markdown
                markdown_text = md(str(wechat_content), heading_style="ATX")
                return markdown_text
        
        # 通用提取逻辑
        # 优先级：article > main > body
        content = (
            soup.find("article") or 
            soup.find("main") or 
            soup.find("body") or 
            soup
        )
        
        if not content:
            logger.warning(f"无法提取正文内容: {url}")
            return ""
        
        # 转换为 Markdown
        markdown_text = md(str(content), heading_style="ATX")
        
        return markdown_text
        
    except requests.RequestException as e:
        logger.error(f"网页抓取失败: {url}, 错误: {e}")
        raise


def _clean_markdown(markdown_text: str) -> str:
    """
    清洗 Markdown 文本
    
    - 移除多余的空行（超过 2 个连续换行压缩为 2 个）
    - 移除首尾空白
    
    Args:
        markdown_text: 原始 Markdown 文本
    
    Returns:
        清洗后的 Markdown 文本
    """
    import re
    
    # 移除超过 2 个的连续换行
    cleaned = re.sub(r'\n{3,}', '\n\n', markdown_text)
    
    # 移除首尾空白
    cleaned = cleaned.strip()
    
    return cleaned


if __name__ == "__main__":
    # 测试内容提取功能
    logging.basicConfig(level=logging.INFO)
    
    # 初始化数据库
    db.init_db()
    
    # 测试数据（含 content_encoded）
    test_item = {
        "guid": "test-content-1",
        "title": "测试文章",
        "link": "https://example.com/test",
        "pub_date": None,
        "content_encoded": """
        <html>
        <body>
        <h1>测试标题</h1>
        <p>这是一段测试内容。</p>
        <p>这是第二段内容。</p>
        </body>
        </html>
        """,
    }
    
    with db.get_connection() as conn:
        result = extract_content(test_item, conn)
        print(f"\n提取结果:")
        print(f"Title: {result['title']}")
        print(f"Content length: {len(result['content_md'])} chars")
        print(f"\nContent preview:")
        print(result['content_md'][:200] + "...")