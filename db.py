"""
数据库管理模块
负责 SQLite 连接管理和 CRUD 操作
"""

import sqlite3
import json
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from config import config


# SQL DDL 语句
DDL_RSS_SOURCES = """
CREATE TABLE IF NOT EXISTS rss_sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url         TEXT NOT NULL UNIQUE,
    name        TEXT,
    created_at  TEXT NOT NULL
);
"""

DDL_REGULATIONS = """
CREATE TABLE IF NOT EXISTS regulations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name_cn         TEXT NOT NULL,
    name_en         TEXT,
    publish_date    TEXT,
    effective_date  TEXT,
    publisher       TEXT,
    jurisdiction    TEXT,
    category        TEXT,
    source_url      TEXT,
    last_modified   TEXT NOT NULL
);
"""

DDL_REGULATIONS_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS trg_regulations_update
AFTER UPDATE ON regulations
FOR EACH ROW
BEGIN
    UPDATE regulations SET last_modified = datetime('now', 'localtime')
    WHERE id = NEW.id;
END;
"""

DDL_CACHED_ARTICLES = """
CREATE TABLE IF NOT EXISTS cached_articles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_guid   TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    content_md  TEXT NOT NULL,
    source_url  TEXT,
    cached_at   TEXT NOT NULL
);
"""

DDL_PROCESS_HISTORY = """
CREATE TABLE IF NOT EXISTS process_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_guid       TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    step2_result    TEXT NOT NULL,
    processed_at    TEXT NOT NULL
);
"""

DDL_LLM_LOG_STEP2 = """
CREATE TABLE IF NOT EXISTS llm_log_step2 (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_guid   TEXT NOT NULL,
    title       TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    response    TEXT NOT NULL,
    result      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""

DDL_LLM_LOG_STEP4 = """
CREATE TABLE IF NOT EXISTS llm_log_step4 (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_guid   TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    response    TEXT NOT NULL,
    result      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""

DDL_LLM_LOG_STEP5 = """
CREATE TABLE IF NOT EXISTS llm_log_step5 (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_guid       TEXT NOT NULL,
    prompt          TEXT NOT NULL,
    response        TEXT NOT NULL,
    segment_count   INTEGER,
    created_at      TEXT NOT NULL
);
"""

DDL_LLM_LOG_STEP6 = """
CREATE TABLE IF NOT EXISTS llm_log_step6 (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    item_guid           TEXT NOT NULL,
    segment_index       INTEGER NOT NULL,
    prompt              TEXT NOT NULL,
    response            TEXT NOT NULL,
    regulations_extracted INTEGER,
    created_at          TEXT NOT NULL
);
"""

DDL_LLM_LOG_STEP7A = """
CREATE TABLE IF NOT EXISTS llm_log_step7a (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    new_reg_name        TEXT NOT NULL,
    existing_reg_batch  TEXT NOT NULL,
    rag_query           TEXT NOT NULL,
    rag_result          TEXT NOT NULL,
    llm_prompt          TEXT NOT NULL,
    llm_response        TEXT NOT NULL,
    is_duplicate        INTEGER NOT NULL,
    created_at          TEXT NOT NULL
);
"""

DDL_LLM_LOG_STEP8 = """
CREATE TABLE IF NOT EXISTS llm_log_step8 (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    regulation_id   INTEGER NOT NULL,
    field_name      TEXT NOT NULL,
    rag_query       TEXT,
    rag_result      TEXT,
    llm_prompt      TEXT NOT NULL,
    llm_response    TEXT NOT NULL,
    filled_value    TEXT,
    created_at      TEXT NOT NULL
);
"""

DDL_LLM_LOG_STEP9 = """
CREATE TABLE IF NOT EXISTS llm_log_step9 (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    regulation_id   INTEGER NOT NULL,
    rag_query       TEXT NOT NULL,
    rag_result      TEXT NOT NULL,
    llm_prompt      TEXT NOT NULL,
    llm_response    TEXT NOT NULL,
    category        TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
"""


@contextmanager
def get_connection() -> sqlite3.Connection:
    """
    获取数据库连接（上下文管理器）
    启用 WAL 模式和外键约束，自动提交/回滚
    """
    conn = sqlite3.connect(config.db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    # 启用 row_factory 以便结果按列名访问
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """
    初始化数据库：创建所有表和触发器
    在应用启动时调用一次
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 创建所有表
        cursor.execute(DDL_RSS_SOURCES)
        cursor.execute(DDL_REGULATIONS)
        cursor.execute(DDL_CACHED_ARTICLES)
        cursor.execute(DDL_PROCESS_HISTORY)
        cursor.execute(DDL_LLM_LOG_STEP2)
        cursor.execute(DDL_LLM_LOG_STEP4)
        cursor.execute(DDL_LLM_LOG_STEP5)
        cursor.execute(DDL_LLM_LOG_STEP6)
        cursor.execute(DDL_LLM_LOG_STEP7A)
        cursor.execute(DDL_LLM_LOG_STEP8)
        cursor.execute(DDL_LLM_LOG_STEP9)
        
        # 创建触发器（需先删除已存在的触发器再创建）
        cursor.execute("DROP TRIGGER IF EXISTS trg_regulations_update;")
        cursor.execute(DDL_REGULATIONS_TRIGGER)
        
        # 如果 rss_sources 表为空，插入默认源
        cursor.execute("SELECT COUNT(*) FROM rss_sources;")
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO rss_sources (url, name, created_at) VALUES (?, ?, ?);",
                (config.rss_feed_url, "Default RSS Feed", datetime.now().isoformat())
            )


# ==================== rss_sources 表操作 ====================

def insert_rss_source(conn: sqlite3.Connection, url: str, name: Optional[str] = None) -> int:
    """插入 RSS 源"""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO rss_sources (url, name, created_at) VALUES (?, ?, ?);",
        (url, name, datetime.now().isoformat())
    )
    return cursor.lastrowid


def get_all_rss_sources(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """获取所有 RSS 源"""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM rss_sources;")
    return [dict(row) for row in cursor.fetchall()]


# ==================== regulations 表操作 ====================

def insert_regulation(conn: sqlite3.Connection, reg: Dict[str, Any], source_url: str) -> int:
    """
    插入法规记录
    
    Args:
        conn: 数据库连接
        reg: 法规信息字典，包含 name_cn, name_en, publish_date, effective_date, publisher, jurisdiction
        source_url: 来源链接
    
    Returns:
        新记录的 id
    """
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(
        """INSERT INTO regulations 
           (name_cn, name_en, publish_date, effective_date, publisher, jurisdiction, category, source_url, last_modified)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);""",
        (
            reg.get("全名") or reg.get("name_cn"),
            reg.get("name_en"),
            reg.get("发布日期") or reg.get("publish_date"),
            reg.get("生效日期") or reg.get("effective_date"),
            reg.get("发布机构") or reg.get("publisher"),
            reg.get("国家/地区") or reg.get("jurisdiction"),
            reg.get("category"),
            source_url,
            now
        )
    )
    return cursor.lastrowid


def get_all_regulations(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """获取所有法规记录"""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM regulations ORDER BY id;")
    return [dict(row) for row in cursor.fetchall()]


def get_regulations_with_missing_fields(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """获取有缺失字段的法规记录（name_en, publish_date, effective_date, publisher, jurisdiction 任一为空）"""
    cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM regulations 
           WHERE name_en IS NULL 
              OR publish_date IS NULL 
              OR effective_date IS NULL 
              OR publisher IS NULL 
              OR jurisdiction IS NULL;"""
    )
    return [dict(row) for row in cursor.fetchall()]


def get_regulations_without_category(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """获取未分类的法规记录（category 为 NULL）"""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM regulations WHERE category IS NULL;")
    return [dict(row) for row in cursor.fetchall()]


def update_regulation_field(conn: sqlite3.Connection, reg_id: int, field: str, value: str):
    """
    更新法规记录的单个字段
    注意：触发器会自动更新 last_modified
    """
    # 验证字段名，防止 SQL 注入
    allowed_fields = {"name_en", "publish_date", "effective_date", "publisher", "jurisdiction", "category"}
    if field not in allowed_fields:
        raise ValueError(f"不允许更新的字段: {field}")
    
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE regulations SET {field} = ? WHERE id = ?;",
        (value, reg_id)
    )


# ==================== cached_articles 表操作 ====================

def insert_cached_article(conn: sqlite3.Connection, item_guid: str, title: str, content_md: str, source_url: Optional[str] = None) -> int:
    """插入或更新缓存文章"""
    cursor = conn.cursor()
    # 使用 INSERT OR REPLACE 处理重复 GUID 的情况
    cursor.execute(
        """INSERT OR REPLACE INTO cached_articles (item_guid, title, content_md, source_url, cached_at)
           VALUES (?, ?, ?, ?, ?);""",
        (item_guid, title, content_md, source_url, datetime.now().isoformat())
    )
    return cursor.lastrowid


def get_cached_article_by_guid(conn: sqlite3.Connection, item_guid: str) -> Optional[Dict[str, Any]]:
    """根据 guid 获取缓存文章"""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cached_articles WHERE item_guid = ?;", (item_guid,))
    row = cursor.fetchone()
    return dict(row) if row else None


# ==================== process_history 表操作 ====================

def insert_process_history(conn: sqlite3.Connection, guid: str, title: str, result: str):
    """插入处理历史记录"""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO process_history (item_guid, title, step2_result, processed_at) VALUES (?, ?, ?, ?);",
        (guid, title, result, datetime.now().isoformat())
    )


def is_guid_processed(conn: sqlite3.Connection, guid: str) -> bool:
    """检查 guid 是否已处理过"""
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM process_history WHERE item_guid = ?;", (guid,))
    return cursor.fetchone() is not None


# ==================== LLM 日志表操作 ====================

def insert_llm_log(conn: sqlite3.Connection, table: str, data: Dict[str, Any]):
    """
    通用 LLM 日志插入函数
    
    Args:
        conn: 数据库连接
        table: 日志表名（llm_log_step2, llm_log_step4 等）
        data: 日志数据字典
    """
    # 添加时间戳
    data["created_at"] = datetime.now().isoformat()
    
    # 根据表名构建 SQL
    table_columns = {
        "llm_log_step2": ["item_guid", "title", "prompt", "response", "result", "created_at"],
        "llm_log_step4": ["item_guid", "prompt", "response", "result", "created_at"],
        "llm_log_step5": ["item_guid", "prompt", "response", "segment_count", "created_at"],
        "llm_log_step6": ["item_guid", "segment_index", "prompt", "response", "regulations_extracted", "created_at"],
        "llm_log_step7a": ["new_reg_name", "existing_reg_batch", "rag_query", "rag_result", "llm_prompt", "llm_response", "is_duplicate", "created_at"],
        "llm_log_step8": ["regulation_id", "field_name", "rag_query", "rag_result", "llm_prompt", "llm_response", "filled_value", "created_at"],
        "llm_log_step9": ["regulation_id", "rag_query", "rag_result", "llm_prompt", "llm_response", "category", "created_at"],
    }
    
    if table not in table_columns:
        raise ValueError(f"未知的日志表: {table}")
    
    columns = table_columns[table]
    placeholders = ", ".join(["?" for _ in columns])
    values = [data.get(col) for col in columns]
    
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders});"
    cursor = conn.cursor()
    cursor.execute(sql, values)


# ==================== 数据导出操作 ====================

def get_table_data_for_sync(conn: sqlite3.Connection, table_name: str) -> tuple:
    """
    获取指定表的所有数据，用于同步到 Google Sheets
    
    Returns:
        (headers, rows) - 表头列表和数据行列表
    """
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name};")
    rows = cursor.fetchall()
    
    if rows:
        headers = list(rows[0].keys())
        data = [list(row) for row in rows]
        return headers, data
    else:
        # 表为空，返回空表头
        return [], []