# M2.2 统一日志与可观测性设计

日期：2026-08-19  
状态：已确认，进入实施

## 目标

建立统一、可诊断且不泄露实验数据的日志基础设施，优先覆盖应用启动、设备连接、单次/批量采集、数据库保存和 LSPR 分析。日志应能回答“哪个模块、哪个任务、何时、因何失败”，同时不写入完整光谱、用户目录或敏感配置。

## 当前问题

- 启动器、控制器、采集、数据库和批量模块大量使用 `print`，无法统一级别、文件滚动和任务上下文。
- LSPR 模块已经局部使用 `logging`，但没有统一 handler、session ID 或 correlation ID。
- `main.py` 的全局异常钩子单独写 `crash.log`，与普通运行日志分离，且异常处理本身静默吞错。
- 后台线程和外部进程失败时，日志缺少稳定的任务标识，难以从多次采集记录中还原一次任务。

## 设计

### 日志配置模块

新建 `nanosense/utils/logging_config.py`，提供：

- `configure_logging(log_dir=None, level=None) -> Path`：幂等配置根 logger，返回实际日志文件路径；重复调用不重复添加 handler。
- `get_logger(name)`：统一获取模块 logger。
- `new_session_id()`：生成短、不可预测的启动会话 ID。
- `logging_context(session_id=None, correlation_id=None)`：context manager，临时设置任务上下文并在退出时恢复。
- `current_context()`：只返回 session/correlation 标识，不返回实验数据。

使用 `contextvars.ContextVar` 保存上下文，配合 `ContextFilter` 将 `session_id`、`correlation_id` 注入每条 LogRecord。格式为纯文本键值风格，便于人工阅读和后续采集：

```text
2026-08-19 12:00:00,123 INFO nanosense.core.acquisition session=abc123 correlation=acq-456 event=acquisition_started
```

控制台使用 `StreamHandler`；文件使用 `RotatingFileHandler`，默认单文件 5 MB、保留 3 个备份。日志文件放在 `logs/nanosense.log`，该目录已被 `.gitignore` 忽略。

### 启动与异常钩子

`main.py` 在创建 Qt 应用前配置日志并创建启动 session ID。全局异常钩子使用 `logger.exception` 记录完整 traceback，KeyboardInterrupt 仍交给默认钩子；写日志失败时不递归抛错。启动、欢迎页硬件选择、主窗口启动失败和应用退出记录结构化事件。

### 关键路径上下文

- 单次采集 `AcquisitionService.start()` 为一次运行建立 correlation ID，并在开始、停止、超时、错误和完成时记录事件。
- 批量采集 `start_batch()` 为 worker 建立 correlation ID，记录批量开始、完成、取消和失败；不记录光谱数组。
- LSPR 服务在公开预测入口创建或继承 correlation ID，记录 backend、操作类型、耗时和错误分类。
- 数据库关键写入/迁移记录操作类型、实验/批量 ID 和结果，不记录完整数据数组或本机绝对路径。

### 迁移范围

本阶段优先替换以下模块中的关键 `print` 和无上下文异常输出：

- `main.py`
- `nanosense/core/acquisition.py`
- `nanosense/core/controller.py`
- `nanosense/core/batch_acquisition.py`
- `nanosense/core/database_manager.py`
- `nanosense/ml/lspr_ai_service.py`
- `nanosense/ml/lspr_inprocess_backend.py`
- `nanosense/ml/lspr_subprocess_backend.py`

算法、报表和 GUI 辅助模块暂保留行为，仅在其错误跨越关键边界时使用 logger；后续按诊断需要迁移。禁止无说明的 `except Exception: pass`，可恢复错误记录上下文，不可恢复错误继续交给统一边界。

## 测试与验收

新建 `tests/test_logging_config.py`，覆盖：

1. 配置幂等，重复调用不会添加重复 handler。
2. 日志文件创建、滚动参数和指定目录生效。
3. session/correlation 上下文注入并在嵌套 context 退出后恢复。
4. `logger.exception` 保留 traceback 文本。
5. 日志中不出现完整光谱数组、用户主目录或敏感配置值。
6. 采集、批量和 LSPR 关键事件包含稳定的 correlation 字段。

验收命令为 py39 环境下的新增测试、全量 pytest、`pip check`、`compileall` 和 `git diff --check`。日志目录和生成文件不得进入 Git。

## 非目标

本阶段不引入第三方日志依赖，不强制把全部 257 处 `print` 一次性改完，不改变业务错误传播、数据库 schema 或用户界面文案；M2.3 再升级 GUI 行为测试。
