# FindJobAgent

简历优化智能助手 —— 前后端分离项目。

## 技术栈

- 后端：FastAPI + SQLAlchemy(async) + PostgreSQL
- 前端：Vue3 + Vite + Element Plus + Pinia + Vue Router

## 项目结构

```
FindJobAgent/
├── backend/          # FastAPI 后端
│   ├── app/
│   │   ├── main.py          # 应用入口
│   │   ├── core/            # 配置、数据库连接
│   │   ├── api/v1/          # API 路由
│   │   ├── models/          # SQLAlchemy 数据模型
│   │   ├── schemas/         # Pydantic 请求/响应模型
│   │   ├── crud/            # 数据库操作
│   │   └── services/        # 业务逻辑
│   ├── requirements.txt
│   └── .env.example
├── frontend/         # Vue3 前端
│   ├── src/
│   │   ├── api/             # axios 封装与接口
│   │   ├── router/          # 路由
│   │   ├── stores/          # Pinia 状态管理
│   │   ├── views/           # 页面
│   │   ├── layouts/         # 布局组件
│   │   └── components/      # 通用组件
│   ├── package.json
│   └── .env.example
└── README.md
```

## 快速开始

### 后端

```bash
cd backend
conda env update -n Agent -f environment.yml
conda activate Agent
cp .env.example .env  # 修改数据库连接等配置
uvicorn app.main:app --reload --port 8000
```

访问 API 文档：http://localhost:8000/docs

### 前端

```bash
cd frontend
npm install
cp .env.example .env.local  # 修改 API 地址
npm run dev
```

访问前端页面：http://localhost:5173

## 协作约定

- 分支策略：各成员使用自己的功能分支开发，通过 Pull Request 合并到 main
- 后端代码风格：`ruff check` + `black` 格式化
- 前端代码风格：`eslint` + `prettier`
- 提交信息格式：`<type>: <description>`（如 `feat: 添加简历上传接口`）
