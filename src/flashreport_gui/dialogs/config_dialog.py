"""Public-API-backed configuration dialog / 通过 public API 的配置对话框。"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

import flashreport_core.api as api
from flashreport_core.models import AppConfig


def load_persisted_config(settings: QSettings) -> AppConfig:
    """Read the isolated QSettings config through the public API."""

    stored = settings.value("config/data", "")
    if not stored:
        return api.default_config()
    try:
        if isinstance(stored, bytes):
            stored = stored.decode("utf-8")
        return api.config_from_dict(json.loads(str(stored)))
    except (TypeError, ValueError, json.JSONDecodeError):
        return api.default_config()


class ConfigDialog(QDialog):
    """Edit the supported AppConfig projection without importing core internals."""

    configSaved = Signal(object)  # noqa: N815

    def __init__(
        self,
        config: AppConfig | None = None,
        settings: QSettings | None = None,
        parent: QDialog | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("configDialog")
        self.setWindowTitle("Settings / 设置")
        self.setModal(True)
        self._settings = settings or QSettings()
        self._config = config if config is not None else self._load_stored_config()
        self._config_path: str | None = None
        self._build_form()
        self._load_form(self._config)

    def _load_stored_config(self) -> AppConfig:
        return load_persisted_config(self._settings)

    def _persist_config(self, config: AppConfig) -> None:
        self._settings.setValue(
            "config/data",
            json.dumps(api.config_to_dict(config), ensure_ascii=False, sort_keys=True),
        )

    def _build_form(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.testerSaEdit = QLineEdit(self)
        self.testerSaEdit.setObjectName("testerSaEdit")
        form.addRow("Tester SA / Tester 地址", self.testerSaEdit)

        self.autoDetectCheck = QCheckBox("Auto detect / 自动检测", self)
        self.autoDetectCheck.setObjectName("autoDetectCheck")
        form.addRow("Addressing / 地址", self.autoDetectCheck)
        self.enable11BitCheck = QCheckBox("Enable 11-bit heuristic / 启用 11 位启发式", self)
        self.enable11BitCheck.setObjectName("enable11BitCheck")
        form.addRow("", self.enable11BitCheck)
        self.enable29BitCheck = QCheckBox("Enable 29-bit normal fixed / 启用 29 位标准地址", self)
        self.enable29BitCheck.setObjectName("enable29BitCheck")
        form.addRow("", self.enable29BitCheck)

        self.addressingModeCombo = QComboBox(self)
        self.addressingModeCombo.setObjectName("addressingModeCombo")
        self.addressingModeCombo.addItems(["auto", "normal", "extended", "mixed"])
        form.addRow("ISO-TP mode / ISO-TP 模式", self.addressingModeCombo)

        self.timeoutEdits: dict[str, QSpinBox] = {}
        for key, label in (
            ("isotp_fc_ms", "ISO-TP FC timeout (ms) / FC 超时"),
            ("isotp_cf_ms", "ISO-TP CF timeout (ms) / CF 超时"),
            ("uds_p2_ms", "UDS P2 timeout (ms) / P2 超时"),
            ("uds_p2_star_ms", "UDS P2* timeout (ms) / P2* 超时"),
        ):
            spin = QSpinBox(self)
            spin.setObjectName(key)
            spin.setRange(0, 2_147_483_647)
            self.timeoutEdits[key] = spin
            form.addRow(label, spin)

        layout.addLayout(form)
        self.errorLabel = QTextEdit(self)
        self.errorLabel.setObjectName("configErrorLabel")
        self.errorLabel.setReadOnly(True)
        self.errorLabel.setVisible(False)
        self.errorLabel.setMaximumHeight(90)
        layout.addWidget(self.errorLabel)

        file_buttons = QDialogButtonBox(self)
        self.loadButton = QPushButton("Load JSON / 加载 JSON", self)
        self.loadButton.setObjectName("loadConfigButton")
        self.saveAsButton = QPushButton("Save JSON / 保存 JSON", self)
        self.saveAsButton.setObjectName("saveConfigButton")
        file_buttons.addButton(self.loadButton, QDialogButtonBox.ButtonRole.ActionRole)
        file_buttons.addButton(self.saveAsButton, QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(file_buttons)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self)
        self.saveButton = buttons.button(QDialogButtonBox.StandardButton.Save)
        self.saveButton.setObjectName("saveButton")
        self.cancelButton = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self.cancelButton.setObjectName("cancelButton")
        layout.addWidget(buttons)

        self.testerSaEdit.textChanged.connect(self.validate_form)
        self.autoDetectCheck.stateChanged.connect(self.validate_form)
        self.enable11BitCheck.stateChanged.connect(self.validate_form)
        self.enable29BitCheck.stateChanged.connect(self.validate_form)
        self.addressingModeCombo.currentTextChanged.connect(self.validate_form)
        for spin in self.timeoutEdits.values():
            spin.valueChanged.connect(self.validate_form)
        buttons.accepted.connect(self._accept_validated)
        buttons.rejected.connect(self.reject)
        self.loadButton.clicked.connect(self._load_from_file_dialog)
        self.saveAsButton.clicked.connect(self._save_to_file_dialog)

    def _load_form(self, config: AppConfig) -> None:
        data = api.config_to_dict(config)
        addressing = data["addressing"]
        self.testerSaEdit.setText(addressing["tester_sa"])
        self.autoDetectCheck.setChecked(addressing["auto_detect"])
        self.enable11BitCheck.setChecked(addressing["enable_11bit_heuristic"])
        self.enable29BitCheck.setChecked(addressing["enable_29bit_normal_fixed"])
        self.addressingModeCombo.setCurrentText(data["isotp"]["addressing_mode"])
        for key, spin in self.timeoutEdits.items():
            spin.setValue(data["timeouts"][key])
        self.validate_form()

    def _data_from_form(self) -> dict:
        data = api.config_to_dict(self._config)
        data["addressing"].update(
            {
                "tester_sa": self.testerSaEdit.text(),
                "auto_detect": self.autoDetectCheck.isChecked(),
                "enable_11bit_heuristic": self.enable11BitCheck.isChecked(),
                "enable_29bit_normal_fixed": self.enable29BitCheck.isChecked(),
            }
        )
        data["isotp"]["addressing_mode"] = self.addressingModeCombo.currentText()
        data["timeouts"].update({key: spin.value() for key, spin in self.timeoutEdits.items()})
        return data

    def validate_form(self) -> bool:
        validation = api.validate_config(self._data_from_form())
        self.saveButton.setEnabled(validation.ok)
        if validation.ok:
            self.errorLabel.clear()
            self.errorLabel.setVisible(False)
        else:
            self.errorLabel.setPlainText("\n".join(validation.errors))
            self.errorLabel.setVisible(True)
        return validation.ok

    def set_config_data(self, data: dict) -> bool:
        """Load a candidate dictionary through public API validation."""

        validation = api.validate_config(data)
        self.saveButton.setEnabled(validation.ok)
        if not validation.ok:
            self.errorLabel.setPlainText("\n".join(validation.errors))
            self.errorLabel.setVisible(True)
            return False
        self._config = api.config_from_dict(data)
        self._load_form(self._config)
        return True

    def current_config(self) -> AppConfig:
        return api.config_from_dict(self._data_from_form())

    def save_config(self, path: str) -> bool:
        if not self.validate_form():
            return False
        config = self.current_config()
        api.save_config(config, path)
        self._config = config
        self._config_path = str(path)
        self._persist_config(config)
        self._settings.setValue("ui/last_open_dir", str(Path(path).parent))
        return True

    def load_config(self, path: str) -> bool:
        try:
            config = api.load_config(path)
        except (OSError, ValueError) as exc:
            self.errorLabel.setPlainText(f"{type(exc).__name__}: {exc}")
            self.errorLabel.setVisible(True)
            self.saveButton.setEnabled(False)
            return False
        self._config = config
        self._config_path = str(path)
        self._persist_config(config)
        self._load_form(config)
        self._settings.setValue("ui/last_open_dir", str(Path(path).parent))
        return True

    def _accept_validated(self) -> None:
        if not self.validate_form():
            return
        self._config = self.current_config()
        self._persist_config(self._config)
        self.configSaved.emit(self._config)
        self.accept()

    def _load_from_file_dialog(self) -> None:
        start = self._settings.value("ui/last_open_dir", "")
        path, _ = QFileDialog.getOpenFileName(self, "Load configuration / 加载配置", str(start), "JSON (*.json)")
        if path:
            self.load_config(path)

    def _save_to_file_dialog(self) -> None:
        if not self.validate_form():
            return
        start = self._settings.value("ui/last_open_dir", "flashreport-config.json")
        path, _ = QFileDialog.getSaveFileName(self, "Save configuration / 保存配置", str(start), "JSON (*.json)")
        if path:
            try:
                self.save_config(path)
            except OSError as exc:
                QMessageBox.critical(self, "Save failed / 保存失败", str(exc))
