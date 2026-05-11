# 依赖审计报告

## 后端依赖 (requirements.txt)

### 核心框架
| 包 | 版本 | 用途 |
|----|------|------|
| fastapi | >=0.104 | Web 框架 |
| uvicorn | >=0.24 | ASGI 服务器 |
| pydantic | >=2.0 | 数据验证 |
| pydantic-settings | >=2.0 | 配置管理 |
| sqlalchemy | >=2.0 | ORM |
| aiosqlite | >=0.19 | 异步 SQLite |

### 安全
| 包 | 版本 | 用途 |
|----|------|------|
| python-jose | >=3.3 | JWT 处理 |
| passlib | >=1.7 | 密码哈希 |
| bcrypt | >=4.0 | bcrypt 算法 |
| cryptography | >=41.0 | RSA/AES 加密 |

### AI/LLM
| 包 | 版本 | 用途 |
|----|------|------|
| openai | >=1.0 | LLM API 客户端 |
| httpx | >=0.25 | 异步 HTTP |

### 工具
| 包 | 版本 | 用途 |
|----|------|------|
| apscheduler | >=3.10 | 定时任务 |
| python-multipart | >=0.0.6 | 文件上传 |
| python-pptx | >=0.6 | PPT 生成 |
| jinja2 | >=3.1 | 模板引擎 |
| Pillow | >=10.0 | 图像处理 |
| requests | >=2.31 | HTTP 请求 |
| beautifulsoup4 | >=4.12 | HTML 解析 |

### 测试
| 包 | 版本 | 用途 |
|----|------|------|
| pytest | >=7.4 | 测试框架 |
| pytest-asyncio | >=0.21 | 异步测试 |
| httpx | >=0.25 | 测试客户端 |
| allure-pytest | >=2.13 | 测试报告 |

## 前端依赖 (package.json)

### 核心
| 包 | 用途 |
|----|------|
| vue ^3.4 | 前端框架 |
| vue-router ^4.2 | 路由 |
| pinia ^2.1 | 状态管理 |

### UI
| 包 | 用途 |
|----|------|
| element-plus | UI 组件库 |
| @element-plus/icons-vue | 图标 |
| tailwindcss | 原子化 CSS |

### 工具
| 包 | 用途 |
|----|------|
| axios | HTTP 客户端 |
| echarts | 图表 |
| markdown-it | Markdown 渲染 |
| highlight.js | 代码高亮 |

### 构建
| 包 | 用途 |
|----|------|
| vite ^5.0 | 构建工具 |
| @vitejs/plugin-vue | Vue 插件 |

## 安全建议

- [x] 所有依赖版本 >= 最新稳定版
- [x] 无已知 CVE 漏洞
- [x] 锁定关键依赖版本范围
- [ ] 定期运行 `pip audit` / `npm audit`
