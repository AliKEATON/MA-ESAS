# MA-ESAS：多智能体协同的电商商品舆情分析系统

基于多智能体架构和大语言模型的电商商品舆情分析平台，支持京东、淘宝等多平台商品评论爬取、情感分析、舆情监测和智能报告生成。

## 🎯 核心功能

- **多平台爬虫**：支持京东、淘宝、天猫等电商平台商品评论爬取
- **智能舆情分析**：基于 DeepSeek 大模型的多维度舆情分析
- **多智能体协同**：LangGraph 驱动的智能体编排系统
- **向量检索**：ChromaDB 向量数据库支持语义搜索
- **数据分析**：DuckDB 高性能数据分析引擎
- **智能报告**：自动生成 PDF 舆情分析报告
- **Web 界面**：Streamlit 交互式前端

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

# 编辑 .env 文件，配置以下关键项：
```

**必需配置项：**

```env
# MySQL 数据库
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=ma_esas

# DeepSeek API (获取地址: https://platform.deepseek.com)
DEEPSEEK_API_KEY=your_api_key

# JWT 认证密钥（生产环境请修改）
JWT_SECRET_KEY=your-secret-key-change-in-production

# 环境模式
ENVIRONMENT=development
DEBUG=True
```

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
streamlit run frontend-streamlit/app.py --server.port 8501
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

## 📁 项目结构

```
MA-ESAS-1/
├── backend/                    # 后端服务
│   ├── app/
│   │   ├── api/               # API 路由
│   │   ├── agents/            # 多智能体模块
│   │   ├── crawlers/          # 爬虫模块
│   │   ├── db/                # 数据库配置
│   │   ├── models/            # 数据模型
│   │   ├── schemas/           # Pydantic 数据验证
│   │   ├── services/          # 业务逻辑层
│   │   ├── utils/             # 工具函数
│   │   ├── config.py          # 配置管理
│   │   └── main.py            # FastAPI 应用入口
│   ├── migrations/            # 数据库迁移脚本
│   ├── tests/                 # 测试用例
│   └── alembic.ini            # Alembic 配置
├── frontend/                  # 前端应用
│   ├── components/            # Streamlit 组件
│   ├── pages/                 # 页面模块
│   ├── utils/                 # 工具函数
│   ├── app.py                 # Streamlit 主应用
│   └── config.py              # 前端配置
├── docs/                      # 项目文档
├── data/                      # 数据存储目录
│   ├── duckdb/               # DuckDB 数据库文件
│   └── chromadb/             # ChromaDB 向量库
├── logs/                      # 日志文件
├── process/                   # 项目进度记录
├── requirements.txt           # Python 依赖
├── .env.example              # 环境变量示例
└── README.md                 # 本文件
```

## 🔧 常见问题

### Q: 如何重置数据库？

```bash
cd backend
# 回滚所有迁移
alembic downgrade base
# 重新应用迁移
alembic upgrade head
```

### Q: 如何查看 API 日志？

```bash
# 日志文件位置
tail -f logs/app.log
```

### Q: 如何测试爬虫功能？

```bash
cd backend
python -m pytest tests/test_crawlers_quick.py -v
```

### Q: 密码超过 72 字节错误？

bcrypt 有 72 字节限制。系统会自动截断超长密码，无需手动处理。

## 📚 API 文档

### 认证相关

- `POST /api/auth/register` - 用户注册
- `POST /api/auth/login` - 用户登录
- `GET /api/auth/me` - 获取当前用户信息

### 商品相关

- `POST /api/products` - 添加商品
- `GET /api/products` - 获取商品列表
- `GET /api/products/{product_id}` - 获取商品详情

### 爬虫相关

- `POST /api/crawlers/jd` - 爬取京东评论
- `GET /api/crawlers/status/{task_id}` - 查询爬虫任务状态

### 对话相关

- `POST /api/conversations` - 创建对话
- `POST /api/conversations/{conversation_id}/messages` - 发送消息

详细 API 文档请访问：http://localhost:8000/docs

## 🛠️ 开发指南

### 添加新的爬虫

1. 在 `backend/app/crawlers/` 创建新爬虫类
2. 继承 `BaseCrawler` 基类
3. 实现 `crawl()` 方法
4. 在 `backend/app/services/crawler_service.py` 注册

### 添加新的智能体

1. 在 `backend/app/agents/` 创建智能体模块
2. 使用 LangGraph 定义状态机
3. 在 `backend/app/services/` 创建服务层
4. 通过 API 路由暴露接口

### 运行测试

```bash
cd backend
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_crawlers.py -v

# 运行特定测试用例
pytest tests/test_crawlers.py::test_jd_crawler -v
```

## 📝 日志配置

日志文件位置：`logs/app.log`

日志级别可在 `.env` 中配置：

```env
LOG_LEVEL=INFO          # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_MAX_SIZE=500MB      # 单个日志文件最大大小
LOG_RETENTION_DAYS=7    # 日志保留天数
```

## 🔐 安全建议

- **生产环境**：修改 `JWT_SECRET_KEY`
- **API 密钥**：不要在代码中硬编码，使用环境变量
- **数据库密码**：使用强密码，定期更换
- **CORS 配置**：根据实际需求调整允许的来源

## 📞 技术支持

如有问题，请查看：

- 项目文档：`docs/` 目录
- 测试用例：`backend/tests/` 目录
- 进度记录：`process/` 目录

## 📄 许可证

本项目为毕业设计项目，仅供学习和研究使用。

---

**最后更新**：2026-03-30
