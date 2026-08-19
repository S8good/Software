# M1.3 LSPR 输入与结果校验设计

## 背景

当前 LSPR 请求对象主要承担数据传输职责，`LSPRAIService` 会直接把调用方提供的数组交给进程内或子进程后端。非法输入可能因此延迟到模型内部才失败，GUI 也会把不同类型的错误统一显示为普通字符串异常。结果对象虽然包含后端和模型模式，但还没有统一的 provenance 信息，归档调用方也缺少固定字段约定。

M1.3 的目标是在不改变现有后端协议和正常预测结果的前提下，建立统一输入边界、错误分类和结果追溯信息。

## 目标与非目标

### 目标

- 在协议层提供可复用的光谱和浓度校验。
- 在服务层所有公共入口执行校验，覆盖单谱、对比、数字孪生和批量预测。
- 将配置、输入、模型、外部进程、超时和取消区分为稳定错误代码。
- GUI 显示简洁可执行的错误消息，日志保留完整异常链。
- 结果对象提供模型、后端、时间和调用方 metadata 等 provenance；归档时写入 `analysis_runs.input_context` 和 `algorithm_version`。
- 用自动化测试固定非法输入、错误映射和 provenance 行为。

### 非目标

- 不在本阶段硬编码统一的波长上下限或特定仪器单位范围。
- 不修改 LSPR Master 内部模型算法和 runner 命令协议。
- 不重构已有数据库 schema；复用现有 `analysis_runs` 和 `analysis_metrics` 字段。

## 方案

在 `nanosense/ml/lspr_backend_protocol.py` 增加共享校验函数和错误分类常量，在 `LSPRAIService` 的公共入口统一调用。后端继续负责执行模型和子进程，但将异常转换为稳定的 `ErrorResponse.code`；服务层将后端错误转换为带代码和详情的异常，供 GUI 展示和日志记录。

### 输入校验规则

光谱输入必须满足：

- 波长和强度长度一致。
- 两个数组至少包含 3 个点且不为空。
- 所有值均为有限数值，不接受 `NaN` 或无穷大。
- 波长严格递增，不接受重复或乱序波长。

数字孪生浓度必须是有限且大于或等于 0 的数值。数字孪生的实验光谱若只提供其中一个数组，视为 `input_invalid`；两个数组都省略时表示不叠加实验谱。批量请求不允许为空，并逐条执行同样的光谱校验。

不在协议层强制波长物理上下限和单位，由具体模型或配置在健康检查/执行阶段报告范围错误。

### 错误分类

稳定错误代码为：

- `input_invalid`：请求结构、数组、浓度或批量条目非法。
- `configuration_error`：后端模式、路径或运行配置错误。
- `model_error`：进程内模型加载或推理失败。
- `external_process_error`：子进程退出失败、返回非法 JSON 或 runner 缺失。
- `request_timeout`：子进程超过配置的超时时间。
- `cancelled`：请求被调用方取消。

`ErrorResponse.details` 保存可序列化的字段，例如字段名、索引、期望长度、runner 路径和返回码。服务层异常包含 `code`、用户可读 message 和 details；GUI 不直接显示 traceback。后端或服务捕获异常时通过模块 logger 记录 `logger.exception(...)`，保留完整异常链。

### Provenance

服务层返回的预测、对比和数字孪生结果增加 `provenance` 字典，至少包含：

- `model_mode`
- `backend`
- `requested_at`（UTC ISO 8601）
- 调用方传入的 metadata

批量结果的每一行继承请求级 provenance，并保留样本标签和源文件。调用 `DatabaseManager.save_lspr_ai_prediction()` 时，将 provenance 合并到 `input_context`，并将模型标识或模型模式写入 `algorithm_version`；不把完整光谱数组重复写入 metrics。

## 数据流

GUI/脚本 → `LSPRAIService` 校验 → 构造请求 → 后端执行 → 统一错误映射 → 服务层结果包装并附加 provenance → GUI 展示或数据库归档。

校验失败时不创建后端任务、不启动子进程、不写入数据库。后端失败时保留现有响应对象结构，仅补充稳定错误代码和详情。

## 测试策略

先写失败测试，再实现：

- 共享校验接受合法的 3 点递增光谱。
- 拒绝空数组、长度不一致、少于 3 点、`NaN`/无穷大和非递增波长。
- 拒绝负数或非有限数字孪生浓度，以及不完整的实验光谱对。
- 批量请求拒绝空列表，并报告出错条目索引。
- 服务层在校验失败时不调用 stub backend。
- 缺失模型映射为 `model_error`，runner 失败/非法 JSON 映射为 `external_process_error`，超时映射为 `request_timeout`。
- provenance 包含模式、后端、UTC 时间和 metadata，并可被序列化到归档上下文。
- GUI 显示错误 message 而非 traceback；日志测试确认异常链被记录。

验收命令：

```powershell
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest tests/test_lspr_backend_protocol.py tests/test_lspr_ai_service.py tests/test_lspr_master_bridge.py tests/test_lspr_ai_database.py -q
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pytest -q
& 'C:\ProgramData\anaconda3\envs\py39\python.exe' -m pip check
```

