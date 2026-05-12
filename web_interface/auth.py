# web_interface/auth.py
# 认证模块：处理登录验证、session 管理和本地请求检测

import os
import bcrypt
import logging

logger = logging.getLogger(__name__)


def init_auth(app):
    """
    初始化认证配置。
    从环境变量读取用户名和密码，对密码执行 bcrypt 哈希后存入 app.config。
    应在 Flask app 创建之后、首次请求之前调用。
    """
    username = os.getenv('WEB_USERNAME', 'admin')
    password = os.getenv('WEB_PASSWORD', '')

    if password:
        # 将明文密码 bcrypt 哈希后存储，避免内存中长期保留明文
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    else:
        password_hash = None
        logger.warning("WEB_PASSWORD 未设置，远程登录将被拒绝")

    app.config['AUTH_USERNAME'] = username
    app.config['AUTH_PASSWORD_HASH'] = password_hash

    logger.info(f"认证模块已初始化，用户名: {username}")


def is_local_request(request):
    """
    判断请求是否来自本地回环地址。
    覆盖 IPv4 (127.0.0.1) 和 IPv6 (::1)。
    """
    remote_addr = request.remote_addr
    return remote_addr in ('127.0.0.1', '::1')


def is_authenticated(session):
    """检查 session 中是否存在有效的登录状态。"""
    return session.get('logged_in', False)


def verify_password(username, password, app):
    """
    验证用户名和密码。
    返回 (success: bool, error_message: str)
    """
    stored_username = app.config.get('AUTH_USERNAME', '')
    stored_hash = app.config.get('AUTH_PASSWORD_HASH')

    if stored_hash is None:
        logger.warning("系统未配置 WEB_PASSWORD，拒绝登录")
        return False, "系统未配置登录凭据，请联系管理员"

    if username != stored_username:
        logger.info(f"登录失败：用户名不匹配 (输入: {username})")
        return False, "用户名或密码错误"

    if not bcrypt.checkpw(password.encode('utf-8'), stored_hash):
        logger.info(f"登录失败：密码错误 (用户: {username})")
        return False, "用户名或密码错误"

    logger.info(f"用户 {username} 登录成功")
    return True, ""
