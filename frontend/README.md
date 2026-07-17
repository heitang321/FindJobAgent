# Frontend (FindJobAgent Web)

Vue3 + Vite + Element Plus 前端。

## 启动

```bash
# 安装依赖（需要 Node 18+）
npm install

# 配置环境变量
cp .env.example .env.local

# 启动开发服务器
npm run dev
```

访问 http://localhost:5173

## 目录说明

| 目录 | 职责 |
|------|------|
| `src/api/` | axios 封装与接口定义 |
| `src/router/` | Vue Router 路由配置 |
| `src/stores/` | Pinia 状态管理 |
| `src/views/` | 页面级组件 |
| `src/layouts/` | 布局组件 |
| `src/components/` | 通用可复用组件 |
| `src/assets/` | 静态资源（样式、图片） |

## 构建

```bash
npm run build     # 生产构建，输出到 dist/
npm run preview   # 本地预览构建结果
```

## 约定

- 组件使用 `<script setup>` 语法
- 路径别名 `@` 指向 `src/`
- API 请求统一通过 `src/api/` 封装，组件中不直接写 axios
- Element Plus 组件按需自动导入，无需手动 import
