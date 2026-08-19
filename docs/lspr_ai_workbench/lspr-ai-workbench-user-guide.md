# LSPR AI Workbench 使用指南

## 1. 入口

当前可通过以下方式打开 `LSPR AI Workbench`：

- 分析菜单中的 `LSPR AI Workbench...`
- 测量页中的 `Send to LSPR AI Workbench`
- 数据库浏览器中的 `Open in LSPR AI Workbench`
- 数据库浏览器 `AI Runs` 标签页中重新打开已归档结果

## 2. 配对参考 CEA / 分析物定量

1. 打开工作台并选择分析物。
2. 导入同一 chip/site 的 BSA 参考谱和分析物反应谱。
3. 填写 `Chip ID` 和 `Site ID`，等待配对校验通过。
4. 只有存在已验证模型的分析物才能点击 `Run Paired Prediction`。

执行后可看到：

- 浓度预测结果和单位
- 配对质量控制状态
- 模型版本、预处理版本和输入溯源

当前注册的分析物为 CEA、NSE、Cyfra21-1、ProGRP、SCCA、p53、CA125、TSGF、GAGE-7 和 MAGE-A1。CEA 使用论文配对参考全光谱契约；其余分析物目前只可登记、校验和归档，预测模型尚未提供。

当前仓库未包含论文训练数据或模型制品。未配置 `lspr_cea_model_artifact` 时，CEA 预测会明确报告模型制品不可用，不会回退到旧的单谱模型。

旧版 `Single Spectrum` 结果仍可在数据库中读取，但会被标记为 `legacy_generic`，不能解释为本论文的 CEA 定量结果。

## 3. 谱线对比

工作台 `Analysis` 页会显示：

- 当前输入谱
- 生成谱
- 对齐谱

可使用：

- `Export Current Plot` 导出当前图
- `Find Main Peak` 查看主峰位置、强度和 FWHM

如果当前模型不支持生成器，界面会显示回退说明。

## 4. 数字孪生

切换到 `Digital Twin` 标签页后，可：

- 通过滑块或数值框调节浓度
- 生成物理谱、基线谱和 AI 叠加谱
- 叠加当前实验谱进行对比
- 导出数字孪生图像

关键指标包括：

- Peak Wavelength
- Delta Lambda
- Peak Intensity

## 5. 多模型比较

切换到 `Model Comparison` 标签页后，可：

- 勾选要比较的模型模式
- 运行模型比较
- 查看每个模型的浓度、模式和报告文本
- 对比不同模型的对齐谱

当前默认推荐模型显示为 `Recommended: auto`，由后端自动选择当前环境下最稳妥的可用模式。

## 6. 批量预测

切换到 `Batch Prediction` 标签页后，可：

- 通过 `Load Folder...` 导入文件夹中的多条光谱
- 通过 `Load Multi-column File...` 导入多列表文件
- 点击 `Run Batch Prediction` 生成批量结果
- 使用 `Export CSV...` 导出批量结果
- 双击结果表中的某一行，将该行光谱回填到当前工作台分析页

## 7. 结果归档

在完成单谱预测后，可点击 `Archive AI Result` 将结果写入数据库。

当前归档内容包括：

- 结构化 `analysis_runs`
- 关键指标 `analysis_metrics`
- 输入谱、比较数据、数字孪生上下文等 JSON 元数据

如果当前光谱没有已有实验记录，系统会自动在数据库中创建一个 `LSPR AI Workbench` 项目下的实验记录。

## 8. 数据库回看

数据库浏览器支持两种 AI 回看方式：

- 选中实验后，切换到 `AI Runs` 标签页查看已归档的 AI 结果
- 在 `AI Runs` 页中选中某条记录，点击 `Open in LSPR AI Workbench`

重新打开时，系统会尽量恢复：

- 原始输入谱
- 结果摘要
- 谱线对比数据

如果历史归档缺少谱线上下文，则可能只能恢复指标信息。

## 9. 输入校验与错误处理

提交给 LSPR AI 的光谱必须满足：波长和强度长度一致、至少 3 个点、全部为有限数值，且波长严格递增。当前协议层不硬编码波长上下限，具体模型范围由后端配置和健康检查负责。数字孪生浓度必须为有限且非负数；批量预测会逐条检查输入，空批次或缺少光谱来源会被拒绝。

界面和脚本使用以下稳定错误分类：

- `input_invalid`：输入数组、浓度或批量条目不合法
- `configuration_error`：后端模式、路径或运行配置错误
- `model_error`：模型加载或推理失败
- `external_process_error`：bridge runner 缺失、退出失败或返回非法 JSON
- `request_timeout`：子进程超过超时时间
- `cancelled`：调用方取消请求

归档结果会保留模型模式、后端、UTC 请求时间和调用方 metadata，并写入 `analysis_runs.input_context`；模型模式会作为缺省 `algorithm_version`，便于后续追溯。

## 10. 环境说明

推荐配置：

- `lspr_backend_mode = auto`
- `lspr_master_root` 可显式指向 `LSPR_Spectra_Master` 根目录
- `lspr_subprocess_python` 可指定运行 bridge runner 的 Python 解释器；留空时使用当前解释器

根目录解析优先级为：显式 `lspr_master_root`、环境变量 `LSPR_MASTER_ROOT`、软件目录附近的相邻目录。设置页中的 `Test LSPR Connection` 不会保存配置，只会执行健康检查并显示实际解析路径。若检查失败，详情中会列出候选目录、runner 路径、解释器和缺失的模型文件，便于修复部署问题。

在当前工作站环境中，`auto` 往往会自动回退到 `subprocess`。只要预测和图形结果正常，这属于预期行为。
