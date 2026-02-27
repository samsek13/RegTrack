"""
LangGraph 联网搜索 RAG 模块
基于 LangGraph + Tavily 的联网搜索 RAG 系统
"""

import os
import logging
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langchain_core.messages import HumanMessage, SystemMessage

from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from config import config

# 配置日志
logger = logging.getLogger(__name__)

# ============================================================
# 第一步：初始化 LLM（通过 SiliconFlow）
# ============================================================
_llm: Optional[ChatOpenAI] = None
_tavily_search_tool: Optional[TavilySearch] = None
_graph: Optional[StateGraph] = None


def _get_llm() -> ChatOpenAI:
    """获取或创建 LLM 实例（单例模式）"""
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


def _get_tavily_tool() -> TavilySearch:
    """获取或创建 Tavily 搜索工具实例（单例模式）"""
    global _tavily_search_tool
    if _tavily_search_tool is None:
        _tavily_search_tool = TavilySearch(
            max_results=5,
            search_depth="advanced",
            include_answer=True,
            topic="general",
        )
    return _tavily_search_tool


# ============================================================
# 第二步：把搜索工具绑定到 LLM
# ============================================================
def _get_llm_with_tools():
    """获取绑定了工具的 LLM"""
    llm = _get_llm()
    tools = [_get_tavily_tool()]
    return llm.bind_tools(tools), tools


# ============================================================
# 第三步：定义 LangGraph 的工作流节点
# ============================================================
def _chatbot_node(state: MessagesState):
    """
    接收当前对话状态，调用 LLM。
    LLM 会决定：
      - 直接回答（如果不需要搜索）
      - 或者调用 tavily_search_tool（如果需要搜索）
    """
    system_prompt = SystemMessage(content=(
        "你是一个有帮助的 AI 助手。"
        "当用户的问题需要最新信息、实时数据或你不确定的事实时，"
        "请使用 tavily_search 工具搜索网络获取信息。"
        "当你使用搜索结果回答时，请标注信息来源。"
        "如果搜索结果中没有找到相关信息，请诚实告知用户。"
    ))
    
    llm_with_tools, _ = _get_llm_with_tools()
    messages_with_system = [system_prompt] + state["messages"]
    response = llm_with_tools.invoke(messages_with_system)
    return {"messages": [response]}


def _get_tool_node():
    """获取工具执行节点"""
    _, tools = _get_llm_with_tools()
    return ToolNode(tools=tools)


# ============================================================
# 第四步：构建 LangGraph 工作流图
# ============================================================
def _build_graph():
    """构建并编译 LangGraph 工作流图"""
    # 创建图
    workflow = StateGraph(MessagesState)
    
    # 获取工具节点
    tool_node = _get_tool_node()
    
    # 添加节点
    workflow.add_node("chatbot", _chatbot_node)
    workflow.add_node("tools", tool_node)
    
    # 添加边（定义流程）
    # 1. 起点 → chatbot 节点
    workflow.add_edge(START, "chatbot")
    
    # 2. chatbot 节点 → 条件分支
    #    - 如果 LLM 决定调用工具 → 去 tools 节点
    #    - 如果 LLM 直接回答 → 结束
    workflow.add_conditional_edges(
        "chatbot",
        tools_condition,
    )
    
    # 3. tools 节点（搜索完成后） → 回到 chatbot 节点
    #    让 LLM 基于搜索结果生成最终回答
    workflow.add_edge("tools", "chatbot")
    
    # 编译图
    return workflow.compile()


def _get_graph():
    """获取或创建编译后的图实例（单例模式）"""
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


# ============================================================
# 第五步：定义对外暴露的接口函数
# ============================================================
def search_and_answer(question: str) -> str:
    """
    输入用户问题，返回基于网络搜索的回答。
    
    这是模块对外暴露的唯一接口。
    LLM 会自动决定是否需要搜索网络获取信息。
    
    Args:
        question: 用户的问题
    
    Returns:
        基于网络搜索的回答文本
    """
    logger.info(f"RAG 模块收到问题: {question[:100]}...")
    
    graph = _get_graph()
    
    # 调用图
    result = graph.invoke({
        "messages": [HumanMessage(content=question)]
    })
    
    # 获取最后一条消息（即最终回答）
    final_message = result["messages"][-1]
    
    logger.info(f"RAG 模块返回回答，长度: {len(final_message.content)} 字符")
    return final_message.content


# ============================================================
# 测试入口
# ============================================================
if __name__ == "__main__":
    # 测试问题
    test_questions = [
        "今天的天气怎么样？",
        "Python 的列表和元组有什么区别？",
        "2024年诺贝尔物理学奖获得者是谁？",
    ]
    
    for q in test_questions:
        print(f"\n{'='*60}")
        print(f"问题: {q}")
        print(f"{'='*60}")
        answer = search_and_answer(q)
        print(f"回答: {answer}")