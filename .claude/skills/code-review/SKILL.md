# Code Review Skill

## 描述

多维度代码审查 Skill 系统，支持 production、security、performance、testing、accessibility、documentation 等维度的代码审查。

## Skill 列表

### production - 生产就绪

**描述**: 遵循生产级代码标准

**检查项**:
- 错误处理完整性
- 日志记录
- 配置管理
- 环境变量使用
- 资源管理

**规则**:
- 所有外部调用必须有 try-except 包裹
- 敏感信息必须从环境变量读取
- 必须有适当的日志记录
- 不能有硬编码的配置值

---

### security - 安全优先

**描述**: 强化安全实践，遵循 OWASP 安全最佳实践

**检查项**:
- 输入验证
- SQL 注入防护
- XSS 防护
- CSRF 防护
- 认证授权
- 敏感数据加密
- 密码安全

**规则**:
- 所有用户输入必须验证和清理
- 数据库查询必须使用参数化
- 输出必须 HTML 转义
- 密码必须哈希存储
- 敏感数据必须加密传输

---

### performance - 性能优化

**描述**: 高性能代码设计

**检查项**:
- 算法复杂度
- 数据库查询优化
- 缓存使用
- 异步处理
- 资源管理

**规则**:
- 避免 N+1 查询问题
- 大数据集必须分页
- 重复计算结果必须缓存
- IO 操作必须异步
- 及时释放资源

---

### testing - 测试驱动

**描述**: 完整测试覆盖

**检查项**:
- 单元测试覆盖率
- 集成测试
- 边界条件测试
- 异常场景测试

**规则**:
- 核心功能单元测试覆盖率 > 80%
- 关键路径必须有集成测试
- 边界条件必须测试
- 异常情况必须测试

---

### accessibility - 无障碍

**描述**: 符合 WCAG 无障碍标准

**检查项**:
- 语义化 HTML
- ARIA 属性
- 键盘导航
- 颜色对比度
- 屏幕阅读器兼容

**规则**:
- 所有图片必须有 alt 属性
- 表单必须有 label
- 颜色对比度至少 4.5:1
- 支持键盘导航
- 使用语义化标签

---

### documentation - 文档完善

**描述**: 详细文档和注释

**检查项**:
- 函数文档字符串
- 类文档字符串
- 模块文档
- 代码注释
- README 文档

**规则**:
- 所有公共函数必须有 docstring
- 复杂逻辑必须有注释
- 模块必须有说明文档
- API 必须有使用示例

---

## 使用方式

### 在 CodeReviewAgent 中使用

```python
from app.utils.review.code_review_agent import CodeReviewAgent

# 启用特定 skills
agent = CodeReviewAgent(skills=["production", "security"])

# 执行审查
issues = await agent.review_code(file_path)
```

### 可用的 Skill ID

| Skill ID | 名称 | 权重 |
|----------|------|------|
| production | 生产就绪 | 1.5 |
| security | 安全优先 | 2.0 |
| performance | 性能优化 | 1.3 |
| testing | 测试驱动 | 1.2 |
| accessibility | 无障碍 | 1.0 |
| documentation | 文档完善 | 0.8 |

---

## AI 提示词模板

### 安全审查提示词

```
你是一个安全专家，请根据以下安全要求审查代码：

【安全要求】
1. 所有用户输入必须经过严格验证
2. 数据库查询必须使用参数化，禁止字符串拼接
3. 输出到 HTML 的内容必须转义
4. 密码必须使用 bcrypt 或 Argon2 哈希
5. 实现 CSRF 保护（双重提交 Cookie 模式）
6. 敏感数据必须加密存储

【OWASP Top 10】
- A01: 访问控制失效 - 实现 RBAC
- A02: 加密机制失效 - 使用强加密算法
- A03: 注入 - 参数化查询
- A04: 不安全设计 - 威胁建模
- A05: 安全配置错误 - 安全默认配置
```

### 生产就绪提示词

```
你是一个专业的软件工程师，请根据以下要求审查代码：

【核心要求】
1. 所有外部调用必须有完整的错误处理
2. 使用 logging 模块进行结构化日志记录
3. 配置项从环境变量或配置文件读取，禁止硬编码
4. 使用上下文管理器（with 语句）管理资源
5. 关键操作必须有重试机制和超时控制

【代码质量】
- 遵循 PEP 8 规范
- 函数长度控制在 50 行以内
- 使用类型注解
- 避免嵌套过深（不超过 3 层）
```

---

## 相关资源

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Python Security Best Practices](https://docs.python-guide.org/writing/security/)
- [Python Logging HOWTO](https://docs.python.org/3/howto/logging.html)
- [WCAG Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
