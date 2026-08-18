# agent_skills.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-17 | 状态：已完成
> 归属：Agent 引擎 / Agent 认知技能层
> 路径：`app/utils/agent_skills.py`（415 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块定位

「Agent 认知 Skill 注入」——为 Agent 注入 5 个认知能力：
1. 关键词检测（KeywordDetectionSkill）：检测用户输入关键词，自动触发规格书生成
2. 多角度审查（MultiAngleReviewSkill）：修改前从兼容性/安全/性能/测试/文档/运维角度审查
3. 对比学习（ComparativeLearningSkill）：对比修改前后代码差异，学习最佳实践
4. 反面自查（AntiPatternSelfCheckSkill）：修改后自动检查常见错误模式
5. 风险自评（RiskSelfAssessmentSkill）：评估修改的风险等级

通过 AgentSkillsManager 管理器 + 全局单例 `get_skills_manager()` 暴露；五个技能配置分别从 `configs/keyword_triggers.yaml`、`configs/review_checklist.yaml`、`configs/anti_patterns.yaml` 加载。

## 2. 依赖链与消费方

**全库零消费（模块级死代码）**：
- `get_skills_manager()` 唯一调用点 `helpers.py:197`（在 `get_agent_knowledge_base()` 内，注入 `"cognitive_skills"` 元数据）——而 `get_agent_knowledge_base` 零调用（rg 仅 helpers.py:193 定义；code_tasks.py:171 只 import 未调用）
- `load_cognitive_skills_prompt`（prompt_loader.py:159，prompt 侧兜底路径）零调用
- 5 个 Skill 类 + AgentSkillsManager 全部方法（detect/review/get_review_prompt/detect_patterns/check/get_check_prompt/assess/process_user_input/pre_modify_review/post_modify_check）全库零引用
- **三个 YAML 配置从不加载**（AgentSkillsManager.__init__ 依赖 get_skills_manager() 触发，后者从不执行）

## 3. 发现

### ASK1 [P2] 五个认知 Skill 全库零消费——「为 Agent 注入 5 个认知能力」从未接线（全库确认）

- **Bug 代码**：:26-414 全部 5 个 Skill 类 + AgentSkillsManager + :406-414 全局单例——`get_skills_manager()` 唯一调用点 `helpers.py:197` 位于 `get_agent_knowledge_base()` 内，后者全库零调用（code_tasks.py:171 仅 import）；prompt_loader.py:159 `load_cognitive_skills_prompt` 亦零调用。
- **根因**：docstring「为 Agent 注入 5 个认知能力」的接线链条从未接通——知识库注入函数（get_agent_knowledge_base）自身无消费方，五个技能的实际逻辑（关键词触发追问、修改前多角度审查、修改后自查、对比学习、风险自评）从未在任何生成/修改流程中执行。
- **影响**：能力未接线家族最极端一例——**模块级全死代码**（GRD1 是类级、ASK1 是模块级，构成「声称能力 vs 接线状态」系统偏差的又一证据）；三个 YAML 配置（keyword_triggers/anti_patterns/review_checklist）设计良好却从不加载；`get_all_skills_context` 返回的只是元数据（数量/类别名/levels），「技能名片」而非规则内容。

### ASK2 [P3] post_modify_check 假阳性设计——before 为空全行判新增（TR1/MAR8 假阳性家族）

- **Bug 代码**：:402 `post_modify_check` 调 `detect_patterns("", code)`——before="" → before_lines=[''] → 每一行代码都不等于 '' → added_lines = **全部代码行**；:159-169 只要含 import/def/class/@router/async def 即全 pattern 命中（「新增依赖/新增函数/新增类/新增路由/异步化改造」全报）。
- **影响**：一旦接线（修复 ASK1）即每次修改全量误报所有变更模式（TR1/MAR8 家族）；当前零消费无影响。

### ASK3 [P3] KeywordDetectionSkill 无词边界子串触发——超宽词任意出现即触发（PP8/FCT3 家族）

- **Bug 代码**：:42-44 `keyword.lower() in user_input.lower()`——无词边界；keyword_triggers.yaml 含「实现」「add」「优化」「修复」等超宽词——任意开发请求含「实现/优化」即判触发并注入追问流程；命中顺序由 YAML 配置顺序决定（:38 遍历中首个命中即 return，:47 `questions[:3]` 截断——与 YAML `max_questions: 3` 双处写死）。

### ASK4 [P3] AntiPatternSelfCheck 正则直扫整个代码文本——注释/字符串误命中（DR12/FCT3 家族）

- **Bug 代码**：:224 `re.findall(pattern, code, re.MULTILINE | re.IGNORECASE)`——不排除注释/字符串：`password = "..."` 出现在注释或 docstring 中同样命中 AP-SEC-001；AP-SEC-002 SQL 拼接 pattern `(f".*SELECT|...)` 限定 f-string 前缀过窄（普通字符串拼接 SQL 漏报）；:235-236 正则错误静默跳过（仅 warning）。YAML 中 pattern 直接当正则——写普通子串（含 `.*` 等元字符）会语义错配。

### ASK5 [P3] RiskSelfAssessmentSkill 依赖计数与文件类型子串匹配错算（与 code_tasks.py:267-271 同源）

- **Bug 代码**：:299-301 `if target in file_path` 依赖计数——短 target（如 "utils"）跨文件命中 utils/ 下所有文件、多个 target 命中同一文件则依赖数虚高（reverse_index 遍历全量）；:274-285 文件类型判定同为子串——路径含 "auth"/"security" 即 +30、含 "model"/"db" +20（如 "models/..." 误判）。
- **注**：`_find_affected_files`（code_tasks.py:267-271）用相同 `target in file_path` 模式——同源同 bug 双副本。

### ASK6 [P3] 三个 YAML 配置相对路径 CWD 漂移 + 静默降级（GRD3/EC3 家族）

- **Bug 代码**：:33/:73/:199 `Path(settings.KEYWORD_TRIGGERS_PATH)` 等三个相对路径（settings 默认 `configs/xxx.yaml`）——进程 CWD 不同则 `.exists()` False → `triggers=[]`/`checklist={}`/`patterns=[]` **静默空降级**（:34-36/:75/:201 无日志无异常），技能全部空转且无感知（与 GRD3 相对路径漂移同族）。

### ASK7 [P3] MultiAngleReviewSkill.review 为占位实现——无实际审查逻辑

- **Bug 代码**：:97-102 review() 对每个 category 生成全 `status=pending_review` + 空 notes 的占位结构——实际审查依赖外部 Agent 执行 get_review_prompt（:106-126 生成提示词文本）；审查结果回写/状态更新逻辑从未实现。
- **影响**：五技能中「多角度审查」是核心能力却只有提示词生成 + 占位壳（与 ASK1 合并看：整个技能层从未落地）。

## 4. 演化方向

技能层整体未接线（ASK1）是首要问题：
- **接线决策**：关键词触发（KeywordDetectionSkill.detect）应接入编排入口（orchestrate_endpoints 的请求前处理）——但 ASK3 无词边界子串触发需先改词边界/权重排序；多角度审查/风险自评应接入 pre_modify 流程（对应 code_tasks 修改前阶段）、反面自查/对比学习接入 post_modify——与 FCT 守护合约（guard_contracts.py，helpers.py:185 活跃）协同，FCT 已承担路径安全，技能层专注认知审查
- **修复 ASK2**：post_modify_check 需保存修改前代码快照传入 detect_patterns（非空 before），或改为 diff 算法
- **修复 ASK4**：正则先剥离注释/字符串再匹配；YAML pattern 字段与「字面子串」字段区分（正则 vs 子串双模式）
- **修复 ASK5**：依赖计数改精确路径匹配（resolve 后前缀匹配）而非子串
- **配置治理**：三个 YAML 路径显式化/校验缺失时告警（ASK6）；get_all_skills_context 扩展为返回实际规则内容供知识库注入（当前仅元数据）

## 5. 主线关联

- **能力未接线家族**：ASK1（模块级全死）是 GRD1（类级）/SCT5/EC8/UPL1 的极端延伸——「docstring 声称能力 vs 接线状态」系统偏差的完整证据链
- **假阳性家族**：ASK2（空 before 全命中）加入 TR1/MAR8；ASK3/ASK4 加入 PP8/FCT3/DR12 子串/正则误报族
- **子串匹配双副本**：ASK5 与 code_tasks.py:267-271 `_find_affected_files` 同源同 bug（依赖图 reverse_index 消费方两处同错）
- **配置漂移**：ASK6 加入 GRD3/EC3 相对路径 + 静默降级家族
- **技能层 vs 守护合约**：helpers.py 中 get_agent_knowledge_base（零消费，含技能层）与 load_guard_contracts（活跃 :185-186，守护合约）形成对照——同文件两个知识库来源一个死一个活

## 6. 测试状态

- **零单元测试**：tests/ 下无任何 KeywordDetectionSkill/MultiAngleReviewSkill/AgentSkillsManager 引用
- ASK1 模块级零消费 + 三个 YAML 加载路径 + 各技能判定逻辑全无用例保护；ASK2/ASK4/ASK5 的误报错配行为无测试约束（修复时建议：技能判定纯函数化后以 YAML 为 fixture 建参数化测试）
