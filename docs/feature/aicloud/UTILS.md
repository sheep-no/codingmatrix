# Aicloud 工具函数

## 工具模块位置: `app/utils/aicloud/`

### 核心工具

| 工具 | 文件 | 描述 |
|------|------|------|
| API Client | `api_client.py` | SiliconFlow API 客户端封装 |
| Session Manager | `session_manager.py` | 会话生命周期管理 |
| Code Executor | `code_executor.py` | 沙箱代码执行 |
| File Manager | `file_manager.py` | 文件读写操作 |
| Audit Logger | `audit_logger.py` | 审计日志记录 |
| Review Engine | `review_engine.py` | 内容审查 |

### 使用示例

```python
from app.utils.aicloud.session_manager import SessionManager
from app.utils.aicloud.audit_logger import AuditLogger

# 创建会话
manager = SessionManager()
session = manager.create_session(user_id="1", model="qwen2.5-coder")

# 记录审计日志
logger = AuditLogger()
logger.log(session_id=session.id, action="chat", user_id="1")
```
