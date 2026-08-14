# cross_validator.py 深扫详档

> 版本：v1.66 | 日期：2026-08-09 | 文件：`app/agent/cross_validator.py`（1512 行，方法 30+，全库最大验证模块）
> 结论：**P2 3 项（CV1 实测、CV2/CV3 静态）、P3 3 项**｜单元测试：零

## 定位

spec_first 生成链的**交叉验证层**：对关键文件（认证/支付/安全类）双模型生成 + 裁判 LLM 择优，并对全项目做跨文件一致性验证（导入/符号/API 契约/数据模型/函数签名 5 类）+ LLM 批量修复。

## 跨模块引用链

| 方向 | 模块 | 位置 | 用途 |
|------|------|------|------|
| 被消费 | spec_first_generate.py | :489/:1050 `cross_validate_with_refinement`（双模型 content_a/content_b + 裁判）；:697 `validate_and_fix`（跨文件一致性 + 修复）；:691 实例化 | 交叉验证主链 |
| 被消费 | spec_first_generate.py | `is_critical_file` 判定关键文件 | 触发开关 |
| 依赖 | app.utils.call_llm（llm_caller.py:179） | :181/:1424 `response.get("choices")`——**dict 契约，与 CodeReviewer(AIReviewer 侧) 同族正确方** | 裁判/修复调用 |
| 依赖 | RefinementLoop | cross_validate_with_refinement :263 | 择优后迭代修复 |
| 依赖 | json_parser.safe_parse_json | _extract_json :275 | 裁判结果解析 |
| 依赖 | language_adapter | _validate_imports :876-894 优先走适配器 | 导入验证 |
| 重复 | api_contract_checker / integrity_validator._validate_api_contracts | _validate_api_contracts :1006 | **三套 API 契约校验并存**（TASKS 已记录） |
| 测试 | — | — | **零测试** |

## 关键代码路径

`is_critical_file`（:114）：priority=1 无条件触发 / priority<=2 且路径或类型子串命中 critical_patterns → 双模型交叉验证。`validate_cross_file_consistency`（:282）：5 类正则验证。`validate_and_fix`（:1200）：验证 → 缺模块自动生成 → LLM 批量修复。`validate_and_select`（:141）：双版本裁判择优。

## Bug 清单

### P2

**CV1 [P2] `is_critical_file` 子串假阳性 → 普通文件被双模型交叉验证，成本×3（实测）**

- 位置：`:135-136` `for pattern in self.critical_patterns: if pattern in path_lower or pattern in type_lower`——17 个短词子串匹配（auth/permission/order/admin/access/token/role/guard 等）
- 实测（priority=2，后端文件）：
  ```
  app/order_detail.py          → True   # 'order' 命中，但订单明细非支付核心
  app/administration_utils.py  → True   # 'admin' 命中，行政管理工具
  app/accessibility.py         → True   # 'access' 命中，无障碍
  app/tokenizer.py             → True   # 'token' 命中，分词器
  app/auth_service.py          → True   # 真认证，合理触发
  ```
- 影响：假阳性文件走双模型生成 + 裁判 LLM + refinement = **单文件 3+ 次 LLM 调用**（成本主线「贵」的一侧）；与 BE1/FE1/LD 家族同款子串模式。priority=1 无条件（:126-127）更无辨析
- 修复方向：`path` 拆段（`/` 分隔 + 去扩展名）后全词匹配（`re.fullmatch` 或 `pathlib.PurePath.parts`），排除常见后缀词

**CV2 [P2] 模型一致性验证正则低精度 → 假 model_mismatch → 喂给 LLM 产生幻觉修复（静态确认）**

- 位置：`_extract_model_definitions`（:1165）——Pydantic 只认 `class X(BaseModel):` 单继承（:1175），SQLAlchemy 只认 `= Column(...)` 单行（:1191），`mapped_column`/多继承/嵌套类型注解全漏；`_validate_model_consistency`（:1131）——`:1146` `model_name in content` 子串、`:1153` `re.findall(r'(\w+)\s*=', init_body)` 把方法参数/非赋值 kwargs 当字段
- 影响：定义提取不全 → 真实字段被当「未定义」→ 假 issue 进 `_fix_with_llm`（:1239）→ LLM 无谓改代码（CP1 幻觉补丁风险链）——**验证器低精度是幻觉修复的输入端**
- 修复方向：优先走 language_adapter/真实语法解析；模型字段提取限定类体且排除方法定义区

**CV3 [P2] generic import fallback 第三方库集合不全 → import_error 假阳性（静态确认）**

- 位置：`_is_third_party`（:977-987）硬编码 ~28 库；未列库（click/loguru/rich/tenacity/motor/apscheduler 等）被当项目模块 → `_module_exists_in_files`（:989）找不到 → `_validate_imports`（:905）报「导入的模块不存在」
- 影响：项目生成文件若 import 了集合外第三方库（很常见）→ 假 import_error → validate_and_fix :1226 `_find_missing_modules` 判定缺模块 → `_generate_missing_modules`（:1274）**让 LLM 幻觉生成一个其实是第三方库的"缺失模块"文件**——错误文件进项目。无 language_adapter 的调用路径受影响最大（:896 fallback）；adapter 路径依赖 is_project_module（PP10 已证其本身把外部包当项目模块，方向相反）
- 修复方向：`_is_third_party` 补全常见包集 + 支持 `sys.modules`/环境检查；缺模块生成前对第三方库白名单复核

### P3

**CV4 [P3] API 契约校验三套并存（确认）**

- `_validate_api_contracts`（:1006）与 api_contract_checker、integrity_validator._validate_api_contracts 三套并存——TASKS 已记录，此处确认 cross_validator 为第三套；`_extract_backend_api_specs`/`_extract_frontend_api_calls`/`_find_matching_api` 用正则提取端点+响应字段，精度与整体一致

**CV5 [P3] `_find_missing_modules` 依赖中文 issue 文案正则**

- `:1253` `re.search(r"导入的模块不存在:\s*(\S+)", message)`、`:1260` 依赖 issue message 中文字面量——文案改动即断（同 failure_clusterer FC2 正则脆弱家族）

**CV6 [P3] 双模型交叉验证成本无上限控制**

- priority=1 无条件触发（:126-127），小型项目高优先级文件全量 ×3 成本；无批量/节流（成本主线叠加 CV1）

## 与既有主线闭环

- **成本主线**：CV1 + CV6 是「贵」的一侧放大项（单文件 3+ 次 LLM）；spec_cache SC1/SC3 使「省」失效——两头挤压
- **「存在≠正确」验证主线**：cross_validator 是 spec_first 链的**跨文件语义验证层**（5 类正则），CV2/CV3 假阳性喂给 LLM 产生幻觉修复（CP1 链）；与 code_validator（CV 系列）、api_contract_checker（CV4 三套）共同构成验证栈的多套并存——§5.6 支柱 2（验证器协议统一）的核心收敛对象
- **§5.6 支柱 2 映射**：cross_validator 的 5 类验证器 + CodeValidator 的四套 + 三套 API 契约 = 验证器协议的典型多实现区；CV1 的 critical 判定本质是「门禁触发规则」，应外置为支柱 5（阶段门禁）的配置项
