"""
配置管理模块
从 .env 文件加载并验证所有配置项
"""

import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 获取项目根目录（config.py 所在目录）
PROJECT_ROOT = Path(__file__).parent.resolve()


def _resolve_path(path_str: str) -> str:
    """
    将相对路径转换为绝对路径
    如果是相对路径，则基于项目根目录解析
    """
    path = Path(path_str)
    if path.is_absolute():
        return str(path)
    else:
        return str(PROJECT_ROOT / path)


@dataclass(frozen=True)
class Config:
    """
    不可变的配置对象，包含应用所需的所有配置项
    """
    # SiliconFlow API 配置
    siliconflow_api_key: str
    siliconflow_api_base: str
    siliconflow_model: str  # 保留此字段作为默认模型，与 rag.py 兼容
    
    # Tavily API 配置
    tavily_api_key: str
    
    # Google Sheets 配置
    google_service_account_json: str
    google_sheet_id: str
    
    # 数据库配置
    db_path: str
    backup_dir: str
    
    # RSS 配置
    rss_feed_url: str
    
    # Per-step LLM 模型配置
    llm_model_step2:   str = ""
    llm_model_step4:   str = ""
    llm_model_step5:   str = ""
    llm_model_step6:   str = ""
    llm_model_step7a:  str = ""
    llm_model_step8:   str = ""  # 补充遗漏的 step8
    llm_model_step9:   str = ""
    llm_model_summary: str = ""


def _get_required_env(key: str) -> str:
    """
    获取必需的环境变量，如果缺失则抛出异常
    """
    value = os.environ.get(key)
    if not value:
        raise ValueError(f"缺少必填配置: {key}")
    return value


def _get_optional_env(key: str, default: str) -> str:
    """
    获取可选的环境变量，如果缺失则使用默认值
    """
    return os.environ.get(key, default)


# 创建全局配置实例
config = Config(
    # SiliconFlow API 配置
    siliconflow_api_key=_get_required_env("SILICONFLOW_API_KEY"),
    siliconflow_api_base=_get_optional_env("SILICONFLOW_API_BASE", "https://api.siliconflow.cn/v1"),
    siliconflow_model=_get_optional_env("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V3"),

    # Tavily API 配置
    tavily_api_key=_get_required_env("TAVILY_API_KEY"),

    # Google Sheets 配置 - 使用绝对路径
    google_service_account_json=_resolve_path(_get_required_env("GOOGLE_SERVICE_ACCOUNT_JSON")),
    google_sheet_id=_get_required_env("GOOGLE_SHEET_ID"),

    # 数据库配置 - 使用绝对路径
    db_path=_resolve_path(_get_optional_env("DB_PATH", "./data/regtracker.db")),
    backup_dir=_resolve_path(_get_optional_env("BACKUP_DIR", "./backups")),

    # RSS 配置
    rss_feed_url=_get_optional_env("RSS_FEED_URL", "http://localhost:8001/feed/all.rss"),

    # Per-step LLM 模型配置
    llm_model_step2   = os.environ.get("LLM_MODEL_STEP2", ""),
    llm_model_step4   = os.environ.get("LLM_MODEL_STEP4", ""),
    llm_model_step5   = os.environ.get("LLM_MODEL_STEP5", ""),
    llm_model_step6   = os.environ.get("LLM_MODEL_STEP6", ""),
    llm_model_step7a  = os.environ.get("LLM_MODEL_STEP7A", ""),
    llm_model_step8   = os.environ.get("LLM_MODEL_STEP8", ""),  # 补充遗漏的 step8
    llm_model_step9   = os.environ.get("LLM_MODEL_STEP9", ""),
    llm_model_summary = os.environ.get("LLM_MODEL_SUMMARY", ""),
)
