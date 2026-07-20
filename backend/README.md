# Backend (FindJobAgent API)

FastAPI 后端服务。

## 启动

```bash
# 1. 创建或更新 Conda 环境
conda env update -n Agent -f environment.yml
conda activate Agent

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 修改数据库连接、SECRET_KEY 等

# 3. 首次使用岗位抓取时登录招聘网站
python -m app.tools.login

# 4. 启动服务
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
ruff check app/ tests    # 代码检查
black app/ tests         # 格式化
pytest                   # pytest.ini 只收集 tests/
```

## 工作流说明

- 上传只负责校验并保存 PDF/DOCX，不提前调用模型。
- 简历、岗位和优化接口都要求 Bearer Token，并校验任务归属用户。
- 手动提交 JD URL 时，LangGraph 并行运行“简历分析”和“JD 抓取/结构化”，再执行匹配。
- 自动推荐岗位时，如果简历尚未结构化，搜索接口会先按需运行一次简历分析。
- JD URL 只允许 `JOB_ALLOWED_HOSTS` 中的域名及其子域名。
