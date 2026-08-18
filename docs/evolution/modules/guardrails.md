# guardrails.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-17 | 状态：已完成
> 归属：Agent 引擎 / 输入与异常防护层
> 路径：`app/utils/guardrails.py`（452 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块定位

「异常防护模块——多模型 Agent 系统的输入和异常处理防护」，提供六项防护能力：
1. Prompt 注入检测（PromptInjectionDetector）
2. 输入长度校验（SessionIdValidator）
3. 会话 ID 格式验证（validate_session_id）
4. 路径安全增强（PathSecurityChecker）
5. 请求速率限制（InMemoryRateLimiter）
6. 资源使用监控（DiskSpaceMonitor）

通过 `get_guardrail_context()` 全局单例 + 四个便捷函数（check_prompt_safety/validate_session_id/check_path_safety/check_disk_space/check_rate_limit）暴露。

## 2. 依赖链与消费方

**活跃消费方（仅 2 个便捷函数被接线）**：
- `orchestrate_endpoints.py:122-123` 导入 check_disk_space/check_rate_limit/validate_session_id（第三项实际未用）
  - :254-256 modify 端点 `check_rate_limit(f"modify:{user_id}")` → 429 阻断（**活跃**）
  - :519-521 stream 端点 `check_rate_limit(f"stream:{user_id}")` → 429 阻断（**活跃**）
  - :259-261 modify 端点 `check_disk_space("./projects")` → 507 阻断（**活跃**）
  - :524-526 stream 端点同（**活跃**）

**零消费方（声明能力未接线）**：
- `check_prompt_safety`/`PromptInjectionDetector`——全 app/ 零引用（Prompt 注入防护从未接线）
- `check_path_safety`/`PathSecurityChecker`——零引用（路径安全实际由 FileContract 另套实现承担，FCT 详档）
- `validate_session_id`/`SessionIdValidator`——零引用（schemas.py:25 是**独立同名实现**，:248-249 活跃消费的是 schemas 版）
- `DiskSpaceMonitor`——仅被便捷函数内部使用（经 check_disk_space 活跃）

## 3. 发现

### GRD1 [P2] Prompt 注入检测全库零消费——防护承诺从未兑现（全库确认）

- **Bug 代码**：:407-423 `check_prompt_safety`/`PromptInjectionDetector`（:35-133 完整实现：10 条注入模式正则 + 敏感关键词 + 结构异常检测 + 评分/风险分级）——全 app/ 零引用（rg 仅 guardrails.py 内部）。
- **根因**：模块 docstring 声称「Prompt 注入检测」是防护能力，但生成链（architect/spec_first/engineer 的 requirement 输入）与编排端点均不调用——用户需求/修改请求直接进 LLM 无任何注入检测。
- **影响**：六项防护能力仅 2 项接线（速率+磁盘），注入检测/路径安全/会话 ID 验证三套声称防护全为死能力（SCT5/EC8/UPL1「能力未接线」家族——本模块 docstring 与接线状态的系统性偏差：6 项声称能力 4 项未接线）。

### GRD2 [P2] 内存级限流跨进程失效 + 全局单例无界增长（MCP1 家族）

- **Bug 代码**：:299-371 `InMemoryRateLimiter`（进程内 dict `_entries` + threading.Lock）；:392-400 `_guardrail_context` 全局单例。
- **根因**：
  1. **多进程失效**——orchestrate_endpoints 活跃消费（:254/:519 429 阻断），但限流计数在单进程 dict——多 worker/多进程部署每进程独立计数，限流可被多进程分摊绕过（每进程都能打满 10 次/60s）
  2. **无界增长**——`_entries` 按 key（user_id）累积，攻击者用随机 user_id 即可使 dict 无限增长（cleanup 只清超过 window 的过期条目且 `_last_cleanup` 依赖 check 调用频率，低流量下长期不清理）
  3. **单例无锁**——`get_guardrail_context`（:395-400）并发首次调用无双检（GIL 下可接受，语义缺陷）
- **影响**：限流在单 worker 内有效，多进程部署形同虚设；内存随用户 key 增长（SM1/MCP1 全局单例家族——与 error_classifier/CLH6/ERL5 同族）。

### GRD3 [P3] `check_disk_space("./projects")` 相对路径 CWD 漂移 + 检查失败静默放行（SM8/SE6 + DGV1 家族）

- **Bug 代码**：orchestrate_endpoints:259/:524 硬编码相对路径 `"./projects"`；:253-284 `check` 异常 → `is_low_space=False, available_for_new_session=True`（:282-283「无法检查时不阻止」）。
- **根因**：相对路径依赖进程 CWD（worker/任务进程 CWD 不同则检查错误目录或不存在目录）；目录不存在时 `shutil.disk_usage` 抛 FileNotFoundError → except 返回「不阻止」——**磁盘检查失败 = 放行**（DGV1 放行家族：与 UT5 沙箱 bwrap 缺失恒通过同构），仅 warning 日志无业务感知，且「磁盘充足」与「检查失败」两态在消费方不可区分。

### GRD4 [P3] 限流默认 `max_requests=10/60s` 过严误伤正常使用

- **Bug 代码**：:385-387 GuardrailContext 默认 `InMemoryRateLimiter(max_requests=10, window_seconds=60)`——stream 端点（:519 `check_rate_limit(f"stream:{user_id}")`）每用户每 60s 仅 10 次流式请求。
- **影响**：连续正常对话（多轮修改 + 流式生成 >10 次/分）会 429 误伤；且限流键按 user_id 粒度，非按端点/项目区分（一个用户卡全部流式）。

### GRD5 [P3] 注入检测正则误报面大（一旦接线即误伤）

- **Bug 代码**：:26-35 INJECTION_PATTERNS——`(?i)(execute|run|eval)\s*(code|command|script|shell|python)` 命中正常开发指令「run python script」；`(?i)(泄露|暴露|显示|输出|告诉)\s*(密码|密钥|令牌|凭证|配置|系统)`——「告诉系统」「配置」等宽词命中普通需求；`_has_abnormal_structure`（:118-133）奇数个 ```（单 ``` 代码标记）+ markdown 表格（special_chars>10%）判结构异常 +0.2。
- **影响**：因 GRD1 未接线目前无实际影响；**一旦接线即把合法开发需求判注入**（FCT3/PP8 子串误伤家族）——接线前需重设计规则（词边界 + 白名单豁免 + 结构检测去特征化）。

### GRD6 [P3] `validate_session_id` 同名单函数两处异构（SCT6 双轨家族）

- **Bug 代码**：guardrails.py:426-430 `validate_session_id`（零消费）vs schemas.py:25 `validate_session_id(v, field_name="session_id")`（:248-249 活跃消费的自定义实现）——同名异构双轨。
- **影响**：两实现规则不一致（schemas 版带 field_name 参数错误消息），未来误引 guardrails 版行为漂移（与 DR3/SCT6 双份实现家族一致）。

### GRD7 [P3] PathSecurityChecker/SessionIdValidator 全库零消费 + FORBIDDEN_PATTERNS 误伤风险（能力未接线方法级）

- **Bug 代码**：:183-228 PathSecurityChecker——`^/` 绝对路径全拒 + `\.(env|ini|conf|cfg)$` 配置文件全拒 + `(^|/|\\)(etc|proc|sys|dev|var/run|var/log)` 系统目录；全 app/ 零消费（路径安全实际由 FileContract 承担，FCT 详档 FCT3 同源子串误伤）。
- **影响**：若接线，项目内 `.env`/`config.py` 等合法文件路径被拒（FCT3 同款）；当前零消费无影响——**方法与便捷函数层的能力未接线**（GC6/SCT5 家族）。

### GRD8 [P3] 限流/防护同步调用阻塞 async 端点

- **Bug 代码**：orchestrate_endpoints async 端点内同步调用 check_rate_limit/check_disk_space（InMemoryRateLimiter 用 threading.Lock + dict，DiskSpaceMonitor 用 shutil.disk_usage 同步 I/O）——无 asyncio 集成。
- **影响**：磁盘统计（shutil.disk_usage 可能触发内核 I/O）在事件循环内同步执行，高频请求下阻塞（TR5 家族小实例）。

## 4. 演化方向

防护层「六项声明能力四项未接线」是核心问题：
- **接线决策**：Prompt 注入检测（GRD1）应接在需求入口（architect/orchestrate_endpoints 的 requirement 参数），但 GRD5 规则需先重构（词边界 + 白名单 + 中文模式收窄）再接线，避免误伤合法需求
- **限流升级**（GRD2）：内存级 → 持久化/分布式（Redis 计数，与 conversation_store 的 Redis 基础设施复用）；key 治理（按 user+endpoint 组合 + TTL 过期清理）；单 worker 部署则至少加 LRU 上限
- **磁盘检查**（GRD3）：路径改为显式 projects 根（复用 orchestrator 的 PROJECTS_BASE_DIR）或绝对路径；「检查失败」与「空间不足」两态分离（失败时拒绝还是放行需显式配置，当前静默放行掩盖故障）
- **收敛**：guardrails.validate_session_id 与 schemas 版合并单一来源（GRD6）；防护层与 FileContract 的路径安全职责边界明确（GRD7）

## 5. 主线关联

- **能力未接线家族**：GRD1/GRD7（六项声称防护四项未接线）加入 SCT5/EC8/UPL1/CD1——docstring 声明能力与接线状态的系统性偏差
- **DGV1 放行家族**：GRD3（磁盘检查失败放行）与 UT5（沙箱恒通过）/SCM2（健康失败当通过）同族——防护/验证「失败放行」
- **全局单例**：GRD2 加入 SM1/MCP1/ERL5 家族
- **双轨实现**：GRD6（validate_session_id 同名异构）加入 DR3/SCT6 家族
- **与 docker 测试链**：guardrails 限流/磁盘检查是编排端点侧防护，docker 测试链（docker_runner/service_container_manager）是执行侧——两侧防护均存在「未接线」（GRD1）与「失败放行」（GRD3/SCM2）双重失真

## 6. 测试状态

- **零单元测试**：tests/ 下无任何 guardrails/PromptInjectionDetector/check_rate_limit 引用
- GRD1/GRD2 两个 P2 项全库确认零用例保护；注入检测（GRD5 误报规则）与限流语义（GRD2 跨进程）均无测试约束
