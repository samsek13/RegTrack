"""
Step 5: 聚合文章拆分
使用 LLM 将聚合文章拆分为若干相对独立的文章块
"""

import json
import logging
import re
from typing import List, Dict, Any
import sqlite3

import db
import llm
import config

# 配置日志
logger = logging.getLogger(__name__)

# Step 5 的 Prompt 模板
PROMPT_TEMPLATE = """### 1. 角色定义 (Role)

你是文本结构化分段专家，能够在聚合文章中识别出多个自身相对独立的"文本块"（可能是一个段落，也可能是数个相连的段落），并保持原文片段不变、完整。

### 2. 任务描述 (Task Description)

将输入文章拆分为若干语义独立的段落，要求必须保持原文连续片段与顺序，不进行改写或摘要。若能识别小标题则给出，否则允许 small_title 为 null。

### 3. 输出标准 (Output Format)

仅输出一个 JSON 对象，不要输出任何多余文字或标记：  
{  
"segments": [  
{"small_title": "可选标题或null", "content": "该段原文"}  
]  
}

### 4. 执行约束 (Constraints)

- 只基于输入文本进行分段，不引入外部信息。
- 所有分段加起来必须等于输入文本，不能有任何缺失或重复。
- 每个 segment 的 content 必须来自原文，避免改写。
- small_title 可以为 null，不得虚构标题。
- 输出必须为合法 JSON，且仅包含 segments 字段。
- 【强调】不要带有任何Markdown格式，例如'''json'''等

### 5. 参考示例 (Examples)

示例输入：标题="多项监管动态汇总"，正文含三条法规更新。  
示例输出：{"segments":[{"small_title":null,"content":"第一条原文..."},{"small_title":"某条例发布","content":"第二条原文..."}]}

### 6. 任务

聚合文章：{content}"""


def split_segments(item: Dict[str, Any], conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    将聚合文章拆分为独立文章块
    
    Args:
        item: item 字典，需包含 content_md
        conn: 数据库连接
    
    Returns:
        段落列表，每个元素：{"small_title": str | None, "content": str}
    """
    guid = item["guid"]
    content_md = item.get("content_md", "")
    
    # 构造 prompt（使用 replace 而不是 format，避免 content 中的 {} 被误解析）
    prompt = PROMPT_TEMPLATE.replace("{content}", content_md)
    
    # 调用 LLM
    response = _call_llm_with_retry(prompt)
    
    # 解析 JSON
    segments = _parse_segments_json(response)
    
    # 如果解析失败，将整篇文章作为一个 segment
    if not segments:
        logger.warning(f"JSON 解析失败，将整篇文章作为一个 segment: {item.get('title', '')[:50]}...")
        segments = [{"small_title": item.get("title"), "content": content_md}]
    
    # 记录到 llm_log_step5
    db.insert_llm_log(conn, "llm_log_step5", {
        "item_guid": guid,
        "prompt": prompt,
        "response": response,
        "segment_count": len(segments),
    })
    
    logger.info(f"聚合文章拆分完成，共 {len(segments)} 个 segment")
    return segments


def _call_llm_with_retry(prompt: str, max_retries: int = 3) -> str:
    """
    调用 LLM，获取 JSON 响应
    
    Args:
        prompt: 发送给 LLM 的 prompt
        max_retries: 最大重试次数
    
    Returns:
        LLM 返回的文本
    """
    for attempt in range(max_retries):
        try:
            response = llm.call_llm(prompt, model=getattr(config, 'llm_model_step5', None))
            return response
        except Exception as e:
            logger.error(f"LLM 调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                continue
            raise
    
    return ""


def _parse_segments_json(response: str) -> List[Dict[str, Any]]:
    """
    解析 LLM 返回的 JSON
    
    Args:
        response: LLM 返回的文本
    
    Returns:
        段落列表，解析失败返回空列表
    """
    try:
        # 尝试提取 JSON 部分
        json_str = response.strip()
        
        # 移除可能的 markdown 代码块标记
        # 处理 ```json ... ``` 和 ``` ... ``` 格式
        if "```" in json_str:
            # 使用正则表达式提取代码块内容
            # 匹配 ```json 或 ``` 后面的内容，直到下一个 ``` 或字符串结束
            code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', json_str, re.IGNORECASE)
            if code_block_match:
                json_str = code_block_match.group(1).strip()
            else:
                # 如果没有匹配到完整的代码块，尝试手动提取
                # 找到第一个 ``` 的位置
                first_tick = json_str.find("```")
                if first_tick != -1:
                    # 跳过 ``` 和可能的语言标识符
                    after_first_tick = json_str[first_tick + 3:]
                    # 跳过第一行（可能是 json 标识符）
                    lines = after_first_tick.split('\n', 1)
                    if len(lines) > 1:
                        first_line = lines[0].strip().lower()
                        if first_line in ('json', ''):
                            json_str = lines[1]
                        else:
                            json_str = after_first_tick
                    else:
                        json_str = after_first_tick
                    # 移除结尾的 ```
                    if "```" in json_str:
                        json_str = json_str.rsplit("```", 1)[0].strip()
        
        # 尝试找到 JSON 对象的边界
        start_idx = json_str.find("{")
        end_idx = json_str.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = json_str[start_idx:end_idx + 1]
        else:
            logger.warning(f"无法找到有效的 JSON 对象边界，响应前200字符: {response[:200]}")
            return []
        
        # 清理可能的控制字符和多余空白
        json_str = json_str.strip()
        
        def fix_json_string_value(s: str) -> str:
            """
            修复 JSON 字符串值中的非法转义序列（输入包含首尾引号）
            同时将实际换行符转为 \\n
            """
            if len(s) < 2:
                return s
            
            inner = s[1:-1]  # 去掉首尾引号
            result = []
            i = 0
            
            while i < len(inner):
                ch = inner[i]
                
                if ch == '\\':
                    if i + 1 < len(inner):
                        next_ch = inner[i + 1]
                        if next_ch in ('"', '\\', '/', 'b', 'f', 'n', 'r', 't'):
                            # 合法转义，原样保留
                            result.append('\\')
                            result.append(next_ch)
                            i += 2
                        elif next_ch == 'u':
                            # \uXXXX Unicode 转义，原样保留
                            result.append(inner[i:i+6])
                            i += 6
                        else:
                            # ❗ 非法转义如 \-  → 转成 \\-（反斜杠字面量 + 原字符）
                            result.append('\\\\')
                            result.append(next_ch)
                            i += 2
                    else:
                        # 末尾孤立反斜杠
                        result.append('\\\\')
                        i += 1
                        
                elif ch == '\n':
                    # 实际换行符 → 转义
                    result.append('\\n')
                    i += 1
                elif ch == '\r':
                    result.append('\\r')
                    i += 1
                elif ch == '\t':
                    result.append('\\t')
                    i += 1
                else:
                    result.append(ch)
                    i += 1
            
            return '"' + ''.join(result) + '"'

        json_str = re.sub(
            r'"(?:[^"\\]|\\.|\n|\r)*"',   # 注意加上 \n \r 的匹配
            lambda m: fix_json_string_value(m.group(0)),
            json_str
        )

        # 解析 JSON
        data = json.loads(json_str)
        
        # 验证结构
        if "segments" not in data:
            logger.warning(f"JSON 缺少 'segments' 字段，实际字段: {list(data.keys())}")
            return []
        
        segments = data["segments"]
        if not isinstance(segments, list):
            logger.warning(f"'segments' 不是列表，类型: {type(segments)}")
            return []
        
        # 验证每个 segment 的结构
        result = []
        for seg in segments:
            if not isinstance(seg, dict):
                logger.warning(f"segment 不是字典: {seg}")
                continue
            small_title = seg.get("small_title")
            content = seg.get("content")
            if content:  # content 必须存在
                result.append({
                    "small_title": small_title,
                    "content": str(content)
                })
        
        logger.info(f"成功解析 {len(result)} 个 segments")
        return result
        
    except json.JSONDecodeError as e:
        logger.warning(f"JSON 解析失败: {e}, 响应前500字符: {response[:500]}...")
        return []
    except Exception as e:
        logger.error(f"解析异常: {e}")
        return []


if __name__ == "__main__":
    # 测试拆分功能
    logging.basicConfig(level=logging.INFO)
    
    # 初始化数据库
    db.init_db()
    
    # 测试数据
    test_item = {
        "guid": "test-split-1",
        "title": "本周监管动态汇总",
        "content_md": """
## 1. GDPR 罚款案例

欧盟近日对某科技公司开出巨额罚单...

## 2. 中国数据安全法新规

国家网信办发布新规定...

## 3. 美国隐私法案更新

加州消费者隐私法迎来重要修订...
""",
    }
    
    with db.get_connection() as conn:
        segments = split_segments(test_item, conn)
        print(f"\n拆分结果（{len(segments)} 个 segment）:")
        for i, seg in enumerate(segments):
            print(f"\n--- Segment {i + 1} ---")
            print(f"Title: {seg.get('small_title')}")
            print(f"Content: {seg.get('content', '')[:100]}...")