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

## 项目状态 | Project Status

当前处于 M1：数据层与寻址开发阶段。
Currently in M1: data layer and addressing implementation.

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
