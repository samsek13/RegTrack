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
from model_config import get_model_extra_body_for_thinking

# 配置日志
logger = logging.getLogger(__name__)

# 模块级缓存：key=model_name，value=ChatOpenAI 实例
# 相同 model 的多次调用复用同一实例，避免重复创建
_llm_cache: dict[str, ChatOpenAI] = {}


def _get_llm(model: Optional[str]) -> ChatOpenAI:
    """
    按 model name 获取（或创建并缓存）ChatOpenAI 实例。

    参数：
        model: 模型名称。为 None 或空字符串时 fallback 到 config.siliconflow_model。

    返回：
        对应 model 的 ChatOpenAI 实例（相同 model 复用缓存，不重复创建）。

    说明：
        base_url、api_key、temperature、max_tokens 等参数全局统一，不做 per-model 差异化。
        此函数仅供 call_llm 内部使用，不对外暴露。
    """
    resolved = model if model else config.siliconflow_model

    # 获取适合该模型的 extra_body 参数（考虑兼容性）
    extra_body = get_model_extra_body_for_thinking(resolved, False)

    if resolved not in _llm_cache:
        llm_kwargs = {
            "model": resolved,
            "base_url": config.siliconflow_api_base,
            "api_key": config.siliconflow_api_key,
            "temperature": 0,
            "max_tokens": 4096,
        }

        # 只有在参数存在且有效的情况下才添加 extra_body
        if extra_body:
            llm_kwargs["extra_body"] = extra_body

        _llm_cache[resolved] = ChatOpenAI(**llm_kwargs)
    return _llm_cache[resolved]


def call_llm(prompt: str, model: Optional[str] = None, max_retries: int = 3) -> str:
    """
    调用 LLM 并返回响应文本
    
    Args:
        prompt: 发送给 LLM 的提示文本
        model:  可选。指定使用的模型名称。
                为 None 或空字符串时 fallback 到 SILICONFLOW_MODEL。
        max_retries: 最大重试次数（默认 3 次）
    
    Returns:
        LLM 返回的文本内容（确保是字符串类型）
    
    Raises:
        Exception: 重试次数用尽后仍失败
    """
    llm = _get_llm(model)
    
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


def call_llm_json(prompt: str, model: Optional[str] = None, max_retries: int = 3) -> str:
    """
    调用 LLM 并期望返回 JSON 格式的内容
    
    与 call_llm 相同，但明确表示期望 JSON 输出
    （实际解析由调用方负责）
    
    Args:
        prompt: 发送给 LLM 的提示文本（应包含 JSON 输出要求）
        model:  可选。指定使用的模型名称。
                为 None 或空字符串时 fallback 到 SILICONFLOW_MODEL。
        max_retries: 最大重试次数
    
    Returns:
        LLM 返回的文本内容（期望为 JSON 字符串）
    """
    return call_llm(prompt, model, max_retries)
