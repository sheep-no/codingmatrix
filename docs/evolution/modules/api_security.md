# security.py + security_audit.py + csrf.py + api_response.py API 安全家族

> 第一百二十二轮补扫 | v1.123 | 2026-08-17 | 分析对象：`app/utils/security.py`（190 行，JWT/bcrypt 认证）+ `app/utils/security_audit.py`（109 行，安全审计日志）+ `app/utils/csrf.py`（164 行，CSRF 防护）+ `app/utils/api_response.py`（189 行，统一响应）
>
> 结论：**API 安全家族——JWT 认证（security.py）+ CSRF 防护（csrf.py）+ 审计日志（security_audit.py）+ 统一响应（api_response.py）**——核心风险在 CSRF Token 内存态多 worker 失效与 bcrypt 密码截断。

## 一、模块定位

| 模块 | 职责 | 使用规模 |
|------|------|----------|
| security.py | JWT 签发/验证（access+refresh）、bcrypt 密码、密码强度 | 18 处调用（主认证链路） |
| security_audit.py | 安全事件日志（登录/权限/敏感操作） | security logger 已配置（logging_config.py:170/226） |
| csrf.py | 双重提交 Cookie CSRF 防护 | 仅 auth.py（登录/注册端点） |
| api_response.py | 统一成功/错误/分页响应 | 全 api 仅 3 处调用（未落地） |

## 二、缺陷清单

### P2（2 项）

- **CS1 [P2] CSRF Token 存进程内存 dict——多 worker 部署下生成与校验跨进程失效 + 重启全失效**——csrf.py:28 `self._tokens` 进程内 dict——多 worker/gunicorn 时 **worker A 的 `get_csrf_token` 生成的 token，请求落到 worker B → `validate_token` 查不到 → 403**——auth.py 登录/注册端点随机失败（CSRF 保护自身成为可用性故障点）；进程重启后所有登录态 CSRF token 全失效。修复方向：token 改无状态（HMAC 签名含过期）或共享存储（Redis）。
- **SEC1 [P2] `hash_password`/`verify_password` 密码静默截断 72 字节——超长密码碰撞**——security.py:53 `password.encode("utf-8")[:72]`、:62 同——bcrypt 输入上限 72 字节——**72 字节后不同的两个密码被当作相同密码**（不同用户设 72+ 字节密码可互登）——且无长度上限校验直接截断（validate_password_strength 只查 ≥8 不查上限）。修复方向：密码长度上限校验（拒绝 >72 字节）+ 截断前检测。

### P3（7 项）

- **SEC2 [P3] `refresh_key = f"{SECRET_KEY}_refresh_v1"`——子密钥由主密钥字符串拼接派生——无独立密钥管理**——security.py:170/:176——SECRET_KEY 泄露则 refresh 密钥直接可推（应独立随机密钥 + 版本轮换）。
- **SEC3 [P3] `create_access_token` 的 `refresh_until` 固定 5 天——与 exp 独立——配置不一致时行为混乱**——security.py:72 `refresh_until = now + timedelta(days=5)` 与 :73 exp（ACCESS_TOKEN_EXPIRE_MINUTES）独立——若 ACCESS_TOKEN_EXPIRE_MINUTES > 5 天 → **token 先过 refresh_until 而非 exp**——语义反转。
- **SEC4 [P3] `_decode_and_validate_token` 异常分支拼接异常文本进错误响应**——security.py:109 `f"Token 无效：{e}"`——JWT 库异常细节（库版本/内部信息）进客户端响应（轻微信息泄露）。修复方向：固定文案。
- **CS2 [P3] `csrf_protect_optional` 验证失败静默返回 None——调用方忽略返回值即绕过 CSRF**——csrf.py:143-164——「某些兼容性场景」设计——若路由 Depends 它但不检查返回值 → 无防护（当前 auth.py 仅用 csrf_protect 强校验——optional 未使用但暴露存在）。
- **SA2 [P3] `log_security_event` 是 async 但无真实异步操作——同步 logger 写盘阻塞事件循环**——security_audit.py:18-57——大量失败事件（登录洪水/暴力尝试）时 JSON 序列化 + 日志 I/O 阻塞 async 上下文。修复方向：改同步函数或移线程池。
- **AR1 [P3] 两套响应格式并存——error_handler（`{code,message,details}` 无 success/timestamp）vs api_response（`{success,code,message,details,timestamp}`）**——api_response 仅 3 处调用未落地——但路由层多数直接 return dict——客户端实际面对三种形状。修复方向：统一标准。
- **AR2 [P3] `paginated_response` size=0 → 除零崩溃**——api_response.py:133 `(total + size - 1) // size`——size=0 时 ZeroDivisionError。修复方向：size 下限 1。

## 三、全库交叉确认

- **认证链路健康**：security.py 主认证（18 处）逻辑正确——JWT 签名 key 分离（access 用 SECRET_KEY / refresh 用派生 key）、WS 场景 refresh_until 5 天刷新窗设计、verify_token 校验 type==access——**认证主链路无 P1**（对比 CA12 缓存泄露——认证层反而比缓存层健康）。
- **可用性风险家族**：CS1 与 process_guard PG2（监控卡死）、encryption CRY3（多 worker 密钥分裂）同族——**进程内可变状态在多 worker 部署下的失效模式**。
- **SCT6 家族（secret 处理）**：SEC2 密钥派生与 crypto CRY1（密钥轮换）同族。
- **信息泄露家族**：SEC4 与 error_handler EH1（原始错误泄露）同族——都是异常细节进响应。
- **api_response 未落地**：与 error_codes EC1（40+ 错误码仅 api_response 引用）形成「定义了但未采用」的体系——统一响应标准化工作未完成。

## 四、测试状态

零单元测试。CS1 多 worker 失效、SEC1 密码截断、AR2 除零均无测试约束。修复建议：① CSRF 多进程验证测试（跨实例 validate 断言）；② 72+ 字节密码拒绝测试；③ size=0 分页断言 400 而非 500；④ 审计事件 JSON 完整性测试。
