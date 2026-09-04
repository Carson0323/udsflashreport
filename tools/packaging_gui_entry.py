"""Import-safe GUI entry point for PyInstaller / PyInstaller 可安全导入入口。"""

from flashreport_gui.app import main


if __name__ == "__main__":
    raise SystemExit(main())
