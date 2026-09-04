# udsflashreport

确定性的 UDS/ISO-TP 刷写 Trace 故障归因引擎。
An open-source, deterministic UDS/ISO-TP flash trace fault attribution engine.

## 项目简介 | Overview

`udsflashreport` 面向 ASC/BLF 日志的离线工程分析：识别第一个协议偏离点，给出 Tester/ECU 疑似责任侧、置信度，以及可回跳原始帧的机器可验证证据链。

`udsflashreport` is designed for offline engineering analysis of ASC/BLF logs. It identifies the first protocol deviation, reports the suspected Tester/ECU side and confidence, and provides machine-verifiable evidence chains that link back to raw frames.

GUI 是 core 分析引擎的薄壳 viewer，不执行实时诊断通信或 ECU 刷写。
The GUI is a thin viewer over the core analysis engine; it does not perform live diagnostic communication or ECU flashing.

## v1 范围 | v1 Scope

- 读取 ASC/BLF，并保留 channel、CAN FD、远程帧和错误帧等记录层信息。
  Read ASC/BLF while preserving record-layer channel, CAN FD, remote-frame, and error-frame metadata.
- 支持 Classical CAN、normal addressing、ISO-TP SF/FF/CF/FC 和常用 UDS 服务子集。
  Support Classical CAN, normal addressing, ISO-TP SF/FF/CF/FC, and a common UDS service subset.
- 输出 Markdown/JSON 报告、TraceQuality、first deviation、归因 finding 和 evidence chain。
  Produce Markdown/JSON reports, TraceQuality, first deviation, attribution findings, and evidence chains.
- 提供 CLI batch 分析和 PySide6 Qt Widgets viewer。
  Provide CLI batch analysis and a PySide6 Qt Widgets viewer.

启动图形界面：`flashreport-gui`（或 `python -m flashreport_gui.app`）。
Launch the GUI with `flashreport-gui` (or `python -m flashreport_gui.app`).

## 项目状态 | Project Status

当前处于 M6-B：PySide6 图形界面交互与异步工作器开发阶段。
Currently in M6-B: PySide6 GUI interaction and asynchronous worker development.

M2 已支持 SF/FF/CF/FC 事件化、SN 校验、CF/STmin/BS/WAIT/OVFLW/超时诊断，以及按双向 conversation 进行 Transport Validator 校验。UDS 解码、会话、归因和报告将在后续里程碑完成。
M2 supports SF/FF/CF/FC eventization, sequence-number checks, CF/STmin/BS/WAIT/OVFLW/timeout diagnostics, and bidirectional conversation validation. UDS decoding, sessions, attribution, and reports are scheduled for later milestones.

M3 已支持 UDS 子集解码、NRC/0x78 Pending、事务歧义标记、诊断会话与刷写上下文。
M3 supports the UDS subset decoder, NRC/0x78 pending handling, transaction ambiguity markers, diagnostic sessions, and flash context.

M4 已支持 findings.yaml 驱动的 7 类确定性归因、时序来源、证据契约、first deviation、事务歧义降级和 tester 先行错误对后续 ECU 超时的 supersede 标记。
M4 supports seven findings driven by findings.yaml, timing provenance, evidence contracts, first-deviation selection, ambiguity confidence caps, and supersede marking when a prior tester error explains a later ECU timeout.

M5 已支持直接分析 ASC/BLF、双语 Markdown/JSON 报告、报告 Schema 校验和 CLI 退出码。29 位标准诊断地址可在未配置 tester SA 时自动成对，结果保留歧义标记供测试人员确认。
M5 supports direct ASC/BLF analysis, bilingual Markdown/JSON reports, report-schema validation, and CLI exit codes. Standard 29-bit diagnostic IDs can be paired automatically without a configured tester SA, with ambiguity retained for tester review.

M6-A 提供了 Qt Widgets 主窗口、会话树、原始帧表、Finding 证据卡片和底部详情页，作为 M6-B 交互的基础。
M6-A provides the Qt Widgets main window, conversation tree, raw-frame table, Finding evidence cards, and detail tabs as the foundation for M6-B interaction.

M6-B 已将 Open/Analyze/Export 接入 QThreadPool，并提供错误状态、逐条 evidence 跳转、缺失区间展示和配置持久化。GUI 主线程只负责控件和 Model 更新。
M6-B connects Open/Analyze/Export to QThreadPool and provides error states, per-evidence navigation, absence-window display, and configuration persistence. The GUI thread only updates widgets and models.

开发按冻结规格 M0→M7 进行，每个里程碑都必须通过对应的自动化测试 Gate。
Development follows the frozen M0→M7 specification; each milestone must pass its automated test Gate.

## 安全与责任 | Safety and Responsibility

本项目仅用于工程分析和测试。任何结果用于车辆、ECU、生产环境或安全相关流程前，必须由使用者独立验证。使用者自行承担使用、验证及其后果；项目不提供准确性、适用性或安全性保证。

This project is provided for engineering analysis and testing only. Results must be independently validated before use in any vehicle, ECU, production, or safety-relevant workflow. Users are responsible for their own use, validation, and consequences; no accuracy, fitness, or safety guarantee is provided.

本项目与 Vector、任何 OEM 或其他被提及的厂商没有隶属或合作关系。
This project is not affiliated with Vector, any OEM, or any other referenced vendor.

## 数据边界 | Data Boundary

公开仓库只包含合成样例和脱敏数据。私有语料应放在 `private_corpus/`，该目录默认不会被 Git 跟踪。
The public repository contains synthetic samples and sanitized data only. Private corpora belong in `private_corpus/`, which is ignored by Git by default.

项目不内置厂商私有 seed/key 算法。
The project does not include proprietary vendor seed/key algorithms.

## 许可证 | License

本项目代码采用 MIT License，详见 `LICENSE`。
The project code is licensed under the MIT License; see `LICENSE`.

第三方依赖保留其各自许可证和义务，详见 `THIRD_PARTY_NOTICES.md`。
Third-party dependencies retain their own licenses and obligations; see `THIRD_PARTY_NOTICES.md`.
