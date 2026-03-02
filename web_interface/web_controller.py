from flask import Blueprint, request, jsonify, current_app
from task_manager import TaskManager
import logging

# 获取根日志记录器
logger = logging.getLogger()

bp = Blueprint('web_controller', __name__)
task_manager = TaskManager()

@bp.route('/api/start-daemon', methods=['POST'])
def start_daemon():
    logger.info("API: Start daemon called")
    result = task_manager.start_daemon()
    return jsonify(result)

@bp.route('/api/stop-daemon', methods=['POST'])
def stop_daemon():
    logger.info("API: Stop daemon called")
    result = task_manager.stop_daemon()
    return jsonify(result)

@bp.route('/api/run-backfill', methods=['POST'])
def run_backfill():
    logger.info("API: Run backfill called")
    data = request.get_json()
    date_str = data.get('date')

    # 验证日期格式
    try:
        from datetime import datetime
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"success": False, "message": "日期格式错误，请使用YYYY-MM-DD格式"})

    result = task_manager.run_backfill(date_str)
    return jsonify(result)

@bp.route('/api/run-process', methods=['POST'])
def run_process():
    logger.info("API: Run process called")
    data = request.get_json()
    url = data.get('url')

    # 添加日志
    logger.info(f"Processing URL: {url}")

    # 简单验证URL格式
    if not url or not url.startswith(('http://', 'https://')):
        logger.warning(f"Invalid URL format: {url}")
        return jsonify({"success": False, "message": "URL格式错误，请使用正确的URL格式"})

    result = task_manager.run_process(url)
    logger.info(f"Started processing for URL: {url}")
    return jsonify(result)

@bp.route('/api/status', methods=['GET'])
def get_status():
    logger.info("API: Get status called")
    status = task_manager.get_status()
    return jsonify(status)