# ShadowScanner 深扫（shadow_scanner.py，84 行）

> 第八十轮推演 | 2026-08-13 | 定位：阴影依赖扫描器——发现隐式依赖（eval/exec/dynamic import/env 反射），只记录不阻断

## 1. 模块定位

扫描项目源码中的隐式依赖模式（eval/exec、动态 import、env 反射、动态 getattr），返回 `{file_path: [模式名]}`，设计上「只记录不阻断」。唯一消费方是 dependency_graph.build_from_existing_project（dependency_graph.py:976），该消费方已被证死（DG1）。

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 消费方 | `dependency_graph.py:23/:976` | build_from_existing_project 唯一调用点（async 包装），结果写入 `result["shadow_dependencies"]` |
| 消费方 | `dependency_graph.py:23` | 复用 SKIP_DIRS 常量 |
| 上游死链 | `build_from_existing_project` | **DG1 已证实零生产调用方**（dependency_graph.md）——shadow_scanner 唯一入口依附于死路径 |

## 2. 深扫发现

### P2 项

- **SHS1 阴影扫描整个能力依附于死路径 + 产出键零消费方**——唯一调用点 `build_from_existing_project`（dependency_graph.py:965）是 DG1 已证死的生产死路径（全库零调用方）；且 `result["shadow_dependencies"]` 键（:977）全库**无任何消费方读取**——即使 build_from_existing_project 被接线，阴影扫描结果也只是塞进 result dict 无人读。**阴影依赖信息从未影响任何下游决策**（不做阻断、不做提示、不进依赖图节点），「只记录不阻断」实际「连记录都没有消费方」。这是「能力存在但整链路未接线」家族（UPL1 同类，但更轻——它是辅助信息非核心闭环）。

### P3 项

- **SHS2 getattr_dynamic 正则只匹配字面量属性名（漏检变量/关键字参数）**——`getattr\s*\([^,]+,\s*["']`（:29）要求第二参数是字符串字面量：`getattr(obj, name_var)`（动态变量名，最危险的反射）**漏检**；`getattr(obj, attr="x")`/`attr=var` 关键字形式**漏检**（实测三项全 False）；多行形式因 `\s*` 命中。漏掉的恰是最需要标记的动态反射。
- **SHS3 env_dependency 不分读写方向（误报写/删）**——`:27 os\.environ\b` 无方向判断：`os.environ["PATH"] = x`（写）、`del os.environ["X"]`（删）都命中（实测）——写入/删除环境变量是程序行为，不构成「依赖」，扫描结果混入非依赖信号。
- **SHS4 正则扫非 AST（注释/字符串误报）**——`:25 eval\s*\(` 对注释里的 `# 用 eval() 解析` 或字符串 `"eval("` 都命中；getattr_dynamic 同样无 AST 上下文区分——阴影依赖标记可能被注释文本污染（CV2/CR2 子串正则假阳性家族，但只记录不阻断使危害局限）。
- **SHS5 扫描开销随项目线性增长且每次全量**——`_scan_sync`（:53）每次调用 rglob 全项目 + 逐文件正则；若 build_from_existing_project 接线后每请求调用，大项目 shadow 扫描成隐藏成本；无增量/缓存。asyncio.to_thread（:46）避免阻塞事件循环是正面设计，但吞吐成本仍在。

## 3. 演化方向

### 3.1 依赖图接线后再激活

shadow_scanner 的修复依赖 DG1（build_from_existing_project 接线）——它是依赖图「从已有项目构建」的辅助层。应在 DG 主线（§5.6 支柱 4 共享真相源）接线时一并激活：shadow_dependencies 结果消费方需明确（如标记节点为「动态依赖」影响影响传播判断，或供用户查看），否则保持现状无意义。

### 3.2 检测精化

若激活：getattr 分支补动态变量/关键字参数形式（SHS2）；env 扫描区分读写方向只标记读取为依赖（SHS3）；AST 解析替代纯正则（SHS4，与依赖图主解析对齐）。SHS5 成本问题在依赖图主路径已有（DG5/每文件解析），可合并优化。

## 4. 主线关联

- **「能力未接线」家族再例**：SHS1（阴影扫描唯一入口 DG1 死路径 + 产出零消费）与 UPL1/SL1/FPC1（学习组件零消费方）、TS6（调度能力未接线）同主线——模块存在、实现完整、但整链路无人使用
- **正则假阳性家族**：SHS3/SHS4 与 CV2（模型一致性正则低精度）、CR2（版本检查子串假阳性）、FL1（错误消息拆词 OR）同族——纯正则启发式在文本匹配上的共同缺陷
- **依赖图主线支线**：shadow_scanner 是 DependencyGraph 的伴生扫描器，演化方向应从属 DG 主线而非独立演化

## 5. 测试状态

**零测试覆盖**——无 shadow_scanner 专项测试；正则行为（SHS2 漏检/SHS3 误报）全未验证；异步包装 to_thread 路径无测试。
