# v5.0.0 更新日志 - 需求联想增强 - 2026-05-17

## 版本概览

- **版本号**: v5.0.0
- **发布日期**: 2026-05-17
- **主题**: 需求联想增强 - 三层联想机制 + 数据闭环
- **测试覆盖**: 27 个新增单元测试，100% 通过
- **新增代码**: ~1800 行 (后端 1300 行 + 前端 500 行)
- **修改文件**: 7 个核心文件

---

## 核心功能

### 需求联想增强模块 (Requirement Association)

在 Orchestrator 流程中新增独立模块，位于**复杂度分析之后、架构设计之前**，将"一句话需求"扩展为"结构化需求清单"。

#### 三层递进联想机制

| 层级 | 名称 | 作用 | 数据来源 | 置信度计算 |
|------|------|------|---------|-----------|
| **Layer 1** | 领域模板匹配 | 根据需求关键词加载预置领域知识 | 10 个高频领域 JSON 模板 | 关键词命中率 (0.5-1.0) |
| **Layer 2** | 历史项目匹配 | 关键词检索相似历史项目，反推功能清单 | `data/learning_data/project_metadata.json` | Jaccard 相似度 (0.15-1.0) |
| **Layer 3** | LLM 深度联想 | 基于前两层结果进行开放式推理补全 | 攻坚层模型 (DeepSeek-R1) | 模型标注 (0.6-0.9) |

#### 关键设计点

**1. 自适应数据检查**
```python
# 第二层静默降级机制
if 历史项目 >= 50 且 已标记功能清单 >= 20:
    三层全开
else:
    只执行 Layer 1 + Layer 3
```

**2. 置信度分级展示**
```python
CONFIDENCE_DEFAULT_SHOW = 0.7   # 默认展开
CONFIDENCE_DISPLAY_THRESHOLD = 0.4  # 折叠展示
# <0.4 的项不展示
```

**3. 时间预算控制**
```python
TIME_BUDGET_SECONDS = {
    "medium": 15,
    "large": 20,
    "enterprise": 25,
}
# 超时返回已完成部分，不中断主流程
```

**4. 向后兼容**
- SIMPLE/SMALL 项目默认跳过
- 用户可手动跳过直接进入架构设计
- 跳过时行为与原流程完全一致

---

## 10 个领域模板

已在 `configs/domain_templates/` 创建 10 个高频领域模板：

| 模板 | 核心模块数 | 非功能需求 | 常见陷阱 | 关键决策 |
|------|----------|-----------|---------|---------|
| `banking.json` | 10 | 8 | 6 | 4 |
| `ecommerce.json` | 10 | 6 | 5 | 4 |
| `cms.json` | 9 | 4 | 4 | 3 |
| `saas.json` | 10 | 5 | 5 | 3 |
| `social.json` | 8 | 4 | 5 | 3 |
| `dashboard.json` | 8 | 4 | 4 | 3 |
| `education.json` | 8 | 4 | 5 | 3 |
| `healthcare.json` | 8 | 5 | 5 | 3 |
| `iot.json` | 8 | 5 | 5 | 3 |
| `erp.json` | 8 | 4 | 5 | 3 |

每个模板包含：
- `core_modules`: 核心功能清单 (必选/可选标记)
- `non_functional_requirements`: 非功能需求 (安全/性能/合规)
- `common_pitfalls`: 常见陷阱 (领域特定风险)
- `key_decisions`: 关键决策 (架构级选项)

---

## 前后端集成

### 后端 API

**新增端点**:

| 端点 | 方法 | 描述 | 权限 |
|------|------|------|------|
| `/api/v1/agent/requirement-association` | POST | 生成需求联想清单 | normal |
| `/api/v1/agent/requirement-association/confirm` | POST | 确认用户选择 (数据闭环) | normal |

**Request/Response**:

```python
# 联想请求
class RequirementAssociationRequest(BaseModel):
    requirement: str
    complexity_level: Optional[str]
    skip_association: bool = False

# 联想响应
class RequirementAssociationResponse(BaseModel):
    skipped: bool
    skip_reason: Optional[str]
    domain_matched: Optional[str]
    items: List[Dict]
    classified_items: Dict
    enhanced_requirement: Optional[str]
    elapsed_seconds: float

# 确认请求
class RequirementAssociationConfirmRequest(BaseModel):
    requirement: str
    confirmed_items: List[Dict]
    removed_items: List[Dict]
    modified_items: List[Dict]
```

### 前端交互界面

**新增组件**: `src/components/RequirementAssociation.vue`

**交互流程**:
1. 后端生成联想清单 → SSE 推送给前端
2. 前端弹出"需求确认"对话框
3. 用户逐项确认/修改/删除/推迟
4. 前端将确认后的需求传回后端
5. 后端存入 SharedContext，Architect 读取进行设计

**界面特性**:
- 分类展示 (功能需求/架构影响/潜在风险/关键决策)
- 置信度分级 (高置信度默认展开，低置信度折叠)
- 来源标注 (领域模板/历史项目/AI 联想)
- 一键确认/跳过

---

## 数据闭环

### AssociationFeedbackTracker

复用 `ModelPerformanceTracker` 设计模式：

```python
class AssociationFeedbackTracker:
    DB_PATH = Path("./data/association_feedback.db")
    MAX_DB_SIZE_BYTES = 2 * 1024 * 1024  # 2MB 限制
    RETENTION_DAYS = 90  # 90 天自动清理
    
    def __init__(self):
        # WAL 模式 (并发安全)
        self._conn = sqlite3.connect(str(self.DB_PATH), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        # 自动建表 + 清理
```

**记录用户选择行为**:
```python
tracker.record_choice(
    session_id, requirement,
    confirmed_items, "accepted"
)
tracker.record_choice(
    session_id, requirement,
    removed_items, "rejected"
)
```

**长期价值**:
- 统计各来源项的接受率 → 优化联想准确率
- 分析哪些模板被频繁修改 → 更新模板
- 发现被用户忽略但最终出问题的风险 → 提升预警强度

---

## 集成到主流程

### OrchestratorAgent

**修改文件**:
- `app/agent/orchestrator.py`: 继承 `RequirementAssociationMixin`
- `app/agent/orchestrator_generation.py`: 在 `_initialize_components` 后插入联想环节
- `app/agent/orchestrator_progress.py`: 新增 `requirement_association` 进度标签

**流程变化**:
```
原来:
用户需求 → 复杂度分析 → 架构设计 → 代码生成

新增后:
用户需求 → 复杂度分析 → 需求联想增强 → 用户确认 → 架构设计 → 代码生成
```

**代码示例**:
```python
# orchestrator_generation.py
await self._initialize_components(requirement)

self._association_result = await self._generate_requirement_associations(
    requirement, self.complexity.level.value
)
if not self._association_result.skipped:
    requirement = self._association_result.enhanced_requirement

ctx = SharedContext(requirement, self.output_dir)
```

---

## 单元测试

**测试文件**: `tests/unit/test_requirement_association.py`

**测试覆盖**:

| 测试类 | 测试用例数 | 覆盖内容 |
|--------|----------|---------|
| `TestDomainDetection` | 8 | 领域关键词匹配 |
| `TestLayer1DomainTemplate` | 3 | 领域模板加载 |
| `TestLayer2HistoryMatch` | 2 | 历史项目匹配 (降级) |
| `TestLayer3LLMDeep` | 1 | LLM 联想 (降级) |
| `TestAssociationPipeline` | 3 | 完整流程 |
| `TestEnhancedRequirement` | 2 | 需求增强构建 |
| `TestClassifyItemsForDisplay` | 2 | 置信度分级 |
| `TestTemplateConfidence` | 2 | 模板置信度计算 |
| `TestParseLLMResponse` | 4 | LLM 输出解析 |

**总计**: 27 个测试，100% 通过 (1.99s)

---

## 性能影响

| 指标 | 优化前 | 优化后 | 影响 |
|------|-------|-------|------|
| 小型项目生成时间 | ~40s | ~40s | 无影响 (默认跳过) |
| 中型项目生成时间 | ~90s | ~105s | +15s (联想环节) |
| 大型项目生成时间 | ~180s | ~200s | +20s (联想环节) |
| 需求覆盖率 | 60% (假设) | 85% (目标) | +25% |
| 返工率 | 40% (假设) | 25% (目标) | -15% |

**时间预算控制**:
- 中型项目联想预算: 15s
- 大型项目联想预算: 20s
- 超时返回已完成部分，不中断主流程

---

## 修改文件清单

### 后端 (5 个)

1. `app/agent/orchestrator_requirements.py` - 新增 (516 行)
2. `app/agent/orchestrator.py` - 继承 Mixin
3. `app/agent/orchestrator_generation.py` - 插入联想环节
4. `app/agent/orchestrator_progress.py` - 新增进度标签
5. `app/api/v1/ai_agent.py` - 新增 2 个 API 端点

### 前端 (1 个)

6. `src/components/RequirementAssociation.vue` - 新增 (350 行)

### 配置 (10 个)

7. `configs/domain_templates/banking.json`
8. `configs/domain_templates/ecommerce.json`
9. `configs/domain_templates/cms.json`
10. `configs/domain_templates/saas.json`
11. `configs/domain_templates/social.json`
12. `configs/domain_templates/dashboard.json`
13. `configs/domain_templates/education.json`
14. `configs/domain_templates/healthcare.json`
15. `configs/domain_templates/iot.json`
16. `configs/domain_templates/erp.json`

### 测试 (1 个)

17. `tests/unit/test_requirement_association.py` - 新增 (27 测试)

---

## 已知问题

### 1. 第二层历史项目匹配暂不可用

**问题**: 当前历史项目库数据量不足 (`data/learning_data/project_metadata.json` 不存在)

**影响**: Layer 2 静默降级，只执行 Layer 1 + Layer 3

**解决方案**:
- Phase 1 (当前): 用领域模板 + LLM 联想
- Phase 2 (v5.1): 等项目积累到 50+ 后自动激活

### 2. 向量检索未实现

**问题**: 当前使用关键词匹配 (Jaccard 相似度)

**影响**: 语义相似度不够精确

**解决方案**:
- Phase 1 (当前): 关键词匹配
- Phase 2 (v5.1): 引入 bce-embedding + Faiss 向量数据库

---

## 下一步计划 (v5.1.0)

### P0 优先级

1. **历史项目功能清单自动生成**
   - 每次项目生成完成后，调用 LLM 自动生成一份功能清单
   - 存储到 `project_metadata.json`
   - 为 Layer 2 提供数据基础

2. **向量检索升级**
   - 部署 bce-embedding 推理服务
   - 引入 Faiss/Chroma 向量数据库
   - Layer 2 升级为语义检索

### P1 优先级

3. **数据闭环分析报表**
   - 联想项接受率统计
   - 模板命中率分析
   - 用户偏好挖掘

4. **领域模板扩充**
   - 从 10 个扩展到 20 个领域
   - 根据用户反馈优化模板

---

## 升级指南

### 从 v4.9.0 升级

```bash
# 1. 拉取代码
git pull origin main

# 2. 领域模板已自动包含

# 3. 重启服务
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

# 4. 验证功能
curl -X POST http://localhost:8080/api/v1/agent/requirement-association \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"requirement": "开发一个电商商城系统", "complexity_level": "medium"}'
```

### 兼容性

- ✅ API 向后兼容
- ✅ 数据库 schema 无破坏性变更
- ✅ 前端无需重新构建 (新增组件)
- ✅ SIMPLE/SMALL 项目无性能影响

---

## 贡献者

- AI Agent: 代码生成、测试编写
- Human: 架构设计、代码审查、领域模板设计

---

*发布日期：2026-05-17*
