from __future__ import annotations

from PySide6.QtCore import QSettings

from flashreport_core.api import default_config
from flashreport_gui.dialogs import ConfigDialog


def test_config_dialog_uses_public_api_and_rejects_invalid_data(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "config.ini"), QSettings.Format.IniFormat)
    dialog = ConfigDialog(default_config(), settings)
    qtbot.addWidget(dialog)

    assert dialog.saveButton.isEnabled()
    invalid = {"schema_version": "invalid"}
    assert dialog.set_config_data(invalid) is False
    assert not dialog.saveButton.isEnabled()
    assert not dialog.errorLabel.isHidden()

    config_path = tmp_path / "config.json"
    dialog._load_form(default_config())
    dialog.testerSaEdit.setText("E0")
    assert dialog.save_config(str(config_path)) is True
    assert config_path.is_file()


def test_config_dialog_round_trips_values_through_public_api(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "config.ini"), QSettings.Format.IniFormat)
    dialog = ConfigDialog(default_config(), settings)
    qtbot.addWidget(dialog)
    dialog.testerSaEdit.setText("01")
    dialog.timeoutEdits["uds_p2_ms"].setValue(75)
    candidate = dialog.current_config()

    path = tmp_path / "roundtrip.json"
    assert dialog.save_config(str(path))
    second = ConfigDialog(default_config(), settings)
    qtbot.addWidget(second)
    assert second.load_config(str(path))
    assert second.current_config().addressing.tester_sa == "01"
    assert second.current_config().timeouts.uds_p2_ms == 75


def test_config_dialog_persists_values_in_isolated_qsettings(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "persist.ini"), QSettings.Format.IniFormat)
    dialog = ConfigDialog(settings=settings)
    qtbot.addWidget(dialog)
    dialog.testerSaEdit.setText("E0")
    dialog.saveButton.click()
    settings.sync()

    reopened = ConfigDialog(settings=settings)
    qtbot.addWidget(reopened)
    assert reopened.testerSaEdit.text() == "E0"
