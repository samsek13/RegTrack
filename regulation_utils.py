"""
法规工具模块
职责：为一条法规基于 RAG 生成标准化主旨描述，并按需写入数据库

这是 summary 生成的唯一实现。
Step 6、Step 7A、Step 9 均通过调用本模块实现 summary 生成，不得各自独立实现。
"""

import logging
from typing import Callable, Optional

from rag import search_and_answer
from llm import call_llm
from db import update_regulation_summary

logger = logging.getLogger(__name__)

# summary 生成的固定 prompt 模板，所有调用场景共享同一模板，确保格式一致
_SUMMARY_PROMPT_TEMPLATE = """## 角色
你是一名法律文本摘要专家。

## 任务
基于以下法规的基本信息及搜索结果，生成一段 2-3 句话的标准化主旨描述，用于法规去重与分类。
描述应尽量涵盖：主要规范对象、核心议题、适用范围。
若某项信息未知，跳过该项，不得虚构。

## 输出格式
仅输出纯文本描述，不得包含任何 Markdown、JSON 或额外说明。

## 法规信息
全名：{name_cn}
发布机构：{publisher}
发布日期：{publish_date}
生效日期：{effective_date}
国家/地区：{jurisdiction}

## 搜索结果
{rag_result}"""


def generate_and_save_summary(
    reg_info: dict,
    conn,
    reg_id: int | None = None,
    on_generated: Callable[[str, str], None] | None = None
) -> str:
    """
    基于 RAG 搜索为一条法规生成固定格式的主旨描述。

    参数：
        reg_info: 标准格式的法规信息字典，字段如下（调用方负责字段名转换）：
            {
                "name_cn":        str,         # 法规全名，必填
                "publisher":      str | None,  # 发布机构
                "jurisdiction":   str | None,  # 国家/地区
                "publish_date":   str | None,  # 发布日期 YYYY-MM-DD
                "effective_date": str | None   # 生效日期 YYYY-MM-DD
            }

        conn:   数据库连接（由 pipeline.py 统一管理）

        reg_id: 可选。
                非 None：生成成功后立即写入数据库 summary 字段（step7a、step9 场景）
                为 None：仅返回结果，不写库（step6 场景，由 step7c 在稍后写入）

        on_generated: 可选回调函数，在 summary 成功生成后调用。
                签名：on_generated(prompt: str, response: str) -> None
                用于 step6 记录日志到 llm_log_step6。

    返回：
        summary 字符串（保证非空）。
        所有重试均失败时，以 name_cn 作为回退值返回（不写库）。

    副作用：
        调用 rag.search_and_answer（联网）、llm.call_llm（LLM）
        reg_id 非 None 且生成成功时：调用 db.update_regulation_summary（写库）
        on_generated 非 None 且生成成功时：调用 on_generated 回调
    """
    name_cn = reg_info.get("name_cn", "")

    # --- 步骤一：构造 RAG 查询（跳过空值字段）---
    query_parts = [f"这个法规的主要内容和规范对象是什么？法规名：{name_cn}"]
    if reg_info.get("publisher"):
        query_parts.append(f"发布机构：{reg_info['publisher']}")
    if reg_info.get("jurisdiction"):
        query_parts.append(f"国家/地区：{reg_info['jurisdiction']}")
    query = "，".join(query_parts)

    try:
        rag_result = search_and_answer(query)
    except Exception as e:
        logger.warning(f"法规'{name_cn}'的 RAG 搜索失败，使用 name_cn 作为回退值。原因：{e}")
        return name_cn

    # --- 步骤二：构造 prompt 并调用 LLM ---
    prompt = _SUMMARY_PROMPT_TEMPLATE.format(
        name_cn=name_cn,
        publisher=reg_info.get("publisher") or "未知",
        publish_date=reg_info.get("publish_date") or "未知",
        effective_date=reg_info.get("effective_date") or "未知",
        jurisdiction=reg_info.get("jurisdiction") or "未知",
        rag_result=rag_result,
    )

    summary = None
    final_response = ""
    for attempt in range(3):
        try:
            result = call_llm(prompt).strip()
            final_response = result
            if result:
                summary = result
                break
        except Exception as e:
            logger.warning(f"法规'{name_cn}'的 summary LLM 调用失败，第{attempt + 1}次重试。原因：{e}")

    if not summary:
        logger.warning(f"法规'{name_cn}'的 summary 生成失败（3次重试均失败），使用 name_cn 作为回退值，不写库。")
        return name_cn

    # --- 步骤三：按需写库 ---
    if reg_id is not None:
        try:
            update_regulation_summary(conn, reg_id, summary)
            logger.debug(f"法规'{name_cn}'的 summary 写库成功，reg_id={reg_id}")
        except Exception as e:
            logger.warning(f"法规'{name_cn}'的 summary 写库失败，reg_id={reg_id}。原因：{e}")
            # 写库失败不影响返回值，调用方仍可使用内存中的 summary

    # --- 步骤四：调用回调（如果提供）---
    if on_generated is not None:
        try:
            on_generated(prompt, final_response)
        except Exception as e:
            logger.warning(f"法规'{name_cn}'的 on_generated 回调调用失败。原因：{e}")

    return summary
