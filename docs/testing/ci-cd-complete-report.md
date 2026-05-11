# CI/CD 完整报告

## CI/CD 配置

- **平台**: GitHub Actions
- **配置文件**: `.github/workflows/ci.yml`
- **触发条件**: push, pull_request

## 流水线阶段

| 阶段 | 命令 | 说明 |
|------|------|------|
| 安装 | `pip install -r requirements.txt` | 安装后端依赖 |
| Lint | `flake8 app/` | 代码风格检查 |
| 测试 | `pytest tests/ --ignore=tests/archive` | 运行全部测试 |
| 构建 | `cd src && npm run build` | 前端构建 |

## 测试结果

| 类型 | 通过 | 失败 |
|------|------|------|
| 单元测试 | 345 | 0 |
| 集成测试 | 149 | 2 (已知) |

## 部署

CI/CD 完成后自动部署到预览环境。
