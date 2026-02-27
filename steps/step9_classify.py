"""
Step 9: 法规分类
使用 LangGraph RAG + LLM 判断法规是否属于目标类别
"""

import logging
from typing import Dict, Any, List
import sqlite3

import db
import llm
import rag

# 配置日志
logger = logging.getLogger(__name__)

# Step 9 的 Prompt 模板（RAG 查询）
RAG_QUERY_TEMPLATE = """法规名称：{reg_name}
发布机构：{publisher}
国家/地区：{jurisdiction}

请提供这个法规的主要内容和主题。"""

# Step 9 的 Prompt 模板（LLM 分类）
LLM_PROMPT_TEMPLATE = """## 角色(Role)

你是一名法律与合规领域专家，熟悉国际及地区法规体系，擅长从信息中快速提取法规核心内容，并进行精确分类，尤其精通数据保护、隐私保护、APP/SDK合规及人工智能监管相关法规。

## 主要任务 (Task)

基于用户提供的法规名字，以及一段关于"该法规的主题内容是什么"的描述，判断该法规是否属于以下任意一类法律/法规/政策，只要核心内容命中一类即判定为**属于**。分类应基于法规的主要关注点，而非偶尔提及的内容。若法规内容本质属于其他领域，应判定为**不属于**；如无法完全确定，可作出合理推断，不得回答"无法判断"。

分类类别：  
1）数据保护：涉及个人数据、个人信息、数据处理或数据安全的法规，例如 GDPR、数据安全法、Data Protection Act 等。  
2）隐私保护：规范隐私权或个人隐私处理，可能与数据保护有重叠。  
3）APP合规：规范移动应用或应用程序的运营和合规要求，可能与数据保护、隐私法或 AI 监管相关。  
4）SDK合规：规范移动应用开发工具包或应用程序开发工具包的合规要求。  
5）人工智能监管：涉及 AI 系统、算法或自动化决策的监管法规，例如欧盟 AI Act、人工智能管理条例。  
6）网络安全：规范信息安全、网络运行及防护要求的法规。

## 输出标准 (Output Format)

- 必须只输出一个数字：
  - 若法规属于上述任一类别：输出 1
  - 若法规不属于上述类别：输出 0
- 不得添加任何其他文字、解释或标点
- 保证输出简洁明了，便于机器直接解析

## 执行约束 (Constraints)

- 核心判定依据法规的主要内容，而非偶尔提及的主题
- 避免使用"无法判断"或主观推测，尽量作合理推断
- 不得输出多余文字或额外说明
- 确保分类与法律专业术语一致，保持客观性和专业性

## 参考示例 (Examples)

输入示例 1：  
法规名称：欧盟通用数据保护条例（GDPR）  
法规主题内容：（略）  
输出示例：  
1

输入示例 2：  
法规名称：中华人民共和国公司法  
法规主题内容：（略）  
输出示例：  
0

## 任务

法规名称：{reg_name}

法规主题内容：{rag_result}"""


def classify_regulations(conn: sqlite3.Connection):
    """
    扫描 regulations 表中 category 为 NULL 的行，填写分类（1 或 0）
    
    Args:
        conn: 数据库连接
    """
    # 获取未分类的法规
    regs_to_classify = db.get_regulations_without_category(conn)
    
    if not regs_to_classify:
        logger.info("没有需要分类的法规")
        return
    
    logger.info(f"开始分类 {len(regs_to_classify)} 条法规")
    
    for reg in regs_to_classify:
        reg_id = reg["id"]
        reg_name = reg["name_cn"]
        logger.info(f"分类法规 [{reg_id}]: {reg_name}")
        
        category = _classify_regulation(conn, reg)
        
        if category is not None:
            db.update_regulation_field(conn, reg_id, "category", category)
            logger.info(f"  - 分类结果: {category}")
        else:
            logger.warning(f"  - 分类失败，保留为空")
    
    logger.info("法规分类完成")


def _classify_regulation(conn: sqlite3.Connection, reg: Dict[str, Any]) -> str:
    """
    对单条法规进行分类
    
    Args:
        conn: 数据库连接
        reg: 法规记录字典
    
    Returns:
        "1" 表示相关，"0" 表示不相关，失败返回 None
    """
    reg_name = reg["name_cn"]
    publisher = reg.get("publisher") or "未知"
    jurisdiction = reg.get("jurisdiction") or "未知"
    
    # 构建 RAG 查询
    rag_query = RAG_QUERY_TEMPLATE.format(
        reg_name=reg_name,
        publisher=publisher,
        jurisdiction=jurisdiction
    )
    
    # 调用 RAG 获取法规主题描述
    try:
        rag_result = rag.search_and_answer(rag_query)
        logger.debug(f"  - RAG 结果: {rag_result[:200]}...")
    except Exception as e:
        logger.warning(f"  - RAG 搜索失败: {e}")
        rag_result = "无搜索结果"
    
    # 调用 LLM 进行分类
    llm_prompt = LLM_PROMPT_TEMPLATE.format(
        reg_name=reg_name,
        rag_result=rag_result
    )
    
    # 重试机制
    max_retries = 3
    for attempt in range(max_retries):
        try:
            llm_response = llm.call_llm(llm_prompt)
            result_clean = llm_response.strip()
            
            # 验证结果
            if result_clean in ["0", "1"]:
                # 记录日志
                db.insert_llm_log(conn, "llm_log_step9", {
                    "regulation_id": reg["id"],
                    "rag_query": rag_query,
                    "rag_result": rag_result[:2000] if rag_result else "",
                    "llm_prompt": llm_prompt[:2000],
                    "llm_response": llm_response,
                    "category": result_clean,
                })
                
                return result_clean
            else:
                logger.warning(f"  - LLM 返回非预期结果 (尝试 {attempt + 1}/{max_retries}): {result_clean}")
                if attempt < max_retries - 1:
                    continue
                # 重试用尽，返回 None
                return None
                
        except Exception as e:
            logger.error(f"  - LLM 调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                continue
            # 失败返回 None
            return None
    
    return None


if __name__ == "__main__":
    # 测试分类功能
    logging.basicConfig(level=logging.INFO)
    
    # 初始化数据库
    db.init_db()
    
    with db.get_connection() as conn:
        # 先写入测试法规
        reg_id1 = db.insert_regulation(conn, {
            "全名": "欧盟通用数据保护条例",
            "发布机构": "欧盟",
            "国家/地区": "EU",
        }, source_url="https://example.com/test1")
        
        reg_id2 = db.insert_regulation(conn, {
            "全名": "中华人民共和国公司法",
            "发布机构": "全国人大",
            "国家/地区": "中国",
        }, source_url="https://example.com/test2")
        
        print(f"插入测试法规：id={reg_id1}, id={reg_id2}")
        
        # 测试分类
        classify_regulations(conn)
        
        # 查看结果
        regs = db.get_all_regulations(conn)
        print(f"\n分类后:")
        for reg in regs:
            print(f"  - {reg['name_cn']}: category={reg['category']}")