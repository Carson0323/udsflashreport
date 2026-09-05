# udsflashreport

确定性的 UDS/ISO-TP 刷写 Trace 离线分析工具。
An open-source, deterministic offline analyzer for UDS/ISO-TP flash traces.

## 项目简介 | Overview

`udsflashreport` 读取 ASC/BLF 日志，分析 ISO-TP/UDS 通信，识别协议偏离点，并提供责任侧、置信度和可回跳原始帧的证据。GUI 只做离线查看与报告导出，不执行实时诊断通信或 ECU 刷写。

`udsflashreport` reads ASC/BLF logs, analyzes ISO-TP/UDS traffic, identifies protocol deviations, and provides suspected side, confidence, and evidence linked to raw frames. The GUI is for offline review and report export; it does not perform live diagnostics or ECU flashing.

## 功能 | Features

- 支持 ASC/BLF、Classical CAN、CAN FD 元数据及 ISO-TP SF/FF/CF/FC。
  Supports ASC/BLF, Classical CAN, CAN FD metadata, and ISO-TP SF/FF/CF/FC.
- 解析常用 UDS 服务、子服务、DID、RoutineID、下载地址/长度及 TransferData。
  Decodes common UDS services, subservices, DIDs, RoutineIDs, download address/length, and TransferData.
- 输出 Markdown/JSON 报告，并保留 TraceQuality、Finding 和 evidence chain。
  Exports Markdown/JSON reports with TraceQuality, findings, and evidence chains.
- 提供 Windows GUI、CLI 批处理、时间/方向/CF 筛选、中英文界面和深浅色主题。
  Provides a Windows GUI, CLI batch mode, time/direction/CF filters, bilingual UI, and light/dark themes.

## 快速使用 | Quick Start

### Windows 分发包 | Windows package

从 [Releases](https://github.com/Carson0323/udsflashreport/releases) 下载带版本后缀的单文件 `FlashReport-V1.0.2.exe`，直接运行即可，无需安装 Python、PySide6 或其他项目依赖。

Download the versioned single-file `FlashReport-V1.0.2.exe` from [Releases](https://github.com/Carson0323/udsflashreport/releases) and run it directly. Python, PySide6, and other project dependencies are not required.

### 源码运行 | Run from source

需要 Python 3.11：

Python 3.11 is required:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\flashreport-gui.exe
```

CLI 示例：

CLI example:

```powershell
.\.venv\Scripts\python.exe -m flashreport_core.cli analyze samples/success_full_download.asc --out report.md --out-json report.json
```

GUI 中打开 ASC/BLF 后点击 Analyze；分析完成后可查看 CAN 帧、发现、证据和刷写流程，并导出报告。

Open an ASC/BLF in the GUI and click Analyze. After analysis, review CAN frames, findings, evidence, and flash flow, then export a report.

## 当前版本 | Current Version

**V1.0.2**。详见 [更新记录](CHANGELOG.md)。

**V1.0.2**. See the [changelog](CHANGELOG.md) for details.

## 数据与责任 | Data and Responsibility

公开仓库仅包含源码、合成样例和脱敏数据。请勿上传内部日志、客户数据、密钥或厂商私有资料；私有测试资料应保存在本机或私有存储中。

The public repository contains source code, synthetic samples, and sanitized data only. Do not upload internal logs, customer data, keys, or proprietary vendor material; keep private test data local or in private storage.

本工具仅用于工程分析和测试。任何结果用于车辆、ECU、生产环境或安全相关流程前，必须由使用者独立验证。软件按现状提供，不提供准确性、适用性或安全性保证，使用者自行承担使用及其后果。本项目与 Vector、任何 OEM 或其他被提及的厂商没有隶属或合作关系。

This tool is intended for engineering analysis and testing only. Independently validate all results before using them with vehicles, ECUs, production systems, or safety-related workflows. The software is provided “as is”, without guarantees of accuracy, fitness, or safety; users are responsible for their use and consequences. This project is not affiliated with Vector, any OEM, or other referenced vendor.

## 许可证 | License

本项目代码采用 MIT License，详见 [LICENSE](LICENSE)。第三方依赖保留其各自许可证和义务，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

The code is licensed under the MIT License; see [LICENSE](LICENSE). Third-party dependencies retain their own licenses and obligations; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
