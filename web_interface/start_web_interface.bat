@echo off
REM RegTracker Web界面启动脚本

echo 启动 RegTracker Web界面...
echo.

cd /d "d:\plusDrei\LT3\regtracker\web_interface"

REM 检查Python环境
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python。请确保已安装Python并添加到PATH。
    pause
    exit /b 1
)

REM 检查依赖
echo 正在检查依赖...
python -c "import flask, flask_socketio" >nul 2>&1
if errorlevel 1 (
    echo 未安装所需依赖，正在安装...
    pip install -r requirements.txt
)

REM 启动Web服务器
echo.
echo 正在启动 RegTracker Web界面...
echo 访问 http://127.0.0.1:5000 使用界面
echo.
python app.py