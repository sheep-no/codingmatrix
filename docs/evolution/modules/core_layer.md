# app/core 核心件合扫（第 154 轮 / v1.155）

- 轮次：154（内部编号 v1.155）
- 扫描对象：`app/core/`（config 181 + file_validator 327 + graceful_shutdown 289 + logging_config 247 + \_\_init\_\_ 0 = 4 文件 1044 行）
- 此前该包从未单独扫描（EVOLUTION 仅在第 153 轮列为「下一阶段候选」）

## 三态判定

| 文件 | 判定 | 依据 |
|------|------|------|
| config.py | 活跃 | 全库 settings 消费（main/lru_cache 单例） |
| file_validator.py | 活跃 | file_upload.py:161 validate_file_content 唯一消费 |
| graceful_shutdown.py | 活跃 | main.py:51/:105/:129/:134/:206-222 全链接线 |
| logging_config.py | 活跃 | main.py:100 setup_logging() 启用 dictConfig |

4 文件全部活跃，无死文件。**正面点名**：graceful_shutdown 是「安全设施未接线」家族的反面——信号处理、连接 inflight 计数（main.py:217/:222 中间件挂钩）、lifespan 终结 shutdown_async（:134）全链真实生效；SensitiveDataFilter 随 setup_logging 生效，console/file_app/file_error 全挂 filter。

## P2 发现（1 项）

### FV1 [P2] 魔数检测表使代码文件上传整体失效（file_validator.py:118-173，实测）

- `detect_mime_type` 魔数表只覆盖图片/PDF/压缩包/`{`（JSON）/`<?xml`/`<svg`/`<html`/`#`（text/plain）
- 纯代码文件无魔数命中 → 默认 `application/octet-stream`（:173）→ 不在 ALLOWED_MIME_TYPES（:92）→ 拒绝
- 以 `#` 开头的 .py/.yaml 命中 `b'#'` → text/plain → 与 EXTENSION_MIME_MAP['.py']（text/x-python 系列）不匹配（:96-101）→ 拒绝
- **实测复现**：main.py/app.js/svc.py/config.yaml/style.css 全 REJECT（前四者 octet-stream、.py 系 text/plain 不匹配）；仅 data.json/readme.md PASS
- 影响：**AI 代码生成平台「上传代码文件作为上下文」的核心入口必 400**——file_upload.py:89-101 ALLOWED_EXTENSIONS 白名单声称支持 30+ 扩展名，深度验证把其中大半必杀；幸存代码类只有 .json/.md/.html/.xml/.txt（.md 靠 text/plain 在映射内侥幸通过）
- 修复方向：魔数不可判时按扩展名映射回退（EXTENSION_MIME_MAP 反查）+ 文本类型嗅探替代单字节魔数
- Backlog：#1234

## P3 发现（20 项）

### config.py（5 项）
- **CFG1 [P3]** :45 `os.getenv("ENV", "development")` vs settings.ENV 字段双轨判定——Dockerfile:39 `ENV=production` 掩盖；裸机 .env-only 部署（不导出环境变量）旁路生产校验 → 临时 SECRET_KEY 自动生成 × 多 worker（--workers 2）各 lru_cache 独立实例 → JWT 跨 worker 验签失败 + 重启全失效
- **CFG2 [P3]** :89 ALLOWED_MODELS（10 模型）**零消费**，实际校验用 codeRequest.py:7-16 ALLOWED_MODELS_LIST（8 模型）——双份白名单漂移：GLM-4.1V-9B-Thinking 只在 codeRequest、PaddleOCR-VL/Kolors/bce-embedding 只在 config（双轨家族第 20 处）
- **CFG3 [P3]** 假配置五件套零消费：LOG_RETENTION_DAYS/LOG_COMPRESS_OLD_LOGS/LOG_CLEANUP_SCHEDULE/ALLOWED_FILE_TYPES/WS_MAX_CONNECTIONS（「配置存在未接线」家族；WS 连接无实际上限）
- **CFG4 [P3]** :91 ALLOWED_HOSTS 语义错位——host 列表被 main.py:177 `replace(",", "|")` 当 CORS origin 正则用，`0.0.0.0` 的点未转义匹配任意字符；命名诱导运维填入 host 列表得到与预期不符的放行面
- **CFG5 [P3]** :149 get_provider_registry 每次调用新建 ProviderRegistry（llm_caller.py 4 消费点各建一份），与 ProviderRouter.get_instance 单例参数语义混乱，api_key 无热更新路径

### file_validator.py（5 项）
- **FV2 [P3]** :212/:217/:240/:243/:252 用 print 替代 logger——安全事件（SVG 攻击载荷/路径穿越/压缩包异常）绕过日志审计体系与 SensitiveDataFilter
- **FV3 [P3]** :190-208 SVG 黑名单漏报面：onsubmit/onanimationstart/\<foreignObject\>/data:text/html/HTML 实体编码（&#106;avascript:）全缺——黑名单天生不全（IV1 家族变体），download attachment 头兜底故定 P3
- **FV4 [P3]** EXTENSION_MIME_MAP（28 键）与 file_upload.ALLOWED_EXTENSIONS（30+ 键）不一致——.rar/.7z/.vue/.jsx/.tsx/.scss/.doc 等在上传白名单却无 MIME 映射，:96 跳过扩展名校验全靠魔数；:137 `b'ustar'` 魔数位置错（tar magic 在 offset 257，前 16 字节是文件名）→ .tar 恒 octet-stream 拒（.gz 可过）
- **FV5 [P3]** :233 validate_archive_content 只实现 .zip 分支——.tar/.gz/.rar/.7z 恒 True 放行（:108 五类都进校验），压缩包内容检查双标
- **FV6 [P3]** :78-100 CompressedRotatingFileHandler 死类——LOGGING_CONFIG handlers 全用 "logging.handlers.RotatingFileHandler" 字符串引用，本类零引用（死代码家族第 41 处）

### graceful_shutdown.py（5 项）
- **GS2 [P3]** _do_shutdown 无幂等锁——信号 handler（_handle_sigterm ensure_future）与 lifespan shutdown_async（main.py:134）双路径并发时 TERMINATED 早退检查（:147）非原子 → 关闭逻辑（WS/Celery/db dispose/hooks）可双执行
- **GS3 [P3]** :182-194 _close_websocket_connections 假关闭——只 get_connection_count + sleep(10)，无任何实际 close 调用（「报告动作≠执行动作」家族；日志声称「正在关闭 N 个连接」）
- **GS4 [P3]** :223-242 setup_signal_handlers 覆盖 uvicorn 内建 SIGTERM 处理——uvicorn Server 主循环失去停止信号，关闭路径双轨（自定义链负责排空，uvicorn graceful 行为被旁路）
- **GS5 [P3]** :135-136 initiate_shutdown 在同步上下文对 async pre-hook 调 asyncio.create_task——无事件循环时 RuntimeError 被 :139 吞 → 异步钩子静默跳过（Windows signal.signal 回退路径必现）
- **GS6 [P3]** :131 datetime.utcnow() naive（MD4 家族 +1）

### logging_config.py（5 项）
- **LGC2 [P3]** :52-63 SensitiveDataFilter 只洗 str——record.args 元组中非 str 值（int/bytes 凭据）跳过打码（:67 isinstance 检查）；仅 msg/args 两入口，record 对象其他属性不洗
- **LGC3 [P3]** :11 LOG_DIR = Path("logs") 相对路径（DB9 同族 +1）+ :12 模块导入时 mkdir 副作用——import 即建目录，工作目录耦合
- **LGC4 [P3]** :241-246 启动横幅谎报——「日志轮转：每天，保留 14 天」「安全日志：保留 90 天」，实际全部 10MB 大小轮转（RotatingFileHandler）+ backupCount 5/3/2/10 份；TimedRotatingFileHandler 导入未用（「报告≠实际」家族）
- **LGC5 [P3]** :150-159 file_debug handler 死配置——loggers 段零引用，debug.log 恒空
- **LGC6 [P3]** :98 doRollover 异常元组手抄含 SQLAlchemyError——gzip 压缩路径捕 DB 异常无意义（DB5 异常清单手抄家族变体）

## 认知修正：153 轮 AUT2 降级

第 153 轮 AUT2（auth.py:126 明文 email 进日志）经本轮交叉确认被 **SensitiveDataFilter email 正则打码缓解**——main.py:100 setup_logging() 启用 dictConfig，console/file_app/file_error 三 handler 全挂 sensitive_data filter，auth.py 走 logger.info 的日志在输出前被 `[a-zA-Z0-9._%+-]+@...` 正则替换为 `***EMAIL_REDACTED***`。AUT2 降级为「依赖全局过滤器兜底、auth 侧无双轨一致性」的认知修正（加密模式 :115 手动打码与全局过滤双保险冗余），缺陷级别从 P3 降为注记。

## 家族归并累计

- 双轨家族：+1（CFG2 模型白名单双份，第 20 处）
- 死代码家族：+1（FV6 CompressedRotatingFileHandler，第 41 处）
- MD4（naive/aware）：+1（GS6）
- DB9（相对路径）：+1（LGC3）
- 「报告≠实际」：+1（GS3 假关闭）+1（LGC4 横幅谎报）
- 「配置存在未接线」：+5（CFG3 假配置五件套）
- DB5（异常清单手抄）：+1（LGC6）

## 数据

- 本轮：P2 1 + P3 20 = 21 项，Backlog #1234-#1254
- 累计：P1 17、P2 425、P3 758
- `app/core/` 全包建档完成；正面点名 graceful_shutdown 与 SensitiveDataFilter 两处全链生效设施

## 状态更新（2026-09-20 核实）

- **FV1 [P2] 已修**：`app/core/file_validator.py`。原 `detect_mime_type` 对无魔数的源码/配置只能返回 `application/octet-stream`，而该值不在 `ALLOWED_MIME_TYPES`；以 `#` 开头的 `.py`/`.yaml` 又命中 `b'#'` 判为 `text/plain`，与 `EXTENSION_MIME_MAP` 里代码类扩展名的期望值不匹配。两条路径叠加导致白名单内的代码文件上传必被 400。修复：
  - `detect_mime_type` 增加文本嗅探：前 2048 字节无 NUL 且可 UTF-8 解码则返回 `text/plain`，不再一律落到二进制流。
  - `EXTENSION_MIME_MAP` 为全部文本/代码扩展名补上 `text/plain`，并补齐白名单里缺失的 `.c/.cpp/.go/.rs/.rb/.jsx/.tsx/.vue/.scss/.toml/.ini/.rst/.docx`。
  - 二进制伪装仍被拦截：`.py` 内放 PNG 魔数判为 `image/png` 后与扩展名不匹配而拒，`.css` 内放 zip 同理；SVG 危险模式、`.doc`（无 OLE2 魔数支持）保持 fail-closed。
- **连带修复（原文档未列）**：`generate_safe_filename` 的扩展名正则原为 `^\.[a-z0-9]{2,10}$`，单字符扩展名 `.c` 恒被拒——`file_upload.ALLOWED_EXTENSIONS` 明确允许 `.c`，属同一「白名单声称支持但深度校验必杀」家族。下限改为 1。
- **FV4 部分修复（2026-09-22）**：`.tar` 魔数 `b'ustar'` 原放在 `magic_signatures` 里用 `header.startswith` 比对，但 tar magic 在偏移 257（前 257 字节是首个成员的文件名等元数据），导致合法 `.tar` 恒判 `application/octet-stream` 被白名单拒——`ALLOWED_EXTENSIONS` 与 `EXTENSION_MIME_MAP` 都列了 `.tar`，属「白名单声称支持但深度校验必杀」。现改为独立判 `content[257:262] == b'ustar'`，`.tar` 在 `validate_file_content` 与 `validate_file_path` 双路径均可上传。**`.doc` 仍未处理**：`.docx`（zip 容器）有映射，`.doc` 旧格式的 OLE2 魔数未识别、也无 `application/msword` 条目，上传恒拒。这是 fail-closed，支持 `.doc` 需同时落地 OLE2 魔数、MIME 白名单与下游解析（`knowledge_processor.parse_document` 目前把 `.doc` 交给 python-docx，本身也解析不了旧格式），属能力扩张，待确认后处理。
- 新增回归 `tests/unit/test_file_validator_uploads.py`（57 项）：26 种文本/代码扩展名在 `validate_file_content` 与 `validate_file_path` 双路径下均接受、二进制伪装拒绝、`.docx` zip 容器接受、含脚本 SVG 拒绝。回退 `file_validator.py` 后 46 项失败。

## 状态更新（2026-09-22 核实）

- **CFG1 [P3] 已修复（SECRET_KEY 生产校验双轨）**：`validate_secret_key` 原以 `os.getenv("ENV", "development")` 判定；pydantic 已从 `.env` 解析出 `ENV=production`，但环境变量未导出时读不到，于是静默返回固定开发密钥（多 worker 各自 lru_cache 实例 → JWT 跨 worker 验签失败、重启失效）。现改用 pydantic 校验上下文的 `info.data["ENV"]`（与 `settings.ENV` 同源），`.env`-only 生产部署也会被拒绝启动；随之移除不再使用的 `import os`。
- **CFG4 [P3] 已修复（CORS origin 正则未锚定/未转义）**：`main.py` 原 `allow_origin_regex=settings.ALLOWED_HOSTS.replace(",", "|")`，`re.search` 下 `https://localhost.evil.com`、`http://notlocalhost` 均被放行，`0.0.0.0` 的点未转义可匹配任意字符。现由 `Settings.cors_origin_regex` 派生：对每个主机 `re.escape` 并锚定 `^(?:https?://)?(?:host1|host2)(?::\d+)?$`，只放行所列主机本身及其任意端口；`ALLOWED_HOSTS` 为空时返回 `None`。`docs/TECH-DEBT.md` 第 8 项同步标为已解决。
- **测试**：`tests/unit/test_config_security_defaults.py`（15 项）覆盖生产缺密钥拒绝、开发密钥回退、短密钥拒绝、CORS 正则放行面，以及子串/未转义拒绝。

## 状态更新（2026-09-22 核实·续）

- **CFG2 [P3] 已修复（模型白名单双轨）**：`Settings.ALLOWED_MODELS` 全库零消费，生效白名单的唯一来源是 `MODEL_REGISTRY` → `codeRequest.ALLOWED_MODELS_LIST`。已删除该字段，并移除 `.env.example`/`.env.production.example` 中的 `ALLOWED_MODELS` 行（其示例值与注册表漂移，`.env.example` 还列着注册表中不存在的 `THUDM/GLM-4.1V-9B-Thinking`），改为指向 `MODEL_REGISTRY` 的说明。`codeRequest.GenerateRequest.ALLOWED_MODELS` 是 schema 字段（值来自 `ALLOWED_MODELS_LIST`），与本项无关。
- **CFG5 [P3] 已修复（provider registry 重复构建）**：`get_provider_registry` 原每次调用新建 `ProviderRegistry`，`llm_caller` 的 4 个消费点各建一份。现以模块级缓存复用：注册表只依赖 `settings` 中静态的 API Key/Base URL，而 `settings` 本身是 `lru_cache` 单例。`ProviderRouter.get_instance` 首次即固化实例，后续传入被忽略，故复用无行为变化。
- **本批测试**：`tests/unit/test_config_security_defaults.py` 追加 2 项（provider registry 进程内复用、`ALLOWED_MODELS` 死配置已移除），共 17 项。

## 状态更新（2026-09-22 核实·CFG3 部分）

- **CFG3（部分已修复）**：`WS_MAX_CONNECTIONS` 原在 `Settings` 中零消费——`WebSocketManager` 硬编码 `max_connections=50`。现全局实例改为 `WebSocketManager(max_connections=settings.WS_MAX_CONNECTIONS)`，上限真正可配。`ALLOWED_FILE_TYPES` 零消费（上传实际用 `file_upload.ALLOWED_EXTENSIONS`），已删除字段。
- **CFG3 剩余三项未改**：`LOG_RETENTION_DAYS`/`LOG_COMPRESS_OLD_LOGS`/`LOG_CLEANUP_SCHEDULE` 需与日志子系统（现按大小轮转的 `RotatingFileHandler`、FV6 死类 `CompressedRotatingFileHandler`、LGC4 横幅谎报、`services.md` LC1 假开关）一并设计，改动日志落盘行为，留待日志批次。
- **本批测试**：`tests/unit/test_config_security_defaults.py` 追加 1 项（`ALLOWED_FILE_TYPES` 已移除，共 18 项）；`tests/unit/test_websocket_manager.py` 追加 1 项（全局管理器上限取自 `settings.WS_MAX_CONNECTIONS`）。

## 状态更新（2026-09-22 核实·日志子系统批次）

- **CFG3 [P3] 全部修复（日志三项接线）**：
  - `LOG_RETENTION_DAYS` → `log_archiver._build_log_archiver` 的 `retention_days`。原实现按 `LOG_LEVEL` 派生保留天数（DEBUG 3 / INFO 7 / WARNING 14 / ERROR 30），配置项零消费；现以 `LOG_RETENTION_DAYS`（默认 30）为唯一来源。
  - `LOG_COMPRESS_OLD_LOGS` → 同函数的 `compression_enabled`（原硬编码 `True`）。
  - `LOG_CLEANUP_SCHEDULE` → `app/db/scheduler.py` 的 `log_cleanup` 任务间隔。新增 `_log_cleanup_interval_days()` 映射 `daily→1`/`weekly→7`/`monthly→30`，未知值回退 7；原硬编码 `days=7`。
- **FV6 [P3] 已修复（死类删除）**：删除 `logging_config.CompressedRotatingFileHandler`（零引用的死类）及其连带的未用导入 `RotatingFileHandler`/`TimedRotatingFileHandler`/`SQLAlchemyError`（LGC6 手抄异常清单随该类一并消失）。
- **LGC4 [P3] 已修复（启动横幅谎报）**：原横幅声称「日志轮转：每天，保留 14 天」「安全日志：保留 90 天」，与实际（全部按 10MB/5MB 大小轮转 + 按份数保留）不符。现改为「日志轮转：按大小 10MB/5MB 轮转，按份数保留」「日志归档：保留 N 天（压缩归档：启用/关闭）」，数值取自 `settings`，与实际行为一致。
- **本批测试**：新增 `tests/unit/test_log_subsystem_wiring.py`（9 项）覆盖归档器读数、调度映射与注册间隔、文件日志真实摘挂、死类已删；`services.md` LC1 见该文件对应更新。
