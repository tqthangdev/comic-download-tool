"""
gui/version_dialog.py

The [Version] modal: shows the running version, asks GitHub whether a newer
release exists and — when one does — downloads and prepares it.

The dialog only talks to `core.updater`; it never touches the GitHub API or the
ZIP handling itself.
"""

from __future__ import annotations

import threading

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
)

from core.i18n import tr
from core.logger import logger
from core.updater.checker import UpdateError, check_for_update
from core.updater.installer import InstallError, prepare_update, spawn_updater
from gui.cursor_utils import apply_pointer_cursors


class VersionDialog(QDialog):
    # Bridged from the worker threads back onto the GUI thread.
    checked = pyqtSignal(object)      # UpdateInfo | Exception
    progressed = pyqtSignal(int, int)  # bytes done, bytes total
    staged = pyqtSignal(object)       # Path | Exception

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("version_title"))
        self.setMinimumWidth(460)

        self._info = None
        self._busy = False

        layout = QVBoxLayout(self)

        self.status_label = QLabel(tr("version_checking"))
        self.status_label.setWordWrap(True)

        self.notes_title = QLabel(tr("version_whats_new"))
        self.notes = QTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setFixedHeight(150)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)

        self.buttons = QDialogButtonBox()
        self.btn_update = self.buttons.addButton(
            tr("update"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.btn_later = self.buttons.addButton(
            tr("later"), QDialogButtonBox.ButtonRole.RejectRole
        )
        self.btn_update.setEnabled(False)

        layout.addWidget(self.status_label)
        layout.addWidget(self.notes_title)
        layout.addWidget(self.notes)
        layout.addWidget(self.progress)
        layout.addWidget(self.buttons)

        self._show_update_parts(False)

        self.btn_update.clicked.connect(self._start_update)
        self.btn_later.clicked.connect(self.reject)
        self.checked.connect(self._on_checked)
        self.progressed.connect(self._on_progress)
        self.staged.connect(self._on_staged)

        apply_pointer_cursors(self)

        threading.Thread(target=self._check, daemon=True).start()

    # ---- checking -------------------------------------------------------- #

    def _check(self):
        try:
            info = check_for_update()
        except (UpdateError, Exception) as e:  # noqa: B014 - report anything
            self.checked.emit(e)
            return
        self.checked.emit(info)

    def _on_checked(self, value):
        if isinstance(value, Exception):
            logger.error(f"[updater] version check failed: {value}")
            self.status_label.setText(tr("version_check_failed").format(error=str(value)))
            return

        self._info = value

        if not value.available:
            self.status_label.setText(
                tr("version_latest").format(version=value.latest or value.current)
                + "\n"
                + tr("version_up_to_date")
            )
            self._show_update_parts(False)
            return

        lines = [
            tr("version_available"),
            tr("version_current").format(version=f"v{value.current}"),
            tr("version_latest").format(version=value.latest),
        ]
        has_package = value.asset_for_platform() is not None
        if not has_package:
            lines.append(tr("update_no_package"))
        self.status_label.setText("\n".join(lines))

        self.notes.setPlainText((value.notes or "").strip())
        self._show_update_parts(True)
        self.btn_update.setEnabled(has_package)

    def _show_update_parts(self, visible: bool):
        self.notes_title.setVisible(visible)
        self.notes.setVisible(visible)

    # ---- updating -------------------------------------------------------- #

    def _start_update(self):
        if self._busy or self._info is None:
            return

        self._busy = True
        self.btn_update.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.status_label.setText(
            tr("update_downloading_unknown").format(version=self._info.latest)
        )

        info = self._info
        threading.Thread(target=self._prepare, args=(info,), daemon=True).start()

    def _prepare(self, info):
        try:
            app_root = prepare_update(
                info, progress=lambda done, total: self.progressed.emit(done, total)
            )
        except (InstallError, Exception) as e:  # noqa: B014 - report anything
            self.staged.emit(e)
            return
        self.staged.emit(app_root)

    def _on_progress(self, done: int, total: int):
        if not total:
            self.progress.setRange(0, 0)  # unknown length: busy indicator
            return
        percent = int(done * 100 / total)
        self.progress.setValue(percent)
        self.status_label.setText(
            tr("update_downloading").format(
                version=self._info.latest if self._info else "", percent=percent
            )
        )

    def _on_staged(self, value):
        if isinstance(value, Exception):
            logger.error(f"[updater] update failed: {value}")
            self.status_label.setText(tr("update_failed").format(error=str(value)))
            self.progress.setVisible(False)
            self._busy = False
            self.btn_update.setEnabled(True)
            return

        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status_label.setText(tr("update_ready"))

        try:
            spawn_updater(value, self._info.latest)
        except Exception as e:
            logger.error(f"[updater] cannot start the updater process: {e}")
            self.status_label.setText(tr("update_failed").format(error=str(e)))
            self._busy = False
            return

        # The updater waits for this process to exit before touching anything,
        # so hand over to the normal shutdown path.
        self.accept()
        window = self.window()
        if window is not None:
            window.close()
