# MA-ESAS：多智能体协同的电商商品舆情分析系统

基于多智能体架构和大语言模型的电商商品舆情分析平台，支持京东、淘宝等多平台商品评论爬取、情感分析、舆情监测和智能报告生成。

## 🎯 核心功能

- **多平台爬虫**：支持京东、淘宝、天猫等电商平台商品评论爬取
- **智能舆情分析**：基于 DeepSeek 大模型的多维度舆情分析
- **多智能体协同**：LangGraph 驱动的智能体编排系统
- **向量检索**：ChromaDB 向量数据库支持语义搜索
- **数据分析**：DuckDB 高性能数据分析引擎
- **智能报告**：自动生成 PDF 舆情分析报告
- **Web 界面**：Vue 交互式前端

## 📋 系统要求

- Python 3.10+
- MySQL 8.0+
- Node.js 16+ (可选，仅用于前端开发)

## 🚀 快速启动

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd MA-ESAS-1

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 复制示例配置文件
cp .env.example .env


### 3. 初始化数据库

```bash
# 进入后端目录
cd backend

# 执行数据库迁移
alembic upgrade head

# 返回项目根目录
cd ..
```

### 4. 启动服务

**方式一：分别启动后端和前端**

```bash
# 终端 1：启动 FastAPI 后端
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2：启动 Streamlit 前端
npm run dev
```

**方式二：使用脚本启动（可选）**

```bash
# 创建启动脚本后使用
python scripts/start.py
```

### 5. 访问应用

- **API 文档**：http://localhost:8000/docs
- **前端界面**：http://localhost:8501
- **API 健康检查**：http://localhost:8000/health

