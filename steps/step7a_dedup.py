"""
Step 7A: 法规去重判断
通过 LangGraph RAG + LLM 判断新法规是否已在数据库中
"""

import json
import logging
from typing import Dict, Any, List
import sqlite3

import db
import llm
import rag

# 配置日志
logger = logging.getLogger(__name__)

# 每批对比的法规数量
BATCH_SIZE = 5

# Step 7A 的 Prompt 模板（用于 RAG 查询构建）
RAG_QUERY_TEMPLATE = """{new_reg_name}（发布机构：{publisher}，国家/地区：{jurisdiction}）和以下法规是否为同一个法规？请提供详细的对比分析。

已有法规：
{existing_regs}"""

# Step 7A 的 Prompt 模板（用于 LLM 判断）
LLM_PROMPT_TEMPLATE = """## 角色定义

你是一名专业的法律合规信息分析专家，擅长比较和判断不同法规是否为同一法规。

## 任务描述

基于提供的信息，判断新法规是否与已有法规重复。判断时需要考虑：
1. 法规名称是否相同或高度相似（可能存在翻译差异、简称/全称差异）
2. 发布机构是否相同或相关
3. 国家/地区是否匹配
4. 搜索结果中的额外信息

## 新法规信息

- 名称：{new_reg_name}
- 发布机构：{publisher}
- 国家/地区：{jurisdiction}

## 已有法规信息

{existing_regs}

## 搜索结果

{rag_result}

## 输出标准

仅输出 YES 或 NO：
- YES：新法规与已有法规中的某一个重复
- NO：新法规与所有已有法规都不重复

## 执行约束

- 对于名称相似但不完全相同的法规，需要结合其他信息判断
- 如果搜索结果表明是同一法规的不同表述，应判断为重复
- 如果无法确定，宁可判断为不重复（NO），避免误删
- 只输出 YES 或 NO，不要输出任何解释"""

# Step 7A 的简化 Prompt 模板（用于无 RAG 结果时的本地判断）
LOCAL_COMPARE_PROMPT_TEMPLATE = """## 角色定义

你是一名专业的法律合规信息分析专家，擅长比较和判断不同法规是否为同一法规。

## 任务描述

判断新法规是否与已有法规重复。判断时主要考虑：
1. 法规名称是否相同或高度相似（可能存在翻译差异、简称/全称差异）
2. 发布机构是否相同或相关
3. 国家/地区是否匹配

## 新法规信息

- 名称：{new_reg_name}
- 发布机构：{publisher}
- 国家/地区：{jurisdiction}

## 已有法规信息

{existing_regs}

## 输出标准

仅输出 YES 或 NO：
- YES：新法规与已有法规中的某一个重复
- NO：新法规与所有已有法规都不重复

## 执行约束

- 对于名称相似但不完全相同的法规，需要结合发布机构和国家地区判断
- 如果信息不足以判断，应判断为不重复（NO），避免误删
- 只输出 YES 或 NO，不要输出任何解释"""


def is_duplicate(new_reg: Dict[str, Any], conn: sqlite3.Connection) -> bool:
    """
    判断新法规是否已在数据库中（通过 RAG + LLM）
    
    Args:
        new_reg: 新提取的法规信息字典
        conn: 数据库连接
    
    Returns:
        True 表示重复（应丢弃），False 表示不重复（应写入）
    """
    new_reg_name = new_reg.get("全名", "")
    
    # 获取数据库中的所有法规
    existing_regs = db.get_all_regulations(conn)
    
    if not existing_regs:
        logger.info(f"数据库为空，法规 '{new_reg_name}' 不重复")
        return False
    
    logger.info(f"开始去重判断: '{new_reg_name}'，已有 {len(existing_regs)} 条法规")
    
    # 分批对比
    for i in range(0, len(existing_regs), BATCH_SIZE):
        batch = existing_regs[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        logger.info(f"对比批次 {batch_num}，包含 {len(batch)} 条已有法规")
        
        # 检查该批次是否有重复
        if _check_batch_duplicate(new_reg, batch, conn):
            logger.info(f"法规 '{new_reg_name}' 与批次 {batch_num} 中的法规重复")
            return True
    
    logger.info(f"法规 '{new_reg_name}' 不重复")
    return False


def _check_batch_duplicate(
    new_reg: Dict[str, Any],
    batch: List[Dict[str, Any]],
    conn: sqlite3.Connection
) -> bool:
    """
    检查新法规是否与某批次已有法规重复
    
    Args:
        new_reg: 新提取的法规信息
        batch: 一批次已有法规
        conn: 数据库连接
    
    Returns:
        True 表示重复，False 表示不重复
    """
    new_reg_name = new_reg.get("全名", "")
    publisher = new_reg.get("发布机构") or "未知"
    jurisdiction = new_reg.get("国家/地区") or "未知"
    
    # 构建已有法规描述
    existing_regs_desc = []
    for idx, reg in enumerate(batch, 1):
        desc = f"{idx}. {reg.get('name_cn', '')}"
        if reg.get('publisher'):
            desc += f"（发布机构：{reg.get('publisher')}）"
        if reg.get('jurisdiction'):
            desc += f" [国家/地区：{reg.get('jurisdiction')}]"
        existing_regs_desc.append(desc)
    
    existing_regs_str = "\n".join(existing_regs_desc)
    
    # 构建 RAG 查询
    rag_query = RAG_QUERY_TEMPLATE.format(
        new_reg_name=new_reg_name,
        publisher=publisher,
        jurisdiction=jurisdiction,
        existing_regs=existing_regs_str
    )
    
    # 调用 RAG 模块获取搜索结果
    try:
        rag_result = rag.search_and_answer(rag_query)
        logger.debug(f"RAG 搜索结果: {rag_result[:200]}...")
    except Exception as e:
        logger.warning(f"RAG 搜索失败: {e}，使用本地判断")
        rag_result = ""
    
    # 构建 LLM 判断 Prompt
    if rag_result:
        llm_prompt = LLM_PROMPT_TEMPLATE.format(
            new_reg_name=new_reg_name,
            publisher=publisher,
            jurisdiction=jurisdiction,
            existing_regs=existing_regs_str,
            rag_result=rag_result
        )
    else:
        llm_prompt = LOCAL_COMPARE_PROMPT_TEMPLATE.format(
            new_reg_name=new_reg_name,
            publisher=publisher,
            jurisdiction=jurisdiction,
            existing_regs=existing_regs_str
        )
    
    # 调用 LLM 判断
    try:
        llm_response = llm.call_llm(llm_prompt)
        result_clean = llm_response.strip().upper()
        
        is_dup = result_clean.startswith("YES")
        
        # 记录到 llm_log_step7a
        db.insert_llm_log(conn, "llm_log_step7a", {
            "new_reg_name": new_reg_name,
            "existing_reg_batch": json.dumps(batch, ensure_ascii=False),
            "rag_query": rag_query,
            "rag_result": rag_result[:2000] if rag_result else "",  # 截断以避免过长
            "llm_prompt": llm_prompt[:2000],  # 截断
            "llm_response": llm_response,
            "is_duplicate": 1 if is_dup else 0,
        })
        
        return is_dup
        
    except Exception as e:
        logger.error(f"LLM 判断失败: {e}")
        # 失败时保守处理：视为不重复
        return False


if __name__ == "__main__":
    # 测试去重功能
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
        # 先写入一条测试法规
        db.insert_regulation(conn, {
            "全名": "数据安全管理办法",
            "发布机构": "国家网信办",
            "发布日期": "2024-01-01",
        }, source_url="https://example.com/test")
        
        # 测试去重
        is_dup = is_duplicate(test_reg, conn)
        print(f"\n测试法规是否重复: {'是' if is_dup else '否'}")