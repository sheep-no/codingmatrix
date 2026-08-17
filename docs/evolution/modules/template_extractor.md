# TemplateExtractor 深扫（template_extractor.py，153 行）

> 第一百零二轮推演 | 2026-08-16 | 定位：历史项目功能清单 → 领域通用模板的 LLM 自动萃取（生成 + 审核 + 入库），领域模板数据源的上游写端

## 1. 模块定位

当某领域积累足够历史项目（feature_extractor:28 触发 ≥15 项目）时，用 LLM 从功能清单萃取出该领域通用模板，审核后写入 `configs/domain_templates/{domain}.json`——该文件正是 Layer 1 模板匹配（layer1_template.py:19）与模板注入的唯一数据源。

- `extract_template`（:16-86）：收集有效功能清单（≥5 才继续）→ LLM 萃取（`TEMPLATE_EXTRACT_MODEL`）→ `_parse_template_response` → `_review_template`（`TEMPLATE_REVIEW_MODEL`）→ 审核通过才 `_save_template`
- `_parse_template_response`（:88-105）：`re.search(r'\{[\s\S]*\}', response)` 贪婪提取 JSON
- `_review_template`（:107-140）：LLM 审核（5 条标准），异常返回 `{"approved": False, "reason": "审核过程异常"}`
- `_save_template`（:142-153）：**模板文件已有则备份为 `{domain}_manual.json`，再用自动萃取结果覆盖 `{domain}.json`**

**活跃模块**，调用链：

- `project_metadata.py:191-193`：`trigger_template_extraction` → `TemplateExtractor().extract_template(domain, domain_projects)`（ProjectMetadata 详档消费方）
- `feature_extractor.py:27-32`：`get_projects_by_domain(domain)` ≥15 时触发 `trigger_template_extraction`（传统生成链每轮自动触发）
- `layer1_template.py:19`：读 `DOMAIN_TEMPLATES_DIR / f"{domain}.json"` 做模板匹配（下游消费方，orchestrator_requirements 子包）

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 上游 | `project_metadata.py:191-193` | trigger_template_extraction 调用（活跃） |
| 上游 | `feature_extractor.py:27-32` | 项目数 ≥15 自动触发（活跃） |
| 下游 | `layer1_template.py:19/:25` | 读 `{domain}.json` 做 Layer 1 模板匹配（活跃，数据源唯一读端） |
| 依赖 | `constants.py:8` | `DOMAIN_TEMPLATES_DIR = <repo>/configs/domain_templates`（10 个手工模板） |
| 依赖 | `app.utils` call_llm | 萃取 + 审核两次 LLM 调用（直连，LCL1 家族） |
| 测试 | `tests/unit/test_v5_1_requirement_deep.py:340-368` | 仅 2 解析用例 |

## 2. 深扫发现

### P2 项

- **TE1 [P2] `_save_template` 用自动萃取结果覆盖手工模板（实测）**——:144-150 模板文件已存在时备份为 `{domain}_manual.json`，**再用自动萃取模板覆盖 `{domain}.json`**——而 Layer 1 消费路径恰是 `{domain}.json`（layer1_template.py:19），`{domain}_manual.json` 备份**全库无消费方**。实测：预置手工 banking.json → `_save_template(auto)` → 主文件读出手工 description 变为「自动萃取」，备份 `banking_manual.json` 存在但 layer1 永不读取。**10 个精心编写的手工模板（version 1.0）在领域项目数 ≥15 时被自动萃取模板静默替换，手工版本降级为无人读取的备份文件**——数据源被程序生成数据覆写，「备份语义颠倒」+「自动质量替换人工质量」。
- **TE2 [P2] 审核 LLM 失败即丢弃萃取 + 审核标准与萃取标准矛盾（全库确认）**——`_review_template` 异常返回 `{"approved": False, "reason": "审核过程异常"}`（:140）→ extract_template:78-82 返回 None——**审核失败 = 萃取失败，无降级路径**；且审核标准要求 `core_modules >= 5`（:114），而萃取 prompt 要求「出现频率 >=40% 才提取 core 模块」（:57）——**低频领域（40% 阈值下 core 模块可能 <5）萃取结果必然被自己的审核拒绝**，审核门槛与萃取规则自相矛盾，正常/降级两路径都可能产出零模板。
- **TE3 [P2] `_parse_template_response` 贪婪跨块 + 无降级（实测）**——`\{[\s\S]*\}`（MAR5/EC3/PM1 同款）对多 JSON 块跨块匹配失败（实测 `{...} 附加 {...}` → json.loads 报 Extra data 返回 None），解析失败只 return None 无降级——LLM 输出稍带解释文本即整个萃取链路失败。
- **TE4 [P2] 萃取输入 `all_features[:200]` 截断使频率统计失真（全库确认）**——:36 只把前 200 条功能喂给 LLM，而萃取要求按「出现频率 >=40%」提取 core 模块——**截断后频率基于子样本计算**，前 200 条不能代表全量分布（JP2/PM4 截断家族），且与 15 项目 × 每项目最多 20 条 feature 的上限（project_metadata:178 `features[:20]`）不匹配。

### P3 项

- **TE5 [P3] 模型名硬编码 + 直连 call_llm**——TEMPLATE_EXTRACT_MODEL/TEMPLATE_REVIEW_MODEL 都等于 DEFAULT_REASONING_MODEL（:10-11），萃取/审核走 `app.utils.call_llm` 直连（LCL1 家族），不经 DMR 路由/成本/token 统计。
- **TE6 [P3] `_save_template` 非原子写 + 备份只保留一次**——直接 `open(..., "w")` 写模板，中途失败损坏文件（CS1 写安全家族）；`{domain}_manual.json` 被后续萃取覆盖，手工备份只留最后一份，无版本保留。
- **TE7 [P3] 测试仅 2 解析用例零流程覆盖**——test_v5_1_requirement_deep.py:340-368 只测 `_parse_template_response` 正常/非 JSON 两例，TE1（覆盖手工模板）、TE2（审核失败兜底）、TE3（贪婪跨块）、TE4（截断频率）全部零用例——最严重的 TE1 实测可复现却无任何保护。

## 3. 演化方向

模板萃取是领域数据源的**唯一写端**，其输出直接决定 Layer 1 模板匹配质量，但当前设计使自动生成内容覆盖人工精修内容：
- **写入策略重构（TE1，最高优先）**：`_save_template` 改自动模板写入独立路径（如 `{domain}_auto.json`）或需人工确认才替换 `{domain}.json`——保护 10 个手工模板不被程序生成数据静默覆写；或明确「自动萃取只在不存在的领域新建」。
- **审核语义（TE2）**：审核失败与审核拒绝区分；萃取标准（40% 频率）与审核标准（≥5 core）对齐，避免自相矛盾；审核 LLM 异常可降级为「带标记入库」而非全丢。
- **解析加固（TE3/TE4）**：贪婪 `\{[\s\S]*\}` 换非贪婪/JSON 边界定位（EC3/PM1 同款修复）；全量特征不做 [:200] 截断或按项目分组统计后再截断。
- **写安全与测试（TE6/TE7）**：原子写（临时文件 + os.replace）；补 TE1 覆盖手工模板用例 + 审核/解析失败路径测试。

**修复优先级**：TE1（手工模板被自动覆写）> TE2（审核矛盾 + 无降级）> TE3（解析脆弱）> TE4（截断失真）> TE7（测试盲区）> TE6（非原子写）> TE5（LLM 直连）。

## 4. 主线关联

- **「数据源被程序覆写」严重模式**：TE1 与 PM3（并发丢历史）、CP1（LLM 幻觉补丁破坏代码）、GO2（回滚删分支）同属「写入侧破坏已有正确数据」——但 TE1 更隐蔽：**自动生成内容覆盖人工精修内容且备份无消费**，是「自动质量替换人工质量」的信任模型缺陷。
- **「失败兜底产生伪结果/丢弃」家族**：TE2（审核失败即丢弃）与 EC3（分类失败兜底 LogicError）、DGV1（验证失败兜底 passed）同族——都让 LLM 双调用链路的可靠性成为单点；TE4 截断与 JP2/PM4 同族。
- **「能力未接线」反向镜像**：本模块是**已接线但破坏数据源**的写端——feature_extractor:28 自动触发（≥15 项目）使 TE1 在传统生成链每轮都可能发生，与孤儿家族（SCT5/EC8）相反，警示「接线 + 自动覆写 = 数据源退化」。

## 5. 测试状态

**仅解析单测、零流程覆盖**——test_v5_1_requirement_deep.py:340-368 两个用例只测 `_parse_template_response`（正常 JSON / 非 JSON），全部 4 个 P2 项（TE1 手工模板覆盖实测 / TE2 审核失败兜底 / TE3 贪婪跨块实测 / TE4 截断频率）零用例保护。最严重的 TE1 涉及 `_save_template` 覆盖已有模板文件，测试目录未建、手工模板覆盖场景完全空白——数据源写端的唯一行为未受任何测试约束。
