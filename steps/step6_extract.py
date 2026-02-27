"""
Step 6: 法规信息提取
从"原始文本"中提取结构化法规信息
"""

import json
import logging
import re
from typing import List, Dict, Any
import sqlite3

import db
import llm

# 配置日志
logger = logging.getLogger(__name__)

# Step 6 的 Prompt 模板
PROMPT_TEMPLATE = """## 1. 角色定义 (Role)

你是一名专业的法律信息分析师，具备扎实的法律规范体系知识和政策解读能力，熟悉法律、行政法规、部门规章、地方性法规、政府规范性文件及国家标准的发布与生效机制，能够对文本进行精确识别与结构化信息提取。

## 2. 任务描述 (Task Description)

基于用户提供的网络文章标题及正文内容，完成以下两项任务：  
（1）识别文章中是否提及任何"新的法律、法规、规章、政府政策、国家标准等规范性文件"的发布或生效；  
（2）若提及，则对每一个相关规范性文件分别判断：  
    (a)其是否属于"新发布"或"新生效"，  
    (b)如果对于(a)回答"是"，那么提取它的全称、发布机构、发布日期、生效日期等关键信息。  
    (c)如果对于(a)回答"否"，则直接输出"[]"，表示不存在任何【新发布或新生效的规范性文件】。  
注：若文章中涉及多个规范性文件，须逐一独立分析与输出，不得遗漏。判断应基于文章明确表述，不得推测未明示信息。

## 3. 输出标准 (Output Format)

输出必须为合法 JSON 格式，结构如下，且每次输出结构保持完全一致：

[  
{  
"全名": "规范性文件全称，不要包含任何书名号、双引号等前后的符号",  
"发布机构": "发布机构名称，如未提及则为null",  
"发布日期": "YYYY-MM-DD格式，如未提及则为null",  
"生效日期": "YYYY-MM-DD格式，如未提及则为null",  
"国家/地区": "以jurisdiction为维度，而不以国家为维度，比如HK和中国是不同的，依此类推"  
}  
]

具体要求：

1. 若文章未提及任何【新发布或新生效的规范性文件】，则输出：  
   []
2. 所有日期统一为 YYYY-MM-DD 格式；无法确定具体日期时填 null。
3. 国家/地区填写格式：如果是中国或者台湾，请填入中文（"中国"、"台湾"），如果是其他地区，请填入英文缩写。
4. 不得输出除 JSON 以外的任何说明性文字。
5. 每一个规范性文件必须单独形成一个对象条目。
6. 【强调】不要带有任何Markdown格式，例如'''json'''等

## 4. 执行约束 (Constraints)

- 仅基于用户提供的标题与正文进行判断，不得使用外部知识补充。
- "新的"是指文章明确提及"发布""印发""公布""出台""通过""生效""施行"等表示时间节点的行为。
- 若仅为一般性引用既有法律，而未提及发布或生效信息，则不应当进入输出结果中。
- **重复强调**：若仅为一般性引用既有法律，而未提及发布或生效信息，则不应当进入输出结果中。
- 在你把一个规范性文件加入到输出之前，请务必确保，这篇文章明确提到了这个规范性文件的通过、发布、生效
- 不得推测发布机构或日期；未明确写明的一律填写 null
- 保持字段名称、字段顺序和数据类型在每次输出中完全一致。
- 不得合并多个规范性文件为一个条目。

## 5. 参考示例 (Examples)

### 示例输入

文章标题：国务院发布《数据安全管理条例》  
文章正文：2025年3月1日，国务院公布《数据安全管理条例》，该条例将于2025年6月1日起施行。此外，文章还提及《网络安全法》对数据处理活动作出一般规定。

### 示例输出

[  
{  
"全名": "数据安全管理条例",  
"发布机构": "国务院",  
"发布日期": "2025-03-01",  
"生效日期": "2025-06-01",  
"国家/地区": "中国"  
}  
]

## 6. 任务

标题：{title}

正文：{content}"""


def extract_regulations(
    segment: Dict[str, Any],
    item_guid: str,
    segment_index: int,
    conn: sqlite3.Connection
) -> List[Dict[str, Any]]:
    """
    从文章块中提取结构化法规信息
    
    Args:
        segment: 文章块字典，包含 small_title 和 content
        item_guid: 所属 item 的 guid
        segment_index: 分段索引（0-based）
        conn: 数据库连接
    
    Returns:
        法规信息列表，每个元素：
        {
            "全名": str,
            "发布机构": str | None,
            "发布日期": str | None,
            "生效日期": str | None,
            "国家/地区": str | None
        }
    """
    # 确定标题
    title = segment.get("small_title") or ""
    content = segment.get("content", "")
    
    # 截取正文（避免过长）
    content_preview = content[:6000] if len(content) > 6000 else content
    
    # 构造 prompt（使用 replace 而不是 format，避免 content 中的 {} 被误解析）
    prompt = PROMPT_TEMPLATE.replace("{title}", title).replace("{content}", content_preview)
    
    # 调用 LLM
    response = _call_llm_with_retry(prompt)
    
    # 确保 response 是字符串类型（用于日志记录）
    response_str = response if isinstance(response, str) else str(response) if response else ""
    
    # 解析 JSON
    regulations = _parse_regulations_json(response)
    
    # 记录到 llm_log_step6
    db.insert_llm_log(conn, "llm_log_step6", {
        "item_guid": item_guid,
        "segment_index": segment_index,
        "prompt": prompt,
        "response": response_str,
        "regulations_extracted": len(regulations),
    })
    
    logger.info(f"法规提取完成，提取到 {len(regulations)} 条法规")
    return regulations


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
            response = llm.call_llm(prompt)
            return response
        except Exception as e:
            logger.error(f"LLM 调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                continue
            raise
    
    return "[]"


def _parse_regulations_json(response: str) -> List[Dict[str, Any]]:
    """
    解析 LLM 返回的 JSON
    
    Args:
        response: LLM 返回的文本
    
    Returns:
        法规信息列表，解析失败返回空列表
    """
    try:
        # 确保 response 是字符串类型
        if response is None:
            logger.warning("LLM 响应为 None")
            return []
        
        # 如果 response 不是字符串，尝试转换
        if not isinstance(response, str):
            logger.warning(f"LLM 响应类型异常: {type(response)}，尝试转换")
            try:
                response = str(response)
            except Exception as e:
                logger.error(f"响应转换失败: {e}")
                return []
        
        # 尝试提取 JSON 部分
        json_str = response.strip()
        
        # 移除可能的 markdown 代码块标记
        # 处理 ```json ... ``` 和 ``` ... ``` 格式
        if "```" in json_str:
            # 使用正则表达式提取代码块内容
            code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', json_str, re.IGNORECASE)
            if code_block_match:
                json_str = code_block_match.group(1).strip()
            else:
                # 如果没有匹配到完整的代码块，尝试手动提取
                first_tick = json_str.find("```")
                if first_tick != -1:
                    after_first_tick = json_str[first_tick + 3:]
                    lines = after_first_tick.split('\n', 1)
                    if len(lines) > 1:
                        first_line = lines[0].strip().lower()
                        if first_line in ('json', ''):
                            json_str = lines[1]
                        else:
                            json_str = after_first_tick
                    else:
                        json_str = after_first_tick
                    if "```" in json_str:
                        json_str = json_str.rsplit("```", 1)[0].strip()
        
        # 尝试找到 JSON 数组的边界
        start_idx = json_str.find("[")
        end_idx = json_str.rfind("]")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = json_str[start_idx:end_idx + 1]
        else:
            # 如果没有找到数组边界，可能返回的是空值或无效格式
            logger.warning(f"未找到有效的 JSON 数组边界，响应前200字符: {response[:200]}...")
            return []
        
        # 解析 JSON
        data = json.loads(json_str)
        
        # 验证结构
        if not isinstance(data, list):
            logger.warning(f"JSON 不是数组，类型: {type(data)}")
            return []
        
        # 验证每个法规的结构
        result = []
        for reg in data:
            if not isinstance(reg, dict):
                logger.debug(f"跳过非字典元素: {type(reg)}")
                continue
            
            # 必须有"全名"字段且不为空
            full_name = reg.get("全名")
            if not full_name or not isinstance(full_name, str) or not full_name.strip():
                logger.debug(f"跳过无效法规条目: {reg}")
                continue
            
            result.append({
                "全名": str(full_name).strip(),
                "发布机构": reg.get("发布机构") if isinstance(reg.get("发布机构"), str) else None,
                "发布日期": _validate_date(reg.get("发布日期")),
                "生效日期": _validate_date(reg.get("生效日期")),
                "国家/地区": reg.get("国家/地区") if isinstance(reg.get("国家/地区"), str) else None,
            })
        
        return result
        
    except json.JSONDecodeError as e:
        logger.warning(f"JSON 解析失败: {e}, 响应: {response[:200] if response else 'None'}...")
        return []
    except KeyError as e:
        # 捕获 KeyError 并提供更详细的错误信息
        logger.error(f"JSON 字段访问错误 - KeyError: {e}，响应: {response[:200] if response else 'None'}...")
        return []
    except Exception as e:
        logger.error(f"解析异常: {type(e).__name__}: {e}")
        return []


def _validate_date(date_str: Any) -> Any:
    """
    验证日期格式是否为 YYYY-MM-DD
    
    Args:
        date_str: 日期字符串
    
    Returns:
        验证通过的日期字符串，或 None
    """
    if not date_str:
        return None
    
    date_str = str(date_str).strip()
    
    # 验证 YYYY-MM-DD 格式
    pattern = r"^\d{4}-\d{2}-\d{2}$"
    if re.match(pattern, date_str):
        return date_str
    
    logger.warning(f"日期格式无效: {date_str}")
    return None


if __name__ == "__main__":
    # 测试法规提取功能
    logging.basicConfig(level=logging.INFO)
    
    # 初始化数据库
    db.init_db()
    
    # 测试数据
    test_segment = {
        "small_title": "国务院发布《数据安全管理条例》",
        "content": """
2025年3月1日，国务院公布《数据安全管理条例》，该条例将于2025年6月1日起施行。
条例规定了数据处理者的安全保护义务，明确了数据安全事件的报告要求。
""",
    }
    
    with db.get_connection() as conn:
        regulations = extract_regulations(test_segment, "test-guid", 0, conn)
        print(f"提取到 {len(regulations)} 条法规:")
        for reg in regulations:
            print(f"--- 法规 ---")
            print(f"全名: {reg.get('全名')}")
            print(f"发布机构: {reg.get('发布机构')}")
            print(f"发布日期: {reg.get('发布日期')}")
            print(f"生效日期: {reg.get('生效日期')}")
            print(f"国家/地区: {reg.get('国家/地区')}")