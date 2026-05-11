# CodingMatrix

> AI 驱动的全栈代码生成与开发平台

## 项目概述

CodingMatrix 是一个基于 FastAPI + Vue 3 的 AI 全栈开发平台，提供代码生成、图像生成、PPT 制作、工作流编排、虚拟 AI 对话等多种 AI 能力。

**版本**: v4.2.1 | **技术栈**: FastAPI (Python 3.11) + Vue 3 + SQLite + APScheduler

## 核心能力

| 模块 | 描述 |
|------|------|
| AI 代码生成 | 基于 LLM 的智能代码生成、流式输出、断点续传 |
| AI 项目生成 | 完整项目脚手架生成，支持文件管理、预览、保存 |
| 图像生成 | Kolors 模型支持文生图、图生图、修复、头像、风景、图标 |
| PPT 生成 | 异步任务生成 PPT，支持预览和下载 |
| 虚拟 AI 对话 | GirlAi 多角色 AI 聊天，支持历史管理 |
| 工作流编排 | 可视化工作流定义、执行、导入导出、历史记录 |
| 视觉分析 | 图像理解、OCR、代码提取、安全检查 |
| 知识库 | 文档上传、搜索、知识管理 |
| 用户管理 | 三级权限 (normal/admin/super)、RSA 加密登录 |
| 系统监控 | 服务健康检查、熔断器、限流、日志管理 |
| 主题系统 | 明亮/默认/暗色三套主题，CSS 变量驱动 |

## 快速开始

```bash
# 后端
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 前端
cd src && npm run dev
```

## 文档导航

- [INDEX.md](INDEX.md) - 文档索引
- [MODULES.md](MODULES.md) - 模块说明
- [docs/development/DEVELOPER_GUIDE.md](development/DEVELOPER_GUIDE.md) - 开发者指南
- [docs/architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) - 架构设计
- [docs/api/API-DOCUMENTATION.md](api/API-DOCUMENTATION.md) - API 文档
- [docs/testing/COMPREHENSIVE-TEST-REPORT-20260508.md](testing/COMPREHENSIVE-TEST-REPORT-20260508.md) - 测试报告

## 最新修复 (v4.2.1)
- 修复 `/history` 接口 500 错误 (缓存装饰器兼容 Pydantic 模型)
- 修复 `ProjectGenerate.vue` 编译报错 (清理重复代码块)
- 修复 `security.py` JWT 异常处理兼容性
- 修复 `bottominput.vue` 按钮重叠 UI 问题

## 测试状态

| 类型 | 通过 | 失败 | 总计 |
|------|------|------|------|
| 单元测试 | 345 | 0 | 345 |
| 集成测试 | 149 | 2 (已知) | 151 |
| **总计** | **494** | **2** | **496** |

## 项目结构

```
app/          # 后端 (203 Python 文件, ~57K 行)
src/          # 前端 (90 文件, ~58K 行)
tests/        # 测试
docs/         # 文档
```
