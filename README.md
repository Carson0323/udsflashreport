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

当前版本 **V1.0.1**，包含开发/测试使用者专家评审后的正确性与交付修复。详见 [更新记录](CHANGELOG.md) 和 [评审报告](docs/review-v1.0.1.md)。
Current version: **V1.0.1**, with correctness and distribution fixes from an engineering review. See the changelog and review report for validation boundaries.

已提供 Qt 异步 Open/Analyze/Export、证据逐条跳转、时间/方向/CF 筛选、深浅主题、中英文 UI、按步骤展示的刷写流程表和协议字节/ASCII 详情。
The GUI includes asynchronous loading, analysis and export, evidence navigation, time/direction/CF filters, themes, Chinese/English UI, flash workflow steps, and protocol byte/ASCII details.

修改配置后会重新加载当前日志并使旧结果失效，请重新点击 Analyze。未触发 Finding 仅表示没有满足现有规则，不能单独证明刷写成功。损坏记录会标记输入已知不完整。
Saving configuration reloads the current trace and invalidates previous results; run Analyze again. No findings alone does not prove flashing succeeded. Skipped damaged records mark input as known incomplete.

## 安装与使用 | Installation and Usage

Windows 分发包解压后运行 `FlashReport/FlashReport.exe`，保留完整目录及 `_internal`，无需安装 Python。
Extract the Windows distribution and run `FlashReport/FlashReport.exe`; keep its entire directory, including `_internal`.

源码开发需要 Python 3.11：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\flashreport-gui.exe
.\.venv\Scripts\python.exe -m flashreport_core.cli analyze samples/success_full_download.asc --out report.md --out-json report.json
.\.venv\Scripts\python.exe -m pytest -q
```

CLI 退出码：`0` 分析/导出完成（可能有 Finding），`2` 输入读取或分析失败，`3` 配置/规则无效，`4` 报告校验或导出失败。CI 若需要按故障判失败，应读取 JSON 的 `findings` 和 `input_stats`，而非仅检查退出码。
CLI exit codes: `0` completed (findings may exist), `2` input/analysis error, `3` invalid config/spec, `4` validation/export error. Use the JSON findings and input quality for a diagnostic pass/fail policy.

构建并验证 wheel：

```powershell
python -m pip wheel . --no-deps --wheel-dir dist/wheels
python tools/check_distribution.py dist/wheels/udsflashreport-1.0.1-py3-none-any.whl
```

Windows EXE 构建需另行安装 PyInstaller，再运行 `python tools/build_m7.py --build-name v1.0.1`。依赖范围见 `pyproject.toml`；当前未提交依赖锁文件。
For a Windows EXE build, install PyInstaller and run the build command above. Dependency ranges are in `pyproject.toml`; no dependency lock file is currently committed.

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
