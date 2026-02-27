"""
Step 2: 标题过滤
使用 LLM 判断 item 标题是否可能涉及规范性文件
"""

import logging
from typing import List, Dict, Any
import sqlite3

import db
import llm

# 配置日志
logger = logging.getLogger(__name__)

# Step 2 的 Prompt 模板
PROMPT_TEMPLATE = """# Role

你是一位资深的法律合规情报分析专家，专门负责从海量资讯标题中识别"规范性文件"的更新动态。

# Task Description

判断提供的文本（标题或描述）是否涉及：新的法律、法规、规章、国家政策、国家标准等规范性文件的发布、修订、征求意见或废止。

# Classification Logic (判定准则)

## 1. 判定为 YES 的情况 (包含但不限于)

- 明确匹配：标题含"法律、条例、规定、办法、标准、指南、指引、意见、通知、公告"等词汇。
- 动作匹配：标题含"印发、发布、施行、修订、废止、通过、征求意见、解读"等词汇。
- 宽泛/集合类标题 (宁滥勿缺)：标题具有概括性，暗示正文可能包含法规。例如：
  - 周期性报告：'AI合规要闻'、'数据法治周报'、'xx行业月报'。
  - 列表类：以'等'结尾，或含'多项政策'、'政策汇编'。
  - 存在疑问：只要无法百分之百断定其"不含政策法规"，均回答 YES。

## 2. 判定为 NO 的情况 (严格排他)

- 纯案例类：仅涉及具体的法院判例、处罚决定书，且未提及法规修订（如'xx公司偷税案判决结果'）。
- 纯事务类：仅涉及会议通知、培训广告、行业活动、人事任免。
- 纯新闻评论：不涉及具体条文，仅为宽泛的市场趋势评论或轶闻。

# Examples (少样本参考)

- 输入："关于《数据安全法》征求意见的公告" -> 输出：YES
- 输入："2024年3月网络安全合规月报" -> 输出：YES (理由：宽泛标题需包含)
- 输入："最高法发布五起典型知识产权案例" -> 输出：NO (理由：明确仅为案例)
- 输入："关于举办合规培训班的邀请函" -> 输出：NO (理由：纯事务通知)

# Constraints

- 必须严格遵守"宁滥勿缺"原则。
- 先在内心分析是否属于宽泛标题，再输出结论。
- 输出格式：仅输出 YES 或 NO ，严禁任何额外解释。

# Task

标题：{title}"""


def filter_by_title(items: List[Dict[str, Any]], conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    使用 LLM 过滤 item，跳过已处理的 guid
    
    Args:
        items: item 列表
        conn: 数据库连接
    
    Returns:
        标题判断为 YES 的 item 列表
    """
    filtered_items: List[Dict[str, Any]] = []
    
    for item in items:
        guid = item["guid"]
        title = item["title"]
        
        # 检查是否已处理过
        if db.is_guid_processed(conn, guid):
            logger.info(f"[SKIP] item 已处理过: {title[:50]}...")
            continue
        
        # 构造 prompt
        prompt = PROMPT_TEMPLATE.format(title=title)
        
        # 调用 LLM 判断
        result = _call_llm_with_retry(prompt)
        
        # 解析结果
        result_clean = result.strip().upper()
        if result_clean.startswith("YES"):
            step2_result = "YES"
            filtered_items.append(item)
            logger.info(f"[YES] 标题可能涉及规范性文件: {title[:50]}...")
        elif result_clean.startswith("NO"):
            step2_result = "NO"
            logger.info(f"[NO] 标题不涉及规范性文件: {title[:50]}...")
        else:
            # 非 YES/NO 响应，保守处理为 YES（宁滥勿缺）
            step2_result = "YES"
            filtered_items.append(item)
            logger.warning(f"[UNCLEAR] LLM 返回非预期结果，保守处理为 YES: {result[:50]}...")
        
        # 记录到 process_history
        db.insert_process_history(conn, guid, title, step2_result)
        
        # 记录到 llm_log_step2
        db.insert_llm_log(conn, "llm_log_step2", {
            "item_guid": guid,
            "title": title,
            "prompt": prompt,
            "response": result,
            "result": step2_result,
        })
    
    logger.info(f"标题过滤完成: 输入 {len(items)} 个 item，输出 {len(filtered_items)} 个")
    return filtered_items


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
            
            # 重试用尽，返回原始响应
            return response
            
        except Exception as e:
            logger.error(f"LLM 调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                continue
            raise
    
    return ""


if __name__ == "__main__":
    # 测试标题过滤功能
    import sys
    logging.basicConfig(level=logging.INFO)
    
    # 初始化数据库
    db.init_db()
    
    # 测试数据
    test_items = [
        {
            "guid": "test-1",
            "title": "关于《数据安全法》征求意见的公告",
            "description": "",
            "link": "https://example.com/1",
            "pub_date": None,
            "content_encoded": None,
        },
        {
            "guid": "test-2",
            "title": "关于举办合规培训班的邀请函",
            "description": "",
            "link": "https://example.com/2",
            "pub_date": None,
            "content_encoded": None,
        },
    ]
    
    with db.get_connection() as conn:
        filtered = filter_by_title(test_items, conn)
        print(f"\n过滤后剩余 {len(filtered)} 个 item:")
        for item in filtered:
            print(f"  - {item['title']}")