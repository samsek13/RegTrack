"""
Step 7A: 法规去重判断
改造后逻辑：
  阶段一：jurisdiction 过滤（SQL，零 LLM 成本）
  阶段一点五：旧法规 summary 补全（按需 RAG，仅对 summary=NULL 的记录触发）
  阶段二：主旨语义比对（纯 LLM，无联网 RAG）
"""

import json
import logging
from typing import Dict, Any, List
import sqlite3

import db
import llm
from regulation_utils import generate_and_save_summary

# 配置日志
logger = logging.getLogger(__name__)

# 每批对比的法规数量
BATCH_SIZE = 5


def is_duplicate(new_reg: Dict[str, Any], conn: sqlite3.Connection) -> bool:
    """
    判断新法规是否与数据库中已有法规重复。
    
    参数：
        new_reg: Step 6 提取的法规字典，必须包含 'summary' 键
        conn:    数据库连接
    
    返回：
        True  = 数据库中已存在实质相同的法规，应丢弃新法规
        False = 数据库中不存在重复法规，可写入
    """
    # --- 阶段一：jurisdiction 过滤 ---
    jurisdiction = new_reg.get("国家/地区")
    if jurisdiction:
        existing_regs = db.get_regulations_by_jurisdiction(conn, jurisdiction)
        filter_desc = f"jurisdiction={jurisdiction}"
    else:
        existing_regs = db.get_all_regulations(conn)
        filter_desc = "jurisdiction=NULL（全量比对）"
        logger.warning(f"新法规'{new_reg.get('全名')}'的 jurisdiction 为空，退化为全量比对")

    if not existing_regs:
        logger.debug(f"过滤后无匹配旧法规，直接判定为不重复（{filter_desc}）")
        return False

    # --- 阶段一点五：补全 summary 为 NULL 的旧法规 ---
    # 改造前写入的记录 summary 为 NULL，需先通过 RAG 补生成再参与比对
    for reg in existing_regs:
        if not reg.get('summary'):
            # 数据库字段名已与标准格式一致，直接构造传入（无需字段名转换）
            reg_info = {
                "name_cn":        reg["name_cn"],
                "publisher":      reg.get("publisher"),
                "jurisdiction":   reg.get("jurisdiction"),
                "publish_date":   reg.get("publish_date"),
                "effective_date": reg.get("effective_date"),
            }
            # reg_id=reg['id']：step7a 场景，生成后立即写库，供后续任务复用
            summary = generate_and_save_summary(reg_info, conn, reg_id=reg["id"])
            reg["summary"] = summary  # 同步更新内存中的值供本次比对使用

    # --- 阶段二：分批主旨语义比对（纯 LLM，无 RAG） ---
    new_reg_name = new_reg.get("全名", "")
    new_reg_summary = new_reg.get("summary", new_reg_name)

    for batch_start in range(0, len(existing_regs), BATCH_SIZE):
        batch = existing_regs[batch_start: batch_start + BATCH_SIZE]
        if _compare_batch(new_reg_name, new_reg_summary, batch, filter_desc, conn):
            logger.info(f"法规'{new_reg_name}'判定为重复，跳过写入")
            return True

    return False


def _compare_batch(
    new_name: str,
    new_summary: str,
    batch: List[Dict[str, Any]],
    jurisdiction_filter: str,
    conn: sqlite3.Connection
) -> bool:
    """
    对单批旧法规执行语义比对，返回是否存在重复。
    
    此时 batch 中所有记录的 summary 均已保证非空（经阶段一点五处理）。
    LLM 返回非 YES/NO 时重试最多 3 次；仍失败则视为 NO（保守策略）。
    每批结果写入 llm_log_step7a。
    """
    batch_lines = []
    for i, reg in enumerate(batch, 1):
        batch_lines.append(f"{i}. 名称：{reg['name_cn']}\n   主旨：{reg['summary']}")
    existing_list_str = "\n".join(batch_lines)

    prompt = f"""## 角色
你是一名法律信息去重专家。

## 任务
判断"新法规"与下列"已有法规"中，是否存在任何一条与新法规实质上是同一部法规。
判断依据：法规名称、主旨描述所体现的规范对象与核心议题。
注意：同一法规可能存在中英文名称差异或不同表述，请基于实质内容判断。

## 输出格式
仅输出 YES 或 NO。YES 表示存在重复，NO 表示均不重复。不得输出任何其他内容。

## 新法规
名称：{new_name}
主旨：{new_summary}

## 已有法规列表
{existing_list_str}"""

    batch_json = json.dumps(
        [{"name_cn": r["name_cn"], "summary": r.get("summary")} for r in batch],
        ensure_ascii=False
    )

    llm_response = ""
    is_dup = False

    for attempt in range(3):
        try:
            llm_response = llm.call_llm(prompt).strip().upper()
            if llm_response in ("YES", "NO"):
                is_dup = (llm_response == "YES")
                break
            logger.warning(f"Step 7A LLM 返回非法值'{llm_response}'，第{attempt+1}次重试")
        except Exception as e:
            logger.warning(f"Step 7A LLM 调用失败，第{attempt+1}次重试，原因：{e}")
    else:
        logger.warning("Step 7A 比对失败（3次重试均失败），保守判定为不重复")
        is_dup = False

    db.insert_llm_log(conn, "llm_log_step7a", {
        "new_reg_name": new_name,
        "new_reg_summary": new_summary,
        "existing_reg_batch": batch_json,
        "llm_prompt": prompt,
        "llm_response": llm_response,
        "is_duplicate": 1 if is_dup else 0,
        "jurisdiction_filter": jurisdiction_filter,
    })

    return is_dup


if __name__ == "__main__":
    # 测试去重功能
    logging.basicConfig(level=logging.INFO)
    
    # 初始化数据库
    db.init_db()
    
    with db.get_connection() as conn:
        # 写入一条已有法规（含 summary）
        reg_id = db.insert_regulation(conn, {
            "全名": "儿童在线隐私保护规则",
            "国家/地区": "US"
        }, "https://ftc.gov")
        db.update_regulation_summary(conn, reg_id, "该法规由美国联邦贸易委员会发布，主要规范面向13岁以下儿童的网站和在线服务的隐私保护要求，于1999年生效。")
        print("插入测试法规1（有summary）")
        
        # 写入一条旧法规（summary 为 NULL，模拟改造前写入的记录）
        old_reg_id = db.insert_regulation(conn, {
            "全名": "加利福尼亚消费者隐私法",
            "国家/地区": "US",
            "发布机构": "California Legislature"
        }, "https://example.com/ccpa")
        # 不调用 update_regulation_summary，保持 summary=NULL
        print("插入测试法规2（summary=NULL）")
        
        # 测试1：同 jurisdiction + 实质重复的法规 → 应返回 True
        dup_reg = {
            "全名": "COPPA（儿童在线隐私保护法实施细则）",
            "国家/地区": "US",
            "summary": "该规则由FTC依据COPPA法案制定，规定收集13岁以下儿童个人信息须获得家长同意。"
        }
        result = is_duplicate(dup_reg, conn)
        print(f"\n测试1（重复法规）：{result}，期望 True")
        
        # 测试2：不同 jurisdiction → 过滤后无匹配，应直接返回 False（不调用LLM）
        foreign_reg = {
            "全名": "General Data Protection Regulation",
            "国家/地区": "EU",
            "summary": "欧盟数据保护通用条例，规范个人数据处理，于2018年生效。"
        }
        result = is_duplicate(foreign_reg, conn)
        print(f"测试2（不同 jurisdiction）：{result}，期望 False")
        
        # 测试3：同 jurisdiction + 完全不同的法规 → 应返回 False
        different_reg = {
            "全名": "美国反垄断法修正案",
            "国家/地区": "US",
            "summary": "该法规规范市场竞争行为，禁止垄断和不正当竞争，与儿童隐私无关。"
        }
        result = is_duplicate(different_reg, conn)
        print(f"测试3（不同法规）：{result}，期望 False")
        
        # 测试4：验证 summary=NULL 的旧记录在比对后已被补全写入数据库
        regs = db.get_all_regulations(conn)
        old_reg = next((r for r in regs if r['id'] == old_reg_id), None)
        if old_reg and old_reg.get('summary'):
            print(f"\n测试4（NULL summary 补全）：通过，补全后 summary='{old_reg['summary'][:30]}...'")
        else:
            print("\n测试4（NULL summary 补全）：summary 仍为 NULL（RAG 补全可能失败，检查日志）")
        
        print("\n测试完成")
