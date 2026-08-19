# M2.1 采集服务边界设计

日期：2026-08-19  
状态：已确认，待实施

## 目标

统一单次采集和批量采集的生命周期语义，收回线程、停止等待和设备释放的所有权，避免 GUI 直接操作底层线程或设备。M2.1 不重写批量采集的数据处理、预览和数据库业务，只收敛控制边界。

## 当前问题

- `MeasurementWidget` 直接创建和管理 Python `threading.Thread`，并通过 `stop_event`、`is_acquiring` 和 `join(0.5)` 组合控制生命周期。
- `MainWindow` 直接创建 `QThread`、移动 `BatchAcquisitionWorker`、连接停止信号并在关闭时等待线程。
- 两条路径没有统一的状态模型；重复开始、重复停止、窗口关闭期间的竞态可能导致线程残留、设备仍被占用或 UI 状态不一致。
- 设备连接/释放由控制器和 GUI 分散处理，采集异常没有稳定的服务级终态。

## 设计概览

### 状态模型

`nanosense/core/acquisition.py` 定义 `AcquisitionState` 枚举：

- `IDLE`：无采集任务，服务可启动。
- `CONNECTING`：正在准备采集资源或线程。
- `READY`：资源已准备好但尚未采集。
- `ACQUIRING`：采集循环或批量任务正在运行。
- `STOPPING`：已收到停止请求，正在等待任务退出。
- `ERROR`：任务因不可恢复异常结束；调用 `reset()` 后回到 `IDLE`。

状态转换由服务集中执行并发出 `state_changed(AcquisitionState)`。无效或重复操作不抛出线程错误：重复 `start()` 保持当前运行状态，重复 `stop()` 保持 `STOPPING`/`IDLE`，重复 `close()` 安全返回。

### `AcquisitionService`

服务位于 `nanosense/core/acquisition.py`，不承担光谱处理、绘图或数据库写入。它负责：

- 持有控制器引用和采集线程/线程对象；
- 创建、启动、停止和等待单次采集线程；
- 对外发出 `state_changed`、`spectrum_ready`、`error_occurred`、`finished` 信号；
- 统一处理采集异常与停止超时；
- `close(timeout_ms)` 幂等地停止任务并释放服务持有的设备资源。

服务的单次采集循环只调用控制器读取光谱，将 `(wavelengths, spectrum)` 通过 signal 发送给主线程；不直接访问 Qt 控件。服务不在后台线程执行 UI 逻辑。

### 单次采集数据流

`MeasurementWidget` 创建一个服务实例并连接信号：

1. 用户点击开始，widget 调用 `service.start()`。
2. 服务完成启动后进入 `ACQUIRING`，后台线程发出 `spectrum_ready`。
3. widget 的主线程 slot 将最新光谱放入现有 `data_queue`，保留现有 `QTimer` 绘图和处理节流逻辑。
4. 用户点击停止或窗口关闭，widget 调用 `service.stop()`/`service.close()`；不再创建线程、设置底层停止事件或直接 `join()`。
5. 服务发出 `finished` 后 widget 只更新按钮和工作流状态。

### 批量采集数据流

新增服务侧的批量运行句柄 `BatchAcquisitionHandle`，由 `AcquisitionService` 持有线程所有权：

- 服务负责创建 `QThread`、移动 `BatchAcquisitionWorker`、启动线程、连接 worker 完成/错误信号，并提供 `start_batch()`、`stop()`、`wait()`、`close()`。
- `BatchAcquisitionWorker` 保留现有命令队列、预览、峰值分析和数据库收尾逻辑；其 `stop()` 仅表示业务取消请求，不再负责服务外部线程的生命周期。
- `MainWindow` 只创建配置和对话框，订阅服务转发的 worker 信号，并在关闭时调用服务的 `close()`。
- 批量 worker 的最终 `run_status` 映射到统一状态：正常完成回 `READY`/`IDLE`，用户取消回 `IDLE`，未处理异常进入 `ERROR`；原有提示和分析入口保持不变。

### 设备与资源所有权

服务只释放由它创建或明确接管的采集资源。停止顺序固定为：发出停止请求 -> 等待 worker/线程结束 -> 清理 Qt 对象引用 -> 释放设备连接（若服务拥有连接）。超时不强杀线程；服务进入 `ERROR` 并发出错误信号，保留异常上下文供日志记录。

## 错误处理

- 控制器读取异常：服务发出一次结构化错误信号并按现有短暂退避继续采集；连续无法恢复或线程退出异常时进入 `ERROR`。
- 停止超时：服务返回明确的失败结果或发出错误信号，不把“线程仍在运行”伪装成成功关闭。
- GUI 错误提示只消费服务错误消息，不显示原始 traceback；完整异常对象通过日志钩子保留。
- 数据库事务和批量文件收尾继续由现有 worker/数据库模块负责，服务不在异常路径重复写入。

## 测试设计

新建 `tests/test_acquisition_lifecycle.py`，使用可控模拟控制器和最小 Qt 测试对象覆盖：

1. 初始状态、正常启动和停止的状态序列。
2. 重复 `start()`、重复 `stop()`、重复 `close()` 的幂等性。
3. 控制器读取异常不会造成后台线程失控，错误信号和终态可观察。
4. 停止等待在限定时间内完成；超时会报告错误而不虚报成功。
5. 连续 100 次模拟开始/停止后没有存活的采集线程。
6. 批量服务取消和窗口关闭会等待线程结束，并保留 worker 的 `completed`/`aborted`/`failed` 语义。

现有 `test_ocean_acquisition_recovery.py`、批量预览和数据库测试必须保持通过。验收命令使用 py39 环境运行新增测试、全量 pytest、`pip check` 和 `compileall`。

## 范围与非目标

本阶段不改变采集数据格式、预处理算法、批量任务编排、数据库 schema、GUI 布局或设备驱动协议；不引入强制终止线程的做法。日志统一化属于 M2.2，复杂重试策略属于后续阶段。
