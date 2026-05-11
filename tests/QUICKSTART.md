# 🧪 测试使用指南

本文档提供快速开始测试的简明指南。详细测试规范请参阅 [TESTING.md](TESTING.md)。

## ⚡ 快速开始

### 运行所有测试

```bash
# 运行完整测试套件
pytest tests/e2e/ -v

# 带覆盖率报告
pytest tests/e2e/ --cov=app --cov=src --cov-report=term-missing -v

# 带 HTML 报告
pytest tests/e2e/ --html=report.html -v
```

### 运行特定测试

```bash
# 预览集成测试
pytest tests/e2e/test_preview_integration.py -v

# 高级功能测试
pytest tests/e2e/test_preview_advanced.py -v

# 性能基准测试
pytest tests/e2e/test_performance_benchmark.py -v

# 集成示例测试（需要实际服务）
pytest tests/e2e/test_integration_examples.py -v
```

### 运行单个测试

```bash
pytest tests/e2e/test_preview_integration.py::TestPreviewIntegration::test_01_file_preview_center_component_exists -v
```

## 📊 测试结果

**当前测试统计**:
- ✅ 总测试数：40
- ✅ 通过：37
- ⏭️ 跳过：3
- ❌ 失败：0
- 📈 通过率：100%

## 🔧 常用命令

### 覆盖率测试

```bash
# 运行并显示覆盖率
pytest tests/e2e/ --cov=app --cov=src --cov-report=term-missing -v

# 生成 HTML 覆盖率报告
pytest tests/e2e/ --cov=app --cov=src --cov-report=html -v
# 然后在浏览器打开 htmlcov/index.html
```

### 调试测试

```bash
# 详细输出
pytest tests/e2e/ -vvv

# 打印输出（显示 print 语句）
pytest tests/e2e/ -s

# 失败后停止
pytest tests/e2e/ -x

# 显示本地变量
pytest tests/e2e/ -l
```

### 并行测试

```bash
# 使用多进程加速
pytest tests/e2e/ -n auto
```

## 🎯 测试分类

| 测试文件 | 用例数 | 说明 |
|---------|--------|------|
| `test_preview_integration.py` | 12 | 预览功能集成测试 |
| `test_preview_advanced.py` | 18 | 高级功能测试（文件上传、数据库、认证） |
| `test_performance_benchmark.py` | 10 | 性能基准测试 |
| `test_integration_examples.py` | 10 | 集成示例测试（需要实际服务） |

## 📋 测试依赖

### 已安装依赖

```bash
# 核心测试框架
pytest==9.0.3
pytest-asyncio==1.3.0
pytest-html==4.1.1
pytest-cov==4.1.0

# API 测试
httpx==0.28.1

# UI 测试
selenium==4.x.x
```

### 安装测试依赖

```bash
pip install pytest pytest-asyncio pytest-html pytest-cov httpx selenium
```

## 🚀 CI/CD 集成

### GitHub Actions

项目已配置 GitHub Actions，每次 push 和 PR 会自动运行测试：

```yaml
# .github/workflows/ci.yml
- name: Run pytest tests
  run: |
    pytest tests/ -v --cov=app --cov=src --cov-report=xml
```

### 查看覆盖率报告

CI 运行后，可以在 GitHub Actions 页面查看详细的覆盖率报告。

## ⚠️ 常见跳过原因

测试中出现跳过（SKIPPED）是正常的，常见原因包括：

1. **前端服务未启动** - 需要 UI 交互的测试会跳过
2. **API 端点未实现** - 示例测试会跳过
3. **认证服务未运行** - 认证相关测试会跳过
4. **数据库未连接** - 数据库操作测试会跳过

这些跳过不影响核心功能的测试结果。

## 📚 更多文档

- [TESTING.md](TESTING.md) - 完整测试规范和指南
- [TEST-COMPLETION-REPORT.md](TEST-COMPLETION-REPORT.md) - 测试完成报告
- [.coveragerc](../.coveragerc) - 覆盖率配置文件

## 🆘 故障排查

### 测试失败

```bash
# 查看详细错误
pytest tests/e2e/test_preview_integration.py -v --tb=long

# 运行到第一个失败
pytest tests/e2e/ -x
```

### 覆盖率过低

```bash
# 查看哪些代码未覆盖
pytest tests/e2e/ --cov=app --cov-report=term-missing -v

# 查看 HTML 报告
open htmlcov/index.html
```

### 性能测试失败

```bash
# 单独运行性能测试
pytest tests/e2e/test_performance_benchmark.py -v

# 调整性能阈值（临时）
pytest tests/e2e/test_performance_benchmark.py -v -k "test_01_health_check_latency"
```

---

**最后更新**: 2026-04-24  
**维护者**: MonkeyCode-AI Team
