# ServiceConfigTemplates 演化深扫文档

> 版本：v1.0 | 扫描日期：2026-08-14 | 状态：已完成
> 归属：Agent 引擎 / 服务配置模板库（A1-A15 服务支撑）
> 路径：app/agent/service_config_templates.py（461 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

- 第三方服务标准配置模板库：6 种基础设施服务（Redis / PostgreSQL / MySQL / MongoDB / RabbitMQ / Elasticsearch）的标准配置，每种含 Python 包、env 变量、docker-compose 服务定义、连接代码模板，供架构师生成与一致性验证使用（docstring v4.8.0）。
- 主要组成：
  - `ServiceTemplate` dataclass（:17-28）：name / category / python_packages / env_vars / docker_service / connection_code / health_check_command / default_port / docker_image 九字段。
  - `SERVICE_TEMPLATES` 常量表（:31-281）：6 个服务模板实例。
  - 7 个公开函数：`get_service_template`（:284）、`get_all_service_names`（:289）、`detect_services_from_requirements`（:294）、`generate_env_example`（:326）、`generate_docker_compose`（:365）、`get_python_packages_for_services`（:444）、`get_connection_snippets`（:454）。
- 对外接口：`get_service_template` 被 service_container_manager 唯一生产消费；其余 6 函数生产零消费方。

## 2. 依赖与被依赖

- 导入依赖：仅标准库（logging / typing / dataclasses），无第三方运行依赖。
- 生产使用方：`app/utils/service_container_manager.py:392-393`——`_generate_test_env_vars` 内延迟 import `get_service_template`，用 `template.env_vars` 做测试环境变量端口重映射（:397-402）。**仅用 env_vars 字段**，docker_service / connection_code / python_packages / health_check_command 全部未消费。
- 测试覆盖：`tests/unit/test_service_dependency.py:14-82`——TestServiceConfigTemplates 9 个用例覆盖 6 模板存在性、4 字段抽查、detect（6 关键词断言）、env/compose/packages/snippets 生成断言。32 passed（含同文件 DynamicPackageManager / ServiceContainerManager / DependencyGraph 用例）。

## 3. 已探明 Bug（含 bug 代码）

### SCT1 [P1] `generate_docker_compose` 的 depends_on 产出 Python dict 字面量，docker-compose 无法解析

- **现象**：`generate_docker_compose(["redis","postgresql"])` 输出的 app 服务段 `depends_on` 为：
  ```yaml
    depends_on:
      -
        redis: {'condition': 'service_healthy'}
      -
        postgres: {'condition': 'service_healthy'}
  ```
  `{'condition': 'service_healthy'}` 是 Python dict 的 repr 字面量。PyYAML 可解析为 `[{'redis': {'condition': 'service_healthy'}}, {'postgres': ...}]`（list 元素为 dict），但 docker-compose 规范要求 `depends_on` 是 service 名 list 或 `{svc: {condition}}` map——**list 元素为 dict 的形式 docker compose up 直接报错拒绝**。
- **Bug 代码**：
  ```python
  # service_config_templates.py:400-403 构造 list 内含 dict
  for svc_name in template.docker_service:
      app_service["depends_on"].append({
          svc_name: {"condition": "service_healthy"}
      })
  # :424-428 渲染 list 时 item 是 dict，:427 对 dict 内 value 直接 f-string
  for item in val:
      if isinstance(item, dict):
          lines.append("      -")
          for k3, v3 in item.items():
              lines.append(f"        {k3}: {v3}")  # v3 是 dict → Python repr
  ```
- **根因**：渲染器对 list-of-dict 只做一层 dict 展开，内层 dict（condition）未按 YAML 嵌套缩进展开，直接用 f-string 输出 Python repr。正确应输出 `redis:\n        condition: service_healthy` 或短格式 `- redis`。
- **影响**：该函数一旦被接线即产出不可用的 docker-compose.yml。当前函数生产零消费方（SCT5），属「接线即崩」（与 DG1 同类）。
- **触发条件**：`generate_docker_compose` 传入任意 ≥1 个服务，且模板 docker_service 含多个服务（全部 6 模板都触发）。
- **验证方式**：
  ```python
  import yaml
  from app.agent.service_config_templates import generate_docker_compose
  data = yaml.safe_load(generate_docker_compose(["redis"]))
  dd = data["services"]["app"]["depends_on"]
  # -> [{'redis': {'condition': 'service_healthy'}}]，list 元素为 dict，docker-compose 拒绝
  ```

### SCT2 [P2] `detect_services_from_requirements` 短通用词子串误报

- **现象**（实测）：`detect_services_from_requirements("Users need these services")` → `['elasticsearch']`；`"The user session stores tokens"` → `['redis', 'elasticsearch']`；`"business analysis report"` → `['elasticsearch']`。纯英文普通文本几乎必然误检。
- **Bug 代码**：
  ```python
  # service_config_templates.py:304-323
  DETECTION_KEYWORDS = {
      "elasticsearch": ["elasticsearch", "es", "搜索", "search engine", "全文检索"],
      "redis": ["redis", "缓存", "cache", "session store"],
      ...
  }
  for keyword in keywords:
      if keyword in requirement_lower:  # 子串匹配，"es" 命中 "these/users/services"
  ```
- **根因**：`es`（elasticsearch）、`cache`、`search`、`session store` 是通用英文词，`in` 子串匹配无词边界，`es` 出现在大量普通英文单词中。`redis` 关键词组含 `session store` 亦误匹配普通「会话存储」表述。
- **影响**：一旦接线（架构师依赖检测选服务），普通需求会凭空注入 elasticsearch / redis 依赖，放大后续 docker-compose 体积与容器启动成本。当前生产零消费方，误报面被 SCT5 暂时掩盖。
- **触发条件**：需求文本含 `es`/`cache`/`search`/`session store`/`queue`/`mq`/`pg` 等通用词（前 6 项 keywords 中 5 项是通用英文词）。
- **验证方式**：`detect_services_from_requirements("Users need these services")` 断言返回空，实测返回 `['elasticsearch']`。

### SCT3 [P2] 6 个模板 connection_code 全部使用 `os.getenv` 但未 `import os`

- **现象**（实测）：redis 模板 `connection_code` 首行 `import redis`，后续 `os.getenv("REDIS_URL", ...)` 直接用 `os`；6 模板全部 `uses os.getenv=True, imports os=False`。用户按模板复制即 `NameError: name 'os' is not defined`。
- **Bug 代码**：
  ```python
  # service_config_templates.py:56-64 redis 模板
  connection_code="""import redis
  from urllib.parse import urlparse
  REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")  # os 未导入
  ...
  """
  ```
- **根因**：模板代码漏写 `import os`，6 个模板（:56/:99/:145/:189/:231/:269）同错。
- **影响**：connection_code 是「生成给用户的标准连接代码」，复制即崩。`get_connection_snippets` 一旦接线，生成的连接代码全量不可直接运行。
- **触发条件**：用户复制任意模板的 connection_code 运行。
- **验证方式**：`exec(t.connection_code)`（不含 `import os` 前缀）抛 `NameError`。

### SCT4 [P2] `_generate_test_env_vars` 端口替换用全局子串 replace 误伤非端口字段

- **现象**：端口重映射 `str.replace(str(internal_port), str(actual_port))` 对 env 值做**全局子串替换**。实测密码含端口数字被误改：`'amqp://guest:pass5672word@localhost:5672/'` 在映射 `{5672: 5000}` 下变为 `pass5000word@localhost:5000/`——密码部分被破坏。
- **Bug 代码**：
  ```python
  # app/utils/service_container_manager.py:399-402
  for internal_port, actual_port in port_mapping.items():
      env_vars[var_name] = env_vars[var_name].replace(
          str(internal_port), str(actual_port)
      )
  ```
- **根因**：无 URL 解析，对整串做数字子串替换；URL 中 host 端口外的任意数字串（密码、用户名、数据库序号、path 参数）只要恰含端口数字即被误改。
- **影响**：测试容器启动时注入的环境变量中，密码/路径字段可能被破坏导致服务认证失败。当前模板默认密码为空/简单数字串，触发面低，但用户自定义 env 值即触发。
- **触发条件**：env 值（URL/密码/路径）含与映射端口相同的数字子串，且不在端口位置。
- **验证方式**：见上述实测——`"pass5672word@localhost:5672"` 映射 `{5672: 5000}` 后密码被替换。

### SCT5 [P1] 7 个公开函数中 6 个生产零消费方（「能力未接线」家族第八例）

- **现象**（实测）：`rg` 全库精确引用，生产代码仅 `service_container_manager.py:392` import `get_service_template`；`get_all_service_names` / `detect_services_from_requirements` / `generate_env_example` / `generate_docker_compose` / `get_python_packages_for_services` / `get_connection_snippets` **6 函数零生产消费方**，只在 `tests/unit/test_service_dependency.py` 被调用。
- **Bug 代码**：无——是能力未被接线。
- **根因**：docstring 声称「用于架构师生成和一致性验证」，但架构师的 .env / docker-compose 生成实际走 LLM 提示（spec_first_generator.py config_hint），从未调用本模块；`SERVICE_TEMPLATES` 的镜像/健康检查信息被 `SERVICE_CONTAINER_CONFIGS`（service_container_manager.py:25）手工复制了一份独立配置。
- **影响**：整套「确定性服务配置生成」能力从未生效——生成链的服务配置靠 LLM 自由发挥，模板库只是死数据。检测（SCT2）/生成（SCT1/SCT3）缺陷因未接线而隐而不发。
- **触发条件**：无需触发——持续未接线状态。
- **验证方式**：`rg "get_all_service_names|detect_services_from_requirements|generate_env_example|generate_docker_compose|get_python_packages_for_services|get_connection_snippets" app/`（排除自身文件）返回空。

### SCT6 [P2] 服务配置双份拷贝漂移风险（SERVICE_TEMPLATES vs SERVICE_CONTAINER_CONFIGS）

- **现象**（实测对比）：`SERVICE_CONTAINER_CONFIGS`（service_container_manager.py:25）与 `SERVICE_TEMPLATES` 各自维护 6 服务的 image / 端口 / 健康检查。当前 6 服务 image 与 health_cmd 完全一致（elasticsearch:8.12.0 / mongo:7 / mysql:8.0 / postgres:16-alpine / rabbitmq:3-management-alpine / redis:7-alpine），但**手工重复、无单向来源**。
- **Bug 代码**：
  ```python
  # service_container_manager.py:25 SERVICE_CONTAINER_CONFIGS（镜像/端口/health_cmd 手工副本）
  SERVICE_CONTAINER_CONFIGS: Dict[str, Dict] = { ... }
  # service_config_templates.py:31 SERVICE_TEMPLATES（docker_image/health_check_command 另一份）
  ```
- **根因**：两份配置同义数据无共享来源，改动任一份不联动另一份。
- **影响**：升级镜像 / 调整健康检查时极易只改一处 → 测试容器管理与模板生成用的镜像版本漂移，长期不可观测。
- **触发条件**：任一侧升级服务镜像/健康检查。
- **验证方式**：对比两表 image 字段——当前一致，属漂移风险而非既有不一致。

### SCT7 [P2] `generate_env_example` 空密码产生空值 env 行 + SECRET_KEY 硬编码弱口令

- **现象**：redis 模板 `REDIS_PASSWORD: ""`（:39）→ 生成 `.env.example` 输出 `REDIS_PASSWORD=` 空值行；`generate_docker_compose` 解析该行 `key, val = line.split("=", 1)`（:408-410）得到空 val 并注入 app 环境 `REDIS_PASSWORD=`。docker-compose 语义上空字符串 ≠ 未设置，可能覆盖镜像默认行为。
- **Bug 代码**：
  ```python
  # service_config_templates.py:39
  "REDIS_PASSWORD": "",
  # :405-410 generate_docker_compose 把 .env.example 全量灌入 app service
  env_content = generate_env_example(services)
  for line in env_content.split("\n"):
      if "=" in line and not line.startswith("#") and line:
          key, val = line.split("=", 1)
          app_service["environment"].append(f"{key.strip()}={val.strip()}")
  ```
- **根因**：模板允许空默认值，生成器不做空值过滤；同时 `SECRET_KEY=change-me-in-production`（:341）硬编码弱口令直接进入生成配置。
- **影响**：接线后生成的 compose 含空/弱安全配置，生产误用有安全风险（弱 SECRET_KEY / 空密码）。
- **触发条件**：`generate_env_example`/`generate_docker_compose` 生成含空值模板的服务配置。
- **验证方式**：`"REDIS_PASSWORD=" in generate_env_example(["redis"])` 为 True。

## 4. 潜在问题与未知点

- **`default_port` 与 docker ports / env URL 三处重复**：每模板 `default_port`、`docker_service["ports"]`、env_vars URL 内嵌端口三处手工一致（实测全部一致），无校验，改一处不联动。
- **`app_service` 硬编码 `ports: ["8000:8000"]` / `build: {context: ".", dockerfile: "Dockerfile"}`**（:389-395）：与 `_find_available_port` 动态端口分配（service_container_manager.py:373-385）逻辑脱节——compose 生成固定 8000，容器管理器动态换端口，两套端口语义并存。
- **`version: '3.8'`（:414）已废弃**：docker compose v2 忽略并告警（兼容但提示冗余）。
- **`get_service_template` 大小写/别名**：只做 `service_name.lower()`（:286），`postgres`/`mongo`/`es` 等别名与 DETECTION_KEYWORDS 内提到的别名（:306-310 用 postgresql/mongodb 键）不统一，外部按别名查恒 None。
- **模板 Dockerfile 构建场景**：`docker_service` 生成的 healthcheck/test 列表（如 `["CMD", "redis-cli", "ping"]`）经 :424-428 渲染为合法 YAML 列表，但 value 含空格/特殊字符时无引号包裹（如 `command: redis-server --appendonly yes` 为裸字符串，YAML plain scalar 合法但有歧义风险）。

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P1 | `generate_docker_compose` 的 depends_on 渲染：dict value 按嵌套缩进展开为 `svc:\n    condition: service_healthy`，或直接输出短格式 `- svc_name` | 产出 docker-compose 可解析的合法 depends_on | service_config_templates.py:424-428 | #464 |
| 2 | P1 | 接线：在架构师/生成链接入 `detect_services_from_requirements` + `generate_env_example`/`generate_docker_compose`（替代 spec_first 的 config_hint LLM 提示），并将 `SERVICE_CONTAINER_CONFIGS` 收敛为 `SERVICE_TEMPLATES` 派生 | 「能力未接线」第八例落地——确定性服务配置生成替代 LLM 自由发挥；消除双份配置漂移 | spec_first_generator.py config_hint / service_container_manager.py:25 | #465 |
| 3 | P2 | DETECTION_KEYWORDS 用词边界正则（`\bword\b`）+ 移除 `es`/`cache`/`session store` 等通用词，改按 URL/端口/常见框架特征精确检测 | 消除「Users need these services」→elasticsearch 类误报 | service_config_templates.py:304-323 | #466 |
| 4 | P2 | 6 个 connection_code 模板统一加 `import os`（或改 `os.environ.get`），可加一次生成后静态校验 | 模板代码复制即用，消除 NameError | service_config_templates.py:56/99/145/189/231/269 | #467 |
| 5 | P2 | `_generate_test_env_vars` 端口替换改用 urllib URL 解析（只替换 host 端口段）或正则 `:\d+` 边界替换 | 密码/路径中数字串不被误替换 | app/utils/service_container_manager.py:399-402 | #468 |
| 6 | P2 | 空值 env 过滤 + SECRET_KEY 占位符（`${SECRET_KEY}`）+ 加生成后安全校验 | 生成配置不含空密码/弱口令 | service_config_templates.py:337-360/405-410 | #470 |
| 7 | P2 | `default_port`/`docker_service.ports`/env URL 端口三处收敛为单一来源（由 `default_port` 派生），删除 `version: '3.8'` | 消除三处重复漂移 + 废弃字段 | service_config_templates.py:31-281/414 | #469 |

## 6. 演化方向关联

- **阶段判定**：该模块是「拆分解耦」阶段遗留的独立模板库，尚未进入「统一收敛」——`SERVICE_TEMPLATES` 与 `SERVICE_CONTAINER_CONFIGS` 双份配置是收敛对象（SCT6 + §4 端口三处重复）。
- **「能力未接线」家族第八例**：UPL1+SL1+FPC1+SHS1+CC1+MDL2+MAR1+SCT5——本模块 6/7 公开函数死代码，且模板数据本身质量缺陷（SCT1/SCT2/SCT3）全部隐而不发。接线与修模板缺陷需同时进行，否则「接线即崩」（SCT1）或「接线即误报」（SCT2）。
- **服务配置生成方向的参考**：docker-compose 生成是 H 大系统（服务与工具层）的确定性替代方向；修复 SCT1/SCT7 后可作为 spec_first_generator config_hint（LLM 提示）的确定性 fallback，与 global_constraint 的约束注入模式（spec_first:208-209）同源——配置生成从「LLM 自由发挥」走向「模板确定性 + 约束校验」。
