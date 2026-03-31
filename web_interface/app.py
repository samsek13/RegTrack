from flask import Flask, render_template, send_file, request
from flask_socketio import SocketIO
import os
import logging
from web_controller import bp
from log_handler import LogManager
import tempfile
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'regtracker-secret-key-for-web-interface'

# 初始化SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# 初始化日志管理器
log_dir = os.getenv('LOG_DIR', './logs')
log_manager = LogManager(socketio, log_dir)
log_manager.setup_logging()

# 创建一个全局访问点，以便其他模块可以引用这个日志管理器
import builtins
builtins.global_log_manager = log_manager

# 注册蓝图
app.register_blueprint(bp)


@app.before_request
def log_request_info():
    logger.info(f"Request: {request.method} {request.url}")
    if request.data:
        logger.info(f"Request data: {request.get_json()}")


@app.after_request
def log_response_info(response):
    logger.info(f"Response: {response.status_code}")
    return response

@app.route('/')
def index():
    return render_template('index.html')

# 添加日志下载API
@app.route('/api/download-logs', methods=['POST'])
def download_logs():
    # 创建临时文件
    import tempfile
    import os

    # 获取日志内容
    log_content = log_manager.handler.get_log_content()

    # 创建临时文件
    temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8')
    temp_file.write(log_content)
    temp_file.close()

    # 发送文件
    def remove_file(response):
        try:
            os.unlink(temp_file.name)
        except Exception:
            pass
        return response

    resp = send_file(temp_file.name, as_attachment=True, download_name=f"regtracker_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    resp.call_on_close(lambda: os.unlink(temp_file.name))
    return resp

# Socket.IO事件处理
@socketio.on('connect')
def handle_connect(auth=None):
    print('Client connected')
    # 连接时发送最近的日志
    recent_logs = log_manager.get_recent_logs(50)
    for log in recent_logs:
        socketio.emit('log_update', {'log': log})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

if __name__ == '__main__':
    # 从环境变量获取配置，默认本地访问
    host = os.getenv('WEB_HOST', '127.0.0.1')
    port = int(os.getenv('WEB_PORT', 5000))
    debug = os.getenv('DEBUG_MODE', 'False').lower() == 'true'

    socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)