# Changelog

## V1.0.1 — 2026-09-05

面向开发/测试人员的正确性与交付可靠性修复版本。

- 核对 UDS 响应的 SID、子功能、DID、BSC、RoutineID；错配响应不会关闭请求或污染 Pending 链。交错请求仍保留歧义提示。
- 修正 RequestDownload ALFID 的地址/长度宽度解析，流程摘要与证据详情共用解析函数。
- GUI 保存配置后重新加载日志并清除旧结果；显式加载配置用于后续分析；忙碌期间阻止冲突操作。
- 自动 29 位寻址回退遵守配置开关。
- 正确读取 candump CAN FD flags、远程帧与零长度数据帧；校验时间戳、CAN ID 和数据长度。
- 空日志返回读取错误；跳过损坏记录时标记输入已知不完整；CLI 显示输入警告及未识别诊断会话提示。
- 拒绝无效配置地址、非标量寻址模式和残缺规则注册表；损坏 YAML 返回配置错误码。
- 报告输出禁止覆盖原始 Trace，Markdown/JSON 不能使用同一个目标文件。
- wheel/sdist 携带规则及 Schema 资源；新增脱离源码的分发验证工具、Windows CI 与 29 项回归测试。

本地验证：147 项测试通过；wheel 对 6 个公开合成样例完成分析、Schema 校验及双格式导出；PyInstaller onedir 构建、分析自检与 GUI 启动通过。详细发现与验证边界见 [专家评审记录](docs/review-v1.0.1.md)。

## V1.0.0

首个正式版本：离线 ASC/BLF 分析、ISO-TP/UDS 故障归因、Qt GUI、双语报告及 Windows onedir 分发。
