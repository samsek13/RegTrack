"""
LLM 调用模块
封装对 SiliconFlow API 的直接 LLM 调用（非 LangGraph 路径）
"""

import time
import logging
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from config import config

# 配置日志
logger = logging.getLogger(__name__)

# 初始化全局 LLM 实例（temperature=0 确保确定性输出）
_llm: Optional[ChatOpenAI] = None


def _get_llm() -> ChatOpenAI:
    """
    获取或创建 LLM 实例（单例模式）
    """
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            model=config.siliconflow_model,
            base_url=config.siliconflow_api_base,
            api_key=config.siliconflow_api_key,
            temperature=0,
            max_tokens=4096,
        )
    return _llm


def call_llm(prompt: str, max_retries: int = 3) -> str:
    """
    调用 LLM 并返回响应文本
    
    Args:
        prompt: 发送给 LLM 的提示文本
        max_retries: 最大重试次数（默认 3 次）
    
    Returns:
        LLM 返回的文本内容（确保是字符串类型）
    
    Raises:
        Exception: 重试次数用尽后仍失败
    """
    llm = _get_llm()
    
    # 指数退避重试
    for attempt in range(max_retries):
        try:
            message = HumanMessage(content=prompt)
            response = llm.invoke([message])
            # 确保 content 是字符串类型
            content = response.content
            if content is None:
                logger.warning("LLM 返回的 content 为 None")
                return ""
            if not isinstance(content, str):
                logger.warning(f"LLM 返回的 content 类型异常: {type(content)}，尝试转换")
                content = str(content)
            return content
        except Exception as e:
            wait_time = 2 ** attempt  # 1s, 2s, 4s
            logger.warning(
                f"LLM 调用失败 (尝试 {attempt + 1}/{max_retries}): {e}，"
                f"{wait_time}秒后重试..."
            )
            if attempt < max_retries - 1:
                time.sleep(wait_time)
            else:
                logger.error(f"LLM 调用失败，已达最大重试次数: {e}")
                raise
    
    # 不应该到达这里
    raise RuntimeError("LLM 调用失败，未知错误")


def call_llm_json(prompt: str, max_retries: int = 3) -> str:
    """
    调用 LLM 并期望返回 JSON 格式的内容
    
    与 call_llm 相同，但明确表示期望 JSON 输出
    （实际解析由调用方负责）
    
    Args:
        prompt: 发送给 LLM 的提示文本（应包含 JSON 输出要求）
        max_retries: 最大重试次数
    
    Returns:
        LLM 返回的文本内容（期望为 JSON 字符串）
    """
    return call_llm(prompt, max_retries)