# Docker 集成实现

## 概述

CodingMatrix 集成了 Docker 能力，用于沙箱代码执行和隔离环境运行。

## 核心功能

| 功能 | 实现 | 文件 |
|------|------|------|
| 容器运行 | 动态创建容器执行代码 | `utils/docker_runner.py` |
| 资源限制 | CPU/内存限制 | `docker_runner.py` |
| 网络隔离 | 禁用外部网络访问 | `docker_runner.py` |
| 超时控制 | 自动终止超时容器 | `docker_runner.py` |

## DockerRunner 使用

```python
from app.utils.docker_runner import DockerRunner

runner = DockerRunner()
result = runner.run(
    image="python:3.11-slim",
    code="print('hello')",
    timeout=30,
    memory_limit="256m"
)
```

## 安全特性

- 容器运行后立即清理
- 无网络访问权限
- 文件系统只读 (除临时目录)
- CPU/内存硬限制

## API 端点

| 端点 | 权限 | 描述 |
|------|------|------|
| GET /api/v2/Controller/admin/docker/containers | super | 列出容器 |

## 配置

```env
DOCKER_ENABLED=true
DOCKER_TIMEOUT=30
DOCKER_MEMORY_LIMIT=256m
DOCKER_CPU_LIMIT=1.0
```
