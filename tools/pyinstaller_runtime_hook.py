"""Prepare bundled Qt DLL search paths before importing PySide6.

PyInstaller runtime hook / PyInstaller 运行时钩子。

The PySide6 extension modules are stored below ``_internal/PySide6`` in the
onedir package.  Windows does not always search that directory when loading
``QtCore.pyd``.  Registering it before the application imports PySide6 keeps
the packaged GUI independent of the machine's Qt installation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


_DLL_DIRECTORY_HANDLES: list[object] = []


def _register_directory(path: Path) -> None:
    if not path.is_dir():
        return
    if hasattr(os, "add_dll_directory"):
        _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(path)))
    os.environ["PATH"] = str(path) + os.pathsep + os.environ.get("PATH", "")


if getattr(sys, "frozen", False):
    executable_root = Path(sys.executable).resolve().parent
    bundle_roots = {
        Path(sys._MEIPASS) if getattr(sys, "_MEIPASS", None) else None,
        executable_root,
        executable_root / "_internal",
    }
    for bundle_root in (root for root in bundle_roots if root is not None):
        # Onefile and onedir layouts differ slightly between PyInstaller and
        # PySide6 hook versions. Register both the package root and its
        # conventional _internal/PySide6 locations before QtCore is imported.
        pyside_roots = {
            bundle_root / "PySide6",
            bundle_root / "_internal" / "PySide6",
        }
        for pyside_root in pyside_roots:
            _register_directory(bundle_root)
            _register_directory(bundle_root / "_internal")
            _register_directory(pyside_root)
            _register_directory(pyside_root.parent / "shiboken6")
            plugins = pyside_root / "plugins"
            _register_directory(plugins)
            if (pyside_root / "Qt6Core.dll").is_file() and plugins.is_dir():
                os.environ.setdefault("QT_PLUGIN_PATH", str(plugins))
                os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(plugins / "platforms"))
