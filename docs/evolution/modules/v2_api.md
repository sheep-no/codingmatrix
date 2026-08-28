# 第一百四十六轮：app/api/v2/ 管理面合扫

> 扫描日期：2026-08-27
> 状态判定：9 文件中 8 文件「活跃」（main.py:71-84 全部挂载 /api/v2），nginx_ai.py 为「未接入」（router 全库零挂载，端点恒 404）

## 模块定位与状态判定

| 文件 | 行数 | 三态 | 路由挂载（main.py） | 端点 |
|------|------|------|---------------------|------|
| Controller.py | 337 | **活跃** | :74 sysRouter | WS /Controller/sys-status + /Controller/logs |
| admin_config.py | 129 | **活跃** | :71 adminConfigRouter | /api/v2/admin/*（user-limit/config/sandbox-config 6 端点） |
| guardian_router.py | 858 | **活跃** | :76 guardian_router | /api/v2/Controller/*（guard/service/config/stats/backup/rate-limit 24 端点） |
| mcp_admin.py | 232 | **活跃** | :84 mcpAdminRouter | /api/v2/mcp/servers*（6 端点） |
| model_admin.py | 315 | **活跃** | :82 modelAdminRouter | /api/v2/models/*（9 端点）——**声明废弃仍挂载（双轨）** |
| model_config_api.py | 362 | **活跃** | :83 modelConfigRouter | /api/v2/model-config/*（12 端点） |
| nginx_api.py | 503 | **活跃** | :73 nginxRouter | /api/v2/nginx/*（check/generate/deploy/config/backups 7 端点） |
| nginx_ai.py | 100 | **未接入** | 全库零引用，router 未挂载 | 端点恒 404 |
| user_manage.py | 295 | **活跃** | :75 userManageRouter | /api/v2/Controller/users 等 5 端点 |

**模块定位**：v2 是运维管理面（用户/模型/配置/nginx/MCP/守护/限流/备份），8 活跃文件全部 require_superadmin 或 require_admin 门禁（nginx 部分端点降级为 verify_token）。核心风险在 user_manage 提权链（V2U1）与 nginx 信息泄露（V2N2）。nginx_ai.py 是 v2 唯一未接入文件（与 nginx_api 的 /nginx/check 双实现，双轨家族）。

## 活跃面

1. **用户管理（user_manage.py）**：列表/创建/更新/删除/重置密码 5 端点，`Depends(verify_token)` + 手动 `is_admin` 检查；创建时 validate_password_strength、邮箱唯一、缓存失效链完整。
2. **nginx 配置管理（nginx_api.py）**：check（nginx -t + LLM 流式分析）/ generate（模板生成 + 缓存 TTL 300）/ deploy（备份→写入→测试→reload）/ config（读指定配置）/ backups（列表/删除）。
3. **模型管理双轨（model_admin.py + model_config_api.py）**：同一「模型增删改/角色/降级链/上下文长度」能力两套实现——model_admin 走 `dynamic_model_router`（agent_models.json），model_config_api 走 `model_config_manager`（unified_model_config.json，声明为新接口）。
4. **guardian 守护管理（guardian_router.py）**：服务监控启停/熔断/健康探测 + 资源配置 CRUD + Docker 容器列表 + 日志配置 + 内存统计 + 配置备份/恢复 + 限流配置。superadmin 门禁严格。
5. **mcp 管理（mcp_admin.py）**：MCP Server 增删改/切换/连接测试，JSON 配置文件持久化，env 敏感键脱敏。
6. **admin 系统配置（admin_config.py）**：用户并发限制覆盖 + 系统配置读写 + 沙箱开关。superadmin 门禁严格。
7. **Controller.py**：系统状态 WS 推送 + 日志流 WS（LogService 实时推流 + DB 池监控）。

## 未接入面

- **nginx_ai.py（整文件）**：router 从未被 main.py 或任何文件 include（rg 全库零 `nginx_ai` 引用）——`POST /nginx/check` 恒 404。与 nginx_api.py 的 `/nginx/check`（活跃）构成双份实现（双轨家族）：nginx_ai 版无任何认证 + 调 `call_llm` 流式分析、nginx_api 版有 verify_token。DEFAULT_AI_MODEL 各自硬编码 `Qwen/Qwen2.5-Coder-7B-Instruct`（:22/:42）。若该文件被挂载复活，其匿名 /nginx/check 将暴露免费 LLM 调用面。

## 废弃面

无（model_admin 虽声明废弃但按活跃挂载，归入双轨）。

## 缺陷清单

| 编号 | P 级 | 位置 | 描述 |
|------|------|------|------|
| V2U1 | P2 | user_manage.py:126/:147/:198-210 | **admin→superadmin 提权**（越权家族新面）：create_user/update_user 权限门禁仅 `is_admin`（admin 及以上），permission_level 无「不能高于自身」的层级上限约束（pattern 仅限格式 superadmin 合法）——普通 admin 可创建 superadmin 账号或用 update_user 把他人提权 superadmin；reset_password/delete_user 亦无「不能操作 superadmin」约束。提权后绕过 security.py:139 `require_superadmin` 全部门禁（含 V2G 系列 12 个 superadmin 端点） |
| V2N2 | P2 | nginx_api.py:387-425 | `/nginx/config` 仅 `Depends(verify_token)`（任意登录用户）可读取 /etc/nginx 下任意 .conf——泄露 proxy_pass 内网地址/SSL 证书路径/潜在凭据；且 :405 `resolved.startswith(p)` 无 os.sep 边界，`/etc/nginx-evil/x.conf` 前缀碰撞通过（GH4 家族） |
| V2N1 | P3 | nginx_ai.py 整文件 | **未接入**：router 零挂载端点恒 404（死代码家族不计数，属双轨家族第 N 处）；文件内匿名 /nginx/check + 硬编码 DEFAULT_AI_MODEL 双份；修复方向=删除（活跃功能已在 nginx_api 重写）或按 nginx_api 模式补认证后挂载 |
| V2N3 | P3 | nginx_api.py:158/:244 | `/nginx/check`+`/nginx/generate` 仅 verify_token（非 admin）可免费调用 LLM 分析（成本面）+ DEFAULT_AI_MODEL 硬编码无配置化（LCL1 家族） |
| V2N4 | P3 | nginx_api.py:301-384 | `/nginx/deploy`（superadmin）nginx_path 无白名单限制可写任意路径（superadmin 滥用面）+ `req.backup=False` 时 nginx -t 失败坏配置残留磁盘不清理（后续重启即挂）+ reload 返回值不检查（失败静默报成功） |
| V2N5 | P3 | nginx_api.py:428-503 | `/nginx/backups` GET 任意登录用户可列出备份名（信息泄露面）+ DELETE 的 nginx_path startswith 前缀碰撞 |
| V2M1 | P3 | model_admin.py:1-15 | **声明废弃仍挂载（双轨家族）**：文件头 docstring「已废弃改用 /model-config」但 main.py:82 仍挂载——同一能力（模型/角色/降级链/上下文长度）与 model_config_api 两套实现并存（dynamic_model_router vs model_config_manager），配置双源漂移风险 |
| V2M2 | P3 | model_admin.py:82-83 | `/models/default` 直接改模块级全局 `mm._runtime_default_model`——重启失效/多 worker 各自状态/无持久化（运行时状态漂移） |
| V2M3 | P3 | model_admin.py:156-192 | `/agent-config/fallback-chain` 的 `chain_name`（default/error_recovery/code_generation）参数收而不用——只写日志，无条件覆写单一 `config["fallback_chain"]`，无法维护多条链（参数收而不用） |
| V2M4 | P3 | model_config_api.py:163 | `request.dict()` pydantic v1 风格（v2 弃用）+ update_model 无变更检测恒报「已更新」 |
| V2M5 | P3 | mcp_admin.py:48-70 | `_save_config`/`_load_config` JSON 文件读写无锁非原子（CS1 家族，并发更新可丢配置/写半文件） |
| V2A1 | P3 | admin_config.py:102-129 | `/sandbox-config` PUT 用 `os.environ[...] =` 改运行时环境变量——非持久（重启回退）、多 worker 各自进程状态不同步、`restart_required` 提示但无法保证生效 |
| V2G2 | P3 | guardian_router.py:312-345 | `/admin/config/batch` 无 valid_keys 白名单（对比单点 :277-284 有）——批量更新绕过键白名单，语义不一致 |
| V2G3 | P3 | guardian_router.py:664-685 | `/admin/backup/{timestamp}` 下载路径直拼无净化（`config_backup_{timestamp}.json`，前缀+后缀固定实际穿越受限，低危）+ require_admin 即可读取含全量系统配置的备份（含 docker_image/db_pool 等敏感值） |
| V2G4 | P3 | guardian_router.py:688-737 | `/admin/backup/restore` 可写入任意配置键（无白名单）+ 无备份来源/版本校验（任意构造 payload 注入配置） |
| V2G5 | P3 | guardian_router.py:196-205 | `/health/{port}` require_admin 可探测任意端口开关（内网端口扫描面，port 无 ge/le 范围校验） |
| V2G6 | P3 | guardian_router.py:784-859 | rate-limit 配置端点 limit/window 无 `ge=1` 校验（0/负值可关闭限流） |
| V2C1 | P3 | Controller.py:98/:175 | 两 WebSocket 均先 `websocket.accept()` 再验证 token（未验证连接先建立，可占连接资源）+ token 经 query 参数传输（落代理/访问日志） |
| V2U2 | P3 | user_manage.py:269-296 | reset_password 不校验新密码强度（对比 create_user 有 `validate_password_strength`，:130）+ delete_user 无事务包裹（Permission 删除后 commit 失败则 User 已删 Permission 残留） |

## 交叉确认

- 全部 9 文件挂载面经 main.py:71-84 逐一核对：nginx_ai.py 确认不在导入清单（全库 rg 零引用）。
- 提权链闭环：create_user 的 `UserCreateRequest.permission_level` pattern=`^(normal|admin|superadmin)$`（schema/manageUser.py:12）→ admin 提交 superadmin → 新账号登录签发 superadmin JWT → 通过 security.py:139 require_superadmin。verify_token 仅校验 JWT 签名与 type=access，permission_level 取自 JWT 载荷，无 DB 二次核验（改库权限后旧 token 仍有效——与 V2U1 叠加使提权即时生效）。
- guardian_router 自建 require_superadmin（:64，is_superadmin）与 security.py:139 版本语义一致（== "superadmin"）；nginx_api.py:30 `from app.api.v2.guardian_router import require_superadmin` 跨文件复用。
- 与既往缺陷关联：V2N2/V2N5 前缀碰撞同 GH4 家族；V2M5 同 CS1（无锁写文件）；V2N3/V2N1 模型硬编码同 LCL1 家族；V2M1/nginx_ai 双轨同双轨家族；V2G3 备份相对路径 `data/backups` 同 AIC1 CWD 依赖家族。
- **双轨盘点**：nginx_ai/nginx_api（/nginx/check 双实现）、model_admin/model_config_api（模型管理双实现）——v2 内两处双轨，其中 nginx_ai 为未挂载死文件。

## 测试状态

- 无针对 v2 管理面的测试文件（grep 未见）。
- 提权链（V2U1）无任何用例保护；nginx 端点无集成测试（nginx -t 依赖本机 nginx 安装）。

## 修复建议

1. **V2U1（P2 优先）**：create_user/update_user 增加层级约束——非 superadmin 只能创建/提升到 admin 以下，且 `permission_level` 不得超过操作者自身级别；reset_password/delete_user 禁止操作 superadmin；或改用 require_superadmin 依赖替代 is_admin。
2. V2N2：`/nginx/config` 提升为 require_admin + 路径校验改 `is_relative_to`（或等值比较）+ 禁止前缀碰撞。
3. V2N3/V2N4：check/generate 提升为 require_admin；deploy 的 nginx_path 限制在 /etc/nginx 白名单 + backup=False 时测试失败清理坏配置 + reload 检查返回码。
4. V2M1：二选一收敛（model_config_api 为新接口，退役 model_admin 或反向），删除声明废弃文件。
5. V2G2/V2G4：batch/restore 复用同一 valid_keys 白名单。
6. nginx_ai.py：直接删除（活跃实现已在 nginx_api 重写），未接入面缺陷不逐条修复。
7. 其余 P3 按既有家族修复习惯处理（锁、校验、路径净化）。

## 下轮候选

- app/api/v1/ 余下文件（aicloud.py/aicloud_knowledge.py/model_manager.py/vision_api.py/workflow.py/aiGeneratorPptx.py 仅消费方扫过）
- app/services 16 文件（model_config_manager/resource_config/feature_switch/log_config/rate_limit_config/websocket_manager 等本轮依赖方）
- app/schema 13、app/models 12、app/db 12、app/core/middleware 4、app/tasks 3
