# 模型管理接口

> 最后更新：2026-09-03

模型管理分为用户只读浏览、旧版管理员接口和统一模型配置三组 API。新管理功能应使用 `/api/v2/model-config`。

## 接口分组

### 用户模型浏览

前缀：`/api/v1/models`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/api/v1/models/` | 从 `MODEL_REGISTRY` 列出模型，可按能力和免费标记筛选 | 公开 |
| GET | `/api/v1/models/default` | 获取当前运行时默认模型 | 公开 |
| GET | `/api/v1/models/capabilities/list` | 列出能力枚举 | 公开 |
| GET | `/api/v1/models/agent-config` | 读取 Agent 运行时配置 | JWT |
| GET | `/api/v1/models/{model_id}` | 获取注册表模型详情 | 公开 |

该接口读取 `app/utils/aicloud/model_registry.py` 的注册表。默认模型可由旧版管理员 API 在当前进程内切换。

### 统一模型配置

前缀：`/api/v2/model-config`，全部端点要求 superadmin。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v2/model-config/models` | 获取模型，可按类型或启用状态筛选 |
| POST | `/api/v2/model-config/models` | 添加模型 |
| PUT | `/api/v2/model-config/models/{id}` | 更新模型 |
| DELETE | `/api/v2/model-config/models/{id}` | 删除模型 |
| PUT | `/api/v2/model-config/models/{id}/toggle` | 切换启用状态 |
| GET | `/api/v2/model-config/providers` | 获取供应商 |
| POST | `/api/v2/model-config/providers` | 添加供应商 |
| DELETE | `/api/v2/model-config/providers/{id}` | 删除供应商 |
| GET | `/api/v2/model-config/agent` | 获取角色和降级链 |
| PUT | `/api/v2/model-config/agent/role` | 更新角色模型 |
| PUT | `/api/v2/model-config/agent/fallback` | 更新降级链 |
| POST | `/api/v2/model-config/reload` | 从 YAML 重新加载 |

模型字段包括 ID、API 名称、显示名称、供应商、类型、上下文长度、最大输出、温度、超时、推理标记、思考比例、速度、启用状态和标签。支持的类型约定为 `chat`、`embedding`、`image`、`vision`、`audio`。

添加模型时必须引用已存在的供应商。更新角色和降级链时必须引用已存在的模型；角色限于 architect、frontend、backend、reviewer、fallback。

### 旧版管理员接口

前缀：`/api/v2/models`，全部端点要求 superadmin。模块已在源码中标记为废弃并保留兼容性：

- `POST /api/v2/models/default`：切换当前进程默认模型。
- `PUT /api/v2/models/agent-config`：更新角色模型。
- `POST /api/v2/models/agent-config/reload`：重新加载角色配置。
- `PUT /api/v2/models/agent-config/fallback-chain`：更新降级链。
- `PUT /api/v2/models/agent-config/error-type-model`：更新错误类型映射。
- `GET /api/v2/models/context-lengths`：读取上下文长度。
- `PUT /api/v2/models/context-length`：写入上下文长度覆盖。
- `DELETE /api/v2/models/context-length/{model_key}`：删除覆盖并恢复代码默认值。

旧接口直接修改 `data/agent_model_config.yaml` 的部分字段；统一接口以管理面配置为源，因此混用两组写接口可能导致后续同步覆盖旧接口改动。

## 配置生命周期

`ModelConfigManager` 的保存流程：

1. 将 providers、models 和 agent 写入 `data/unified_model_config.yaml`。
2. 将模型、角色和降级链同步到 `data/agent_model_config.yaml`。
3. 保留运行时文件中的 `error_type_models`、`settings`、`cross_validation` 和 `model_context_lengths`。
4. 失效动态模型映射缓存并重新加载角色配置，同时尝试刷新已创建路由实例的降级链。

YAML 通过 `yaml.safe_load` 和 `yaml.safe_dump` 读写。加载失败时管理器回退到代码中的默认供应商和模型配置。

当前保存实现会重建 `version`、`description`、`last_updated`、`providers`、`models` 和 `agent` 顶层字段；现有 `defaults` 顶层映射会在首次管理写入后被移除。`_refresh_runtime_config()` 以同步方式调用异步 `get_dynamic_router()`，因此已创建路由实例的 fallback 链刷新会进入异常处理分支，进程重启或后续代码修复后才会完整应用该部分。

## 当前统一配置

`data/unified_model_config.yaml` 当前只声明 `siliconflow` 供应商，模型覆盖聊天、视觉、图像、嵌入、音频和翻译等类型。默认用途映射包括 code、reasoning、architect、fast、visual、ocr、embedding 和 ppt。

当前 Agent 角色：

| 角色 | 模型 ID |
|------|---------|
| architect | `qwen3-8b` |
| frontend | `deepseek-r1` |
| backend | `deepseek-r1` |
| reviewer | `glm-z1-9b` |
| fallback | `qwen3-8b` |

降级链为 `qwen3-8b -> glm-z1-9b`。

## 三类供应商配置

| 入口 | 存储 | 作用域 | 用途 |
|------|------|--------|------|
| `/api/v2/model-config/providers` | `unified_model_config.yaml` | superadmin 全局 | 模型管理和 Agent 派生配置 |
| `/api/v1/providers` | 后端进程内存 | 已认证调用者共享 | 任意 OpenAI/Anthropic 动态聊天服务 |
| 用户 API Key 接口 | Redis，加进程内恢复对象 | 用户 Token | 使用用户自己的内置供应商密钥 |

这三类入口拥有独立的数据结构和生命周期。统一模型供应商记录仅包含 ID、名称、API Key、Base URL 和启用状态；模型发现和连接测试由 `/api/v1/providers` 的独立实现负责。统一配置中的 API Key 会写入 YAML，列表响应仅返回 `has_api_key` 布尔值。

## 前端

- `UnifiedModelConfig.vue` 管理统一模型、供应商和角色配置。
- `AgentModelConfig.vue` 管理角色与降级链。
- `DynamicProviderManager.vue` 管理独立的进程内动态供应商。

## 相关文件

- `app/api/v1/model_manager.py`
- `app/api/v2/model_admin.py`
- `app/api/v2/model_config_api.py`
- `app/services/model_config_manager.py`
- `app/utils/model_config_io.py`
- `app/utils/aicloud/model_registry.py`
- `app/agent/dynamic_model_router.py`
- `data/unified_model_config.yaml`
- `data/agent_model_config.yaml`
