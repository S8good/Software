# M1.2 LSPR Master 路径解析与健康检查设计

## 背景

`nanosense/ml/lspr_master_bridge.py` 当前在未提供 `lspr_master_root` 且未设置环境变量时，回退到开发机上的固定绝对路径。该行为使软件无法在其他主机、打包目录或新的工作树中可靠启动，也会让 `auto` 后端的故障原因不透明。

M1.2 的目标是移除主机相关的路径依赖，使 LSPR Master 根目录和子进程解释器可配置、可探测、可诊断，并保持现有进程内/子进程后端协议不变。

## 目标与非目标

### 目标

- 统一 LSPR Master 根目录解析优先级：显式配置、`LSPR_MASTER_ROOT` 环境变量、软件目录附近的候选目录。
- 移除代码中的开发机绝对路径，不再静默依赖旧路径。
- 在路径无效或资源缺失时返回可操作的诊断信息。
- 在设置页提供 LSPR 根目录、子进程 Python 解释器选择和连接测试。
- 增加可移植的单元测试和设置集成测试，覆盖 Windows 路径与临时目录场景。

### 非目标

- 不修改 LSPR Master 仓库内部模型、推理算法或 runner 协议。
- 不改变 `auto`、`inprocess`、`subprocess` 三种后端的选择语义。
- 不自动下载或复制 LSPR Master 仓库及模型文件。

## 方案

在现有 `LSPRMasterBridge` 中集中实现解析逻辑，避免为当前范围增加新的路径模块。桥接器负责解析、验证和诊断；后端和服务层只消费桥接器或配置结果。

### 路径解析

解析顺序固定为：

1. 调用方显式传入的 `master_root` 或配置中的 `lspr_master_root`。
2. 环境变量 `LSPR_MASTER_ROOT`。
3. 从当前软件目录推导的相邻候选目录，例如：
   - `<software>/LSPR_Spectra_Master`
   - `<software>/../DeepLearning/LSPR_Spectra_Master`
   - `<software>/../../DeepLearning/LSPR_Spectra_Master`

候选目录只在存在时接受，并继续执行必需文件验证。所有路径使用 `Path.expanduser().resolve()` 规范化。找不到有效目录时抛出包含尝试来源、候选路径和修复建议的错误；代码中不得保留旧开发机绝对路径。

### 配置

在默认设置中增加：

- `lspr_master_root`: 空字符串表示按上述顺序自动解析。
- `lspr_subprocess_python`: 空字符串表示使用当前 Python 解释器。

现有 `lspr_backend_mode` 和其它 LSPR 设置保持兼容。保存设置时保留用户输入的路径字符串，运行时再解析。

### 诊断与健康检查

`LSPRMasterDiagnostics` 增加以下字段：

- `resolution_source`：`explicit`、`environment` 或 `adjacent`。
- `candidate_paths`：按尝试顺序排列的规范化路径列表。
- `missing_files`：缺失的必需文件及其相对路径。
- `runner_path`：子进程 runner 的预期路径。
- `python_executable`：实际使用的子进程解释器。

路径不存在或必需文件缺失时，错误消息必须包含根目录和具体缺失项。健康检查继续返回现有协议对象，并将上述诊断放入 `details`；不要求 GUI 直接解析异常文本。

### 设置页

在 LSPR AI 设置组中：

- 保留根目录文本框和目录选择按钮。
- 增加子进程 Python 解释器文本框及文件选择按钮。
- 增加“测试连接”按钮，使用当前未保存的表单值构造后端并执行健康检查。
- 成功时显示解析根目录和后端；失败时显示结构化错误摘要及修复建议。
- 测试操作不得写入配置，也不得改变当前已打开的分析窗口。

## 数据流与错误处理

设置页测试连接 → 读取表单配置 → 创建后端 → `health_check()` → 返回结构化结果 → GUI 展示摘要。

进程内后端通过 `LSPRMasterBridge` 解析根目录。子进程后端从同一配置解析 runner 路径，并使用 `lspr_subprocess_python` 或 `sys.executable`。解析失败属于预期的可报告错误，不应导致 GUI 崩溃；实际预测请求继续沿用现有错误响应机制。

## 测试策略

先新增失败测试，再实现代码：

- 显式配置优先于环境变量和相邻目录。
- 环境变量在无显式配置时生效。
- 相邻目录可以从 `tmp_path` 推导并被选中。
- 无有效路径时错误不包含旧主机路径，并包含候选目录或修复建议。
- 缺失必需文件时诊断列出具体文件。
- 默认设置包含解释器键；设置页能够读取和保存该键。
- 健康检查返回包含路径来源和 runner 信息的结构化详情。
- 现有 LSPR 测试和完整 py39 测试集保持通过。

验收命令：

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_lspr_master_bridge.py tests/test_lspr_settings_integration.py tests/test_lspr_ai_workbench_plan_smoke.py -q
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest -q
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pip check
```

