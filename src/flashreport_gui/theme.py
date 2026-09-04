"""Light Fusion theme tokens / 浅色 Fusion 主题令牌。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class ThemeTokens:
    background: str
    panel: str
    border: str
    text_primary: str
    text_secondary: str
    selection: str
    severity_high: str
    severity_medium: str
    severity_low: str
    icon_neutral: str


LIGHT_TOKENS = ThemeTokens(
    background="#F5F7FA",
    panel="#FFFFFF",
    border="#D7DCE2",
    text_primary="#1F2933",
    text_secondary="#5B6773",
    selection="#DCEBFA",
    severity_high="#B42318",
    severity_medium="#B54708",
    severity_low="#1D4ED8",
    icon_neutral="#5B6773",
)


def icon_for(name: str, tokens: ThemeTokens = LIGHT_TOKENS, size: int = 20) -> QIcon:
    """Render an SVG asset using the active theme token / 使用主题令牌渲染 SVG。"""

    asset = Path(__file__).resolve().parent / "assets" / "icons" / f"{name}.svg"
    svg = asset.read_text(encoding="utf-8").replace("currentColor", tokens.icon_neutral)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def build_stylesheet(tokens: ThemeTokens = LIGHT_TOKENS) -> str:
    """Build QSS from theme tokens, keeping business colors centralized."""

    return f"""
    QWidget {{
        background: {tokens.background};
        color: {tokens.text_primary};
        font-size: 10pt;
    }}
    QMainWindow, QToolBar, QTabWidget::pane, QScrollArea, QTreeView, QTableView {{
        background: {tokens.panel};
    }}
    QToolBar {{
        border-bottom: 1px solid {tokens.border};
        spacing: 6px;
        padding: 5px 8px;
        min-height: 34px;
        max-height: 44px;
    }}
    QToolBar QPushButton, QPushButton {{
        min-height: 28px;
        padding: 4px 10px;
        border: 1px solid {tokens.border};
        border-radius: 4px;
        background: {tokens.panel};
    }}
    QToolBar QPushButton:hover, QPushButton:hover {{ background: {tokens.selection}; }}
    QPushButton:disabled {{ color: {tokens.text_secondary}; background: {tokens.background}; }}
    QLabel#brandLabel {{ font-size: 12pt; font-weight: 600; padding: 0 8px 0 2px; }}
    QLabel#brandIcon {{ padding: 0 2px 0 0; }}
    QLabel#panelHeading {{
        color: {tokens.text_secondary};
        font-size: 9pt;
        font-weight: 600;
        letter-spacing: 0.3px;
        padding: 5px 7px 2px 7px;
    }}
    QTreeView, QTableView, QTabWidget::pane {{ border: 1px solid {tokens.border}; }}
    QTreeView, QTableView {{ alternate-background-color: {tokens.background}; gridline-color: {tokens.border}; }}
    QTableView::item {{ padding: 3px 5px; min-height: 24px; }}
    QTreeView::item {{ padding: 4px 3px; }}
    QHeaderView::section {{
        background: {tokens.background};
        color: {tokens.text_secondary};
        padding: 5px;
        border: 0;
        border-bottom: 1px solid {tokens.border};
    }}
    QTreeView::item:selected, QTableView::item:selected {{ background: {tokens.selection}; color: {tokens.text_primary}; }}
    QSplitter::handle {{ background: {tokens.border}; }}
    QSplitter::handle:horizontal {{ width: 4px; }}
    QSplitter::handle:vertical {{ height: 4px; }}
    QTabBar::tab {{ padding: 7px 12px; color: {tokens.text_secondary}; }}
    QTabBar::tab:selected {{ color: {tokens.text_primary}; border-bottom: 2px solid {tokens.selection}; }}
    QScrollArea {{ border: 1px solid {tokens.border}; }}
    QStatusBar {{ border-top: 1px solid {tokens.border}; }}
    QLabel#emptyState, QLabel#emptyCenterState {{ color: {tokens.text_secondary}; padding: 18px; }}
    QLabel#errorMessage {{ color: {tokens.severity_high}; padding: 18px; }}
    QLabel#ambiguousBadge {{
        color: {tokens.severity_medium};
        background: {tokens.panel};
        border: 1px solid {tokens.severity_medium};
        border-radius: 4px;
        padding: 6px 8px;
        font-weight: 600;
    }}
    QFrame[severity] {{
        background: {tokens.panel};
        border: 1px solid {tokens.border};
        border-radius: 5px;
        padding: 8px;
    }}
    QFrame[severity="high"] {{ border-left: 4px solid {tokens.severity_high}; }}
    QFrame[severity="medium"] {{ border-left: 4px solid {tokens.severity_medium}; }}
    QFrame[severity="low"] {{ border-left: 4px solid {tokens.severity_low}; }}
    QLabel#secondaryText {{ color: {tokens.text_secondary}; }}
    QLabel#statusState[state="ERROR"] {{ color: {tokens.severity_high}; }}
    QLabel#statusState[state="RESULT"] {{ color: {tokens.severity_low}; }}
    """


def apply_theme(app: QApplication, tokens: ThemeTokens = LIGHT_TOKENS) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet(tokens))
