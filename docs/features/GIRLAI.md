# 虚拟姬 (GirlAi)

虚拟姬是 CodingMatrix 的 AI 情感陪伴功能，提供多角色虚拟对话体验。支持 5 个预设角色、自定义角色创建、用户偏好记忆、对话历史管理等能力。

> 源码: `app/api/v1/GirlAi.py` (855 行) | Schema: `app/schema/girl_request.py`

---

## 概述

虚拟姬是一个 AI 情感陪伴角色系统，用户可以与不同性格的 AI 虚拟角色进行自然对话。系统特点：

- **多角色系统** — 5 个预设角色 + 用户自定义角色
- **智能模型选择** — 根据角色自动匹配最优 LLM 模型
- **情感陪伴优化** — 专用 Prompt 构建，保持角色一致性
- **用户偏好记忆** — 自动从对话中提取用户信息并持久化
- **对话历史管理** — 完整的历史记录、搜索、清除能力
- **并发控制** — 信号量限制最大 10 并发请求

---

## 预设角色

系统内置 5 个预设角色，每个角色有独立的性格、说话风格和模型配置。

| 角色 ID | 名称 | 性格 | 说话风格 | 模型 | temperature |
|---------|------|------|----------|------|-------------|
| `gentle` | 温柔姐姐 | 温柔、体贴、善解人意、成熟 | 语气温柔，常用「呢」「哦」「呀」等语气词，喜欢用~符号 | DeepSeek-R1-0528-Qwen3-8B | 0.8 |
| `lively` | 元气少女 | 活泼、开朗、乐观、元气满满 | 语气轻快，常用感叹号，大量使用 emoji 和颜文字 | Qwen3-8B | 0.9 |
| `tsundere` | 傲娇妹妹 | 傲娇、别扭、嘴硬心软、容易害羞 | 口是心非，常用「才不是」「哼」「笨蛋」等词汇 | Qwen3-8B | 0.85 |
| `intellectual` | 知性学姐 | 知性、理性、博学、优雅 | 语气温和，措辞文雅，偶尔引用名言或知识点 | DeepSeek-R1-0528-Qwen3-8B | 0.7 |
| `companion` | 专属伴侣 | 专一、深情、贴心、浪漫 | 语气温柔亲昵，常用爱称，表达爱意 | DeepSeek-R1-0528-Qwen3-8B | 0.85 |

### 角色问候示例

**温柔姐姐:**
- "亲爱的，今天过得怎么样呀？~"
- "欢迎回来~ 我一直在等你呢"

**元气少女:**
- "呀吼~！今天也要元气满满哦！(≧∇≦)ﾉ"
- "哇！你来啦！我等你好久啦~✨"

**傲娇妹妹:**
- "哼、哼！才、才不是特意等你呢！(￣^￣)"
- "…笨蛋，下次别让我等这么久啦！"

**知性学姐:**
- "你好呀，今天也是求知的一天呢"
- "又见面了，最近在读什么有趣的书吗？"

**专属伴侣:**
- "亲爱的~ 我好想你呀！❤"
- "最喜欢你啦~ 今天也想和你在一起 ❤"

---

## API 端点

全部 11 个端点，路由前缀 `/api/v1/GirlAi`。

### 端点总览

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| POST | `/GirlAi` | AI 对话（主接口） | ✅ |
| GET | `/GirlAi/characters` | 获取角色列表 | ✅ |
| GET | `/GirlAi/characters/{id}/avatar` | 获取角色 SVG 头像 | ❌ |
| GET | `/GirlAi/history` | 获取对话历史 | ✅ |
| GET | `/GirlAi/history/search` | 搜索对话历史 | ✅ |
| DELETE | `/GirlAi/history` | 删除/清除历史记录 | ✅ |
| POST | `/GirlAi/characters/custom` | 创建自定义角色 | ✅ |
| GET | `/GirlAi/characters/custom/list` | 获取自定义角色列表 | ✅ |
| DELETE | `/GirlAi/characters/custom/{id}` | 删除自定义角色 | ✅ |
| GET | `/GirlAi/preferences` | 获取用户偏好 | ✅ |
| DELETE | `/GirlAi/preferences/{id}` | 删除用户偏好 | ✅ |

### 1. AI 对话

**POST `/GirlAi`** — 虚拟姬 AI 对话主接口。

请求体 (`GirlRequest`):

```json
{
  "prompt": "今天心情不太好",
  "character_id": "gentle",
  "temperature": 0.8,
  "max_tokens": 180
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `prompt` | string | ✅ | 用户输入，1-2000 字符 |
| `character_id` | string | ❌ | 角色 ID，默认 `gentle` |
| `temperature` | float | ❌ | AI 温度，0.0-1.5 |
| `max_tokens` | int | ❌ | 最大 Token 数，50-1000 |

响应 (`GirlResponse`):

```json
{
  "message": "怎么啦亲爱的~ 有什么烦恼可以和我说说哦，我会一直陪着你的 ❤",
  "model": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
  "tokens_used": 156
}
```

### 2. 获取角色列表

**GET `/GirlAi/characters`** — 获取所有可用预设角色。

响应:

```json
{
  "characters": [
    {
      "id": "gentle",
      "name": "温柔姐姐",
      "description": "温柔体贴的大姐姐，总是耐心倾听你的烦恼",
      "tags": ["温柔", "治愈", "姐姐", "贴心"],
      "speaking_style": "语气温柔，常用「呢」「哦」「呀」等语气词，喜欢用~符号"
    }
  ],
  "total": 5
}
```

### 3. 获取角色头像

**GET `/GirlAi/characters/{character_id}/avatar`** — 返回 SVG 格式头像。

- 响应类型: `image/svg+xml`
- 若角色 ID 不存在，返回默认头像（温柔姐姐）

### 4. 获取对话历史

**GET `/GirlAi/history`** — 分页获取对话历史记录。

查询参数:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | int | 20 | 返回记录数，1-100 |
| `offset` | int | 0 | 分页偏移量 |

响应 (`HistoryResponse`):

```json
{
  "total": 42,
  "records": [
    {
      "id": "abc123",
      "role": "user",
      "content": "今天心情不太好",
      "model": null,
      "token_usage": null,
      "created_at": "2026-06-22T10:30:00"
    },
    {
      "id": "abc124",
      "role": "assistant",
      "content": "怎么啦亲爱的~ 有什么烦恼可以和我说说哦",
      "model": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
      "token_usage": 156,
      "created_at": "2026-06-22T10:30:01"
    }
  ],
  "has_more": true
}
```

### 5. 搜索对话历史

**GET `/GirlAi/history/search`** — 按关键词搜索历史对话。

查询参数:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `q` | string | ✅ | 搜索关键词，1-100 字符 |
| `limit` | int | ❌ | 返回记录数，默认 20 |
| `offset` | int | ❌ | 分页偏移量，默认 0 |

响应:

```json
{
  "records": [
    {
      "id": "abc123",
      "role": "user",
      "content": "我喜欢看电影",
      "model": null,
      "created_at": "2026-06-22T10:30:00"
    }
  ],
  "total": 1,
  "query": "电影"
}
```

### 6. 删除对话历史

**DELETE `/GirlAi/history`** — 删除指定记录或清除全部历史。

查询参数:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `record_ids` | List[str] | ✅ | 要删除的记录 ID 列表 |
| `all` | bool | ❌ | 是否清除所有记录（忽略 record_ids） |

响应:

```json
{"status": "deleted", "count": 3}
```

### 7. 创建自定义角色

**POST `/GirlAi/characters/custom`** — 创建用户自定义角色（上限 10 个）。

请求体:

```json
{
  "name": "病娇学妹",
  "description": "表面温柔实则占有欲极强的学妹",
  "personality": "温柔、占有欲强、偏执、深情",
  "speaking_style": "语气温柔但偶尔透露出危险的气息",
  "greetings": ["学长~ 今天只和我一个人聊天好不好？"],
  "tags": ["病娇", "学妹", "占有欲"],
  "model": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
  "temperature": 0.85,
  "max_tokens": 180,
  "avatar_color": "#ff6b9d"
}
```

| 字段 | 类型 | 必填 | 限制 | 说明 |
|------|------|------|------|------|
| `name` | string | ✅ | ≤50 字符 | 角色名称 |
| `description` | string | ❌ | ≤200 字符 | 角色描述 |
| `personality` | string | ❌ | ≤200 字符 | 性格特征 |
| `speaking_style` | string | ❌ | ≤200 字符 | 说话风格 |
| `greetings` | List[str] | ❌ | — | 问候语列表 |
| `tags` | List[str] | ❌ | — | 标签列表 |
| `model` | string | ❌ | — | 模型名称，默认 DeepSeek-R1 |
| `temperature` | float | ❌ | — | 温度，默认 0.8 |
| `max_tokens` | int | ❌ | — | 最大 Token，默认 180 |
| `avatar_color` | string | ❌ | ≤20 字符 | 头像颜色，如 `#667eea` |

响应:

```json
{"id": "uuid-xxx", "name": "病娇学妹", "message": "角色创建成功"}
```

### 8. 获取自定义角色列表

**GET `/GirlAi/characters/custom/list`** — 获取当前用户的所有自定义角色。

响应:

```json
{
  "characters": [
    {
      "id": "uuid-xxx",
      "name": "病娇学妹",
      "description": "表面温柔实则占有欲极强的学妹",
      "personality": "温柔、占有欲强、偏执、深情",
      "speaking_style": "语气温柔但偶尔透露出危险的气息",
      "greetings": ["学长~ 今天只和我一个人聊天好不好？"],
      "tags": ["病娇", "学妹"],
      "model": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
      "temperature": 0.85,
      "max_tokens": 180,
      "avatar_color": "#ff6b9d",
      "created_at": "2026-06-22T10:00:00"
    }
  ],
  "total": 1
}
```

### 9. 删除自定义角色

**DELETE `/GirlAi/characters/custom/{character_id}`** — 删除指定自定义角色。

响应: `{"status": "deleted", "id": "uuid-xxx"}`

### 10. 获取用户偏好

**GET `/GirlAi/preferences`** — 获取从对话中自动提取的用户偏好。

响应:

```json
{
  "preferences": [
    {
      "id": "uuid-xxx",
      "key": "name",
      "value": "小明",
      "confidence": 80,
      "source": "extracted",
      "updated_at": "2026-06-22T10:30:00"
    },
    {
      "id": "uuid-yyy",
      "key": "hobby",
      "value": "看电影",
      "confidence": 80,
      "source": "extracted",
      "updated_at": "2026-06-22T09:00:00"
    }
  ]
}
```

### 11. 删除用户偏好

**DELETE `/GirlAi/preferences/{preference_id}`** — 删除指定偏好记录。

响应: `{"status": "deleted", "id": "uuid-xxx"}`

---

## 自定义角色

### 创建流程

1. 调用 `POST /GirlAi/characters/custom` 创建角色
2. 每个用户最多 10 个自定义角色
3. `temperature` 存储时乘以 100 为整数，读取时除以 100 还原
4. `greetings` 和 `tags` 以 JSON 字符串存储

### 使用自定义角色

创建后，通过 `character_id` 参数传入自定义角色的 UUID 即可在对话中使用：

```json
{
  "prompt": "你好呀",
  "character_id": "uuid-xxx"
}
```

---

## 用户偏好

### 自动提取机制

系统在每次对话后**异步**从用户消息中提取偏好信息（不阻塞响应），支持的提取模式：

| 偏好类型 | 匹配模式示例 |
|---------|-------------|
| `name` | "我叫小明"、"叫我小明" |
| `age` | "我18岁"、"我今年20" |
| `hobby` | "我喜欢看电影"、"我的爱好是画画" |
| `mood` | "我很开心"、"今天心情不好" |
| `work` | "我在腾讯工作"、"我是程序员" |
| `location` | "我住在北京"、"我是上海人" |

### 偏好存储

- 存储在 `UserPreference` 表
- 使用 upsert 逻辑：相同 key 更新 value
- 默认 confidence 为 80，source 为 `extracted`
- 偏好在下次对话时自动注入 Prompt，让角色"记住"用户信息

---

## 对话历史

### 存储结构

每轮对话保存两条记录：

| 字段 | 说明 |
|------|------|
| `id` | 记录唯一 ID |
| `role` | `user` 或 `assistant` |
| `content` | 消息内容 |
| `model` | 使用的模型（仅 assistant） |
| `token_usage` | Token 消耗（仅 assistant） |
| `created_at` | 创建时间 |

### 上下文加载

对话时加载最近 10 条消息（`MAX_HISTORY_MESSAGES = 10`）作为上下文，Prompt 中只取最近 6 条用于构建历史部分。

---

## 角色头像

系统使用内联 SVG 生成角色头像，无需外部文件。每个角色有独立的渐变色和面部特征：

| 角色 | 主色调 | 特征 |
|------|--------|------|
| 温柔姐姐 | 粉色 `#f9a8d4 → #f472b6` | 微笑表情 |
| 元气少女 | 黄色 `#fcd34d → #f59e0b` | 星星装饰 + 大笑 |
| 傲娇妹妹 | 红色 `#fca5a5 → #ef4444` | 腮红 + 不高兴表情 |
| 知性学姐 | 紫色 `#a78bfa → #7c3aed` | 眼镜 + 微笑 |
| 专属伴侣 | 玫红 `#fda4af → #e11d48` | 爱心装饰 |

SVG 结构：圆形背景渐变 + 白色头部轮廓 + 面部特征 + 角色专属装饰。

---

## Prompt 构建

`_build_emotion_prompt` 函数负责构建情感陪伴优化的完整 Prompt。

### 构建流程

```
┌─────────────────────────────────┐
│ 1. 角色设定                      │
│ "你是温柔姐姐，温柔体贴的大姐姐…"  │
│ 性格 + 说话风格 + 行为指令         │
├─────────────────────────────────┤
│ 2. 对话示例 (Few-shot)           │
│ 取 greetings 前 2 条作为示例      │
├─────────────────────────────────┤
│ 3. 用户偏好记忆                   │
│ "你记住的用户信息：name: 小明…"   │
│ 按 confidence 降序，最多 10 条    │
├─────────────────────────────────┤
│ 4. 对话历史                      │
│ 最近 6 条消息（user/assistant）   │
├─────────────────────────────────┤
│ 5. 用户称呼                      │
│ （当前未启用，预留字段）           │
├─────────────────────────────────┤
│ 6. 当前输入                      │
│ "用户：今天心情不太好"            │
│ "温柔姐姐："（引导模型续写）      │
└─────────────────────────────────┘
```

### Prompt 模板示例

```
你是温柔姐姐，温柔体贴的大姐姐，总是耐心倾听你的烦恼
性格：温柔、体贴、善解人意、成熟
说话风格：语气温柔，常用「呢」「哦」「呀」等语气词，喜欢用~符号
请始终保持角色设定，给予温暖、贴心的回应。

【对话示例】
你：亲爱的，今天过得怎么样呀？~
你：欢迎回来~ 我一直在等你呢

【你记住的用户信息】
- name：小明
- hobby：看电影
请在对话中自然地运用这些信息，让用户感到被记住和关心。

【对话历史】
用户: 最近工作好累
温柔姐姐: 辛苦啦~ 要注意休息哦，别太勉强自己

【当前对话】
用户：今天心情不太好
温柔姐姐：
```

### 响应清理

`_clean_response` 函数移除模型输出中的冗余前缀：

- 角色名前缀：`温柔姐姐: xxx` → `xxx`
- 方括号标注：`【xxx】xxx` → `xxx`
- 圆括号标注：`(xxx) xxx` → `xxx`
- 引号前缀：`": xxx` → `xxx`

---

## 技术细节

### 并发控制

- 全局信号量 `_max_concurrent_calls = 10`，限制同时 AI 调用数
- Model Adapter 使用异步锁 `_model_adapters_lock` 保证线程安全
- 请求超时 `REQUEST_TIMEOUT = 30.0` 秒
- AI 调用使用 `call_with_retry` 最多重试 3 次

### 模型配置

| 角色 | 模型 | temperature | max_tokens |
|------|------|-------------|------------|
| 温柔姐姐 | DeepSeek-R1-0528-Qwen3-8B | 0.8 | 180 |
| 元气少女 | Qwen3-8B | 0.9 | 150 |
| 傲娇妹妹 | Qwen3-8B | 0.85 | 160 |
| 知性学姐 | DeepSeek-R1-0528-Qwen3-8B | 0.7 | 200 |
| 专属伴侣 | DeepSeek-R1-0528-Qwen3-8B | 0.85 | 200 |
| 默认 | DeepSeek-R1-0528-Qwen3-8B | 0.8 | 180 |

### 数据模型

| 模型 | 文件 | 说明 |
|------|------|------|
| `ChatHistory` | `app/models/chat_history.py` | 对话历史记录 |
| `CustomCharacter` | `app/models/chat_history.py` | 用户自定义角色 |
| `UserPreference` | `app/models/chat_history.py` | 用户偏好记忆 |
