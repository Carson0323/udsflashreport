from __future__ import annotations

from PySide6.QtCore import QSettings, Qt

from flashreport_gui.main_window import MainWindow
from flashreport_gui.theme import DARK_TOKENS, LIGHT_TOKENS, build_stylesheet, icon_for


def test_theme_tokens_and_svg_icons_are_available(qtbot) -> None:
    stylesheet = build_stylesheet()
    assert LIGHT_TOKENS.background in stylesheet
    assert LIGHT_TOKENS.severity_high in stylesheet
    assert DARK_TOKENS.text_primary not in stylesheet
    for name in ("flashreport", "open", "analyze", "export", "settings"):
        assert not icon_for(name).isNull()


def test_window_constraints_hold_at_review_sizes(qtbot, tmp_path) -> None:
    window = MainWindow(QSettings(str(tmp_path / "visual.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    assert window.minimumSize().width() >= 1100
    assert window.findingList.minimumWidth() >= 260
    assert window.findingList.maximumWidth() <= 380
    assert window.detailTabs.minimumHeight() >= 180
    assert window.detailTabs.maximumHeight() <= 350
    for width, height in ((1920, 1080), (1366, 768)):
        window.resize(width, height)
        qtbot.wait(10)
        assert window.width() == width
        assert window.height() == height


def test_theme_can_switch_between_light_and_dark(qtbot, tmp_path) -> None:
    window = MainWindow(QSettings(str(tmp_path / "theme.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    assert window.themeButton.text() == "Dark / 深色"
    qtbot.mouseClick(window.themeButton, Qt.MouseButton.LeftButton)
    assert window.themeButton.text() == "Light / 浅色"
    assert window._dark_mode is True
