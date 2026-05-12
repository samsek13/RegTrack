FROM python:3.12-slim

WORKDIR /app

# 安装编译工具（部分 Python 包需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
COPY web_interface/requirements.txt web_requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r web_requirements.txt

# 复制项目文件
COPY . .

# 确保 data 和 backups 目录存在
RUN mkdir -p /app/data /app/backups

EXPOSE 5000

CMD ["python", "web_interface/app.py"]
