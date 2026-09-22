# 订单详情与物流查询

IT Coding Assessment 项目，使用 **Python / FastAPI + Vue 3 / TypeScript / Vite**。

## 当前状态

已完成前后端工程初始化、后端健康检查、首页连接状态展示和 Git 配置文件。
订单导入、SKU 匹配、GST 计算、物流查询和运费估算尚未实现。
首页的健康检查仅表示本地后端可用，不代表物流 API 已接通。

## 环境要求

- Python 3.11 或以上版本
- Node.js 22.12 或以上的 22.x 版本，或兼容的更新 LTS 版本
- npm（随 Node.js 安装）
- Git

## 本地运行

以下命令从仓库根目录开始，在两个终端中分别启动。

### 后端（Windows PowerShell）

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

macOS / Linux 将上述虚拟环境中的 Python 路径替换为 `.venv/bin/python`。

- 健康检查：http://127.0.0.1:8000/api/health
- 接口文档：http://127.0.0.1:8000/docs

### 前端

```powershell
cd frontend
npm ci
npm run dev
```

打开 http://127.0.0.1:5173 。开发服务器将 `/api` 请求代理到 `http://127.0.0.1:8000`。
后端关闭时，首页会显示连接失败，并允许重试。

### 构建检查

```powershell
cd frontend
npm run build
```

构建包含 TypeScript 类型检查，产物位于 `frontend/dist/`。
生产部署时需要另外配置 `/api` 反向代理至后端；Vite 开发代理不是生产部署配置。

初始化时 npm 官方源连接超时，前端依赖通过 `https://registry.npmmirror.com` 安装，
锁文件保留对应下载地址和完整性校验值；未修改用户的全局 npm 配置。

## 项目结构

```text
backend/
  app/main.py          FastAPI 入口及 /api/health
  .env.example         后续物流集成使用的环境变量名称
  requirements.in      后端直接依赖范围
  requirements.txt     已验证的后端依赖版本
frontend/
  src/App.vue          初始化首页与后端连接状态
  src/style.css        页面样式
  vite.config.ts       Vue 插件及开发 API 代理
  package-lock.json    前端依赖锁定
```

## 题目约束与待确认事项

- 选择 Python + Vue，符合两份题目共同列出的技术栈。
- PDF 第二笔订单的头部编号与商品明细不一致；导入前需记录统一规则。
- PDF 的含税价格与 GST 公式存在冲突；长版规定先将含税价格除以 1.10。业务实现前需确定适用版本。
- PDF 与长版对 TNT 的必做范围不同，后续按确认的版本实现。
- 商品数据应来自题目指定查询网站；当前未查询、导入或编造商品价格及物流结果。
- 后续金额按订单独立计算，支持一个订单对应多个物流单。

## 配置与凭证

当前健康检查无需任何密钥。`backend/.env.example` 仅预留变量名称；当前代码尚未读取这些变量或加载 `.env`。
物流集成时应在服务端通过环境变量读取凭证，并明确配置加载方式。
不要将密钥写入前端代码、README 或 Git 历史。
`.env`、虚拟环境、依赖目录、构建产物和临时 PDF 渲染文件已加入忽略规则。

## 参考

- [FastAPI 入门](https://fastapi.tiangolo.com/tutorial/first-steps/)
- [Vite 项目初始化与环境要求](https://vite.dev/guide/)
