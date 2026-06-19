# 测试文档

**最后更新**: 2026-06-09
**版本**: v5.15.0
**E2E 测试状态**: 77 spec / 409 用例 (最近一次冒烟通过)

---

## 测试概况 (2026-06-09 实测)

| 测试类型 | 文件数 | 测试用例 | 状态 | 说明 |
|----------|--------|----------|------|------|
| **单元测试** | **88** | **1376** | 通过 | 后端业务逻辑 (`tests/unit/`) |
| **集成测试** | **2** (运行) | **24** | 通过 | **多数已归档到 `archive/integration_old/`** |
| **E2E 测试** | **77** | **409** | 待验证 | Playwright 前端测试 (`tests/e2e/`) |
| **性能测试** | 2 | - | 通过 | `tests/performance/` |
| **归档测试** | 56+ | - | 历史保留 | `tests/archive/legacy/` + `integration_old/` |
| **总计** | **169+** | **1809+** | - | 实际运行 + 归档 |

> **重要变更**: 集成测试目录从 v5.11.0 报告的 20+ 文件**缩减到 2 个**（`test_auth_api.py` 18 cases, `test_health_api.py` 6 cases）。其余集成测试已迁移到 `tests/archive/integration_old/` 保留为历史参考。如需恢复，可从 archive 目录取回。

---

## 目录结构 (2026-06-09 实际)

```
tests/
├── conftest.py                    # Pytest 配置和 fixtures
├── e2e/                           # Playwright E2E 测试 (77 spec.js, 409 用例)
│   ├── 01-auth.spec.js            # 认证流程测试
│   ├── 02-core-navigation.spec.js # 核心导航测试
│   ├── 03-chat.spec.js            # 聊天功能测试
│   ├── 04-tools-panel.spec.js     # 工具面板测试
│   ├── 05-tools-chat.spec.js      # 工具 + 聊天测试
│   ├── 06-project-generate.spec.js # 项目生成测试
│   ├── 07-image-generator.spec.js # 图像生成测试
│   ├── 08-workflow.spec.js        # 工作流测试
│   ├── 09-ppt-generator.spec.js   # PPT 生成测试
│   ├── 10-admin.spec.js           # 管理后台测试
│   ├── 11-apikey-management.spec.js # API Key 管理测试
│   ├── 11-theme-shortcuts.spec.js # 主题快捷测试
│   ├── smoke-test-simple.spec.js  # 冒烟测试 (推荐先跑)
│   ├── agent-*.spec.js            # Agent 系列 (20+ spec)
│   ├── auth-*.spec.js             # 认证系列
│   ├── test-*.spec.js             # 临时调试 spec
│   ├── fixtures/
│   │   └── auth.js                # 认证 helper 函数
│   └── (77 个 .spec.js)
├── unit/                          # 单元测试 (后端, 88 文件 / 1376 用例)
│   ├── test_agent.py              # Agent 系统测试
│   ├── test_agent_capabilities.py # Agent 能力测试
│   ├── test_comprehensive.py      # 综合单元测试
│   ├── test_v4_8_features.py      # v4.8 特性测试
│   ├── test_aicloud.py            # AI 云测试
│   ├── test_executor.py           # 执行器测试
│   ├── test_spec_first_generator.py # 规格优先生成测试
│   └── ... (88 文件)
├── integration/                   # 集成测试 (当前 2 文件, 历史 20+ 已归档)
│   ├── test_auth_api.py           # 认证 API (18 cases)
│   └── test_health_api.py         # 健康 API (6 cases)
├── performance/                   # 性能测试
│   ├── benchmark_apikey.py        # API Key 性能基准
│   └── test_smart_modifications.py # 智能修改性能测试
├── frontend/                      # 前端测试
│   └── test_components.py         # Vue 组件测试配置
└── archive/                       # 归档的历史测试 (56+ 文件)
    ├── legacy/                    # 旧版 Python 测试 (35+)
    ├── integration_old/           # 旧版集成测试 (21+)
    └── playwright/                # 旧版 Playwright 脚本
```

---

## 测试运行命令

### 全部测试

```bash
# pytest (Makefile / 脚本统一入口)
make test                       # 等价 pytest tests/ -v
make test-cov                   # 等价 pytest --cov=app --cov-report=html

# 完整命令
pytest tests/ -v --tb=short
pytest tests/unit/ -v            # 仅单元
pytest tests/integration/ -v    # 仅集成 (仅 2 文件)
pytest --cov=app --cov=src --cov-report=html
```

### Playwright E2E

```bash
# 冒烟测试 (推荐先跑，约 18 秒)
npx playwright test tests/e2e/smoke-test-simple.spec.js

# 所有 E2E
npx playwright test tests/e2e/ --reporter=list

# 指定文件
npx playwright test tests/e2e/01-auth.spec.js

# 带 UI 调试
npx playwright test --ui
```

### 当前 Playwright 配置 (`playwright.config.js` 根级)

```js
{
  testDir: './tests/e2e',
  fullyParallel: false,     // 串行
  workers: 1,               // 单 worker
  retries: 0,               // 不重试
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:3000',  // 前端 Vite 端口 (与历史 8000 不同)
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1024, height: 600 } } }
  ],
  outputDir: 'test-results/runs/',
}
```

> 注意：测试 baseURL 已从历史 `localhost:8000` 改为 `127.0.0.1:3000`（前端 Vite 开发服务器），因为当前架构是前后端分离：后端 8000 / 前端 3000，Vite 通过代理转发 `/api` 到后端。`configs/playwright.config.js` 保留了多浏览器并行配置用于 CI。

### 覆盖率配置

- 根 `pyproject.toml` + `configs/.coveragerc` 双份配置（合并生效）
- 源目录：`app, src`
- `fail_under=70`
- HTML 报告：`htmlcov/index.html`

---

## E2E 测试 (Playwright)

### 测试文件清单

| # | 文件 | 测试场景 | 覆盖功能 |
|---|------|----------|----------|
| 1 | `01-auth.spec.js` | 认证流程 | 登录/登出/Token 刷新/权限路由 |
| 2 | `02-core-navigation.spec.js` | 核心导航 | 页面跳转/路由守卫 |
| 3 | `03-chat.spec.js` | 聊天功能 | 消息发送/历史加载/SSE 流 |
| 4 | `04-tools-panel.spec.js` | 工具面板 | 工具切换/状态展示 |
| 5 | `05-tools-chat.spec.js` | 工具 + 聊天 | 工具调用/结果集成 |
| 6 | `06-project-generate.spec.js` | 项目生成 | 表单提交/进度跟踪 |
| 7 | `07-image-generator.spec.js` | 图像生成 | 文生图/参数配置 |
| 8 | `08-workflow.spec.js` | 工作流 | 流程定义/执行/历史 |
| 9 | `09-ppt-generator.spec.js` | PPT 生成 | 大纲生成/预览/下载 |
| 10 | `10-admin.spec.js` | 管理后台 | 资源控制/用户管理 |
| 11 | `11-theme-shortcuts.spec.js` | 主题快捷 | 主题切换/快捷键 |
| 12 | `smoke-test-simple.spec.js` | **冒烟测试** | **核心功能快速验证** ✅ |
| 13 | `test-smart-resume.spec.js` | **智能会话恢复** | **LLM 语义匹配恢复历史 session** ✅ |
| 14-43 | `agent-*.spec.js` | Agent 专项 | 多模态/诊断/能力/准确性 |
| 43-48 | 其他功能 | 扩展功能 | SSE/文件上传/系统监控等 |

### ✅ 冒烟测试 (smoke-test-simple.spec.js)

**目的**: 快速验证核心功能，日常开发使用

**测试用例**:
1. ✅ 后端 API 健康检查 (`/api/v1/health`)
2. ✅ 前端页面加载
3. ✅ 登录页面交互
4. ✅ API CSRF Token 获取
5. ✅ 文件上传 API 可用

**执行时间**: 18.3 秒  
**通过率**: **100% (5/5)**

**运行命令**:
```bash
# 运行冒烟测试
npx playwright test tests/e2e/smoke-test-simple.spec.js --reporter=list

# 查看报告
npx playwright show-report

# 有头模式调试
npx playwright test --headed
```

### Agent 专项 E2E 测试

| 文件 | 测试焦点 | 覆盖场景 |
|------|----------|----------|
| `test-smart-resume.spec.js` | 智能会话恢复 | LLM语义匹配/历史session搜索/相关性排序 |
| `agent-capability.spec.js` | 能力验证 | 代码生成/文件操作/多模态 |
| `agent-multimodal-test.spec.js` | 多模态 | 图像理解/OCR/视觉分析 |
| `agent-accurate-test.spec.js` | 准确性 | 代码准确率/需求理解 |
| `agent-full-diagnosis.spec.js` | 全诊断 | 端到端诊断流程 |
| `agent-error-diagnosis.spec.js` | 错误诊断 | 错误分类/修复建议 |
| `agent-token-diagnosis.spec.js` | Token 诊断 | Token 计数/优化建议 |
| `agent-generate-test.spec.js` | 代码生成 | 单文件生成/测试运行 |
| `agent-generate-full-test.spec.js` | 完整生成 | 多文件项目生成 |
| `agent-project-generation.spec.js` | 项目生成 | 项目管理/版本控制 |

### 如何运行 E2E 测试

```bash
# 运行所有 E2E 测试
npx playwright test tests/e2e/ --reporter=list

# 运行特定测试文件
npx playwright test tests/e2e/auth.spec.js

# 运行匹配名称的测试
npx playwright test -g "登录"

# 运行特定浏览器
npx playwright test --project=chromium

# 有头模式 (调试用)
npx playwright test --headed

# 查看 HTML 报告
npx playwright show-report

# 运行冒烟测试 (推荐日常使用)
npx playwright test tests/e2e/smoke-test-simple.spec.js
```

---

## 单元测试 (Pytest)

### 核心测试文件

| 文件 | 测试数 | 覆盖模块 | 关键测试 |
|------|--------|----------|----------|
| `test_comprehensive.py` | 50+ | 核心模块 | 需求解析/代码生成 |
| `test_v4_8_features.py` | 30+ | v4.8 特性 | DockerRunner/服务检测 |
| `test_agent.py` | 20+ | Agent 系统 | 工具执行/对话管理 |
| `test_aicloud.py` | 47 | AI 云 | 多供应商模型路由 |
| `test_executor.py` | 17 | 执行器 | 工具调用/结果解析 |
| `test_spec_first_generator.py` | 25+ | 规格优先 | 需求→设计→任务 |
| `test_state_machine.py` | 23 | 状态机 | 状态流转/并发控制 |
| `test_task_queue.py` | 27 | 任务队列 | 优先级/调度 |
| `test_security_services.py` | 24 | 安全服务 | CSRF/XSS/注入检测 |
| `test_graph_validator.py` | 14 | 图验证 | 依赖图/循环检测 |
| `test_database_services.py` | 23 | 数据库 | CRUD/事务 |
| `test_small_model_optimization.py` | 37 | 小模型优化 | 分块/摘要 |

### 运行单元测试

```bash
# 运行所有单元测试
pytest tests/unit/ -v

# 运行特定测试文件
pytest tests/unit/test_aicloud.py -v

# 运行匹配名称的测试
pytest -k "test_multi_provider" -v

# 查看覆盖率
pytest --cov=app --cov-report=html

# 仅运行失败测试
pytest --last-failed
```

---

## 集成测试 (API)

### API 测试清单

| 文件 | 端点 | 测试场景 |
|------|------|----------|
| `test_auth_api.py` | `/api/v1/login` `/api/v1/csrf-token` | 登录/CSRF/Token 刷新 |
| `test_ai_agent_api.py` | `/api/v1/ai/agent/*` | Agent 对话/工具调用 |
| `test_aicode_api.py` | `/api/v1/code/*` | 代码生成/审查 |
| `test_aicloud_api.py` | `/api/v1/aicloud/*` | 模型列表/切换 |
| `test_kolors_api.py` | `/api/v1/kolors/*` | 文生图/图生图 |
| `test_ppt_api.py` | `/api/v1/ppt/*` | PPT 生成/预览 |
| `test_file_upload_api.py` | `/api/v1/files/upload` | 文件上传/解析 |
| `test_vision_api.py` | `/api/v1/vision/*` | 图像理解/OCR |
| `test_v2_admin_api.py` | `/api/v2/admin/*` | 资源控制/熔断 |
| `test_health_api.py` | `/api/v1/health` | 健康检查/模型列表 |
| `test_girlai_api.py` | `/api/v1/girlai/*` | 虚拟 AI 对话 |
| `test_aiprojectcode_api.py` | `/api/v1/aiproject/*` | 项目生成/管理 |
| `test_kolors_history_api.py` | `/api/v1/kolors/history` | 图像历史 |
| `test_github_api.py` | `/api/v1/github/*` | Git 操作 |
| `test_task_queue_api.py` | `/api/v1/task-queue/*` | 任务队列管理 |

### 运行集成测试

```bash
# 运行所有集成测试
pytest tests/integration/ -v

# 运行特定 API 测试
pytest tests/integration/test_auth_api.py -v

# 跳过慢速测试
pytest -m "not slow" -v

# 需要后端服务运行
pytest tests/integration/ --backend-url=http://localhost:8000
```

---

## 测试配置

### Pytest 配置 (pytest.ini)

```ini
[pytest]
testpaths = tests/unit tests/integration
python_files = test_*.py
python_functions = test_*
addopts = -v --tb=short --strict-markers
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: marks tests as integration tests
    api: marks tests as API tests
```

### Playwright 配置 (playwright.config.ts)

```typescript
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  retries: 1,
  workers: 1,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report/html' }]
  ],
  use: {
    baseURL: 'http://localhost:8000',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
})
```

---

## 测试覆盖率

### 覆盖率目标

| 模块 | 当前覆盖率 | 目标 | 状态 |
|------|-----------|------|------|
| Agent 核心 | ~85% | 90% | 🟡 接近 |
| API 层 | ~80% | 85% | 🟡 接近 |
| Utils 工具 | ~75% | 80% | 🟡 接近 |
| 多供应商适配器 | 100% | 100% | ✅ 完成 |
| 前端组件 | ~60% | 70% | 🟡 改进中 |

### 查看覆盖率

```bash
# 生成覆盖率报告
pytest --cov=app --cov-report=html

# 查看 HTML 报告
open htmlcov/index.html

# 覆盖率摘要
pytest --cov=app --cov-report=term-missing
```

---

## 已知问题

### E2E 测试

| 问题 | 影响 | 解决方案 | 状态 |
|------|------|----------|------|
| 登录 UI 选择器脆弱 | 部分测试失败 | 使用宽松选择器 | ✅ 已修复 |
| 页面加载超时 | 随机失败 | 增加超时时间 | ✅ 已修复 |
| 并发执行冲突 | 资源竞争 | 串行执行 | ✅ 已修复 |
| 后端服务依赖 | 需要启动后端 | 手动或使用脚本 | 📝 文档化 |

### 单元测试

| 问题 | 影响 | 解决方案 |
|------|------|----------|
| 外部 API 依赖 | 需要 API Key | Mock 或跳过 |
| Docker 依赖 | 需要 Docker | Mock DockerRunner |
| 数据库状态 | 测试隔离 | 使用事务回滚 |

---

## 最佳实践

### 编写测试

1. **命名规范**
   ```python
   def test_<module>_<scenario>_<expected>:
       """测试描述""""
   ```

2. **AAA 模式** (Arrange-Act-Assert)
   ```python
   def test_example():
       # Arrange - 准备数据
       # Act - 执行操作
       # Assert - 验证结果
   ```

3. **Fixtures 复用**
   ```python
   @pytest.fixture
   def mock_db():
       # 准备 fixture
       yield
       # 清理
   ```

### 运行测试

1. **本地开发**: 运行冒烟测试
   ```bash
   npx playwright test tests/e2e/smoke-test-simple.spec.js
   ```

2. **CI/CD**: 运行所有测试
   ```bash
   npx playwright test tests/e2e/
   pytest tests/unit/ tests/integration/
   ```

3. **调试模式**:
   ```bash
   npx playwright test --headed --debug
   pytest -s --pdb
   ```

---

## 持续改进

### 进行中

- [ ] 增加前端组件单元测试 (Vitest)
- [ ] 完善 Agent 系统 E2E 覆盖
- [ ] 集成到 GitHub Actions

### 计划中

- [ ] 视觉回归测试
- [ ] 性能基准测试
- [ ] 安全扫描自动化

---

## 参考资料

- [Playwright 文档](https://playwright.dev)
- [Pytest 文档](https://docs.pytest.org)
- [E2E 测试报告](../tests/e2e/E2E-TEST-REPORT.md)
- [E2E 冒烟测试](E2E-TEST-DIAGNOSIS.md)
- [E2E 修复总结](FIX-SUMMARY.md)

---

*最后更新：2026-06-09*
