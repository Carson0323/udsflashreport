# M6-C acceptance / M6-C 验收

## Scope / 范围

Complete the light visual system with centralized ThemeTokens, SVG toolbar
icons, spacing and responsive size constraints, and structural screenshot
artifacts for empty, loaded, finding, ambiguous, and error states.

通过集中式 ThemeTokens、SVG 工具栏图标、间距和响应式尺寸约束，以及 empty、
loaded、finding、ambiguous、error 五种状态的结构化截图产物，完成浅色视觉系统。

## Gate / Gate

```text
pytest tests/gui -q
pytest -q
```

Required local artifacts / 必需本地产物：

```text
artifacts/M6-ui-test-report.txt
artifacts/M6-ui-state.json
artifacts/ui/empty.png
artifacts/ui/loaded.png
artifacts/ui/finding.png
artifacts/ui/ambiguous.png
artifacts/ui/error.png
```

Screenshots are ignored by Git and must never contain private corpus data.
截图文件被 Git 忽略，且不得包含私有语料数据。
