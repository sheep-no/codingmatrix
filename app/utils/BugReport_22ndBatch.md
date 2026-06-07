# Bug Report: app/utils/ Utility Modules (22nd Batch)

**Date**: 2026-06-07  
**Scope**: 51 utility modules under `app/utils/`  
**Focus Areas**: Async safety, error handling, security, logic errors

---

## Confirmed Bug (HIGH)

### BUG-22-01
- **File**: `app/utils/retry.py:52-63`
- **Problem**: `enable_jitter` parameter has no effect — both branches use identical `wait_exponential` strategy
- **Severity**: HIGH
- **Fix**: Implement jitter logic (e.g., random exponential backoff) when `enable_jitter=True`

### BUG-22-02
- **File**: `app/utils/http_client.py`
- **Problem**: `HTTPClientPool.get_client()` has no lock for lazy initialization — race condition when called concurrently from multiple coroutines
- **Severity**: HIGH
- **Fix**: Add `asyncio.Lock()` to protect client creation

### BUG-22-03
- **File**: `app/utils/AiCodeUtil.py:19-27`
- **Problem**: `get_embedding()` creates new `httpx.AsyncClient` per call instead of reusing shared client — connection pool exhaustion risk
- **Severity**: HIGH
- **Fix**: Reuse the shared `get_http_client()` instance

### BUG-22-04
- **File**: `app/utils/task_dispatcher.py:18`
- **Problem**: `_lock = asyncio.Lock()` at class level, but `__new__` is synchronous — lock not properly initialized for async context
- **Severity**: HIGH
- **Fix**: Initialize lock lazily in async method or use `asyncio.Lock()` in `__init__`

### BUG-22-05
- **File**: `app/utils/AiCodeUtil.py:19-27`
- **Problem**: Embedding cache uses `OrderedDict` without async lock protection for disk I/O — race condition when writing to disk concurrently
- **Severity**: HIGH
- **Fix**: Add `asyncio.Lock()` around cache read/write operations

---

## Confirmed Bug (MEDIUM)

### BUG-22-06
- **File**: `app/utils/task_manager.py:18`
- **Problem**: Hardcoded `REDIS_URL = "redis://localhost:6379/0"` instead of using config — will fail in production
- **Severity**: MEDIUM
- **Fix**: Read from environment variable or config file

### BUG-22-07
- **File**: `app/utils/web_search.py:30`
- **Problem**: `DISABLE_SSL_VERIFY` environment variable can disable SSL verification — security risk
- **Severity**: MEDIUM
- **Fix**: Remove or restrict this option, use proper certificate validation

### BUG-22-08
- **File**: `app/utils/process_guard.py`
- **Problem**: `find_pid_by_port` uses `asyncio.create_subprocess_shell` with f-string command — potential command injection if port is user-controlled
- **Severity**: MEDIUM
- **Fix**: Use `subprocess.exec` with argument list instead of shell string

### BUG-22-09
- **File**: `app/utils/service_config_manager.py`
- **Problem**: Uses `threading.RLock()` (sync lock) in async context — potential deadlock risk if called from async code
- **Severity**: MEDIUM
- **Fix**: Replace with `asyncio.Lock()` or use `asyncio.to_thread()` for sync operations

### BUG-22-10
- **File**: `app/utils/docker_runner.py`
- **Problem**: References `app.agent.test_framework_config`, `app.agent.framework_detector`, `app.agent.output_parser` — may cause import errors if not available
- **Severity**: MEDIUM
- **Fix**: Add try/except import or use lazy imports

---

## Excluded False Positives

### FP-22-01
- **File**: `app/utils/AiCodeUtil.py:19`
- **Why False**: `asyncio.Lock()` at module level is acceptable — asyncio locks are designed to be created at module level and used across coroutines

### FP-22-02
- **File**: `app/utils/encryption.py` / `app/utils/crypto.py`
- **Why False**: Both have `RSAKeyManager` classes — this is duplication but not a bug (both are used in different contexts)

---

## Summary

| Category | Count |
|----------|-------|
| Confirmed Bug (HIGH) | 5 |
| Confirmed Bug (MEDIUM) | 5 |
| Excluded False Positives | 2 |
| **Total Confirmed Bugs** | **10** |

**Top Issues Requiring Immediate Fix**:
1. BUG-22-01: Jitter parameter has no effect (retry logic)
2. BUG-22-02: Race condition in HTTP client pool initialization
3. BUG-22-03: Connection pool exhaustion from new client per call
4. BUG-22-04: asyncio.Lock initialization race in task dispatcher
5. BUG-22-05: Cache disk I/O race condition
