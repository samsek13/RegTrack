# RegTracker - 法规情报自动化采集系统

## 项目简介

RegTracker 是一个自动化法规情报采集系统，通过 RSS 源获取法规资讯，使用 LLM 智能提取结构化法规信息，并自动同步到 Google Sheets。

### 主要功能

- **自动采集**：定时从 RSS 源获取法规资讯
- **智能提取**：使用 LLM 从文章中提取法规名称、发布机构、发布日期、生效日期等信息
- **去重判断**：通过 RAG + LLM 智能判断法规是否已存在
- **字段补全**：联网搜索补全缺失的法规信息（英文名、日期等）
- **智能分类**：自动判断法规是否与数据保护、隐私、APP/SDK 合规、AI 监管、网络安全相关
- **Google Sheets 同步**：自动将数据同步到 Google Sheets

### 三种运行模式

1. **定时自动模式**：每日 00:15 和 12:15 自动运行
2. **手动回溯模式**：指定日期范围，手动触发一次性采集
3. **手动链接模式**：直接传入单篇文章链接进行处理

## 安装

### 1. 环境要求

- Python 3.14.x
- pip

### 2. 安装依赖

```bash
cd regtracker
pip install -r requirements.txt
```

### 3. 配置

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# SiliconFlow API 配置
SILICONFLOW_API_KEY=sk-your-key-here
SILICONFLOW_API_BASE=https://api.siliconflow.cn/v1
SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V3

# Tavily API 配置（联网搜索）
TAVILY_API_KEY=tvly-your-key-here

# Google Sheets 配置
GOOGLE_SERVICE_ACCOUNT_JSON=./service_account.json
GOOGLE_SHEET_ID=your-sheet-id-here

# 数据库配置
DB_PATH=./data/regtracker.db
BACKUP_DIR=./backups

# RSS 配置
RSS_FEED_URL=http://localhost:8001/feed/all.rss
```

### 4. Google Service Account 配置

1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建新项目或选择现有项目
3. 启用 Google Sheets API
4. 创建 Service Account：
   - 导航到 "IAM & Admin" > "Service Accounts"
   - 点击 "Create Service Account"
   - 填写名称和描述
   - 授予 "Editor" 角色
   - 创建 JSON 密钥并下载
5. 将下载的 JSON 文件保存为 `service_account.json` 放在项目根目录
6. 创建 Google Sheet 并与 Service Account 共享：
   - 创建新的 Google Sheet
   - 点击 "共享" 按钮
   - 添加 Service Account 的邮箱地址（在 JSON 文件中找到 `client_email` 字段）
   - 授予 "编辑者" 权限
7. 从 Google Sheet URL 中获取 Sheet ID：
   - URL 格式：`https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit`
   - 将 `{SHEET_ID}` 填入 `.env` 的 `GOOGLE_SHEET_ID`

## 使用方法

### 启动守护进程（定时任务）

```bash
python main.py daemon
```

守护进程将在每日 00:15 和 12:15 自动执行：

- 备份数据库
- 从 RSS 源获取资讯
- 处理并提取法规信息
- 同步到 Google Sheets

按 `Ctrl+C` 停止守护进程。

### 手动回溯

处理指定日期之前的所有 RSS item：

```bash
python main.py backfill 2026-02-26
```

### 处理单篇文章链接

```bash
python main.py process https://mp.weixin.qq.com/s/xxxxx
```

### 重置数据库

> # RegTracker 数据库重置工具
> 
> 本项目提供了两个脚本来帮助您一键清空和重置数据库，方便快速重置项目状态。
> 
> ## 脚本说明
> 
> ### 1. reset_db.py
> 
> - **功能**: 一键完全重置数据库
> - **操作**: 清空所有表的数据，并重新初始化数据库结构
> - **适用场景**: 完全重置项目状态
> 
> ### 2. clear_db.py
> 
> - **功能**: 交互式数据库清理工具
> - **操作选项**:
>   - 清空数据（保留表结构）
>   - 重置数据库（清空数据并重新初始化表结构）
> - **适用场景**: 需要选择性清理或调试时使用
> 
> ## 使用方法
> 
> ### 方法一：使用 reset_db.py（推荐）
> 
> ```bash
> cd regtracker
> python reset_db.py
> ```
> 
> ### 方法二：使用 clear_db.py
> 
> ```bash
> cd regtracker
> python clear_db.py
> ```
> 
> 然后根据提示选择相应操作。
> 
> ## 注意事项
> 
> - 执行脚本前，请确保没有其他程序正在使用数据库文件
> - 重置操作不可逆，请确保不需要保留现有数据
> - 重置后，数据库将恢复到初始状态，包括默认的RSS源等配置
> - 数据库文件位于 `./data/regtracker.db`
> 
> ## 恢复后验证
> 
> 重置完成后，您可以运行以下命令验证数据库状态：

## 项目结构

```
regtracker/
├── main.py              # CLI 入口
├── config.py            # 配置管理
├── db.py                # 数据库操作
├── llm.py               # LLM 调用封装
├── rag.py               # LangGraph RAG 模块
├── backup.py            # 数据库备份
├── pipeline.py          # 核心流程编排
├── sync.py              # Google Sheets 同步
├── scheduler.py         # 定时调度
├── steps/               # 各步骤模块
│   ├── __init__.py
│   ├── step1_rss.py     # RSS 获取
│   ├── step2_title.py   # 标题过滤
│   ├── step3_content.py # 内容提取
│   ├── step4_agg.py     # 聚合判断
│   ├── step5_split.py   # 文章拆分
│   ├── step6_extract.py # 法规提取
│   ├── step7a_dedup.py # 去重判断
│   ├── step7b_write.py  # 写入数据库
│   ├── step8_enrich.py  # 字段补全
│   └── step9_classify.py# 法规分类
├── data/                # SQLite 数据库目录
├── backups/             # 数据库备份目录
├── .env                 # 环境变量配置
├── .env.example         # 环境变量示例
├── requirements.txt     # 依赖列表
└── README.md            # 本文档
```

## 数据库结构

应用启动时自动创建以下表：

- `rss_sources`：RSS 源配置（不同步到 Sheets）
- `regulations`：法规主表
- `cached_articles`：文章缓存
- `process_history`：处理历史（不同步到 Sheets）
- `llm_log_step2` ~ `llm_log_step9`：各步骤 LLM 交互日志

## 注意事项

1. **API 密钥安全**：请勿将 `.env` 和 `service_account.json` 文件提交到版本控制系统

2. **数据库备份**：每次运行 pipeline 前都会自动备份数据库，保留最近 30 个备份

3. **Google Sheets 同步**：采用全量覆盖策略，每次同步会清空目标 Sheet 并写入最新数据

4. **错误处理**：单个 item 处理失败不会中断整体流程，会记录错误并继续处理下一个

5. **LLM 调用**：所有 LLM 调用都有重试机制（最多 3 次，指数退避）

## 依赖版本

详见 `requirements.txt`：

```
feedparser==6.0.11
requests==2.32.3
beautifulsoup4==4.12.3
lxml==5.3.0
markdownify==0.13.1
langchain-openai==0.3.14
langchain-core==0.3.55
langgraph==0.3.18
langchain-tavily==0.1.6
gspread==6.1.4
google-auth==2.37.0
apscheduler==3.10.4
python-dotenv==1.0.1
```

## License

MIT

---

## 更新说明

### Pipeline 流程调整（2026-02-27）

当前 pipeline 已跳过 **Step 4（聚合判断）** 和 **Step 5（文章拆分）**，直接从 Step 3 进入 Step 6。调整后的处理流程如下：

```
Step 1: RSS 获取 → Step 2: 标题过滤 → Step 3: 内容提取 
→ Step 6: 法规提取 → Step 7a: 去重判断 → Step 7b: 写入数据库 
→ Step 8: 字段补全 → Step 9: 法规分类
```

**调整原因**：
- 对于性能好的LLM，文章不拆分也可以较好地识别提取法规
- 简化流程可以提升处理效率，减少不必要的 LLM 调用
- 后续如需要，可重新启用 Step 4+5

**跳过的步骤文件仍保留在项目中**：
- `steps/step4_agg.py` - 聚合判断模块（备用）
- `steps/step5_split.py` - 文章拆分模块（备用）
