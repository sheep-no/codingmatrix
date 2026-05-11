# Windows 快速启动指南

## 环境要求

- Windows 10/11
- Python 3.11+
- Node.js 18+

## 启动步骤

### 1. 安装 Python 依赖

```powershell
pip install -r requirements.txt
```

### 2. 安装前端依赖

```powershell
cd src
npm install
cd ..
```

### 3. 设置环境变量

创建 `.env` 文件:

```env
SECRET_KEY=your-secret-key
SILICONFLOW_API_KEY=your-api-key
DATABASE_URL=sqlite+aiosqlite:///./app.db
```

### 4. 启动服务

**方式一: 使用启动脚本**
```powershell
.\start.ps1
```

**方式二: 手动启动**

终端 1 (后端):
```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

终端 2 (前端):
```powershell
cd src
npm run dev
```

### 5. 访问应用

- 前端: http://localhost:5173
- API 文档: http://localhost:8000/docs

## 常见问题

### Python 未找到
安装 Python 并确保添加到 PATH。

### npm 未找到
安装 Node.js。

### 端口被占用
修改后端端口: `--port 8001`
修改前端端口: `npx vite --port 5174`
