import io
import logging
import threading
import os
from datetime import datetime
from flask_socketio import SocketIO

# 全局变量用于存储日志管理器实例
_global_log_manager_instance = None

class LogCaptureHandler(logging.Handler):
    def __init__(self, socketio, log_dir=None):
        super().__init__()
        self.socketio = socketio
        self.level = logging.INFO
        self.log_buffer = []
        self.buffer_size = 1000  # 保留最近1000条日志

        # 设置日志文件存储
        if log_dir:
            self.log_dir = log_dir
            os.makedirs(log_dir, exist_ok=True)
        else:
            self.log_dir = './logs'
            os.makedirs(self.log_dir, exist_ok=True)

        # 创建日志文件处理器
        self.file_handler = logging.FileHandler(
            os.path.join(self.log_dir, f"regtracker_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
            encoding='utf-8'
        )
        self.file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.file_handler.setFormatter(self.file_formatter)

    def emit(self, record):
        # 格式化日志消息
        log_entry = self.format(record)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_log = f"[{timestamp}] {log_entry}"

        # 添加到缓冲区
        self.log_buffer.append(formatted_log)
        if len(self.log_buffer) > self.buffer_size:
            self.log_buffer.pop(0)  # 移除最旧的日志

        # 写入文件
        try:
            self.file_handler.emit(record)
        except Exception:
            pass  # 避免文件写入错误影响应用

        # 通过Socket.IO发送到前端
        try:
            # 直接在当前线程发送，Flask-SocketIO 5.x 支持后台线程直接调用
            self.socketio.emit('log_update', {'log': formatted_log})
        except Exception as e:
            # 防止Socket.IO异常影响应用，但也记录错误
            print(f"Socket.IO emit error: {e}")

    def get_log_content(self, max_lines=1000):
        """获取日志内容用于下载"""
        recent_logs = self.log_buffer[-max_lines:] if len(self.log_buffer) >= max_lines else self.log_buffer.copy()
        return '\n'.join(recent_logs)


class LogManager:
    def __init__(self, socketio, log_dir=None):
        global _global_log_manager_instance
        self.socketio = socketio
        self.handler = LogCaptureHandler(socketio, log_dir)
        self.handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))

        # 设置为全局实例
        _global_log_manager_instance = self

    def setup_logging(self):
        """设置日志捕获"""
        # 获取根日志记录器并添加我们的处理器
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        # 先移除可能存在的相同处理器，避免重复
        for handler in root_logger.handlers[:]:
            if isinstance(handler, LogCaptureHandler):
                root_logger.removeHandler(handler)
        root_logger.addHandler(self.handler)

        # 避免重复添加处理器
        import sys
        if hasattr(sys, '_called_from_test'):
            # 如果是从测试调用的，避免与测试日志冲突
            pass

    def get_recent_logs(self, count=100):
        """获取最近的日志条目"""
        return self.handler.log_buffer[-count:] if len(self.handler.log_buffer) >= count else self.handler.log_buffer.copy()

    def clear_logs(self):
        """清空日志缓冲区"""
        self.handler.log_buffer.clear()


def get_global_log_manager():
    """获取全局日志管理器实例"""
    global _global_log_manager_instance
    return _global_log_manager_instance