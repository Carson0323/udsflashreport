# 第三方声明 | Third-party notices

本文件记录随项目使用或分发的第三方组件及其许可证义务。
This file records third-party components used or distributed with the project and their license obligations.

M7 锁定版本清单 | M7 locked versions:

| Component / 组件 | Version / 版本 | License / 许可证 | License text / 许可证原文 |
| --- | --- | --- | --- |
| PySide6 / Qt | 6.11.2 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only OR Commercial | [Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html) |
| python-can | 4.6.1 | LGPL-3.0 | [LICENSE](https://github.com/hardbyte/python-can/blob/main/LICENSE.txt) |
| can-isotp | 2.0.7 | LGPL-3.0 | [LICENSE](https://github.com/pylessard/python-can-isotp/blob/master/LICENSE) |
| udsoncan | 1.26.1 | MIT | [LICENSE](https://github.com/pylessard/python-udsoncan/blob/master/LICENSE) |
| jsonschema | 4.26.0 | MIT | [LICENSE](https://github.com/python-jsonschema/jsonschema/blob/main/COPYING) |
| PyYAML | 6.0.3 | MIT | [LICENSE](https://github.com/yaml/pyyaml/blob/main/LICENSE) |
| PyInstaller (build only) | 6.22.2 | GPL-2.0 with bootloader exception | [LICENSE](https://github.com/pyinstaller/pyinstaller/blob/main/COPYING.txt) |

完整锁定清单（含传递依赖和测试工具）见 `packaging/requirements.lock`。
The complete lock, including transitive dependencies and test tools, is in `packaging/requirements.lock`.

Qt LGPL 履约说明 | Qt LGPL compliance:

- The distributed application must preserve Qt's applicable notices and license text.
  分发应用必须保留 Qt 适用的声明和许可证文本。
- Dynamic Qt libraries must remain replaceable by the user; do not statically link Qt for the release package.
  Qt 动态库必须保持可由使用者替换；发布包不得静态链接 Qt。
- The final release package must include the exact Qt/PySide6 component inventory and a review of LGPL obligations.
  最终发布包必须包含确切的 Qt/PySide6 组件清单，并完成 LGPL 义务复核。

M7 PyInstaller onedir contents / M7 PyInstaller onedir 内容：

- `FlashReport.exe` and the Python/Qt runtime DLLs required by the verified build.
  `FlashReport.exe` 及已验证构建所需的 Python/Qt 运行时 DLL。
- `flashreport_gui/assets/icons/*.svg` GUI assets.
  `flashreport_gui/assets/icons/*.svg` GUI 资源。
- No private corpus, proprietary seed/key algorithm, or internal trace file.
  不包含私有语料、厂商私有 seed/key 算法或内部报文记录。

项目代码的 MIT License 不会改变第三方组件各自的许可证义务。
The MIT License for project code does not change the license obligations of third-party components.
