"""
Step 4: 聚合文章判断
使用 LLM 判断文章是否为聚合类文章
"""

import logging
from typing import Dict, Any
import sqlite3

import db
import llm

# 配置日志
logger = logging.getLogger(__name__)

# Step 4 的 Prompt 模板
PROMPT_TEMPLATE = """### 1. 角色定义 (Role)

你是文本结构识别专家，擅长从资讯类文章中准确判断其是否为多条法规/政策的聚合汇编。

### 2. 任务描述 (Task Description)

基于输入的标题与正文，判断该文章是否包含多个相对独立的法规/政策条目，属于并列汇总或合辑式写法；若仅围绕单一法规展开则判定为非聚合。请给出明确的布尔结果，确保判断稳定、可复用且符合语义结构。

### 3. 输出标准 (Output Format)

输出YES或NO

### 4. 执行约束 (Constraints)

- 只依据输入文本判断，不引入外部知识。
- 输出内容只包含YES或者NO。
- 不输出解释、推理过程或 Markdown等多余文字。

### 5. 参考示例 (Examples)

示例输入：标题="本周数据合规要闻汇总"，正文包含多条独立法规消息。  
示例输出：YES

### 6. 任务

标题：{title}
正文：{content}"""


def is_aggregate(item: Dict[str, Any], conn: sqlite3.Connection) -> bool:
    """
    判断文章是否为聚合类
    
    Args:
        item: item 字典，需包含 title 和 content_md
        conn: 数据库连接
    
    Returns:
        True 表示聚合类文章，False 表示非聚合类文章
    """
    guid = item["guid"]
    title = item["title"]
    content_md = item.get("content_md", "")
    
    # 截取正文（避免过长）
    # 保留前 4000 字符用于判断
    content_preview = content_md[:4000] if len(content_md) > 4000 else content_md
    
    # 构造 prompt
    prompt = PROMPT_TEMPLATE.format(title=title, content=content_preview)
    
    # 调用 LLM 判断
    result = _call_llm_with_retry(prompt)
    
    # 解析结果
    result_clean = result.strip().upper()
    is_agg = result_clean.startswith("YES")
    
    if is_agg:
        logger.info(f"[YES] 聚合类文章: {title[:50]}...")
    else:
        logger.info(f"[NO] 非聚合类文章: {title[:50]}...")
    
    # 记录到 llm_log_step4
    db.insert_llm_log(conn, "llm_log_step4", {
        "item_guid": guid,
        "prompt": prompt,
        "response": result,
        "result": "YES" if is_agg else "NO",
    })
    
    return is_agg


def _call_llm_with_retry(prompt: str, max_retries: int = 3) -> str:
    """
    调用 LLM，如果返回非 YES/NO 则重试
    
    Args:
        prompt: 发送给 LLM 的 prompt
        max_retries: 最大重试次数
    
    Returns:
        LLM 返回的文本
    """
    for attempt in range(max_retries):
        try:
            response = llm.call_llm(prompt)
            result_clean = response.strip().upper()
            
            # 检查是否为有效响应
            if result_clean.startswith("YES") or result_clean.startswith("NO"):
                return response
            
            logger.warning(f"LLM 返回非预期结果 (尝试 {attempt + 1}/{max_retries}): {response[:50]}...")
            
            if attempt < max_retries - 1:
                continue  # 重试
            
            # 重试用尽，视为非聚合类
            return "NO"
            
        except Exception as e:
            logger.error(f"LLM 调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                continue
            # 失败时视为非聚合类
            return "NO"
    
    return "NO"


if __name__ == "__main__":
    # 测试聚合判断功能
    logging.basicConfig(level=logging.INFO)
    
    # 初始化数据库
    db.init_db()
    
    # 测试数据
    test_items = [
        {
            "guid": "test-agg-1",
            "title": "本周数据合规要闻汇总",
            "content_md": "1. GDPR 罚款案例\n2. 中国数据安全法新规\n3. 美国隐私法案更新",
        },
        {
            "guid": "test-agg-2",
            "title": "欧盟发布人工智能法案",
            "content_md": "欧盟委员会今日正式发布了人工智能法案，该法案将于明年生效...",
        },
    ]
    
    with db.get_connection() as conn:
        for item in test_items:
            result = is_aggregate(item, conn)
            print(f"\n{item['title']}: {'聚合' if result else '非聚合'}")