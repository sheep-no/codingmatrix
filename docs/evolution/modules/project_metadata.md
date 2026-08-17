# ProjectMetadataManager 深扫（project_metadata.py，194 行）

> 第一百轮推演 | 2026-08-16 | 定位：历史项目元数据管理与功能清单 LLM 提取（JSON 持久化 + 向量索引联动），layer2 语义/关键词链路活跃消费

## 1. 模块定位

历史项目元数据仓库：`extract_and_save` 每次生成后用 LLM 提取功能清单并持久化到 `project_metadata.json`，供 Layer 2 需求匹配（向量检索 + 关键词兜底）与模板萃取消费。

- `ProjectMetadataManager`（:17-193）：`_projects` 内存列表 + `METADATA_PATH`（vector_index.py:15 `VECTOR_INDEX_DIR / "project_metadata.json"`）JSON 持久化
- `extract_and_save`（:57-91）：LLM 提取功能清单 → 追加项目 → `_save` → 向量索引 `vi.add_project`
- `_extract_feature_list`（:93-140）：主模型 `FEATURE_EXTRACTION_MODEL`（DEFAULT_REASONING_MODEL）失败降级 `FEATURE_EXTRACTION_FALLBACK`（DEFAULT_CODE_MODEL）再失败 `_fallback_feature_list`
- `_parse_feature_response`（:149-166）：JSON 提取（`re.search(r'\{[\s\S]*\}', response)` 贪婪）+ 行级文本回退
- `trigger_template_extraction`（:180-193）：领域项目 ≥ min_projects（默认 15）时调 TemplateExtractor

**活跃生产模块**，消费方：

- `orchestrator_generation/feature_extractor.py:13-31`：`extract_and_save_feature_list` 调 `pm.extract_and_save` + `get_projects_by_domain` + `trigger_template_extraction`（>=15 时）；传统链 `traditional_generate.py:326` → `mixin.py:139-144` → feature_extractor
- `orchestrator_requirements/layer2_semantic.py`：`:21` `vi.total_count()` / `:29-31` `get_all_projects`（向量结果 feature_list 缺失时补查）/ `:63-72` 关键词兜底 `get_all_projects`+`keyword_match_history` / `:94-97` `total_count`+`count_with_features`（`check_history_data_available`）
- `vector_index.py:62-67`：`build_from_metadata` 读 `METADATA_PATH`

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 消费方 | `feature_extractor.py:13-31` | extract_and_save + trigger_template_extraction（活跃，传统链） |
| 消费方 | `layer2_semantic.py:29-37/:63-72/:92-104` | get_all_projects/total_count/count_with_features（活跃） |
| 依赖 | `vector_index.py:15` | METADATA_PATH（数据文件共享） |
| 依赖 | `template_extractor.py` | trigger_template_extraction（:191-193） |
| 依赖 | `app/utils` call_llm | 功能清单 LLM 提取（:123/:131，直连 LCL 家族） |
| 测试 | `tests/unit/test_v5_1_requirement_deep.py:85-120` | 仅 CRUD（load/add/count/domain），零解析/降级用例 |

## 2. 深扫发现

### P2 项

- **PM1 [P2] `_parse_feature_response` JSON 解析路径三缺陷（实测）**——(1) **`features: null` → TypeError 逃逸**：`:156` `parsed.get("features", [])` 返回 None 时 `for f in features` 抛 `TypeError: 'NoneType' object is not iterable`，而 `:157` 只捕获 `json.JSONDecodeError`——TypeError 未捕获向上传播，feature_extractor.py:35-36 吞掉返回 None，整个功能清单提取静默失败；(2) **`features` 为 dict → 静默空**：`:156` 迭代 dict 得 keys，`isinstance(f, str)` 过滤后返回 `[]`，无告警；(3) **多 JSON 块贪婪跨块匹配**：`re.search(r'\{[\s\S]*\}', response)`（MAR5/EC3 同款贪婪）对含解释文本的多块响应匹配整段 → json.loads 失败走文本回退（PM2）。三类缺陷使 LLM 响应格式稍偏即功能清单全丢。
- **PM2 [P2] 降级双路径污染：文本回退把 JSON 原文当功能项 + `_fallback_feature_list` 文件名伪功能无标记（实测）**——(1) 多 JSON 块时行级回退（:160-166）把 `'{"features": ["f1"]} 补充 {"features": ["f2"]}'` 整行当功能项输出（实测）——回退路径输出垃圾功能；(2) LLM 双模型失败时 `_fallback_feature_list`（:168-178）用文件名 stem 生成 `"{filename} 模块"` 伪功能（黑名单仅 6 个常见名）——**伪功能无标记写入元数据且 `count_with_features` 计入**，layer2 语义/关键词匹配（layer2_semantic:26/:80）把伪功能当真实历史功能关联新项目，污染需求匹配输入（EC3 LogicError 兜底 / DGV1 passed 兜底家族）。
- **PM3 [P2] `_save` 无锁非原子全量写 + 每次实例化 load/mkdir（全库确认）**——`extract_and_save`（:76-77）`append` 后 `_save`（:35-37）全量 `json.dump`，无锁无原子写（CS1 读改写家族）：并发生成多项目时 last-write-wins 丢历史项目；且消费方每次调用新建实例（feature_extractor:14 / layer2_semantic 四处），`:20` 每次 `mkdir` + `_load` 读全文件——频繁实例化重复 I/O，`_projects` 无单例缓存。

### P3 项

- **PM4 [P3] `_summarize_files` 截断无标记（全库确认）**——`:144` `[:50]` 文件数 + `:145` `content[:200]` 内容截断，均无「已截断」标记（JP2/TR2 家族），LLM 无法感知文件列表/内容不完整。
- **PM5 [P3] 模板萃取阈值双处硬编码（全库确认）**——`trigger_template_extraction` 默认 `min_projects=15`（:181）与 feature_extractor.py:28 `if len(domain_projects) >= 15` 硬编码 15 重复——双处阈值漂移风险（TFC4 默认值双处家族）。
- **PM6 [P3] 测试仅 CRUD 零解析/降级覆盖（全库确认）**——test_v5_1_requirement_deep.py:85-120 仅测 load/add_and_count/get_projects_by_domain 三基础 CRUD，`_parse_feature_response`/`_extract_feature_list`/`_fallback_feature_list` 零用例——PM1（TypeError 逃逸/贪婪跨块）、PM2（回退污染）全部实测可复现但零用例保护（TR2/DR8 弱断言家族）。

## 3. 演化方向

元数据仓库是 Layer 2 历史匹配的输入源，提取端（LLM 解析）与持久化端（文件写）都有失真：
- **解析加固（PM1/PM2）**：`features` 取值后校验类型（list 且元素 str），TypeError/ValueError 一并捕获；贪婪 `\{[\s\S]*\}` 改非贪婪或 JSON 边界定位；降级路径（行级回退 / 文件名伪功能）需带标记（如 `[fallback]` 前缀）或写入 `source` 字段，避免 `count_with_features` 与 layer2 匹配把伪数据当真。
- **持久化原子性（PM3）**：`_save` 改临时文件 + `os.replace` 原子写 + 锁，实例化缓存单例避免重复 load/mkdir（§5.6 支柱 1 收敛）。
- **阈值/截断归一（PM4/PM5）**：min_projects 收敛到单点；截断加标记（JP2 家族统一）。
- **测试补强（PM6）**：解析用例（null/dict/多块/文本回退）+ 降级路径断言，防 PM1/PM2 回归。

**修复优先级**：PM1（功能清单提取静默失败）> PM2（伪数据污染 Layer 2 匹配）> PM3（并发丢数据）> PM5（阈值漂移）> PM4（截断无标记）> PM6（测试盲区）。

## 4. 主线关联

- **「失败兜底产生伪数据」家族**：PM2 与 EC3（分类失败兜底 LogicError）、DGV1（验证失败兜底 passed）、TFC1（依赖未安装照跑测试）同族——降级路径产出「看似正常实则伪造」的数据被下游当真实数据消费，Layer 2 历史匹配输入被污染。
- **「存在≠正确」解析路径**：PM1 的贪婪跨块（MAR5/EC3 同款 `\{[\s\S]*\}`）+ 静默空（dict）与 MLP1（字符串未剥离）、JP1（JSON 标量崩溃）同族——LLM 输出解析是反复失真的横切点。
- **写安全/并发**：PM3 无锁非原子全量写（CS1 读改写、GO12 reset 无备份、SM1 单例家族）。
- **能力未接线反向**：本模块是「已接线但输入失真」而非孤儿——与方法级死代码（EC8/SCT5）相反，警示「接线 ≠ 正确」。

## 5. 测试状态

**仅 CRUD 无行为覆盖**——test_v5_1_requirement_deep.py:85-120 三用例（load_empty/add_and_count/get_projects_by_domain）只验证基本持久化与计数，`_parse_feature_response` 三种失败形态（null/dict/多块）、`_fallback_feature_list` 伪功能生成、`extract_and_save` 的 LLM 降级链全部零用例。PM1（TypeError 逃逸导致功能清单静默丢失）、PM2（回退污染）实测可复现但无任何用例保护——测试固化「元数据可存取」而非「元数据内容正确/不被降级路径污染」。
