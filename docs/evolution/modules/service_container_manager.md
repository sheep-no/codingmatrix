# service_container_manager.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-17 | 状态：已完成
> 归属：Agent 引擎 / 测试执行链（Docker 依赖服务容器管理）
> 路径：`app/utils/service_container_manager.py`（524 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块定位

ServiceContainerManager——DockerRunner 测试时启动依赖服务容器（Redis/PG/MySQL/MongoDB/RabbitMQ/Elasticsearch）。v4.8.0 新增（自动启动依赖服务容器）、v4.8.1 增强（ES 优化/并行启动/健康缓存 TTL 300s 复用）。

核心能力：
- `start_service_containers`——并行启动依赖服务容器（asyncio.gather + 健康缓存复用）
- `_start_and_register`/`_start_container`——单容器启动 + 健康检查（TCP 探测 + exec 命令双阶段）
- `wait_for_health`——供 DockerRunner 调用的整体健康等待
- `cleanup_containers`/`cleanup_all`——容器清理
- `detect_project_services`——从项目检测所需服务（requirements.txt/.env.example/docker-compose.yml 三源）

消费方：`docker_runner.py`（:469-474 启动服务容器、:521-528 健康等待、:585 清理）、`orchestrator_testing.py:229`（detect_project_services）。

## 2. 依赖链与消费方

```
DockerRunner.run_validation（docker_runner.py）
  ├─ ServiceContainerManager.start_service_containers(required_services, client)
  │    ├─ _start_and_register → _start_container → _wait_for_health_single（TCP + exec）
  │    ├─ 健康缓存复用（TTL 300s）
  │    └─ _generate_test_env_vars（service_config_templates.get_service_template）
  ├─ ServiceContainerManager.wait_for_health(service_containers, client)
  ├─ generate_test_env_vars → 注入验证容器 env
  └─ finally: ServiceContainerManager.cleanup_containers(client)
```

- 消费外部：`service_config_templates.get_service_template`（env 模板，SCT4 详档端口误伤源头在本模块 :399-401）
- 被消费方：DockerRunner（docker_runner 详档 DR 家族）；`detect_project_services` 另被 orchestrator_testing:229 消费

## 3. 发现

### SCM1 [P2] `cleanup_containers` 缓存判断写反——服务容器在 TTL 内永不停止（全库确认）

- **Bug 代码**：:412-415

```python
for service_name, container_id in self._running_containers.items():
    cached = self._health_cache.get(service_name)
    if cached and cached.container_id == container_id:
        continue
```

- **根因**：`_start_and_register` **每次启动都写入健康缓存**（:198-202，`_HealthCacheEntry(container_id=本次容器 id, ...)`），所以「本次新启动的容器」其 ID 一定在缓存中且等于 running_containers 中的 id → :414 条件恒 True → `continue` 跳过停止。缓存复用的容器（:153 `self._running_containers[svc] = cached.container_id`）同样命中缓存 → 也不停止。
- **影响**：docstring 声称「仅清理本次启动的」（:408）但实现恰好**跳过本次启动的全部容器**——docker 测试每次 run_validation 结束都调 cleanup_containers（docker_runner finally :585），而测试时长通常 <300s TTL，缓存新鲜 → **服务容器全部泄漏不停止**，仅当 TTL 过期后缓存失效、重新启动新容器（:414 不等）时才停止新容器——容器资源随时间累积耗尽（与 DR7 谎报成功叠加，docker 依赖服务管理三端失效）。

### SCM2 [P2] 健康命令失败当健康通过（DGV1 放行家族）

- **Bug 代码**：:312-313

```python
logger.warning(f"服务 {service_name} exec 健康检查未通过")
return True  # TCP 已通，视为基本可用
```

- **根因**：exec 精确健康命令（`redis-cli ping`/`pg_isready`/`curl -sf http://localhost:9200/_cluster/health`）10s 内持续失败 → 仅 warning 后 `return True`——**「TCP 已通」覆盖「应用层未就绪」**。
- **影响**：服务进程起来但应用未就绪（ES 正在启动、DB 未接受连接）时仍判健康 → 测试在依赖未就绪时运行（DGV1「验证失败兜底通过」家族在依赖服务健康检查的实例；与 UT5 沙箱恒通过/DR2 安全扫描放行同主线）。

### SCM3 [P2] `_start_container` 健康检查失败仍返回 container_id（全库确认）

- **Bug 代码**：:252-257

```python
health_ok = await self._wait_for_health_single(...)
if not health_ok:
    logger.warning(f"服务 {service_name} 健康检查超时")
return container_id
```

- **根因**：健康检查失败仅 warning，仍返回容器 ID → `_start_and_register` 认为启动成功（:183 `if not container_id: return None` 只判容器创建失败）→ 调用方（docker_runner）以为服务就绪。
- **影响**：与 SCM2 叠加——**健康检查整体空转**（失败既不阻断也不反馈），docker_runner:524-527 依赖 wait_for_health 返回 False 才失败，而 wait_for_health 因缓存（:334-336）基本空转（SCM8）。

### SCM4 [P3] `detect_project_services` 子串假阳性（PP8/BE1 家族）

- **Bug 代码**：:517 `if image_key in content.lower()`（docker-compose 内容子串）+ :499 `if var_name in content`（.env.example 内容子串）。
- **根因**：`"redis" in compose_content`——注释/服务名/镜像名含关键词即命中（compose 里 `image: redis:7-alpine` 的 redis、名为 `mysql-db` 的服务、注释 `# mongo backup` 全命中）；`.env.example` 注释里的 `MONGODB_URL` 也命中。
- **影响**：多启动非必要服务容器（资源浪费 + 端口占用）；要求 Python 项目有 requirements.txt/.env.example/docker-compose.yml 三源之一，pyproject.toml 项目漏检测。

### SCM5 [P3] `_port_is_open_async` 同步 socket 阻塞事件循环（TR5 家族）

- **Bug 代码**：:344-355 `sock = socket.socket(...)` + `sock.connect_ex(...)` settimeout(1) **同步阻塞调用在 async 函数内**，:283-288 while 循环最多 `min(startup_timeout,15)` 次、每次 1s 超时——未用 `asyncio.to_thread`/`asyncio.open_connection`。
- **影响**：最多 15s/服务的事件循环阻塞（并行启动 N 服务叠加）。

### SCM6 [P3] `_find_available_port` 并发竞态 + 单次重试不验证（MCP1 家族）

- **Bug 代码**：:373-385 `while port in self._allocated_ports: port += 1` 非原子检查 + bind OSError 仅 `return port + 1`（不循环重试、不验证 port+1 是否也被占）。
- **影响**：并发启动（asyncio.gather 多服务）端口分配竞态；占用时可能返回仍被占的端口 → 容器启动失败（Docker APIError）。

### SCM7 [P3] `startup_timeout` 被 `min(startup_timeout, 15)` 硬编码截断（TFC4 家族）

- **Bug 代码**：:283 `while (time.time() - tcp_start) < min(startup_timeout, 15):`——elasticsearch 配置 `startup_timeout: 45`（:85）被截断到 15s。
- **影响**：ES 冷启动通常 >15s，TCP 探测提前放弃 → `return False` → 服务判未就绪（或 SCM2 误判通过）。

### SCM8 [P3] `wait_for_health` 与 `_start_container` 双健康检查（缓存使第二次空转）

- **Bug 代码**：`_start_container` Phase2 已做健康检查（:252-254），docker_runner:521-523 又调 `wait_for_health`；wait_for_health :334-336 缓存命中 continue——刚启动的服务缓存必然新鲜 → 第二次检查基本全跳过。
- **影响**：docker_runner 侧健康等待是「无操作」装饰（cache TTL 内恒过）；若 `_start_container` 已失败（SCM3 返回 id），wait_for_health 也无法再拦截。

### SCM9 [P3] `_generate_test_env_vars` 异常静默返回 {}（EC3 静默降级家族）

- **Bug 代码**：:404-405 `except Exception: return {}`——get_service_template 异常/模板缺失 → 空 env_vars，服务连接环境变量缺失。
- **影响**：测试容器里缺少 DATABASE_URL 等变量时**无任何告警**（与 detect_project_services 检测到服务但 env 注入失败的「启动成功但连不上」场景叠加）。

## 4. 演化方向

依赖服务容器管理「启动→健康→清理」三环：
- **清理环（SCM1）最严重**——缓存判断写反使容器永不停止，修复：cleanup_containers 应停止 running_containers 中的全部（缓存复用者除外仅当显式声明持久），或缓存写入与 running 分离——「本次启动的应清理，缓存的复用者按 TTL 到期才清理」
- **健康环（SCM2/SCM3/SCM7）**——健康命令失败放行 + 启动失败仍返回 id + 超时截断，修复：exec 健康失败即 return False（不因 TCP 已通放行）、_start_container 健康失败 return None、startup_timeout 尊重配置值
- **检测环（SCM4）**——词边界/键名精确匹配替代子串；requirements.txt 之外补 pyproject.toml/package.json 源

## 5. 主线关联

- **DGV1「验证失败兜底通过」家族**：SCM2（健康失败当通过）与 UT5（沙箱恒通过）/DR2（安全扫描放行）/DGV1/EC3 同族——验证执行端「失败放行」在依赖服务健康检查的又一实例
- **「存在≠正确」测试执行链**：docker 依赖服务三环（启动 SCM3/健康 SCM2/清理 SCM1）全部不可信——与 docker_runner 详档 DR1-DR7（依赖安装恒失败/超时缺失/验证任务谎报）共同构成 docker 验证侧「启动不可信 + 健康不可信 + 清理不可信 + 结果不可信」四端全失
- **容器资源泄漏**：SCM1 与 DR5（每次实例化 pull 镜像）叠加——docker 侧资源持续累积
- **双份配置**：SERVICE_CONTAINER_CONFIGS 与 service_config_templates.SERVICE_TEMPLATES 并存（SCT 详档 SCT4 端口误伤源头即本模块 :399-401 的全局子串 replace）
- **同步阻塞**：SCM5 加入 TR5 家族

## 6. 测试状态

- **零单元测试**：tests/ 下无任何 ServiceContainerManager/detect_project_services 引用（docker 依赖需 mock，但 detect_project_services 纯文件解析可测）
- SCM1-SCM3 三个 P2 项全部全库确认，零用例保护——容器泄漏/健康放行/启动失败返回 id 均无测试约束
