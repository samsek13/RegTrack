"""
RegTracker - 法规情报自动化采集系统
CLI 入口
"""

import sys
import logging
from datetime import date, datetime

def setup_shared_logging_if_available():
    """如果在Web界面环境中运行，则使用共享的日志处理器"""
    try:
        # 尝试获取Web界面设置的共享日志管理器
        import log_manager_holder
        web_log_manager = log_manager_holder.log_manager

        # 重新配置日志系统以使用Web界面的日志处理器
        root_logger = logging.getLogger()

        # 移除现有的处理器
        for handler in root_logger.handlers[:]:
            if not isinstance(handler, type(web_log_manager.handler)):
                root_logger.removeHandler(handler)

        # 确保使用Web界面提供的日志处理器
        root_logger.addHandler(web_log_manager.handler)
        root_logger.setLevel(logging.INFO)

    except ImportError:
        # 不在Web界面环境中，使用常规的日志配置
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )


# 延迟初始化日志系统，允许后续重置
def init_logging_system():
    """初始化日志系统，可在运行时被多次调用以重置日志配置"""
    # 不要在这里立即执行日志设置，而是提供一个函数
    # 以便在适当的时候重新设置
    setup_shared_logging_if_available()


init_logging_system()  # 初始设置
logger = logging.getLogger(__name__)

import db
import backup
import pipeline
import sync
import scheduler


# 其余代码保持不变...

def print_usage():
    """打印使用说明"""
    print("""
RegTracker - 法规情报自动化采集系统

用法:
    python main.py daemon                    启动守护进程（定时任务）
    python main.py backfill YYYY-MM-DD       手动回溯到指定日期
    python main.py process <URL>            处理单篇文章链接

命令说明:
    daemon      启动后台守护进程，每日 00:15 和 12:15 自动运行
    backfill    手动触发一次性采集，处理指定日期之前的所有 RSS item
    process     手动传入单篇文章链接，跳过 RSS 采集直接处理

示例:
    python main.py daemon                    # 启动守护进程
    python main.py backfill 2026-02-26      # 回溯处理 2026-02-26 之前的内容
    python main.py process https://mp.weixin.qq.com/s/xxx  # 处理单篇文章
""")


def run_daemon():
    """启动守护进程"""
    logger.info("启动守护进程模式")

    # 初始化数据库
    db.init_db()
    logger.info("数据库初始化完成")

    # 启动调度器
    scheduler.run_scheduler()


def run_backfill(cutoff_date: date):
    """运行手动回溯任务"""
    logger.info(f"开始手动回溯任务，截止日期: {cutoff_date}")

    # 初始化数据库
    db.init_db()
    logger.info("数据库初始化完成")

    # 备份数据库
    try:
        backup_path = backup.backup_db()
        logger.info(f"数据库备份成功: {backup_path}")
    except Exception as e:
        logger.error(f"数据库备份失败: {e}")
        sys.exit(1)

    # 运行 pipeline
    try:
        pipeline.run_pipeline(cutoff_date)
    except Exception as e:
        logger.error(f"Pipeline 执行失败: {e}")

    # 同步到 Google Sheets
    try:
        sync.sync_to_sheets()
    except Exception as e:
        logger.error(f"Google Sheets 同步失败: {e}")

    logger.info("手动回溯任务完成")


def run_process_url(url: str):
    """运行手动链接处理"""
    logger.info(f"开始处理链接: {url}")

    # 初始化数据库
    db.init_db()
    logger.info("数据库初始化完成")

    # 备份数据库
    try:
        backup_path = backup.backup_db()
        logger.info(f"数据库备份成功: {backup_path}")
    except Exception as e:
        logger.error(f"数据库备份失败: {e}")
        sys.exit(1)

    # 运行 pipeline（手动链接模式）
    try:
        pipeline.run_pipeline(date.today(), manual_url=url)
    except Exception as e:
        logger.error(f"Pipeline 执行失败: {e}")

    # 同步到 Google Sheets
    try:
        sync.sync_to_sheets()
    except Exception as e:
        logger.error(f"Google Sheets 同步失败: {e}")

    logger.info("链接处理完成")


def main():
    """主入口"""
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "daemon":
        # 启动守护进程
        run_daemon()

    elif command == "backfill":
        # 手动回溯
        if len(sys.argv) < 3:
            print("错误: backfill 命令需要指定日期")
            print("用法: python main.py backfill YYYY-MM-DD")
            sys.exit(1)

        try:
            cutoff_date = datetime.strptime(sys.argv[2], "%Y-%m-%d").date()
        except ValueError:
            print(f"错误: 日期格式无效 '{sys.argv[2]}'，应为 YYYY-MM-DD")
            sys.exit(1)

        run_backfill(cutoff_date)

    elif command == "process":
        # 手动处理链接
        if len(sys.argv) < 3:
            print("错误: process 命令需要指定 URL")
            print("用法: python main.py process <URL>")
            sys.exit(1)

        url = sys.argv[2]
        run_process_url(url)

    else:
        print(f"错误: 未知命令 '{command}'")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()