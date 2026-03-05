"""
从 Google Sheets 反向同步数据到本地数据库
仅同步 regulations 表

使用方式:
    python sync_from_sheets.py
"""

import logging
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import os

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 加载 .env
load_dotenv()

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.resolve()

# 配置
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "./service_account.json")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
DB_PATH = os.environ.get("DB_PATH", "./data/regtracker.db")
BACKUP_DIR = os.environ.get("BACKUP_DIR", "./backups")

# Google Sheets API 范围
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]

# regulations 表的字段列表（与 db.py 中 DDL_REGULATIONS 一致）
REGULATIONS_COLUMNS = [
    "id",
    "name_cn",
    "name_en",
    "publish_date",
    "effective_date",
    "publisher",
    "jurisdiction",
    "category",
    "source_url",
    "last_modified",
    "summary",
]


def _resolve_path(path_str: str) -> str:
    """将相对路径转换为绝对路径"""
    path = Path(path_str)
    if path.is_absolute():
        return str(path)
    return str(PROJECT_ROOT / path)


def _validate_headers(headers: List[str]) -> None:
    """
    校验 Google Sheets 表头与数据库字段名是否完全一致

    Args:
        headers: 从 Sheets 读取的表头列表

    Raises:
        ValueError: 如果表头不一致
    """
    expected = REGULATIONS_COLUMNS
    if headers != expected:
        # 找出差异
        missing = [h for h in expected if h not in headers]
        extra = [h for h in headers if h not in expected]
        wrong_order = expected != headers and not missing and not extra

        error_parts = ["表头与数据库字段名不一致，停止同步:"]
        if missing:
            error_parts.append(f"  缺少字段: {missing}")
        if extra:
            error_parts.append(f"  多余字段: {extra}")
        if wrong_order:
            error_parts.append(f"  字段顺序不一致")
            error_parts.append(f"  期望顺序: {expected}")
            error_parts.append(f"  实际顺序: {headers}")

        logger.error("\n".join(error_parts))
        raise ValueError("\n".join(error_parts))

    logger.info("表头校验通过")


def _get_gspread_client() -> gspread.Client:
    """获取 gspread 客户端（只读权限）"""
    service_account_path = _resolve_path(GOOGLE_SERVICE_ACCOUNT_JSON)
    credentials = Credentials.from_service_account_file(
        service_account_path,
        scopes=SCOPES
    )
    return gspread.authorize(credentials)


def _open_spreadsheet(client: gspread.Client) -> gspread.Spreadsheet:
    """打开 Google Spreadsheet"""
    if not GOOGLE_SHEET_ID:
        raise ValueError("GOOGLE_SHEET_ID 未配置，请检查 .env 文件")

    try:
        return client.open_by_key(GOOGLE_SHEET_ID)
    except gspread.SpreadsheetNotFound:
        logger.warning("通过 ID 未找到 spreadsheet，尝试通过名称打开...")
        return client.open(GOOGLE_SHEET_ID)


def fetch_regulations_from_sheets() -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    从 Google Sheets 读取 regulations 数据

    Returns:
        (headers, records) - 表头列表和法规记录列表
    """
    logger.info("正在从 Google Sheets 读取 regulations 数据...")

    client = _get_gspread_client()
    spreadsheet = _open_spreadsheet(client)

    try:
        worksheet = spreadsheet.worksheet("regulations")
    except gspread.WorksheetNotFound:
        raise ValueError("Google Sheets 中未找到 'regulations' worksheet")

    # 读取所有数据
    all_values = worksheet.get_all_values()

    if not all_values:
        logger.warning("regulations worksheet 为空")
        return [], []

    # 第一行是表头
    headers = all_values[0]
    data_rows = all_values[1:]

    if not data_rows:
        logger.info("regulations worksheet 无数据行")
        return headers, []

    # >>> 新增：校验表头与数据库字段名是否一致
    _validate_headers(headers)

    # 转换为字典列表
    records = []
    for row in data_rows:
        record = {}
        for i, header in enumerate(headers):
            if i < len(row):
                record[header] = row[i] if row[i] else None
            else:
                record[header] = None
        records.append(record)

    logger.info(f"从 Google Sheets 读取到 {len(records)} 条记录")
    return headers, records


def _backup_db() -> str:
    """
    备份当前数据库文件到 /backups 目录

    Returns:
        备份文件的完整路径
    """
    db_path = _resolve_path(DB_PATH)
    backup_dir = _resolve_path(BACKUP_DIR)

    # 确保 backup 目录存在
    Path(backup_dir).mkdir(parents=True, exist_ok=True)

    # 生成备份文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"regtracker_backup_{timestamp}.db"
    backup_path = Path(backup_dir) / backup_filename

    # 复制文件
    shutil.copy2(db_path, backup_path)

    logger.info(f"数据库已备份到: {backup_path}")
    return str(backup_path)


def _get_db_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    db_path = _resolve_path(DB_PATH)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def sync_to_db(records: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    将从 Sheets 读取的数据同步到本地数据库

    同步策略（全面覆盖）:
    1. 先备份当前数据库
    2. 清空 regulations 表
    3. 插入所有 Sheets 数据

    Args:
        records: 从 Sheets 读取的法规记录列表

    Returns:
        统计信息: {"inserted": n}
    """
    stats = {"inserted": 0}

    # 备份数据库
    _backup_db()

    conn = _get_db_connection()
    try:
        cursor = conn.cursor()

        # 清空表
        cursor.execute("DELETE FROM regulations")
        logger.info("已清空 regulations 表")

        # 插入所有数据
        for record in records:
            name_cn = record.get("name_cn")
            name_en = record.get("name_en")
            publish_date = record.get("publish_date")
            effective_date = record.get("effective_date")
            publisher = record.get("publisher")
            jurisdiction = record.get("jurisdiction")
            category = record.get("category")
            source_url = record.get("source_url")
            summary = record.get("summary")
            last_modified = record.get("last_modified") or datetime.now().isoformat()

            # name_cn 为必填
            if not name_cn:
                logger.warning(f"跳过无 name_cn 的记录: {record}")
                continue

            cursor.execute("""
                INSERT INTO regulations (
                    name_cn, name_en, publish_date, effective_date,
                    publisher, jurisdiction, category, source_url,
                    summary, last_modified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name_cn, name_en, publish_date, effective_date,
                publisher, jurisdiction, category, source_url,
                summary, last_modified
            ))
            stats["inserted"] += 1

        conn.commit()
        logger.info(f"同步完成: 插入 {stats['inserted']} 条记录")

    except Exception as e:
        conn.rollback()
        logger.error(f"同步失败: {e}")
        raise
    finally:
        conn.close()

    return stats


def main():
    """主入口"""
    logger.info("=== 开始从 Google Sheets 同步到本地数据库 ===")

    try:
        # 1. 从 Google Sheets 读取数据
        headers, records = fetch_regulations_from_sheets()

        # 2. 同步到数据库
        stats = sync_to_db(records)

        # 3. 输出统计
        logger.info(f"同步结果: {stats}")

    except Exception as e:
        logger.error(f"同步过程出错: {e}")
        raise

    logger.info("=== 同步完成 ===")


if __name__ == "__main__":
    main()