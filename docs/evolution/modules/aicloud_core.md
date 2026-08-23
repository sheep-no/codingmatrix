# AI Cloud 核心路由与审计（model_registry + provider_router + providers + dynamic_provider + permission + audit_logger + http_client）

> 第一百三十七轮补扫 | v1.138 | 2026-08-17 | 分析对象：`app/utils/aicloud/` 核心路由与审计族——`model_registry.py`（334 行）+ `provider_router.py`（133 行）+ `providers.py`（64 行）+ `dynamic_provider.py`（166 行）+ `permission.py`（97 行）+ `audit_logger.py`（266 行）+ `http_client.py`（139 行）+ 消费方 `app/api/v1/aicloud.py`、`app/api/v1/model_manager.py`、`app/api/v1/providers.py`
>
> 结论：**动态供应商管理 API 无 admin 校验可被普通用户用于供应商投毒（全站模型路由劫持）；模型名双套体系（registry model_key vs config id）叠加前缀模糊匹配导致非 siliconflow 路由死路径与误路由；审计日志双轨且 details 序列化破坏结构化**。llm_caller 已在第一百二十九轮建档，本轮跳过。

## 一、模块定位

| 组件 | 位置 | 接线状态 |
|------|------|----------|
| MODEL_REGISTRY（17 模型静态表） | model_registry.py:70 | model_manager.py:80、aicloud.py:86/:872 真实消费 |
| get_model / get_default_model / get_available_models | model_registry.py:296-320 | aicloud.py/model_manager.py 真实消费 |
| ProviderRouter | provider_router.py:73 | llm_caller.py:239/:330 真实消费（route/get_fallback_providers） |
| MODEL_PROVIDER_MAP | provider_router.py:59 | llm_caller 路由核心 |
| ProviderRegistry / ProviderConfig | providers.py:23-64 | provider_router 消费 |
| DynamicProviderManager | dynamic_provider.py:51 | llm_caller.py:255、provider_router.py:100、providers API 真实消费 |
| get_user_permission_level / check_aicloud_permission | permission.py:20/:47 | aicloud.py / aicloud_knowledge.py 真实消费（admin 门禁） |
| require_aicloud_permission | permission.py:72 | **全库零消费——死依赖** |
| log_operation / log_file_read / log_file_write / query_audit_logs | audit_logger.py | aicloud.py 真实消费 |
| get_http_client / call_with_retry / RateLimitedClient | http_client.py | adapters/ 8 文件 + GirlAi.py 真实消费 |

## 二、缺陷清单

### P2（10 项）

- **PAPI1 [P2] 动态供应商全局共享、无用户隔离——用户 A 添加的供应商对全站所有用户调用生效**——app/api/v1/providers.py 允许任何登录用户添加自带 key/base_url 的动态供应商（**这是合理的用户级功能，admin 门禁并非必要**）——但 `get_dynamic_provider_manager()` 是全局单例，llm_caller.py:255 `get_by_model(model)` **全局搜索**——**用户 A 配置与内置模型同 id 的供应商 → 用户 B 调用同名模型时命中 A 的供应商，B 的请求内容（prompt/上下文）外泄给 A 的服务器**——正确修复是**按用户隔离供应商**（providers 归属 user_id，路由仅查当前用户的供应商），而非简单加 admin。
- **PAPI2 [P2] sync/test 端点 SSRF——向用户可控 base_url 发请求**——providers.py `sync_models` 调 `fetch_models_openai`（dynamic_provider.py:114 `{base_url}/models`）、`test_connection` 调 `{base_url}/messages`——base_url 由普通用户任意配置（无协议白名单/内网 IP 校验）——**服务端发起对内网/metadata 的请求**（169.254.169.254 等）——与 WS2/HRQ1 SSRF 家族同源，且此处是普通用户即可触发。
- **MR1 [P2] 两套模型名体系分裂——registry model_key vs config id——非 siliconflow 路由死路径**——aicloud.py:335 `model=model_info.model_key`（"Qwen/Qwen3-8B"）传给 call_llm → llm_caller.py:239 `router.route(model)`——而 `MODEL_PROVIDER_MAP` 键是 `data/agent_model_config.json` 的模型 **id**（"qwen3-8b"，provider_router.py:32-37）——**model_key 与 id 互不匹配** → route() 精确匹配失败 → 全部静默兜底 SILICONFLOW——config 中非 siliconflow 供应商（qwen-plus→DASHSCOPE 等兜底条目）对 registry 驱动路径永远不生效。
- **PR1 [P2] route() 前缀模糊匹配误路由**——provider_router.py:116-118 `model_name.startswith(model_key.split("/")[0])`——"deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"（siliconflow 托管）前缀命中兜底键 "deepseek-ai/DeepSeek-R1"（:45）→ **误路由 DEEPSEEK 官方**——用不存在的模型名调 deepseek 官方 API → 报错/降级（MR1 与 PR1 叠加）。
- **MR2 [P2] is_free 全部 False——免费模型过滤双处失效**——model_registry.py 17 个 ModelInfo 无一 `is_free=True` → `get_available_models(free_only=True)` 恒空列表；且 model_manager.py list_models（:71-98）接受 `free_only` 参数**却从不检查**——API 层免费过滤直接忽略（参数存在即假象）。
- **PR2 [P2] 模块级 import 读盘副作用 + 配置失败静默降级**——provider_router.py:59 `MODEL_PROVIDER_MAP = _load_provider_map()`——每次 import 读 data/agent_model_config.json——文件缺失/损坏时 logger.warning 后静默用兜底 setdefault 集合（TDC5/AIU2 家族）。
- **DP1 [P2] 动态供应商内存单例无持久化——重启全丢 + 多 worker 每进程独立**——dynamic_provider.py:104-111 `_manager` 进程内存——用户添加的供应商在重启/多 worker（gunicorn）下丢失或不一致（WF5/CS1/TM3 家族）。
- **DP2 [P2] fetch_models_openai 无 SSRF/协议校验（库函数层面）**——dynamic_provider.py:114-152 直接拼 `{base_url}/models` 请求，无内网 IP 黑名单、无协议白名单、无响应体大小限制——PAPI2 的底层放行点。
- **ADT1 [P2] audit `details` 用 `str(details)` 序列化——结构化审计数据变字符串落库**——audit_logger.py:49 `details=str(details) if details else None`——dict 变 Python repr 字符串（含单引号）——查询/统计/检索无法结构化使用，审计日志名存实亡（SLG1 双层序列化家族）。
- **ADT2 [P2] 审计日志双轨——两套 audit_logger 并存**——app/utils/aicloud/audit_logger.py vs app/services/audit_logger.py——同名模块两实现，schema/写入语义各自独立（**双轨家族第 17 处**）。

### P3（18 项）

- **MR3 [P3] 双 ModelProvider 枚举并存**——model_registry.py:32（仅 SILICONFLOW 单值 + 预留注释）vs providers.py:12（七值）——**双轨家族第 18 处**。
- **MR4 [P3] 语音/嵌入/重排模型能力标错 TEXT**——sense-voice/telespeech-asr/bce-embedding/bge 系列 capabilities 全是 `ModelCapability.TEXT`——按能力过滤混入非文本模型。
- **MR5 [P3] docstring 与 registry 漂移**——model_registry.py:8-25 声明 15 模型（含 paddleocr-vl-1.5），实际 17 个（多 glm-4.1v-9b、无 paddleocr）。
- **PR3 [P3] get_instance 单例无锁 + set_registry 直接换实例**——provider_router.py:84-95——并发首访竞态；set_registry 后旧引用持有者仍用旧实例（状态分裂）。
- **PR4 [P3] route() 动态分支异常静默 pass**——provider_router.py:109-110——动态供应商查询失败静默降级（LMC8 家族）。
- **PR5 [P3] PROVIDER_FALLBACK 硬编码与 dynamic_model_router 配置双源**——provider_router.py:62-70 vs agent/dynamic_model_router 自有降级链——fallback 语义两处。
- **PRV1 [P3] ProviderRegistry.register 静默丢弃无效配置**——providers.py:48-51——缺 api_key/base_url 的配置直接跳过，调用方不知情（SC4 家族）。
- **DP3 [P3] api_key 明文内存驻留 + list() 返回共享 models 列表引用**——dynamic_provider.py:43 api_key 字段明文；list()（:79-88）新建 DynamicProvider 但 `models=p.models` 共享原对象列表——外部可改内部状态。
- **DP4 [P3] fetch_models_anthropic 假拉取**——dynamic_provider.py:155-166 硬编码已知模型列表，无实际 API 调用——sync 对 anthropic 供应商是假同步（last_sync 被更新但列表固定）。
- **DP5 [P3] add() 无 base_url 格式/可达性校验**——dynamic_provider.py:57-64 任意字符串直存。
- **PAPI3 [P3] delete/toggle/sync/test 无所有者校验**——providers.py 各端点 `manager.get(pid)` 无 user_id 关联——任何登录用户可操作他人添加的供应商（越权）——**与 PAPI1 同根因（供应商无归属隔离）**。
- **PAPI4 [P3] api_key 仅查 `len >= 10` 弱校验**——providers.py:83——弱凭据放行。
- **PERM1 [P3] require_aicloud_permission 依赖项零消费死代码**——permission.py:72-97 全库零引用（aicloud.py 手动调 check_aicloud_permission）——**死代码家族累计第 15 处**。
- **ADT3 [P3] log_operation 每次 db.commit 无批量**——audit_logger.py:52-54——高频文件读写审计逐个提交。
- **ADT4 [P3] cleanup_old_audit_logs 只清 success 状态**——audit_logger.py:259 `status == "success"`——failed 日志永不清理，表膨胀。
- **HC1 [P3] call_with_retry 只判 status_code==200 成功**——http_client.py:69——非 200 且不在 retry_on_status 的响应（400/401）静默返回给调用方，调用方需自行识别失败。
- **HC2 [P3] 模块级 `_max_concurrent_calls` 死常量**——http_client.py:19 定义后从未使用（RateLimitedClient 用实例 semaphore）——**死代码家族累计第 16 处**。
- **HC4 [P3] 并发控制双轨**——aicloud http_client 的 Semaphore 体系 vs llm_caller 的 global+model 信号量体系（LMC6）——两套并发防线互不知晓。

## 三、全库交叉确认

- **供应商投毒链（修正定位）**：PAPI1 的正确缺陷是**全局共享无用户隔离**——`get_dynamic_provider_manager()` 全局单例 + `get_by_model` 全局搜索——用户 A 添加的供应商影响用户 B 的调用——修复是供应商按 user_id 归属、路由仅查当前用户；PAPI3（无所有者校验）是同一根因。
- **SSRF 链**：PAPI2（端点触发）→ DP2（库函数放行）→ fetch_models_openai 向任意 base_url 发 GET——与 WS2（web_search 详情页）、HRQ1/HRQ2（http_request 节点）构成第四处服务端外连面。
- **模型名双轨**：MR1 + PR1——registry 的 model_key（"Qwen/Qwen3-8B"）与 config 的 id（"qwen3-8b"）在 route() 处不匹配——非 siliconflow 路由全死 + 前缀误匹配把 siliconflow 托管模型路由到官方供应商——**模型路由层两处缺陷叠加**。
- **死代码家族累计第 15/16 处**：PERM1（require_aicloud_permission 死依赖）、HC2（_max_concurrent_calls 死常量）。
- **双轨家族第 17/18 处**：ADT2（审计双轨）、MR3（双 ModelProvider 枚举）。
- **与第一百二十九轮衔接**：llm_caller 路由核心在本轮建档（provider_router/providers）——LMC6 信号量体系与 HC4 并发双轨是本轮 HC4 的依据。

## 四、测试状态

零单元测试。PAPI1（无 admin 校验）、MR1（model_key vs id 路由失配）、PR1（前缀误路由）、MR2（free_only 双处失效）、ADT1（details 字符串化）全部实码可证无任何用例保护。修复建议：① PAPI1/PAPI3 供应商按 user_id 归属隔离（路由仅查当前用户的供应商，勿用 admin 门禁替代）；② PAPI2/DP2 加 base_url 白名单（https + 域名）+ 内网 IP 阻断；③ MR1/PR1 统一模型名来源（route 直接吃 registry model_key 或配置对齐）并删除前缀模糊匹配改精确匹配；④ MR2 补 is_free 数据或删 free_only 参数；⑤ ADT1 用 JSON 序列化 details；⑥ ADT2 收敛审计模块；⑦ 下轮转 code_executor + auto_executor + sandbox + sandbox_operator + content_analyzer + context_isolator + sensitive_filter + review_queue + knowledge_processor。
