# permissions.py + system_config.py + system_monitor.py 权限与配置

> 第一百二十三轮补扫 | v1.124 | 2026-08-17 | 分析对象：`app/utils/permissions.py`（51 行，三级权限校验）+ `app/utils/system_config.py`（175 行，系统配置管理）+ `app/utils/system_monitor.py`（43 行，系统状态统计）
>
> 结论：**权限与配置小件——三级权限工具（normal/admin/superadmin）+ 系统配置管理器（并发限制/会话/PPT）+ 系统状态统计**——核心风险在系统配置的读取路径与默认配置结构不匹配导致并发限制功能死路径，以及 JWT 内嵌权限等级的时效性问题。

## 一、模块定位

| 模块 | 职责 | 消费方 |
|------|------|--------|
| permissions.py | 三级权限数值化 + is_admin/is_superadmin | guardian_router、api/v1 路由 |
| system_config.py | 并发限制/会话管理/PPT 配置持久化 | 管理员热更新入口 |
| system_monitor.py | CPU/内存/磁盘/网络实时统计 | 监控面板 |

## 二、缺陷清单

### P2（2 项）

- **SC1 [P2] `get_user_concurrent_limit` 读取路径与默认配置结构不匹配——并发限制功能死路径**——system_config.py:97-103 从 `self._config["system_config"]["user_concurrent_limits"]` 读取 `user_overrides`/`default_tiers`——但默认配置 :61-92 的并发限制在**顶层** `user_concurrent_limits.role_defaults`（:73-82，不在 system_config 内）——**:97-103 永远读不到 → 恒返回 default 1**——用户覆盖配置（update_user_override 写入的）与角色层级限制（free=1/premium=5）全部失效——所有用户并发限制退化为 1。且 `default_tiers` key（:102）与默认配置的 `role_defaults`（:76）命名不一致——**同一模块内配置 key 拼写漂移**。修复方向：读取路径对齐 `user_concurrent_limits.role_defaults` + `user_overrides`（顶层）。
- **PER1 [P2] 权限等级内嵌 JWT payload——权限降级/账号禁用不即时生效**——security.py:80 `permission_level` 写进 access token——permissions.py:44-51 校验仅读 payload——**管理员降级用户/禁用账号后，旧 token 在 ACCESS_TOKEN_EXPIRE_MINUTES 有效期内仍持原权限**——权限变更延迟生效（高危操作如 superadmin 被降级仍可操作至 token 过期）。修复方向：校验时二次查询 DB 权限或缩短 access token TTL + 权限版本号。

### P3（6 项）

- **PER2 [P3] `get_permission_level` 未知级别静默返回 0**——permissions.py:27——fail-closed（安全）但调用方若直接用数值比较而非 has_permission 会误解语义（0 被当成最低权限而非无效）。
- **SC2 [P3] `SystemConfigManager.__new__` 单例无锁构造竞态**——system_config.py:21-24——多线程首次并发构造重复初始化（DCC1 家族）。
- **SC3 [P3] 默认相对路径 `./configs/system_config.json`——CWD 漂移（GRD3 家族）**——system_config.py:19——部署 CWD 不同 → 配置找不到 → 生成新默认配置——管理员热更新写丢。
- **SC4 [P3] 配置损坏时静默用默认 + 覆盖写盘**——system_config.py:44-46 load 失败 → 默认 → :43 save_config **覆盖原文件**——损坏配置被静默覆盖，历史值丢失。
- **SC5 [P3] `save_config` 无锁——并发写配置竞态**——system_config.py:48-57——多管理员同时更新 → 互相覆盖。
- **SM1 [P3] `system_monitor.get_system_stats` 无异常处理**——system_monitor.py:10-20——psutil 缺失/调用异常直接冒泡 → 监控 API 500（对比 resource_guard 有 _HAS_PSUTIL 降级——本模块无）。修复方向：try/except + psutil 可用性检查。

## 三、全库交叉确认

- **并发限制家族**：SC1 与 dynamic_concurrent DCC2（检查注册非原子）、resource_concurrency 详档同族——**并发限制本是多层防线，但 SC1 使 system_config 层的配置读取失效**——system_config 与 ConcurrentLimitManager 双轨：热更新走 concurrent_mgr（:129-131 生效），但 get_user_concurrent_limit 走文件配置（死路径）——**同模块内两套限制来源不一致**。
- **权限时效家族**：PER1 与 auth/security 的 JWT 体系相关——权限变更延迟生效是 JWT 通用取舍，本项目无权限版本号机制。
- **GRD3 家族（相对路径）**：SC3 与 CRY3（keys/）、PG10（data/service_configs.json）、file_operator 同族——**系统配置类文件路径全面依赖 CWD**。
- **单例竞态家族**：SC2 与 DCC1、crypto CRY6 同族——`__new__` 单例无锁三处复现。

## 四、测试状态

零单元测试。SC1 配置读取路径、PER1 权限时效、SM1 异常冒泡均无测试约束。修复建议：① get_user_concurrent_limit 读取默认 role_defaults 断言（free=1/premium=5）；② 用户覆盖配置生效测试；③ 权限降级 token 失效测试；④ system_monitor 无 psutil 环境降级测试。

## 五、状态更新（2026-09-18 核实）

按当前代码逐条核实后的结论：

- **SC1 [P2] 已修**：`get_user_concurrent_limit` 改为同时兼容两种结构——`_get_default_config()` 的顶层 `user_concurrent_limits.role_defaults`，以及既有部署文件的 `system_config.user_concurrent_limits.default_tiers`；`user_overrides` 同样回退读取顶层。核实要点：仓库内实际部署文件 `configs/system_config.json` 用的是 `system_config.user_concurrent_limits.default_tiers`，因此现网路径原本可用，真正失效的是「文件不存在 → 默认配置」的新库（读 `default_tiers` 恒 miss → 恒返回 1）。修复后两种结构均命中。
- **SC2 [P3] 已修**：`SystemConfigManager.__new__` 用 `_instance_lock = threading.Lock()` 双检锁。`__new__` 为同步方法，线程锁是正确实现。
- **SC5 [P3] 已修**：`save_config` 纳入 `_config_lock = threading.RLock()`，避免多管理员并发写文件交错。
- **SC4 [P3] 经核实不成立**：`load_config` 的异常分支（:44-46）只把 `_config` 置为默认值，**不调用** `save_config`；只有「文件不存在」分支（:40-43）才写盘，属首次创建。损坏配置不会被静默覆盖。
- **SM1 [P3] 已修**：`system_monitor` 改为 `try: import psutil` + `_HAS_PSUTIL`，`get_system_stats` 内部 try/except；psutil 缺失或采集异常时返回结构与正常路径一致的降级数据（含 `error` 说明），不再冒泡导致监控 API 500。
- **SC3 [P3] 未处理**：`_config_file = Path("./configs/system_config.json")` 仍依赖 CWD，留待与 RM7/CRY3 的路径统一收敛批次一并处理。
- **PER1 [P2] 未处理**：权限等级仍内嵌 JWT payload，校验不二次查询 DB。修复需引入权限版本号或二次查询，涉及认证体系口径，未改。
- **PER2 [P3] 未处理**：`get_permission_level` 未知级别返回 0 属 fail-closed，保留。

新增回归测试 `tests/unit/test_permissions_config.py`（9 项）；回退 `system_config.py`/`system_monitor.py` 后 3 项失败（默认结构 role_defaults、psutil 异常降级、psutil 缺失降级）。
