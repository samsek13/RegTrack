"""
定时调度模块
使用 APScheduler 管理定时任务
"""

import logging
from datetime import date, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

import db
import backup
import pipeline
import sync

# 配置日志
logger = logging.getLogger(__name__)


def scheduled_job():
    """
    定时任务：备份 -> 运行 pipeline -> 同步到 Google Sheets
    """
    logger.info("=" * 60)
    logger.info("开始执行定时任务")
    logger.info("=" * 60)
    
    try:
        # 1. 备份数据库
        logger.info("步骤 1: 备份数据库")
        try:
            backup_path = backup.backup_db()
            logger.info(f"数据库备份成功: {backup_path}")
        except Exception as e:
            logger.error(f"数据库备份失败: {e}")
            raise  # 备份失败则终止
        
        # 2. 运行 pipeline（截止日期为昨天）
        logger.info("步骤 2: 运行 pipeline")
        cutoff_date = date.today() - timedelta(days=1)
        try:
            pipeline.run_pipeline(cutoff_date)
        except Exception as e:
            logger.error(f"Pipeline 执行失败: {e}")
            # pipeline 失败不阻塞，继续执行同步
        
        # 3. 同步到 Google Sheets
        logger.info("步骤 3: 同步到 Google Sheets")
        try:
            sync.sync_to_sheets()
        except Exception as e:
            logger.error(f"Google Sheets 同步失败: {e}")
            # 同步失败不阻塞
        
        logger.info("=" * 60)
        logger.info("定时任务执行完成")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"定时任务执行失败: {e}")


def run_scheduler():
    """
    启动调度器（阻塞式）
    
    定时任务运行时间：
    - 每日 00:15
    - 每日 12:15
    """
    scheduler = BlockingScheduler()
    
    # 注册定时任务：每日 00:15 和 12:15 执行
    scheduler.add_job(
        scheduled_job,
        CronTrigger(hour="0,12", minute=15),
        id="regtracker_scheduled_job",
        name="RegTracker 定时任务",
        misfire_grace_time=60,  # 允许任务迟到60秒内仍执行
    )
    
    logger.info("调度器启动，定时任务运行时间：每日 00:15 和 12:15")
    logger.info("按 Ctrl+C 停止调度器")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("调度器停止")
        scheduler.shutdown()


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # 初始化数据库
    db.init_db()
    
    # 启动调度器
    run_scheduler()