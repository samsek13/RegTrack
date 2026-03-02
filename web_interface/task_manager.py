import threading
import subprocess
import sys
import os
from pathlib import Path
import logging

# 导入全局日志管理器
from log_handler import get_global_log_manager

class TaskManager:
    def __init__(self):
        # 设置Python路径，确保能找到main模块
        # main.py 在 regtracker 目录下，即 web_interface 的父目录
        regtracker_path = str(Path(__file__).parent.parent)
        sys.path.insert(0, regtracker_path)

        self.daemon_process = None
        self.current_task = None
        self.task_lock = threading.Lock()

    def start_daemon(self):
        """启动守护进程"""
        with self.task_lock:
            if self.daemon_process and self.daemon_process.poll() is None:
                return {"success": False, "message": "守护进程已在运行"}

            try:
                # 使用subprocess启动守护进程
                cmd = [sys.executable, "main.py", "daemon"]
                regtracker_dir = Path(__file__).parent.parent
                self.daemon_process = subprocess.Popen(
                    cmd,
                    cwd=regtracker_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                return {"success": True, "message": "守护进程已启动"}
            except Exception as e:
                return {"success": False, "message": f"启动守护进程失败: {str(e)}"}

    def stop_daemon(self):
        """停止守护进程"""
        with self.task_lock:
            if self.daemon_process and self.daemon_process.poll() is None:
                self.daemon_process.terminate()
                self.daemon_process.wait(timeout=5)  # 等待最多5秒
                self.daemon_process = None
                return {"success": True, "message": "守护进程已停止"}
            else:
                return {"success": False, "message": "守护进程未在运行"}

    def run_backfill(self, cutoff_date):
        """运行回溯任务"""
        if self.current_task is not None:
            return {"success": False, "message": "有任务正在执行，请等待完成"}

        def execute():
            try:
                # 通过导入模块执行回溯任务
                import sys
                from pathlib import Path
                import logging
                # main.py 在 web_interface 的父目录下
                regtracker_path = str(Path(__file__).parent.parent)
                if regtracker_path not in sys.path:
                    sys.path.insert(0, regtracker_path)

                # 导入全局日志管理器并设置为当前线程使用的日志管理器
                global_log_manager = get_global_log_manager()

                # 直接使用全局日志管理器的处理器
                if global_log_manager:
                    # 获取当前线程的根日志记录器
                    root_logger = logging.getLogger()

                    # 移除可能已经存在的LogCaptureHandler处理器
                    handlers_to_remove = []
                    for handler in root_logger.handlers:
                        if type(handler).__name__ == 'LogCaptureHandler':
                            handlers_to_remove.append(handler)

                    for handler in handlers_to_remove:
                        root_logger.removeHandler(handler)

                    # 添加全局日志管理器的处理器
                    root_logger.addHandler(global_log_manager.handler)
                    root_logger.setLevel(logging.INFO)

                    # 创建一个模块来持有日志管理器的引用
                    import importlib
                    import sys
                    try:
                        log_manager_holder = importlib.import_module('log_manager_holder')
                    except ImportError:
                        # 如果模块不存在，创建一个新的
                        import types
                        log_manager_holder = types.ModuleType('log_manager_holder')
                        sys.modules['log_manager_holder'] = log_manager_holder

                    # 设置日志管理器
                    log_manager_holder.log_manager = global_log_manager

                import main
                from datetime import datetime
                cutoff = datetime.strptime(cutoff_date, "%Y-%m-%d").date()

                # 确保使用正确的日志配置
                main.run_backfill(cutoff)
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.error(f"回溯任务执行失败: {e}")
            finally:
                self.current_task = None

        self.current_task = threading.Thread(target=execute)
        self.current_task.start()
        return {"success": True, "message": f"回溯任务已启动，截止日期: {cutoff_date}"}

    def run_process(self, url):
        """运行链接处理任务"""
        if self.current_task is not None:
            return {"success": False, "message": "有任务正在执行，请等待完成"}

        def execute():
            try:
                # 通过导入模块执行链接处理
                import sys
                from pathlib import Path
                import logging
                # main.py 在 web_interface 的父目录下
                regtracker_path = str(Path(__file__).parent.parent)
                if regtracker_path not in sys.path:
                    sys.path.insert(0, regtracker_path)

                # 导入全局日志管理器并设置为当前线程使用的日志管理器
                global_log_manager = get_global_log_manager()

                # 直接使用全局日志管理器的处理器
                if global_log_manager:
                    # 获取当前线程的根日志记录器
                    root_logger = logging.getLogger()

                    # 移除可能已经存在的LogCaptureHandler处理器
                    handlers_to_remove = []
                    for handler in root_logger.handlers:
                        if type(handler).__name__ == 'LogCaptureHandler':
                            handlers_to_remove.append(handler)

                    for handler in handlers_to_remove:
                        root_logger.removeHandler(handler)

                    # 添加全局日志管理器的处理器
                    root_logger.addHandler(global_log_manager.handler)
                    root_logger.setLevel(logging.INFO)

                    # 创建一个模块来持有日志管理器的引用
                    import importlib
                    import sys
                    try:
                        log_manager_holder = importlib.import_module('log_manager_holder')
                    except ImportError:
                        # 如果模块不存在，创建一个新的
                        import types
                        log_manager_holder = types.ModuleType('log_manager_holder')
                        sys.modules['log_manager_holder'] = log_manager_holder

                    # 设置日志管理器
                    log_manager_holder.log_manager = global_log_manager

                import main
                main.run_process_url(url)
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.error(f"链接处理任务执行失败: {e}")
            finally:
                self.current_task = None

        self.current_task = threading.Thread(target=execute)
        self.current_task.start()
        return {"success": True, "message": f"链接处理任务已启动，URL: {url}"}

    def get_status(self):
        """获取系统状态"""
        daemon_running = (self.daemon_process is not None and
                         self.daemon_process.poll() is None)
        task_running = self.current_task is not None

        return {
            "daemon_running": daemon_running,
            "task_running": task_running,
            "current_task": self.current_task.__class__.__name__ if task_running else None
        }