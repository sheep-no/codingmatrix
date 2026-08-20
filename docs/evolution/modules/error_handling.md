# json_parser.py + error_handler.py + error_codes.py 错误处理家族

> 第一百二十一轮补扫 | v1.122 | 2026-08-17 | 分析对象：`app/utils/json_parser.py`（219 行，容错 JSON 解析）+ `app/utils/error_handler.py`（225 行，全局异常处理）+ `app/utils/error_codes.py`（106 行，错误码枚举）
>
> 结论：**错误处理家族——容错 JSON 解析（LLM 输出 → 结构化数据）+ 全局异常处理（统一错误响应）+ 错误码枚举（api_response 消费）**——核心风险在容错解析的破坏性修复（损坏合法数据）与异常处理的信息泄露。

## 一、模块定位

| 模块 | 职责 | 消费方 |
|------|------|--------|
| json_parser.py | 容错 JSON 解析（4 策略降级） | LLM 输出解析（extract_json_from_llm） |
| error_handler.py | 全局异常 → 统一 JSON 错误响应 | FastAPI 注册（register_exception_handlers） |
| error_codes.py | 错误码枚举（AUTH_1xxx/VAL_2xxx/RES_3xxx/BIZ_4xxx/SYS_5xxx） | api_response.py |

## 二、缺陷清单

### P2（2 项）

- **EH1 [P2] `integrity_error_handler` 把原始 SQLAlchemy 错误暴露给用户——数据库结构信息泄露**——error_handler.py:144 `details={"original_error": str(exc.orig)}`——`exc.orig` 含表名/约束名/字段名/SQL 片段——返回给客户端——与 generic_exception_handler 的「服务器内部错误」信息隐藏策略（:205）**自相矛盾**（统一错误格式但这里泄露细节）。修复方向：details 移除 original_error（仅日志记录）。
- **JP1 [P2] RobustJSONParser `_fix_common_errors` 破坏性正则修复——损坏含撇号/冒号的合法 JSON**——json_parser.py:122 `re.sub(r"'([^']*)'", r'"\1"', text)`——**字符串值内的撇号被替换**（`"don't"` → `"don"t"` 直接非法）；:125 `(\s)([a-zA-Z_][a-zA-Z0-9_]*)(\s*):` 给词加引号——**字符串值内的冒号被误匹配**（`"time: 12:30"` → 冒号前被加引号）——LLM 输出含撇号/冒号的合法 JSON 被"修复"成损坏——策略 3 是策略 1/2 失败后的路径，触发即数据损坏（CII 家族）。修复方向：正则修复改为 token 级 JSON 修复（用 json 解析器逐步补全而非正则替换）。

### P3（5 项）

- **JP2 [P3] `extract_json_from_llm` 策略 3「第一个 `{` 到最后一个 `}`」——多 JSON 对象拼接时跨对象截取损坏**——json_parser.py:172-176——LLM 输出多个对象/含非 JSON 尾部时，起始到最末 `}` 间可能混入非对象内容 → 解析失败或截断。修复方向：逐对象提取第一个完整 JSON。
- **JP3 [P3] 容错解析静默接受部分数据——截断数据无告警**——parse_json/extract_json_from_llm 容错路径成功后调用方无感知（不知道数据是"修复"过的）——**下游把部分/损坏数据当完整结果**。修复方向：解析器返回修复标记。
- **EH2 [P3] 429 的 Retry-After 硬编码 60——与 rate_limiter 实际窗口不符**——error_handler.py:115 `headers["Retry-After"] = "60"`——客户端按 60s 重试但限流窗口可能是其他值。修复方向：从限流配置读取。
- **EH3 [P3] 两套错误码体系并存——响应错误码格式不统一**——error_handler.py 用字符串 code（VALIDATION_ERROR/DATABASE_ERROR/HTTP_ERROR），error_codes.py 用枚举 code（AUTH_1001/SYS_5001）——**api_response 用枚举、error_handler 用字符串——客户端需兼容两种格式**。修复方向：统一到 error_codes 枚举。
- **EC1 [P3] error_codes 定义 40+ 错误码但消费方仅 api_response——体系未被路由层采用**——全库仅 api_response.py:45 引用——大部分错误码（AUTH_1002 等）死代码未落地——与 error_handler 的字符串码并存形成双轨。修复方向：路由层全面迁移枚举或裁剪。

## 三、全库交叉确认

- **CII 家族（数据完整性）**：JP1/JP2/JP3 直接破坏 LLM 输出→结构化数据的转换完整性——与 web_search WS3（摘要注入）同属 LLM 输出处理链。
- **信息泄露家族**：EH1 与 crypto CRY5（解密吞错）、cache CA12（跨用户泄露）同族——但 EH1 是「对响应端的结构泄露」。
- **双轨模式**：EH3（字符串码 vs 枚举码）与加密双轨/缓存双轨/CodeValidator 双轨同族——两套错误码体系并存。
- **错误隐藏策略不一致**：generic/handler 对未知异常隐藏（防泄露）vs integrity handler 暴露原始错误——**同一文件内策略冲突**。

## 四、测试状态

零单元测试。EH1 原始错误泄露、JP1 正则损坏、JP3 部分数据无告警均无测试约束。修复建议：① 含撇号/冒号 JSON 修复测试（don't/time: 12:30 样本断言不损坏）；② integrity handler 响应不含 original_error 断言；③ 多 JSON 对象拼接提取测试；④ 错误码统一断言。
