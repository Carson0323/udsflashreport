# M6-A acceptance / M6-A 验收

## Scope / 范围

Implement the PySide6 Qt Widgets shell, frozen object names, light Fusion
theme, and Model/View projections for conversations, raw frames, and findings.
The GUI may display API/model objects but must not reimplement protocol
inference or import core implementation modules.

实现 PySide6 Qt Widgets 界面外壳、冻结对象名、浅色 Fusion 主题，以及会话、
原始帧和 findings 的 Model/View 投影。GUI 可以展示 API/model 对象，但不得
重新实现协议推导，也不得导入 core 内部实现模块。

## Gate / Gate

```text
pytest tests/gui/test_main_window.py tests/gui/test_frame_model.py tests/gui/test_conversation_tree.py -q
pytest -q
```

The M6-A shell starts in `EMPTY`, keeps Analyze/Export disabled until data is
available, and exposes bilingual labels and the required object names.

M6-A 外壳初始状态为 `EMPTY`，数据可用前禁用 Analyze/Export，并提供双语标签
和规定的对象名。
