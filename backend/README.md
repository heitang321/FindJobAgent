# Backend (FindJobAgent API)

FastAPI 后端服务。

## 启动

```bash
# 1. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate    # Linux/Mac

# 2. 安装依赖
pip install -r requirements-dev.txt   # 含开发工具
# 或只装运行时依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 修改数据库连接、SECRET_KEY 等

# 4. 启动开发服务器
uvicorn app.main:app --reload --port 8000
```

启动后：

- API 文档 (Swagger UI): http://localhost:8000/docs
- 健康检查: http://localhost:8000/api/v1/health

## 目录说明

| 目录 | 职责 |
|------|------|
| `app/main.py` | 应用入口，生命周期、中间件、路由注册 |
| `app/core/` | 配置管理、数据库连接 |
| `app/api/v1/` | API 路由，按业务模块拆分 |
| `app/api/deps.py` | 公共依赖（数据库会话、当前用户） |
| `app/models/` | SQLAlchemy ORM 模型 |
| `app/schemas/` | Pydantic 请求/响应模型 |
| `app/crud/` | 数据库操作封装 |
| `app/services/` | 业务逻辑层 |

## 代码规范

```bash
ruff check app/          # 代码检查
black app/               # 格式化
pytest                   # 运行测试
```
