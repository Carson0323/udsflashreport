"""Light Fusion theme tokens / 浅色 Fusion 主题令牌。"""

from __future__ import annotations

from dataclasses import dataclass

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
)


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
        padding: 4px;
    }}
    QPushButton {{
        padding: 5px 10px;
        border: 1px solid {tokens.border};
        border-radius: 4px;
        background: {tokens.panel};
    }}
    QPushButton:hover {{ background: {tokens.selection}; }}
    QPushButton:disabled {{ color: {tokens.text_secondary}; }}
    QTreeView, QTableView, QTabWidget::pane {{ border: 1px solid {tokens.border}; }}
    QHeaderView::section {{
        background: {tokens.background};
        color: {tokens.text_secondary};
        padding: 5px;
        border: 0;
        border-bottom: 1px solid {tokens.border};
    }}
    QTreeView::item:selected, QTableView::item:selected {{ background: {tokens.selection}; color: {tokens.text_primary}; }}
    QStatusBar {{ border-top: 1px solid {tokens.border}; }}
    QLabel#emptyState {{ color: {tokens.text_secondary}; padding: 18px; }}
    QFrame#findingCard {{
        background: {tokens.panel};
        border: 1px solid {tokens.border};
        border-radius: 5px;
        padding: 8px;
    }}
    QFrame#findingCard[severity="high"] {{ border-left: 4px solid {tokens.severity_high}; }}
    QFrame#findingCard[severity="medium"] {{ border-left: 4px solid {tokens.severity_medium}; }}
    QFrame#findingCard[severity="low"] {{ border-left: 4px solid {tokens.severity_low}; }}
    QLabel#secondaryText {{ color: {tokens.text_secondary}; }}
    """


def apply_theme(app: QApplication, tokens: ThemeTokens = LIGHT_TOKENS) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet(tokens))
