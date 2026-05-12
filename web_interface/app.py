from flask import Flask, render_template, send_file, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO
from dotenv import load_dotenv
from pathlib import Path
import os
import logging
from web_controller import bp
from log_handler import LogManager
from auth import init_auth, is_local_request, is_authenticated, verify_password
import tempfile
from datetime import datetime

# 加载项目根目录的 .env 文件
load_dotenv(Path(__file__).parent.parent / '.env')

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# SECRET_KEY 从环境变量读取，没有则使用默认值
_secret_key = os.getenv('FLASK_SECRET_KEY', '')
if _secret_key:
    app.config['SECRET_KEY'] = _secret_key
else:
    app.config['SECRET_KEY'] = 'regtracker-secret-key-for-web-interface'
    logger.warning("FLASK_SECRET_KEY 未设置，使用默认值。生产环境请务必设置此环境变量。")

# 初始化认证模块（读取 WEB_USERNAME / WEB_PASSWORD 并 bcrypt 哈希）
init_auth(app)

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
def check_authentication():
    """
    认证检查钩子，在所有请求之前执行。
    - 静态资源、登录页、登出页直接放行
    - 本地请求（127.0.0.1 / ::1）自动跳过验证
    - 其他请求需验证 session 登录状态
    - 页面请求未登录 → 302 重定向到 /login
    - API 请求未登录 → 返回 401 JSON
    """
    # 放行静态资源
    if request.path.startswith('/static'):
        return None

    # 放行登录和登出路由
    if request.path in ('/login', '/logout'):
        return None

    # 放行 Socket.IO 相关路径
    if request.path.startswith('/socket.io'):
        return None

    # 本地请求自动放行
    if is_local_request(request):
        return None

    # 检查是否已登录
    if not is_authenticated(session):
        # API 请求返回 401 JSON，页面请求重定向到登录页
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "message": "未登录，请先登录"}), 401
        return redirect(url_for('login_page'))

    return None


@app.before_request
def log_request_info():
    logger.info(f"Request: {request.method} {request.url}")
    if request.data:
        try:
            logger.info(f"Request data: {request.get_json()}")
        except Exception:
            pass


@app.after_request
def log_response_info(response):
    logger.info(f"Response: {response.status_code}")
    return response

# ---- 认证相关路由 ----

@app.route('/login', methods=['GET'])
def login_page():
    """渲染登录页面。已登录用户直接跳转到主界面。"""
    if is_authenticated(session):
        return redirect(url_for('index'))

    # 从查询参数获取错误信息（登录失败时传递）
    error = request.args.get('error', '')
    # 传递 is_local 标志给模板，本地访问时显示提示
    is_local = is_local_request(request)
    return render_template('login.html', error=error, is_local=is_local)


@app.route('/login', methods=['POST'])
def login():
    """处理登录表单提交。"""
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')

    # 基本验证：字段不能为空
    if not username or not password:
        return redirect(url_for('login_page', error='用户名和密码不能为空'))

    # 验证凭据
    success, error_msg = verify_password(username, password, app)

    if success:
        session['logged_in'] = True
        session['username'] = username
        logger.info(f"用户 {username} 已登录")
        return redirect(url_for('index'))

    # 登录失败，回到登录页并显示错误
    return redirect(url_for('login_page', error=error_msg))


@app.route('/logout')
def logout():
    """清除 session 并重定向到登录页。"""
    session.clear()
    logger.info("用户已登出")
    return redirect(url_for('login_page'))


# ---- 主界面路由 ----

@app.route('/')
def index():
    return render_template('index.html')

# 添加日志下载API
@app.route('/api/download-logs', methods=['POST'])
def download_logs():
    """下载日志文件（需登录或本地访问）。"""

    # 获取日志内容
    log_content = log_manager.handler.get_log_content()

    # 创建临时文件
    temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8')
    temp_file.write(log_content)
    temp_file.close()

    # 发送文件
    resp = send_file(temp_file.name, as_attachment=True,
                     download_name=f"regtracker_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
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