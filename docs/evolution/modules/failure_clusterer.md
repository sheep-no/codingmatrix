# FailureClusterer 演化详档

- 文件：`app/agent/failure_clusterer.py`（219 行）
- 扫描日期：2026-08-09
- 状态：✅ 已完成
- 模块定位：测试失败根因聚类——对批量失败分组，识别共同错误类型和位置，「减少修复次数」

## 职责

`cluster`（:48-163）：

1. 空/单失败直接返回
2. 多失败：`_parse_traceback` 提取 (error_type, error_location, keywords) → 按 `(error_type, error_location)` 精确键聚类
3. `max_clusters = len//2` 压缩：按 count 排序保留主簇，小簇并入同 error_type 的第一个主簇（:126-152）
4. `_parse_traceback`（:165-199）：正则提取错误类型/位置/关键词
5. `_generate_hint`（:201-219）：静态错误提示映射

## 消费方

- `orchestrator_testing.py:122-123`：`clusterer = FailureClusterer(); clusters = clusterer.cluster(test_results)`——构造无参，**不受 OT16 构造失败影响**（与 ImpactAnalyzer/TestSelector 不同），但调用在 TR 测试执行分支内，且 clusters 结果仅由 OT 侧消费
- `orchestrate_endpoints.py`：import（引用）
- 测试状态：**零单元测试**（tests/unit 无对应文件）

## 实测确认的 bug

### FC2 [P2] 位置解析只认标准 Python traceback——pytest 短格式恒空，聚类退化为仅按错误类型

- 位置：:186 `re.findall(r'File "([^"]+)", line (\d+)', traceback)`
- 实测：pytest 短格式 `tests/test_x.py:12: in test_x\n assert foo\nE AssertionError: x` → error_location = `''`（无 `File "..."` 模式）
- 影响：TR 链（OT21/OT22 docker 分支）实际跑 pytest 输出短格式 → **error_location 基本恒空** → 聚类键退化为 `(error_type, '')`，位置维度全丢，「识别共同错误位置」的核心目标失效
- 修复方向：兼容 `file.py:line: in func` 格式 + 归一化路径（相对化、去行号可选）

## 其余发现

### FC1 [P3] 聚类键含绝对路径 + 精确行号

- 位置：:98 `cluster_key = (parsed['error_type'], parsed['error_location'])`
- 事实：error_location 是**绝对路径**（`/proj/util.py:42`）——同一代码在不同环境路径下分簇；且行号精确使「同类型同文件不同行」的同类错误（如两处独立 AttributeError）分簇
- 实测边界：同根因同抛错点（最后帧相同）能正确聚 1 簇——聚类在「同抛错帧」场景可用，问题在路径归一化与粒度
- 修复方向：路径相对化、文件级（去行号）作聚类键、或引入模糊聚类

### FC3 [P3] 关键词只有 1 个——最后一行前 50 字符

- 位置：:197 `keywords = [last_line[:50]] if last_line else []`
- 影响：单关键词 + 50 字符截断；traceback 以空行结尾时恒空；信息量极低，对根因提示无实际增益

### FC5 [P3] `result['name']` 直接索引，缺键 KeyError

- 位置：:76/:86
- 影响：test_results 项缺 `name` 字段时整次聚类崩溃（无 try 包裹）

## 修复优先级

| 项 | 级别 | 关键点 |
|---|---|---|
| FC2 | P2 | 位置维度失效，聚类退化为单维 |
| FC1 | P3 | 路径归一化 + 粒度 |
| FC3 | P3 | 关键词信息量 |
| FC5 | P3 | 缺键崩溃 |

## 关联

- OT21/OT22 [P2]：TR 双路径（docker 跳过聚类）——聚类只在本地路径触发，docker 分支根本不聚
- TR/OP/FD 链：聚类输入来自测试结果，输出驱动「减少修复次数」——若 RefinementLoop 不消费 clusters，聚类结果无下游
- 测试选择四连失效（OT16/IA3/TS1/TS6）：聚类是失败后的补救，但智能选择从未生效时聚类面对的是全量失败
