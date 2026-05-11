# 生产就绪 Skill (production-ready)

## 描述
确保代码达到生产环境标准，遵循工业级最佳实践。

## 检查项
- [x] 错误处理完整性
- [x] 日志记录
- [x] 配置管理
- [x] 环境变量使用
- [x] 资源管理
- [x] 异常恢复

## 规则

### 1. 错误处理
```python
# ✅ 正确
try:
    result = external_api_call()
except requests.exceptions.Timeout:
    logger.warning("API 超时，使用缓存数据")
    result = get_cached_data()
except requests.exceptions.RequestException as e:
    logger.error(f"API 调用失败：{e}")
    raise

# ❌ 错误
result = external_api_call()  # 没有错误处理
```

### 2. 日志记录
```python
# ✅ 正确
import logging
logger = logging.getLogger(__name__)

logger.info("用户登录成功", extra={"user_id": user_id})
logger.warning("尝试登录失败", extra={"attempts": attempts})
logger.error("数据库连接失败", exc_info=True)

# ❌ 错误
print("用户登录了")  # 使用 print
print(f"错误：{e}")  # 没有堆栈跟踪
```

### 3. 配置管理
```python
# ✅ 正确
import os
from app.core.config import settings

DATABASE_URL = os.getenv("DATABASE_URL", settings.default_db_url)
API_KEY = settings.api_key  # 从配置中心读取

# ❌ 错误
DATABASE_URL = "postgresql://user:pass@localhost/db"  # 硬编码
API_KEY = "sk-1234567890"  # 硬编码密钥
```

### 4. 资源管理
```python
# ✅ 正确
with open("file.txt", "r") as f:
    content = f.read()

async with aiohttp.ClientSession() as session:
    async with session.get(url) as response:
        data = await response.json()

# ❌ 错误
f = open("file.txt", "r")
content = f.read()
# 忘记关闭文件
```

## AI 提示词模板

```
你是一个专业的软件工程师，请根据以下要求生成生产就绪的代码：

【核心要求】
1. 所有外部调用必须有完整的错误处理
2. 使用 logging 模块进行结构化日志记录
3. 配置项从环境变量或配置文件读取，禁止硬编码
4. 使用上下文管理器（with 语句）管理资源
5. 关键操作必须有重试机制和超时控制
6. 函数和类必须有完整的文档字符串

【代码质量】
- 遵循 PEP 8 规范
- 函数长度控制在 50 行以内
- 使用类型注解
- 避免嵌套过深（不超过 3 层）

【安全考虑】
- 验证所有用户输入
- 不暴露敏感信息
- 使用参数化查询防止 SQL 注入

请生成符合上述标准的代码。
```

## 验证清单

- [ ] 所有 public 函数都有 docstring
- [ ] 所有外部 IO 都有异常处理
- [ ] 日志级别使用正确（INFO/WARNING/ERROR）
- [ ] 无硬编码配置
- [ ] 资源正确释放
- [ ] 有适当的超时和重试机制
- [ ] 敏感信息已脱敏

## 相关资源

- [Python Logging HOWTO](https://docs.python.org/3/howto/logging.html)
- [The Twelve-Factor App](https://12factor.net/)
- [PEP 8 Style Guide](https://pep8.org/)
