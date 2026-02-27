"""
Google Sheets 同步模块
将数据库内容同步到 Google Sheets
"""

import logging
from typing import List, Tuple

import gspread
from google.oauth2.service_account import Credentials

import db
from config import config

# 配置日志
logger = logging.getLogger(__name__)

# 需要同步的表列表（排除 rss_sources 和 process_history）
TABLES_TO_SYNC = [
    "regulations",
    "cached_articles",
    "llm_log_step2",
    "llm_log_step4",
    "llm_log_step5",
    "llm_log_step6",
    "llm_log_step7a",
    "llm_log_step8",
    "llm_log_step9",
]

# Google Sheets API 范围
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

# Google Sheets 单单元格最大字符数限制
MAX_CELL_CHARS = 50000


def sync_to_sheets():
    """
    将数据库内容同步到 Google Sheets
    
    全量覆盖策略：每次同步前清空目标 sheet 的数据区（保留表头），再写入当前数据库全量数据
    """
    logger.info("开始同步到 Google Sheets")
    
    try:
        # 认证并获取客户端
        client = _get_gspread_client()
        
        # 打开目标 spreadsheet
        # 尝试通过 key (ID) 打开，如果失败则尝试通过名称打开
        spreadsheet = _open_spreadsheet(client, config.google_sheet_id)
        logger.info(f"成功打开 spreadsheet: {spreadsheet.title}")
        
        # 同步每张表
        with db.get_connection() as conn:
            for table_name in TABLES_TO_SYNC:
                try:
                    _sync_table(conn, spreadsheet, table_name)
                except Exception as e:
                    logger.error(f"同步表 {table_name} 失败: {e}")
                    continue
        
        logger.info("Google Sheets 同步完成")
        
    except Exception as e:
        logger.error(f"Google Sheets 同步失败: {e}")
        # 同步失败不影响本地数据库，仅记录日志


def _open_spreadsheet(client: gspread.Client, sheet_id_or_name: str):
    """
    打开 Google Spreadsheet
    
    首先尝试通过 key (ID) 打开，如果失败（404），则尝试通过名称打开。
    如果名称也失败，则抛出异常并提供详细的错误信息。
    
    Args:
        client: gspread 客户端
        sheet_id_or_name: Spreadsheet ID 或名称
    
    Returns:
        Spreadsheet 对象
    
    Raises:
        Exception: 当无法打开 spreadsheet 时
    """
    # 首先尝试通过 key (ID) 打开
    try:
        spreadsheet = client.open_by_key(sheet_id_or_name)
        logger.info(f"通过 ID 成功打开 spreadsheet")
        return spreadsheet
    except gspread.SpreadsheetNotFound:
        logger.warning(f"通过 ID 未找到 spreadsheet，尝试通过名称打开...")
    except Exception as e:
        logger.warning(f"通过 ID 打开失败: {e}，尝试通过名称打开...")
    
    # 尝试通过名称打开
    try:
        spreadsheet = client.open(sheet_id_or_name)
        logger.info(f"通过名称成功打开 spreadsheet")
        return spreadsheet
    except gspread.SpreadsheetNotFound:
        error_msg = (
            f"未找到名为 '{sheet_id_or_name}' 的 spreadsheet。\n"
            f"请确保：\n"
            f"1. Spreadsheet 名称拼写正确\n"
            f"2. Service Account ({config.google_service_account_json}) 有权限访问该 spreadsheet\n"
            f"3. 或者使用 Spreadsheet ID 代替名称（推荐）\n"
            f"   Spreadsheet ID 可以从 URL 中获取: https://docs.google.com/spreadsheets/d/{{SPREADSHEET_ID}}/edit"
        )
        logger.error(error_msg)
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"通过名称打开 spreadsheet 失败: {e}"
        logger.error(error_msg)
        raise Exception(error_msg)


def _get_gspread_client() -> gspread.Client:
    """
    获取 gspread 客户端
    
    Returns:
        认证后的 gspread 客户端
    """
    # 加载 Service Account 凭证
    credentials = Credentials.from_service_account_file(
        config.google_service_account_json,
        scopes=SCOPES
    )
    
    # 创建客户端
    client = gspread.authorize(credentials)
    return client


def _sync_table(conn, spreadsheet, table_name: str):
    """
    同步单张表到 Google Sheets
    
    Args:
        conn: 数据库连接
        spreadsheet: gspread Spreadsheet 对象
        table_name: 表名
    """
    logger.info(f"同步表: {table_name}")
    
    # 从数据库读取数据
    headers, rows = db.get_table_data_for_sync(conn, table_name)
    
    # 获取或创建 worksheet
    try:
        worksheet = spreadsheet.worksheet(table_name)
        logger.info(f"找到已存在的 worksheet: {table_name}")
    except gspread.WorksheetNotFound:
        # 创建新的 worksheet
        worksheet = spreadsheet.add_worksheet(
            title=table_name,
            rows=1000,
            cols=26
        )
        logger.info(f"创建新 worksheet: {table_name}")
    
    # 清空现有内容
    worksheet.clear()
    logger.info(f"清空 worksheet: {table_name}")
    
    # 写入数据
    if headers and rows:
        # 写入表头
        worksheet.append_row(headers)
        
        # 截断超长单元格内容以符合 Google Sheets 限制
        truncated_rows = _truncate_cell_values(rows, MAX_CELL_CHARS)
        
        # 写入数据行
        if truncated_rows:
            worksheet.append_rows(truncated_rows)
            logger.info(f"写入 {len(truncated_rows)} 行数据到 {table_name}")
    else:
        logger.info(f"表 {table_name} 为空，仅清空")


def _truncate_cell_values(rows: List[List], max_chars: int) -> List[List]:
    """
    截断每行中超过最大字符数的单元格值
    
    Args:
        rows: 数据行列表
        max_chars: 单个单元格最大字符数
    
    Returns:
        处理后的数据行列表
    """
    truncated_rows = []
    for row in rows:
        truncated_row = []
        for cell in row:
            if isinstance(cell, str) and len(cell) > max_chars:
                truncated_row.append(cell[:max_chars])
            else:
                truncated_row.append(cell)
        truncated_rows.append(truncated_row)
    return truncated_rows


if __name__ == "__main__":
    # 测试同步功能
    logging.basicConfig(level=logging.INFO)
    
    # 初始化数据库
    db.init_db()
    
    # 测试同步
    sync_to_sheets()