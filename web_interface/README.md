# RegTracker Web界面

RegTracker Web界面是一个为法规情报自动化采集系统提供的图形化操作界面，使用户可以通过浏览器轻松控制系统的三大核心功能，并实时监控运行日志。

## 功能特性

1. **守护进程控制** - 启动和停止后台守护进程（定时任务）
2. **手动回溯控制** - 执行手动回溯任务，指定日期范围
3. **手动链接处理** - 处理单篇文章链接
4. **实时日志查看** - 实时显示系统运行日志
5. **日志下载** - 下载系统运行日志文件

## 安装依赖

在项目根目录下运行：

```bash
pip install -r requirements.txt
```

## 运行Web界面

```bash
cd regtracker/web_interface
python app.py
```

服务器默认运行在 http://127.0.0.1:5000

## 配置选项

- WEB_HOST: Web服务器监听地址（默认 127.0.0.1）
- WEB_PORT: Web服务器端口（默认 5000）
- DEBUG_MODE: 调试模式开关（默认 False）

例如：
```bash
WEB_HOST=0.0.0.0 WEB_PORT=8080 DEBUG_MODE=True python app.py
```

## 安全说明

此Web界面仅供本地访问，没有实现用户认证机制。请勿将其暴露到公共网络。

## 技术架构

- 后端：Flask + Socket.IO
- 前端：HTML5 + Bootstrap 5 + JavaScript
- 实时通信：WebSocket（通过Socket.IO）