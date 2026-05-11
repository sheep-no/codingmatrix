# CI/CD 配置指南

## GitHub Actions 配置

### .github/workflows/ci.yml

```yaml
name: CI

on:
  push:
    branches: [master, main]
  pull_request:
    branches: [master, main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: |
          export SECRET_KEY=test
          export SILICONFLOW_API_KEY=test
          export DATABASE_URL='sqlite+aiosqlite:///./test.db'
          pytest tests/ --ignore=tests/archive -v

  build:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Install dependencies
        run: cd src && npm install
      - name: Build
        run: cd src && npm run build
```

## 环境变量

CI 环境中需要设置以下环境变量:

| 变量 | 值 | 说明 |
|------|-----|------|
| SECRET_KEY | test | 测试密钥 |
| SILICONFLOW_API_KEY | test | AI API Key (测试用) |
| DATABASE_URL | sqlite+aiosqlite:///./test.db | 测试数据库 |

## 本地运行

```bash
# 模拟 CI 环境
export SECRET_KEY=test
export SILICONFLOW_API_KEY=test
export DATABASE_URL='sqlite+aiosqlite:///./test.db'

# 运行测试
pytest tests/ --ignore=tests/archive -v

# 构建前端
cd src && npm install && npm run build
```
