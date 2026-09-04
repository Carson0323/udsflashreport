# M6-B acceptance / M6-B 验收

## Scope / 范围

Connect Open, Analyze, and Export to QThreadPool workers; implement the frozen
load/analyze/export signals, error states, frame/detail projection, one-button
per-evidence navigation, WindowEvidence interval display, and a configuration
dialog backed only by `flashreport_core.api` and `flashreport_core.models`.

将 Open、Analyze、Export 接入 QThreadPool worker；实现冻结的加载/分析/导出信号、
错误状态、帧/详情投影、每条 evidence 独立导航、WindowEvidence 区间展示，以及
只通过 `flashreport_core.api` 和 `flashreport_core.models` 的配置对话框。

## Gate / Gate

```text
pytest tests/gui/test_evidence_navigation.py tests/gui/test_async_analysis.py tests/gui/test_ui_state_machine.py tests/gui/test_error_states.py tests/gui/test_config_dialog.py -q
pytest tests/gui -q
pytest -q
```

All parse, analyze, export, and report disk operations are performed outside
the GUI thread. UI mutation occurs only after queued completion signals.

所有解析、分析、导出及报告落盘操作均不在 GUI 主线程执行；界面只在完成信号
到达后更新。
