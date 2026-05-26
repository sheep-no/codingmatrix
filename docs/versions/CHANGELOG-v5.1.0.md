# v5.1.0 更新日志 - 需求理解深度增强 - 2026-05-17

## 版本概览

- **版本号**: v5.1.0
- **发布日期**: 2026-05-17
- **主题**: 需求理解深度增强 - 从"部分可用"到"全面激活"
- **测试覆盖**: 56 个测试 (28 原有 + 28 新增)，100% 通过
- **新增代码**: ~1200 行后端 + ~450 行前端
- **新增文件**: 3 个后端模块 + 1 个测试文件

---

## 核心更新

### 2.1 数据闭环打通

#### 功能清单自动生成 (`app/agent/project_metadata.py`)

每次项目生成完成后，自动调用模型反向分析生成的项目，提取结构化功能清单并存入 `project_metadata.json`。

- 每次成功生成都在为下一次联想做贡献
- 主模型: DeepSeek-R1-0528-Qwen3-8B，降级: Qwen3-8B
- 功能清单上限 30 项，防止膨胀
- 生成后自动追加到 FAISS 向量索引

#### FAISS 语义检索 (`app/agent/vector_index.py`)

Layer 2 从 Jaccard 关键词匹配升级为 FAISS 语义检索：

- 启动时从 `project_metadata.json` 加载全量向量，构建内存索引
- 新项目保存后异步追加向量
- 查询使用 bce-embedding-base_v1 (768 维)
- 相似度阈值 0.35，返回最多 10 个匹配项目
- 数据不足阈值 (5 条) 时自动降级到关键词匹配

#### 领域模板自动萃取 (`app/agent/template_extractor.py`)

某领域历史项目达到 15 个时，自动触发模板萃取：

1. 聚合功能清单，调用 DeepSeek-R1 提取共性部分
2. GLM-Z1 严格审核 (core_modules >=5, NFR 含 security, pitfalls >=3, decisions >=2)
3. 审核通过后入库，原手工模板自动备份为 `_manual.json`

---

### 2.2 联想质量增强

#### 双模型交叉联想

Layer 3 使用两个模型独立做联想，合并结果：

| 模型 | 标识 | 用途 |
|------|------|------|
| DeepSeek-R1-0528-Qwen3-8B | DUAL_MODEL_A | 深度推理 |
| THUDM/GLM-Z1-9B-0414 | DUAL_MODEL_B | 交叉验证 |

合并策略：
- 两模型都提到的项 → `dual_model_agreement: both_agree`，置信度 +0.1
- 仅一个模型提到的 → `dual_model_agreement: needs_confirmation`，置信度 *0.95
- 两模型都失败 → 降级到 Qwen3-8B fallback

#### 跨领域联想

用户需求可能跨领域 (如"医疗电商平台")。系统匹配多个领域模板，按匹配度加权合并：

- `_detect_domains()` 返回最多 3 个匹配领域
- 每个领域独立加载模板，去重后合并
- source 字段标注领域来源 (如 `domain_template:banking`)
- 重复项取高置信度版本

---

### 2.3 生成后校验

#### 需求覆盖校验

Architect 输出架构后，自动逐项检查确认清单中的功能需求是否在架构设计中有所体现：

- 确定性规则检查 (关键词匹配)，不需要模型推理
- 功能项关键词在文件描述 + 架构描述中匹配 >=30% 即视为覆盖
- 未覆盖项标记为"遗漏"，反馈给用户 (写入 warnings)
- 覆盖率计入返回结果

#### 魔鬼代言人反向审视

需求确认后，GLM-Z1 模型扮演质疑者：

- 只对置信度 >=0.7 的联想项进行审视
- 从三个角度质疑：前置条件遗漏、连锁风险、缺失环节
- 输出: target_item / challenge / severity / suggestion
- 结果通过 `devil_review_items` 返回前端展示

---

### 2.4 交互体验升级

#### 联想过程流式展示

联想过程通过 `_report_progress` 推送 6 步进度：

1. `detecting_domain` - 正在匹配领域模板...
2. `searching_history` - 正在检索相似项目...
3. `deep_association` - 正在生成深度联想...
4. `devil_review` - 正在进行反向审视...
5. `building_result` - 正在构建结果...
6. `complete` - 联想完成

#### 联想质量显式反馈

需求确认界面底部增加"这些建议对你有帮助吗?":
- 很有帮助 (`very_helpful`)
- 部分有用 (`somewhat_helpful`)
- 不太有用 (`not_helpful`)

通过 `/requirement-association/helpfulness` API 记录到 DB。

#### 拒绝理由记录

用户删除联想项时弹出选择对话框：
- 不相关 (`irrelevant`)
- 已有计划 (`already_planned`)
- 超出范围 (`out_of_scope`)
- 其他 (`other`)

`AssociationFeedbackTracker` 新增 `rejection_reason` 和 `overall_helpfulness` 字段。

---

## 修改文件清单

### 后端新增 (3 个)

1. `app/agent/vector_index.py` - FAISS 索引管理 (~130 行)
2. `app/agent/project_metadata.py` - 功能清单自动生成 (~170 行)
3. `app/agent/template_extractor.py` - 领域模板自动萃取 (~120 行)

### 后端修改 (3 个)

4. `app/agent/orchestrator_requirements.py` - 双模型联想、跨领域联想、反向审视、流式进度
5. `app/agent/orchestrator_generation.py` - 需求覆盖校验、生成后提取功能清单
6. `app/api/v1/ai_agent.py` - 新增 2 个 API 端点、更新请求/响应模型

### 前端修改 (1 个)

7. `src/components/RequirementAssociation.vue` - 流式展示、显式反馈、拒绝理由、魔鬼代言人

### 测试新增 (1 个)

8. `tests/unit/test_v5_1_requirement_deep.py` - 28 个新增测试

---

## API 端点变更

| 端点 | 方法 | 版本变更 | 描述 |
|------|------|---------|------|
| `/requirement-association` | POST | v5.0→v5.1 | 新增 `domains_matched`, `devil_review_items`, `dual_model_agreement` |
| `/requirement-association/confirm` | POST | v5.0→v5.1 | 新增 `rejection_reason` 字段 |
| `/requirement-association/helpfulness` | POST | **新增** | 记录整体帮助性评价 |
| `/requirement-association/stats` | GET | **新增** | 获取反馈统计+拒绝理由统计 |

---

## 资源影响

| 更新项 | 内存增量 | CPU 影响 | 模型调用增量 |
|--------|---------|---------|------------|
| FAISS 索引 (5000条) | +15MB | <1ms/查询 | 无 |
| 双模型联想 | 无 | +3-10s | +1次 |
| 功能清单自动生成 | 无 | 低频 | +1次 (生成后) |
| 模板自动萃取 | 无 | 低频 | +2次 (萃取+审核) |
| 反向审视 | 无 | +2-5s | +1次 |
| 需求覆盖校验 | 无 | 毫秒级 | 无 |

---

## 测试覆盖

| 测试类 | 用例数 | 覆盖内容 |
|--------|-------|---------|
| TestVectorIndexManager | 2 | 空索引创建、空索引搜索 |
| TestProjectMetadataManager | 3 | 加载/统计/领域筛选 |
| TestAssociationFeedbackTracker | 3 | 记录+统计、拒绝理由、帮助性 |
| TestDualModelMerge | 2 | 双模型一致合并、单模型 |
| TestCrossDomainDetection | 4 | 单领域/跨领域/无匹配/上限 |
| TestDevilAdvocateReview | 3 | JSON解析/空响应/部分解析 |
| TestRequirementCoverageCheck | 3 | 无联想/好覆盖/差覆盖 |
| TestLayer1CrossDomainTemplate | 2 | 跨领域合并/去重 |
| TestLayer2SemanticMatch | 1 | 无数据返回空 |
| TestTemplateExtractor | 2 | JSON解析/无效输入 |
| TestFeatureExtractionParsing | 3 | JSON/文本/fallback |

+ 原有 28 个 v5.0.0 测试 (已适配新方法名)

**总计**: 56 个测试，100% 通过 (4.10s)

---

## 与 v5.0.0 的关系

v5.0.0 建立了三层联想框架，但 Layer 2 因数据不足静默降级。v5.1.0 的核心任务就是让这个框架从"部分可用"变为"全面激活":

| 维度 | v5.0.0 | v5.1.0 |
|------|--------|--------|
| Layer 2 数据来源 | 静默降级 (无数据) | 功能清单自动生成 + FAISS 索引 |
| Layer 2 检索方式 | Jaccard 关键词 | FAISS 语义检索 (降级关键词) |
| Layer 3 模型 | 单模型 (DeepSeek-R1) | 双模型交叉 (DeepSeek-R1 + GLM-Z1) |
| Layer 1 领域 | 单领域匹配 | 跨领域加权合并 |
| 反向审视 | 无 | 魔鬼代言人 (GLM-Z1) |
| 交互反馈 | 仅 accept/reject | 拒绝理由 + 显式帮助性评价 |
| 模板来源 | 纯手工 | 自动萃取 + 严格审核 |
| 生成后闭环 | 无 | 功能清单提取 + 覆盖率检查 |

---

## 下一步计划 (v5.2.0)

1. **数据闭环分析报表**: 联想项接受率统计、模板命中率分析、用户偏好挖掘
2. **领域模板扩充**: 从 10 个扩展到 20 个，根据反馈优化
3. **流式展示完整集成**: SSE 推送 6 步进度到前端实时渲染
4. **覆盖率趋势可视化**: 前端展示覆盖率变化曲线

---

*发布日期：2026-05-17*