"""
Step 8: 字段补全
使用 LangGraph RAG + LLM 补全法规记录中缺失的字段
"""

import logging
import re
from typing import Dict, Any, List, Optional
import sqlite3

import db
import llm
import rag
import config

# 配置日志
logger = logging.getLogger(__name__)

# 需要补全的字段列表（按顺序处理）
ENRICH_FIELDS = ["name_en", "publish_date", "effective_date", "publisher", "jurisdiction"]

# 用于检测中文字符的正则表达式
CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def enrich_regulations(conn: sqlite3.Connection):
    """
    扫描 regulations 表中有缺失字段的行，依次补全
    
    Args:
        conn: 数据库连接
    """
    # 获取有缺失字段的法规
    regs_to_enrich = db.get_regulations_with_missing_fields(conn)
    
    if not regs_to_enrich:
        logger.info("没有需要补全的法规")
        return
    
    logger.info(f"开始补全 {len(regs_to_enrich)} 条法规的缺失字段")
    
    for reg in regs_to_enrich:
        reg_id = reg["id"]
        reg_name = reg["name_cn"]
        logger.info(f"补全法规 [{reg_id}]: {reg_name}")
        
        # 按顺序补全各字段
        _enrich_regulation(conn, reg)
    
    logger.info("字段补全完成")


def _enrich_regulation(conn: sqlite3.Connection, reg: Dict[str, Any]):
    """
    补全单条法规的缺失字段
    
    Args:
        conn: 数据库连接
        reg: 法规记录字典
    """
    reg_id = reg["id"]
    reg_name = reg["name_cn"]
    jurisdiction = reg.get("jurisdiction")
    
    # 1. 首先处理 name_en
    if reg.get("name_en") is None:
        name_en = _enrich_name_en(conn, reg)
        if name_en:
            db.update_regulation_field(conn, reg_id, "name_en", name_en)
            reg["name_en"] = name_en
            logger.info(f"  - name_en 补全: {name_en}")
    
    # 2. 处理其他缺失字段
    for field in ENRICH_FIELDS[1:]:  # 跳过 name_en
        if reg.get(field) is None:
            value = _enrich_field(conn, reg, field)
            if value:
                db.update_regulation_field(conn, reg_id, field, value)
                reg[field] = value
                logger.info(f"  - {field} 补全: {value}")


def _enrich_name_en(conn: sqlite3.Connection, reg: Dict[str, Any]) -> Optional[str]:
    """
    补全法规英文名
    
    Args:
        conn: 数据库连接
        reg: 法规记录字典
    
    Returns:
        补全的英文名，失败返回 None
    """
    reg_name = reg["name_cn"]
    jurisdiction = reg.get("jurisdiction")
    publisher = reg.get("publisher")
    
    # 如果国家/地区是中国或台湾，直接返回 N/A
    if jurisdiction in ["中国", "台湾"]:
        logger.info(f"  - name_en: 国家/地区为 {jurisdiction}，设为 N/A")
        return "N/A"
    
    # 如果法规名不含中文，直接复制法规名作为英文名
    if not CHINESE_PATTERN.search(reg_name):
        logger.info(f"  - name_en: 法规名不含中文，直接使用: {reg_name}")
        return reg_name
    
    # 否则需要通过 RAG 查询英文名
    # 构建查询信息
    info_parts = [f"法规名称：{reg_name}"]
    if publisher:
        info_parts.append(f"发布机构：{publisher}")
    if jurisdiction:
        info_parts.append(f"国家/地区：{jurisdiction}")
    
    query = f"这个法规的英文名称是什么？{' '.join(info_parts)}"
    
    try:
        # 调用 RAG 获取信息
        rag_result = rag.search_and_answer(query)
        logger.debug(f"  - RAG 结果: {rag_result[:200]}...")
        
        # 调用 LLM 提取英文名
        llm_prompt = f"""基于以下搜索结果，提取法规"{reg_name}"的英文名称。

搜索结果：
{rag_result}

要求：
1. 如果能确定英文名，直接输出英文名称（不要输出其他任何文字）
2. 如果无法确定，输出 [TBC]
3. 不要输出解释、引号或其他多余内容"""

        llm_response = llm.call_llm(llm_prompt, model=getattr(config, 'llm_model_step8', None))
        name_en = llm_response.strip()
        
        # 清理可能的引号
        name_en = name_en.strip('"\'').strip()
        # 记录日志
        db.insert_llm_log(conn, "llm_log_step8", {
            "regulation_id": reg["id"],
            "field_name": "name_en",
            "rag_query": query,
            "rag_result": rag_result[:2000] if rag_result else None,
            "llm_prompt": llm_prompt,
            "llm_response": llm_response,
            "filled_value": name_en,
        })
        
        return name_en if name_en else "[TBC]"
        
    except Exception as e:
        logger.error(f"  - name_en 补全失败: {e}")
        return "[TBC]"


def _enrich_field(conn: sqlite3.Connection, reg: Dict[str, Any], field: str) -> Optional[str]:
    """
    补全法规的单个字段
    
    Args:
        conn: 数据库连接
        reg: 法规记录字典
        field: 字段名
    
    Returns:
        补全的值，失败返回 None
    """
    reg_name = reg["name_cn"]
    
    # 构建查询信息
    info_parts = [f"法规名称：{reg_name}"]
    
    # 添加已知字段信息（跳过空值）
    if reg.get("name_en") and reg["name_en"] not in ["N/A", "[TBC]"]:
        info_parts.append(f"英文名称：{reg['name_en']}")
    if reg.get("publisher"):
        info_parts.append(f"发布机构：{reg['publisher']}")
    if reg.get("jurisdiction"):
        info_parts.append(f"国家/地区：{reg['jurisdiction']}")
    if reg.get("publish_date"):
        info_parts.append(f"发布日期：{reg['publish_date']}")
    if reg.get("effective_date"):
        info_parts.append(f"生效日期：{reg['effective_date']}")
    
    # 字段中文名映射
    field_names = {
        "publish_date": "发布日期",
        "effective_date": "生效日期",
        "publisher": "发布机构",
        "jurisdiction": "国家/地区",
    }
    
    field_name = field_names.get(field, field)
    query = f"这个法规的{field_name}是什么？{' '.join(info_parts)}"
    
    try:
        # 调用 RAG 获取信息
        rag_result = rag.search_and_answer(query)
        logger.debug(f"  - RAG 结果: {rag_result[:200]}...")
        
        # 调用 LLM 提取值
        # 日期字段需要严格格式
        if field in ["publish_date", "effective_date"]:
            llm_prompt = f"""基于以下搜索结果，提取法规"{reg_name}"的{field_name}。

搜索结果：
{rag_result}

要求：
1. 输出格式必须是 YYYY-MM-DD（如 2025-01-15）
2. 如果无法确定具体日期，输出 [TBC]
3. 只输出日期，不要输出其他任何内容"""
        elif field == "jurisdiction":
            llm_prompt = f"""基于以下搜索结果，提取法规"{reg_name}"的国家/地区。

搜索结果：
{rag_result}

要求：
1. 如果是中国或台湾，输出中文（"中国" 或 "台湾"）
2. 如果是其他地区，输出英文缩写（如 US、UK、EU、JP 等）
3. 如果无法确定，输出 [TBC]
4. 只输出国家/地区，不要输出其他任何内容"""
        else:
            llm_prompt = f"""基于以下搜索结果，提取法规"{reg_name}"的{field_name}。

搜索结果：
{rag_result}

要求：
1. 直接输出{field_name}
2. 如果无法确定，输出 [TBC]
3. 不要输出解释或其他多余内容"""

        llm_response = llm.call_llm(llm_prompt, model=getattr(config, 'llm_model_step8', None))
        value = llm_response.strip()
        
        # 验证日期格式
        if field in ["publish_date", "effective_date"]:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
                if value != "[TBC]":
                    logger.warning(f"  - 日期格式无效: {value}，设为 [TBC]")
                    value = "[TBC]"
        
        # 记录日志
        db.insert_llm_log(conn, "llm_log_step8", {
            "regulation_id": reg["id"],
            "field_name": field,
            "rag_query": query,
            "rag_result": rag_result[:2000] if rag_result else None,
            "llm_prompt": llm_prompt,
            "llm_response": llm_response,
            "filled_value": value,
        })
        
        return value if value and value != "[TBC]" else None
        
    except Exception as e:
        logger.error(f"  - {field} 补全失败: {e}")
        return None


if __name__ == "__main__":
    # 测试补全功能
    logging.basicConfig(level=logging.INFO)
    
    # 初始化数据库
    db.init_db()
    
    with db.get_connection() as conn:
        # 先写入一条测试法规
        reg_id = db.insert_regulation(conn, {
            "全名": "GDPR",
            "发布机构": None,
            "发布日期": None,
        }, source_url="https://example.com/test")
        
        print(f"插入测试法规，id={reg_id}")
        
        # 测试补全
        enrich_regulations(conn)
        
        # 查看结果
        regs = db.get_all_regulations(conn)
        print(f"\n补全后:")
        for reg in regs:
            print(f"  - {reg['name_cn']} / {reg['name_en']} / {reg['publish_date']} / {reg['publisher']}")