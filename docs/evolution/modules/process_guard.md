# process_guard.py 进程守护链

> 第一百一十七轮补扫 | v1.118 | 2026-08-17 | 分析对象：`app/utils/process_guard.py`（300 行，AsyncProcessGuardian）+ `app/utils/async_enhanced_guard.py`（146 行，AsyncSmartGuardian）+ `app/utils/service_config_manager.py`（168 行，配置持久化）+ `app/api/v2/guardian_router.py`（859 行，监控 API）
>
> 结论：**进程守护链——API（superadmin 手动配置）→ AsyncSmartGuardian（学习+熔断）→ AsyncProcessGuardian（端口探测+杀进程+重启）→ ServiceConfigManager（磁盘持久化）**——核心风险集中在「端口失联即杀进程+执行 restart_cmd 自动重启」的自动化路径：误杀、无超时卡死、任意命令常驻执行。

## 一、链路结构

```
/Controller/guard/start（superadmin）──► guardian_router:103 watch_port(cfg) ──► AsyncSmartGuardian
scan_and_learn（学习模式）──────────────► psutil 进程扫描 ──► get_or_create_config ──► ServiceConfigManager（data/service_configs.json）
watch_port 循环：is_port_open ─失联► find_pid_by_port ─杀旧进程► restart_service ─communicate► 等待端口就绪 ─失败► 熔断（fuse）─► 冷却后重试
```

- `restart_cmd` 来源：① 手动 API（guardian_router.py:96 `body.restart_cmd` 用户输入直通）；② 自动学习（service_config_manager.py:96 `_guess_restart_cmd` 硬编码模板——redis/mysql/nginx 专用命令，非任意 cmdline——**学习模式相对安全**）。
- 熔断持久化：watch_port :267-271 `config_manager.configs[key] = config` + `save_configs()`。

## 二、缺陷清单

### P2（4 项）

- **PG1 [P2] 端口失联自动执行 restart_cmd——superadmin 手动配置任意 shell 命令常驻自动触发（CII1 家族弱化版）**——guardian_router.py:91-96 `/guard/start` 把用户 `restart_cmd` 直通 → process_guard.py:120 `asyncio.create_subprocess_shell(restart_cmd)`（shell=True，无白名单/无二次确认）——superadmin 本身高权限（接受度中），但**该命令在服务失联时被守护循环自动反复执行**——一旦 configs 文件被篡改或超管误配，失联即触发任意命令。且 watch_port 循环内无命令来源审计日志（无记录谁何时配置了什么命令）。修复方向：restart_cmd 白名单/参数数组化（`create_subprocess_exec`），配置变更留审计。
- **PG2 [P2] `restart_service` 的 `proc.communicate()` 无超时——前台重启命令永久挂起 → 监控循环卡死、熔断失效**——process_guard.py:127 `stdout, stderr = await proc.communicate()`——重启命令若为前台服务（`python app.py`，无 `&`）→ 永不退出 → stdout 管道不关闭 → `await` 永久阻塞 → `_wait_for_service_ready` 永远到不了——**端口恢复也无人知道，熔断机制完全失效，监控线程卡死**——:150 `except asyncio.TimeoutError` 成死代码（communicate 无 timeout 参数不会抛）。修复方向：`communicate(timeout=...)` 或 spawn 后直接轮询端口、命令后台化约定。
- **PG3 [P2] 端口失联即杀旧进程——无进程级健康确认 + `kill_process` 未校验 PID create_time（TOCTOU/PID 重用 + 误杀健康进程）**——process_guard.py:233-239 `is_port_open` 不通 → `find_pid_by_port` → `kill_process`——① `is_port_open` 仅 TCP connect，服务启动中/网络抖动/仅接受特定 host 时误报失联 → **杀掉正在启动的健康进程**；② `kill_process` :80-92 `psutil.Process(pid)` 后直接 terminate/kill，**未比对 process.create_time()**——端口上旧 PID 已被系统回收并被新进程复用 → **杀无关进程**。修复方向：kill 前校验 PID 的 create_time 与扫描时一致；失联后先探测进程存在性再决定杀/重启。
- **PG4 [P2] guardian_router.py:672 `download_backup` 路径穿越（FCT/PP 家族）**——`Path(f"data/backups/config_backup_{timestamp}.json")`——timestamp 用户可控且**无 `..` 校验**——admin 可传 `../../etc/xxx` 读取任意以 .json 结尾文件（delete_backup :747 有 `..`/`/` 校验——**两个端点不对称**）。修复方向：download 端点与 delete 端点同款校验，或改用文件索引+UUID。

### P3（7 项）

- **PG5 [P3] `find_pid_by_port` lsof 多 PID → `int()` 抛 ValueError → 静默返回 None**——process_guard.py:61/70 `lsof -i :{port} -t` 输出多行时 `int(stdout.decode().strip())` 抛异常 → except 吞掉返回 None → **旧进程未杀 → 重启服务 bind 失败**。修复方向：取首行/多 PID 处理。
- **PG6 [P3] 熔断持久化 `config['process_signature']` 直接下标——KeyError 监控任务崩溃**——process_guard.py:269 下标访问——config 无该键（旧版配置/手动构造）→ KeyError 不在 :287 except 白名单（ValueError/TypeError/RuntimeError/OSError）→ **watch_port 协程崩溃退出**。修复方向：`config.get()`。
- **PG7 [P3] 子进程无资源限制——重启服务无 cpu/mem 上限（UT5 家族）**——restart_service spawn 的服务无 cgroup/资源约束——资源失控（内存泄漏）时守护循环反复拉起 → 系统资源耗尽。修复方向：cgroup/资源上限配置。
- **PG8 [P3] watch_port 必填键直接下标——name/port/restart_cmd 缺失即崩溃**——process_guard.py:174-176 `config["name"]`——异常在 while 外层冒泡 → 任务崩溃。
- **PG9 [P3] `_guess_restart_cmd` 模板 `systemctl restart mysql`——受限环境必然失败→熔断循环，且误伤共享服务**——service_config_manager.py:144——无 systemd/容器环境执行失败；重启 mysql 影响其他应用。修复方向：环境能力探测。
- **PG10 [P3] ServiceConfigManager 默认相对路径 `data/service_configs.json`——CWD 漂移（GRD3 家族）**——service_config_manager.py:16——与 CRY3（keys/ 路径）、FO 家族同族——多 worker 各自读写不同配置文件 → 监控配置分裂。
- **PG11 [P3] async_enhanced_guard.py:100 `is_trusted` 直接下标 `config["display_name"]`——潜在 KeyError**——学习模式下 get_or_create_config 会设置 display_name，但手动构造 config 可能缺失。

## 三、全库交叉确认

- **CII1 家族（命令注入）**：PG1 与 guardrails 命令执行检查（GRD）、sanitize_command（EC 家族）同族——但进程守护链是**合法 shell 执行场景**，风险在「自动触发 + 无审计」而非注入本身。
- **UT5 家族（sandbox 资源隔离）**：PG7 与 docker_runner 资源上限、bwrap 隔离同族——守护重启的服务完全无资源限制。
- **GRD3 家族（相对路径 CWD 漂移）**：PG10 与 CRY3（keys/）、FileOperator base_path 同族。
- **PP 家族（路径穿越）**：PG4 与 download_backup 直接相关——guardian_router 的 delete_backup 有校验而 download 没有（不对称修复模式）。
- **熔断状态一致性**：watch_port :229 冷却结束 `restart_count[name] = 0` 但 :246 成功后也重置——两处重置逻辑并存，语义重复（弱）。
- **正面对比**：进程守护比 agent 的 kill_process 防御（UT2 强制进程）**没有对目标进程做任何限制**——被守护服务无隔离无资源限制，仅靠端口探测判断存活。

## 四、测试状态

零单元测试。PG2 无超时卡死、PG3 PID 重用误杀、PG4 路径穿越、PG5 多 PID 均无测试约束。修复建议：① restart_service communicate 超时测试（模拟前台命令挂起）；② kill_process PID create_time 校验测试；③ download_backup 路径穿越参数化测试（../ 序列样本）；④ lsof 多行输出解析测试。
