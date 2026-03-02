// static/js/main.js
document.addEventListener('DOMContentLoaded', function() {
    // 连接到Socket.IO服务器
    const socket = io();

    // 获取页面元素
    const startDaemonBtn = document.getElementById('start-daemon');
    const stopDaemonBtn = document.getElementById('stop-daemon');
    const daemonStatusSpan = document.getElementById('daemon-status');
    const backfillDateInput = document.getElementById('backfill-date');
    const runBackfillBtn = document.getElementById('run-backfill');
    const articleUrlInput = document.getElementById('article-url');
    const runProcessBtn = document.getElementById('run-process');
    const logOutputDiv = document.getElementById('log-output');
    const downloadLogsBtn = document.getElementById('download-logs');

    // 存储日志以便下载
    let allLogs = [];

    // Socket.IO事件监听
    socket.on('log_update', function(data) {
        const logLine = document.createElement('div');
        logLine.className = 'log-entry';
        logLine.textContent = data.log;
        logOutputDiv.appendChild(logLine);

        // 滚动到底部
        logOutputDiv.scrollTop = logOutputDiv.scrollHeight;

        // 添加到下载日志数组
        allLogs.push(data.log);

        // 限制显示的日志数量，避免内存溢出
        if (logOutputDiv.children.length > 1000) {
            logOutputDiv.removeChild(logOutputDiv.firstChild);
        }
    });

    // 按钮事件监听
    startDaemonBtn.addEventListener('click', function() {
        // 显示加载状态
        startDaemonBtn.disabled = true;
        startDaemonBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 启动中...';

        fetch('/api/start-daemon', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            alert(data.message);
            updateStatus(); // 更新状态显示
            // 恢复按钮状态
            startDaemonBtn.disabled = false;
            startDaemonBtn.innerHTML = '启动守护进程';
        })
        .catch(error => {
            console.error('Error:', error);
            alert('请求失败: ' + error.message);
            // 恢复按钮状态
            startDaemonBtn.disabled = false;
            startDaemonBtn.innerHTML = '启动守护进程';
        });
    });

    stopDaemonBtn.addEventListener('click', function() {
        // 显示加载状态
        stopDaemonBtn.disabled = true;
        stopDaemonBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 停止中...';

        fetch('/api/stop-daemon', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            alert(data.message);
            updateStatus(); // 更新状态显示
            // 恢复按钮状态
            stopDaemonBtn.disabled = false;
            stopDaemonBtn.innerHTML = '停止守护进程';
        })
        .catch(error => {
            console.error('Error:', error);
            alert('请求失败: ' + error.message);
            // 恢复按钮状态
            stopDaemonBtn.disabled = false;
            stopDaemonBtn.innerHTML = '停止守护进程';
        });
    });

    runBackfillBtn.addEventListener('click', function() {
        const dateValue = backfillDateInput.value;
        if (!dateValue) {
            alert('请选择日期');
            return;
        }

        // 显示加载状态
        runBackfillBtn.disabled = true;
        runBackfillBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 执行中...';

        fetch('/api/run-backfill', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({date: dateValue})
        })
        .then(response => response.json())
        .then(data => {
            alert(data.message);
            // 恢复按钮状态
            runBackfillBtn.disabled = false;
            runBackfillBtn.innerHTML = '执行回溯任务';
        })
        .catch(error => {
            console.error('Error:', error);
            alert('请求失败: ' + error.message);
            // 恢复按钮状态
            runBackfillBtn.disabled = false;
            runBackfillBtn.innerHTML = '执行回溯任务';
        });
    });

    runProcessBtn.addEventListener('click', function() {
        const urlValue = articleUrlInput.value;
        if (!urlValue) {
            alert('请输入URL');
            return;
        }

        // 显示加载状态
        runProcessBtn.disabled = true;
        runProcessBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 处理中...';

        fetch('/api/run-process', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({url: urlValue})
        })
        .then(response => response.json())
        .then(data => {
            alert(data.message);
            // 恢复按钮状态
            runProcessBtn.disabled = false;
            runProcessBtn.innerHTML = '处理链接';
        })
        .catch(error => {
            console.error('Error:', error);
            alert('请求失败: ' + error.message);
            // 恢复按钮状态
            runProcessBtn.disabled = false;
            runProcessBtn.innerHTML = '处理链接';
        });
    });

    downloadLogsBtn.addEventListener('click', function() {
        // 创建日志文件并下载
        const blob = new Blob([allLogs.join('\n')], {type: 'text/plain'});
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = `regtracker_logs_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.txt`;
        document.body.appendChild(a);
        a.click();

        // 清理
        setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }, 100);
    });

    // 更新状态的函数
    function updateStatus() {
        fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            if (data.daemon_running) {
                daemonStatusSpan.textContent = '状态: 运行中';
                daemonStatusSpan.className = 'ms-3 text-success';
            } else {
                daemonStatusSpan.textContent = '状态: 停止';
                daemonStatusSpan.className = 'ms-3 text-danger';
            }
        })
        .catch(error => {
            console.error('获取状态失败:', error);
        });
    }

    // 页面加载后更新一次状态
    updateStatus();
});