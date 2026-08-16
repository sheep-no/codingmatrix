# TestFrameworkConfig 深扫（test_framework_config.py，88 行）

> 第九十九轮推演 | 2026-08-16 | 定位：测试框架预设数据模块（6 框架配置 + 2 访问函数），framework_detector/docker_runner 活跃消费

## 1. 模块定位

测试栈的框架预设数据源：定义 6 种测试框架（pytest/jest/maven/go_test/cargo/make）的配置（语言、命令、安装命令、Docker 镜像、输出格式、自定义参数）。

- `TestFrameworkConfig`（:17-26）：dataclass，6 字段（language/framework/test_command/setup_commands/docker_image/output_format/custom_args）
- `FRAMEWORK_PRESETS`（:29-78）：6 预设键 → 配置
- `get_framework_config`（:81-83）：按 key 查预设（**生产零消费**）
- `get_default_config`（:86-88）：默认 pytest 配置

**活跃生产模块**，三个消费方：

- `framework_detector.py:15-18`：import 全部符号；detect 结果即 `TestFrameworkConfig`，`_check_*` 方法直接索引 `FRAMEWORK_PRESETS["..."]`（:72/:81/:98/:116/:131/:141/:160/:164/:168/:172/:179/:181/:183/:185/:187）
- `docker_runner.py:41`：import `FRAMEWORK_PRESETS, TestFrameworkConfig`；`run_validation` 消费 `detected_config.test_command`（:492）与 `detected_config.docker_image`（:495-497），检测到框架后切换命令与镜像
- `orchestrator_testing.py:230`：`FrameworkDetector().detect(self.output_dir)`；消费 `detected_config.output_format`（:273）→ `OutputParser.parse(raw, output_format)`（:276）
- `test_runner.py:202`：`detect`；消费 `test_command`（:577-578）、`language/framework`（:641-674）、`output_format`（:742-746）

### 依赖链

| 方向 | 模块/位置 | 说明 |
|------|-----------|------|
| 消费方 | `framework_detector.py`（多处） | detect 返回 TestFrameworkConfig（活跃） |
| 消费方 | `docker_runner.py:492-497` | test_command + docker_image（活跃） |
| 消费方 | `test_runner.py:577-578/:742-746` | test_command + output_format（活跃） |
| 消费方 | `orchestrator_testing.py:273-276` | output_format → OutputParser（活跃） |
| 未消费 | `get_framework_config` | 生产零调用（仅定义） |
| 未消费 | `setup_commands` / `custom_args` 字段 | 全库零读取 |
| 测试 | `tests/unit/test_v4_8_features.py:137-140` | 仅断言 `len(FRAMEWORK_PRESETS) == 6` |

## 2. 深扫发现

### P2 项

- **TFC1 [P2] `setup_commands` 全库零消费 → 非 Python 项目 Docker/本地测试依赖从未安装（实测链路）**——FRAMEWORK_PRESETS 中 6 套预设都定义了 `setup_commands`（pip install / npm install / mvn dependency:resolve / go mod download / cargo build / make build），但**全库无任何代码读取该字段**：docker_runner 安装依赖硬编码 `"pip install --no-cache-dir --disable-pip-version-check -r requirements.txt"`（:536-539），本地 test_runner `_install_dependencies` 也只对 requirements.txt 做 pip install（:474-489）——**npm install / go mod download 等从未执行**。实测链路：orchestrator_testing:243 `install_deps = req_path.exists() or pkg_path.exists()`（package.json 存在即 True）→ docker_runner:531 条件 `install_deps and requirements_path and requirements_path.exists()`——**pkg-only 项目无 requirements.txt → 条件不满足 → 依赖安装被跳过**，容器内 `npm test` 在无 node_modules 的 node 镜像上必然失败；本地 JS 项目同样无 npm install。预设数据「命令存在但消费缺失」，非 Python 项目测试链路依赖安装整条缺失。

### P3 项

- **TFC2 [P3] `get_framework_config` 生产零消费死函数（全库确认）**——:81-83 是模块对外唯一的「按 key 查询」API，但全库（含三个消费方）都直接 `FRAMEWORK_PRESETS["..."]` dict 索引（framework_detector 13 处 / docker_runner），该函数无任何生产调用（仅定义 + 测试未引用）——与 DR8/EC8 同族「公共 API 存在但消费缺失」，且绕过函数直取 dict 使 key 拼写错误运行时才暴露（无 get 默认值保护）。
- **TFC3 [P3] `custom_args` 字段定义零消费（全库确认）**——dataclass :26 定义 `custom_args: List[str] = field(default_factory=list)`，但全库（含 FRAMEWORK_PRESETS 各预设）无任何读或写——「可自定义参数」能力完全未接线（GC6/SCT5 家族），且 6 预设无一设置，字段恒空。
- **TFC4 [P3] 默认输出格式双处硬编码重复（全库确认）**——test_runner.py:742 `output_format = "pytest_xml"` 与 orchestrator_testing.py:271 `output_format = "pytest_xml"` 各自硬编码同值默认（detect 失败时兜底），与 `get_default_config`（:86-88）三处默认来源并存——新增框架预设或改默认格式需同步三处，已存在同值漂移风险（双份配置家族）。
- **TFC5 [P3] 测试仅数量断言零字段级/链路覆盖（全库确认）**——test_v4_8_features.py:137-140 只断言 `len(FRAMEWORK_PRESETS) == 6`，无任何字段级断言（test_command/docker_image/output_format 具体值）、无 `get_framework_config`/`get_default_config` 用例、无 docker_runner/test_runner 消费链路测试——TFC1（setup_commands 零消费）全库确认可复现但零用例保护（TR2/DR8 弱断言家族）。

## 3. 演化方向

预设数据本身完整（6 框架、字段齐全、与 output_parser 的 6 种解析器一一对应），但**消费端只用了字段子集**：
- **setup_commands 接线（TFC1）**：docker_runner 安装依赖应从「硬编码 pip」改为执行 `detected_config.setup_commands`（非 Python 项目按预设装依赖），本地 test_runner 同理——修复后非 Python 项目测试链路依赖安装恢复。
- **访问函数收敛（TFC2/TFC3）**：删除 `get_framework_config`/`custom_args` 或让消费方走函数访问（带 key 校验），与 EC8/DR8 死代码清理合并。
- **默认值单一来源（TFC4）**：三处默认 output_format 收敛到 `get_default_config()`，与 §5.6 支柱 1（协议统一）对齐。
- **测试补强（TFC5）**：字段级断言 + 消费链路测试（detect → docker/test 命令），防止 TFC1 类接线缺口回归。

**修复优先级**：TFC1（非 Python 项目依赖安装缺失，功能缺口）> TFC4（默认值三处漂移风险）> TFC2（死函数）> TFC3（死字段）> TFC5（测试盲区）。

## 4. 主线关联

- **「能力未接线」家族**：TFC1/TFC2/TFC3 与 SCT5（6/7 公开函数零消费）、GC6、EC8、UPL1 同族——预设数据是设计好的能力，但消费方只取 test_command/docker_image/output_format，setup_commands/custom_args/get_framework_config 全成死数据。
- **「存在≠正确」验证语义**：TFC1 使非 Python 项目的测试执行在「无依赖安装」状态下进行——测试跑起来但环境不完整，与 TR1（无测试文件=通过）、CV2 同族：测试命令「执行了」但前提（依赖）缺失，结果无意义。
- **测试断言强度**：TFC5 与 MLP3/DR8「测试全绿 ≠ 解析正确」同族——len==6 计数断言固化「预设存在」而非「预设正确/被消费」。
- **双份配置**：TFC4 默认 output_format 三处并存（§5.6 支柱 1 收敛对象）。

## 5. 测试状态

**存在性断言、零行为断言**——仅 test_v4_8_features.py:137-140 一个用例断言 `len(FRAMEWORK_PRESETS) == 6`（REQ-1「6 种测试框架预设」计数）。无字段级断言、无 get_framework_config/get_default_config 用例、无消费链路（detect → docker/test_runner 命令选择）测试。TFC1（setup_commands 零消费，非 Python 项目依赖安装缺失）全库确认可复现但零用例保护——测试固化「6 个预设存在」而完全未触及「预设如何被消费、安装命令是否执行」。
