# V1.0.1 开发与测试使用者专家评审

日期：2026-09-05。基线：`093cf38` / V1.0.0。评审方法：关键链路代码检查、现有测试、针对真实操作边界构造公开合成输入、先复现再修复、源码与分发产物验证。未使用或上传私有报文。

## 结论

基线 118 项测试通过，但没有覆盖响应错配、非对称 ALFID、修改配置后重分析、异常输入及安装包脱离源码运行等关键场景。以下问题已修复，V1.0.1 本地验证通过。结果依然受 v1 协议范围及输入完整性限制，不能把“未触发规则”解释为刷写成功证明。

## 发现与修复

| 优先级 | 问题与用户影响 | 修复及验证 |
| --- | --- | --- |
| P1 | 响应直接绑定最近请求，忽略 SID 与回显标识，可能给出错误事务、错误超时及刷写流程 | 按 SID、子功能、DID、BSC、RoutineID 筛选；错配保留歧义且不关闭请求；覆盖交错服务、错配 Pending/NRC、截断响应 |
| P1 | ALFID 高低半字节颠倒；地址宽度与长度宽度不同时，下载地址和大小错误 | 公共解析器按低半字节地址宽度、高半字节长度宽度读取；用 `34 00 12 AB CD 20` 验证地址 `0xABCD`、长度 `0x20`，同时检查流程与帧详情 |
| P1 | GUI 配置更新只修改变量，旧寻址会话和旧报告仍可用 | 保存配置后重新加载、清除结果并禁用导出；加载时显式配置保留到后续分析；防止并发加载/导出冲突 |
| P1 | 关闭自动识别或 29 位寻址后，动态配对仍会执行 | 回退路径受相同开关控制，分别覆盖两个开关 |
| P1 | 普通 wheel 未包含 findings.yaml/Schema，源码目录掩盖了安装后分析失败 | 构建时从唯一规范源复制资源，sdist 收录规范；隔离进程断言从 wheel 导入并运行全部公开样例 |
| P1 | 导出路径可以覆盖原始 Trace，或让 JSON 覆盖同路径 Markdown | 写入前比较规范化路径及同文件关系，错误时保持输入与目标不变 |
| P2 | candump FD flags 被当作数据，RTR 未识别，零长度数据被误判为远程帧 | 按 can-utils 格式解析 flags 与 `R{len}`，区分空数据帧；修正旧测试中的非标准 FD 样例 |
| P2 | 空/无法读取的日志呈现 NO FINDINGS，部分损坏记录没有传入完整性状态 | API 对零有效帧报错，CLI 返回 2；跳过记录计数传递至 known_incomplete，保留并提示输入警告 |
| P2 | 时间戳排序后才检测单调性，诊断恒真；非有限时间戳、越界 ID/DLC 可进入分析 | 排序前记录单调性，拒绝非有限时间戳及不一致帧，保留跳过记录计数 |
| P2 | 配置验证接受非法十六进制和布尔 channel，数组寻址模式触发 TypeError；损坏/空规则导致未捕获异常 | 提前进行类型、格式与范围验证；YAML 错误规范为 ValueError；缺少规则时返回 CLI 配置错误码 3 |
| P2 | 缺少自动化分发 Gate；README 保留已过期里程碑状态及不存在的 lock 文件说明 | 新增 Windows 测试与 wheel 验证 CI；更新安装、CLI 退出码和版本文档 |

ALFID 字段核对依据：[udsoncan 的 AddressAndLengthFormatIdentifier 实现](https://udsoncan.readthedocs.io/en/latest/_modules/udsoncan/common/AddressAndLengthFormatIdentifier.html)。candump 格式核对依据：[linux-can/can-utils cansend](https://github.com/linux-can/can-utils/blob/master/cansend.c)。

## 验证记录

- 基线：`python -m pytest -q`，118 passed。
- 首批新增用例修复前：21 failed，确认问题可复现。
- 修复后：`python -m pytest -q`，147 passed（含 Qt 异步、状态、证据导航、布局及性能测试）。
- `python -m pip wheel . --no-deps --no-build-isolation --wheel-dir dist/review-1.0.1`：构建成功。
- `python tools/check_distribution.py dist/review-1.0.1/udsflashreport-1.0.1-py3-none-any.whl`：隔离目录中 6 个公开 ASC 样例分析与 Markdown/JSON 导出通过；确认使用 wheel 内部规则资源。
- `python tools/build_m7.py --build-name v1.0.1 --output artifacts/V1.0.1-build-benchmark.json`：PyInstaller 构建与启动/分析自检 SUCCESS。
- 远端 CI 的执行结果以 GitHub Actions 为准，本地通过不代表远端已执行。

## 验证边界与后续工作

- 本轮没有对私有语料或实车执行分析，也没有在全新、完全未安装 Python 的 Windows 主机上复测。EXE 自检在本机执行。
- 保持 v1 范围：CAN FD 仅保留记录元信息；extended/mixed ISO-TP、完整 OEM 刷写状态机不在本轮扩展范围内。
- 时间窗完整性仍可能是 unknown；多请求交错仍降低可信度，无法仅凭 SID 完全消除重试事务歧义。
- 多文件导出不是文件系统级事务；某个输出目标的磁盘权限/容量错误可能导致部分报告已生成。原始 Trace 路径已保护。
- 后续可用脱敏大规模语料完善协议覆盖、峰值内存及人工桌面交互验收；本轮不将这些未完成项记为已验证。
