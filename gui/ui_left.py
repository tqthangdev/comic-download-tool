from pathlib import Path

from PyQt6.QtGui import QMovie, QIntValidator
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QLabel,
    QTreeWidget,
    QHeaderView,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
    QSpinBox,
    QToolButton,
    QRadioButton,
    QButtonGroup,
    QStackedWidget,
    QFrame,
    QComboBox,
)
from PyQt6.QtCore import Qt, QSize, QSettings

from core.utils import get_resource_path, CONFIG, save_config
from core.i18n import tr, set_lang, get_lang
from gui.cursor_utils import apply_pointer_cursors
from gui.theme import (
    RADIO_STYLE,
    CHECKBOX_STYLE,
    MANGA_TITLE_STYLE,
    HELP_TITLE_STYLE,
    TREE_STYLE,
    CHAPTER_PANEL_STYLE,
    CONFIG_DIALOG_STYLE,
    HELP_BUTTON_STYLE,
    COMPACT_INPUT_STYLE,
)

def make_radio_button(text: str) -> QRadioButton:
    """Create a QRadioButton with the app's custom indicator icons
    (checked/unchecked SVGs) applied, so every radio button in the app
    looks consistent without repeating the same stylesheet everywhere.
    """
    btn = QRadioButton(text)
    btn.setStyleSheet(RADIO_STYLE)
    return btn


def make_checkbox(text: str) -> QCheckBox:
    """Create a QCheckBox with the app's custom indicator icons
    (checked/unchecked SVGs) applied, so every checkbox in the app
    looks consistent without repeating the same stylesheet everywhere.
    """
    cb = QCheckBox(text)
    cb.setStyleSheet(CHECKBOX_STYLE)
    return cb

class LeftPanel(QWidget):
    """
    Left side of the main window:
    - Mode selector (manual / auto) + input row (URL/paste or file/choose)
    - Save path input + folder picker
    - "Use this path by default" checkbox
    - Add Queue button
    - Chapter header (loading spinner, thumbnail, title)
    - Chapter tree
    """

    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)

        self.settings = settings
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ================= MODE AREA (top, aligned with Queue label) =================
        self.mode_area = QWidget()

        mode_layout = QHBoxLayout(self.mode_area)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(6)

        mode_label = QLabel(tr("mode"))
        self.rb_manual = make_radio_button(tr("mode_manual"))
        self.rb_auto = make_radio_button(tr("mode_auto"))

        # Default: manual (paste URL) — the historical behavior
        self.rb_manual.setChecked(True)

        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.rb_manual)
        mode_layout.addWidget(self.rb_auto)
        mode_layout.addStretch()

        self.rb_manual.toggled.connect(self._on_mode_changed)
        self.rb_auto.toggled.connect(self._on_mode_changed)

        # ================= INPUT STACK (manual page / auto page) =================
        self.input_stack = QStackedWidget()
        self.input_stack.setFrameShape(QFrame.Shape.NoFrame)
        self.input_stack.setContentsMargins(0, 0, 0, 0)

        # --- manual page ---
        manual_page = QWidget()
        manual_layout = QHBoxLayout(manual_page)
        manual_layout.setContentsMargins(0, 0, 0, 0)
        manual_layout.setSpacing(6)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(tr("url_placeholder"))
        self.url_input.setReadOnly(True)
        self.url_input.setFixedHeight(29)

        self.btn_paste = QPushButton(tr("paste"))
        self.btn_paste.setFixedWidth(80)

        manual_layout.addWidget(self.url_input, 1)
        manual_layout.addWidget(self.btn_paste)

        # --- auto page ---
        auto_page = QWidget()
        auto_layout = QHBoxLayout(auto_page)
        auto_layout.setContentsMargins(0, 0, 0, 0)
        auto_layout.setSpacing(6)

        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText(tr("file_placeholder"))
        self.file_input.setReadOnly(True)
        self.file_input.setFixedHeight(29)

        # Clicking the readonly textbox is the same as the button
        self.file_input.mousePressEvent = self._pick_file_for_event

        self.btn_pick_file = QPushButton(tr("file_pick"))
        self.btn_pick_file.setFixedWidth(80)

        auto_layout.addWidget(self.file_input, 1)
        auto_layout.addWidget(self.btn_pick_file)

        self.input_stack.addWidget(manual_page)  # index 0 = manual
        self.input_stack.addWidget(auto_page)    # index 1 = auto

        # ================= CHECKBOX + SETTINGS =================
        settings_row = QWidget()
        settings_layout = QHBoxLayout(settings_row)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(6)

        checkbox_col = QVBoxLayout()
        checkbox_col.setContentsMargins(0, 0, 0, 0)
        checkbox_col.setSpacing(6)

        self.shutdown_cb = make_checkbox(tr("shutdown_after_done"))
        shutdown_saved = self.settings.value("shutdown_after_done", False, type=bool)
        self.shutdown_cb.setChecked(shutdown_saved)
        self.shutdown_cb.toggled.connect(self.on_shutdown_toggled)

        # Text box next to the checkbox: countdown (seconds) before shutdown.
        saved_delay = self.settings.value("shutdown_delay", 60, type=int)
        self.shutdown_delay = QLineEdit()
        self.shutdown_delay.setValidator(QIntValidator(1, 3600, self))
        self.shutdown_delay.setText(str(saved_delay if isinstance(saved_delay, int) else 60))
        self.shutdown_delay.setFixedSize(38, 22)
        self.shutdown_delay.setStyleSheet(COMPACT_INPUT_STYLE)
        self.shutdown_delay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.shutdown_delay.setToolTip(tr("shutdown_delay_hint"))
        self.shutdown_delay.editingFinished.connect(self._save_shutdown_delay)
        self.shutdown_delay.setEnabled(self.shutdown_cb.isChecked())

        self.shutdown_delay_unit = QLabel(tr("shutdown_seconds"))
        self.shutdown_delay_unit.setToolTip(tr("shutdown_delay_hint"))

        shutdown_row = QWidget()
        shutdown_row_layout = QHBoxLayout(shutdown_row)
        shutdown_row_layout.setContentsMargins(0, 0, 0, 0)
        shutdown_row_layout.setSpacing(6)
        shutdown_row_layout.addWidget(self.shutdown_cb)
        shutdown_row_layout.addWidget(self.shutdown_delay)
        shutdown_row_layout.addWidget(self.shutdown_delay_unit)
        shutdown_row_layout.addStretch()

        self.auto_queue_cb = make_checkbox(tr("auto_queue"))
        auto_queue_saved = self.settings.value("auto_queue", False, type=bool)
        self.auto_queue_cb.setChecked(auto_queue_saved)
        self.auto_queue_cb.toggled.connect(self.on_auto_queue_toggled)

        checkbox_col.addWidget(shutdown_row, 0, Qt.AlignmentFlag.AlignLeft)
        checkbox_col.addWidget(self.auto_queue_cb, 0, Qt.AlignmentFlag.AlignLeft)

        self.btn_settings = QPushButton(tr("settings"))
        self.btn_settings.setFixedWidth(80)
        self.btn_settings.clicked.connect(self.open_settings)

        settings_layout.addLayout(checkbox_col, 1)
        settings_layout.addWidget(self.btn_settings)
        settings_layout.setAlignment(self.btn_settings, Qt.AlignmentFlag.AlignTop)

        # ================= PATH AREA =================
        path_area = QWidget()
        path_layout = QHBoxLayout(path_area)

        self.btn_folder = QPushButton(tr("folder"))
        self.btn_folder.setFixedWidth(80)

        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(6)

        self.path_input = QLineEdit()
        default_path = str(Path.home() / "Documents")
        saved_path = self.settings.value("save_path", "", type=str)

        # The saved path may come from another machine (e.g. Windows E:\...) or a
        # disconnected drive -> fall back to the default folder.
        if not saved_path or not Path(saved_path).is_absolute() or not Path(saved_path).exists():
            saved_path = default_path

        self.path_input.setPlaceholderText(tr("path_placeholder"))
        self.path_input.setText(saved_path)
        # The path is always editable; each change (pick folder / typing) is saved
        self.path_input.editingFinished.connect(self._save_path)

        path_layout.addWidget(self.path_input, 1)
        path_layout.addWidget(self.btn_folder)

        # ================= TREE =================
        self.tree = QTreeWidget()
        self.tree.setObjectName("detail_tree")
        self.tree.setStyleSheet(TREE_STYLE)

        self.tree.setHeaderLabels(["Chapter", "Time"])
        self.tree.setHeaderHidden(True)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )
        self.tree.header().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.ResizeToContents,
        )

        # ================= ADD QUEUE BUTTON =================
        self.btn_add = QPushButton(tr("add_queue"))
        self.btn_add.setDisabled(True)

        # ================= HEADER PANEL =================
        self.chapter_header = QWidget()

        header_main = QVBoxLayout(self.chapter_header)
        header_main.setContentsMargins(4, 4, 4, 4)
        header_main.setSpacing(4)

        # ===== LOADING ROW =====
        loading_layout = QHBoxLayout()

        self.loading = QLabel()
        self.loading.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.movie = QMovie(str(get_resource_path("assets/loading.gif")))
        self.movie.setScaledSize(QSize(48, 48))

        self.loading.setMovie(self.movie)

        loading_layout.addStretch()
        loading_layout.addWidget(self.loading)
        loading_layout.addStretch()

        # ===== INFO ROW =====
        info_layout = QHBoxLayout()

        # THUMB
        self.manga_thumb = QLabel()
        self.manga_thumb.setFixedSize(150, 200)
        self.manga_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # TITLE
        self.manga_title = QLabel("")
        self.manga_title.setStyleSheet(MANGA_TITLE_STYLE)
        self.manga_title.setWordWrap(True)
        self.manga_title.setMaximumHeight(200)

        info_layout.addWidget(self.manga_thumb)
        info_layout.addWidget(self.manga_title)
        info_layout.addStretch()

        header_main.addLayout(loading_layout)
        header_main.addLayout(info_layout)

        # ================= DETAIL CHAPTER PANEL =================
        self.detail_chapter = QWidget()
        self.detail_chapter.setObjectName("detail_chapter")
        self.detail_chapter.setStyleSheet(CHAPTER_PANEL_STYLE)

        detail_layout = QVBoxLayout(self.detail_chapter)
        detail_layout.addWidget(self.chapter_header, 0)
        detail_layout.addWidget(self.tree, 1)

        # ================= ASSEMBLE LEFT PANEL =================
        # The Mode row replaces the old top spacer; minor vertical margins keep
        # the Mode label flush at the top, aligned with the Queue label row.
        layout.addWidget(self.mode_area, 0)
        layout.addWidget(self.input_stack, 0)
        layout.addWidget(path_area, 0)
        layout.addWidget(settings_row, 0)
        layout.addWidget(self.btn_add, 0)
        layout.addWidget(self.detail_chapter, 1)

        # events that only affect this panel's own widgets
        self.btn_folder.clicked.connect(self.pick_folder)
        self.btn_pick_file.clicked.connect(self.pick_file)
        self.url_input.textChanged.connect(lambda _=None: self._update_add_button())
        self.file_input.textChanged.connect(lambda _=None: self._update_add_button())
        self._on_mode_changed(self.rb_manual.isChecked())

    # =========================
    # SAVE THE SELECTED PATH (for the next run)
    # =========================
    def _save_path(self):
        path = self.path_input.text().strip()
        if path:
            self.settings.setValue("save_path", path)

    # =========================
    # checkbox "Automatically add to queue"
    # =========================
    def on_auto_queue_toggled(self, checked):
        self.settings.setValue("auto_queue", checked)

    # =========================
    # checkbox "Shutdown when done"
    # =========================
    def on_shutdown_toggled(self, checked):
        self.settings.setValue("shutdown_after_done", checked)
        self.shutdown_delay.setEnabled(checked)

    def _save_shutdown_delay(self):
        """Clamp + persist the countdown value typed in the delay text box."""
        try:
            value = max(1, min(int(self.shutdown_delay.text().strip() or "60"), 3600))
        except ValueError:
            value = 60
        self.shutdown_delay.setText(str(value))
        self.settings.setValue("shutdown_delay", value)

    @property
    def shutdown_delay_seconds(self) -> int:
        """Countdown (seconds) currently shown next to the shutdown checkbox."""
        try:
            return max(1, min(int(self.shutdown_delay.text().strip() or "60"), 3600))
        except ValueError:
            return 60

    # =========================
    # UPDATE TEXT WHEN THE LANGUAGE CHANGES
    # =========================
    def retranslate(self):
        self.file_input.setPlaceholderText(tr("file_placeholder"))
        self.btn_pick_file.setText(tr("file_pick"))
        self.url_input.setPlaceholderText(tr("url_placeholder"))
        self.path_input.setPlaceholderText(tr("path_placeholder"))
        self.btn_paste.setText(tr("paste"))
        self.btn_folder.setText(tr("folder"))
        self.btn_settings.setText(tr("settings"))
        self.btn_add.setText(tr("add_queue"))
        self.auto_queue_cb.setText(tr("auto_queue"))
        self.shutdown_cb.setText(tr("shutdown_after_done"))
        self.shutdown_delay.setToolTip(tr("shutdown_delay_hint"))
        self.shutdown_delay_unit.setText(tr("shutdown_seconds"))
        self.shutdown_delay_unit.setToolTip(tr("shutdown_delay_hint"))
        if hasattr(self, "rb_manual"):
            self.rb_manual.setText(tr("mode_manual"))
            self.rb_auto.setText(tr("mode_auto"))

    # =========================
    # SETTINGS MODAL (read/write config.json)
    # =========================
    def open_settings(self):
        dialog = _ConfigDialog(self)
        dialog.exec()

    # =========================
    # FOLDER PICKER
    # =========================
    def pick_folder(self):
        from PyQt6.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(self, tr("pick_folder_title"))
        if folder:
            self.path_input.setText(folder)
            self._save_path()

        # =========================
    # FILE PICKER (add jobs from file)
    # =========================
    def _pick_file_for_event(self, event):
        self.pick_file()

    def pick_file(self):
        """Open a file dialog and validate the chosen file as a link list.

        Any file type can be picked ("All files"). The content is then
        validated via core.utils.parse_link_file: it must be readable as
        text and every non-empty, non-comment line must look like a valid
        http(s) URL. On failure, an error modal is shown and the file is
        not imported.
        """
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        from core.utils import parse_link_file

        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("file_pick_title"),
            "",
            f"{tr('all_files')} (*)",
        )
        if not path:
            return

        _urls, error_code, error_detail = parse_link_file(path)

        if error_code is not None:
            message = tr(f"import_error_{error_code}")
            if error_detail:
                message = f"{message}\n\n{error_detail}"

            QMessageBox.critical(self, tr("import_error_title"), message)
            return

        self.file_input.setText(path)
        self._save_file_path()
        self._update_add_button()

    def _save_file_path(self):
        self.settings.setValue("import_file", self.file_input.text().strip())

    # =========================
    # MODE CHANGE (manual / auto)
    # =========================
    def _on_mode_changed(self, checked):
        """Switch between manual (paste URL) and auto (add jobs from a file).

        Uses a QStackedWidget, so only one input row is ever visible:
        - manual: URL text box + paste button
        - auto:   file text box + choose-file button
        """
        manual = self.rb_manual.isChecked()

        # Show the matching page of the input stack.
        self.input_stack.setCurrentIndex(0 if manual else 1)

        # add_queue is only enabled once a valid input is present:
        # manual -> a URL has been loaded; auto -> a file has been chosen.
        self._update_add_button()

    # =========================
    # UPDATE ADD-QUEUE BUTTON STATE
    # =========================
    def _update_add_button(self):
        """Enable the Add Queue button when a valid input is present:
        - manual mode: a URL has been loaded (title available)
        - auto mode:   a file has been chosen
        """
        if self.rb_auto.isChecked():
            self.btn_add.setEnabled(bool(self.file_input.text().strip()))
            return

        # manual mode: URL field may be populated; title is filled by on_load_chapters.
        self.btn_add.setEnabled(
            bool(self.url_input.text().strip())
            and bool(self.manga_title.text().strip())
        )

    # =========================
    # SHOW / HIDE LOADING
    # =========================
    def on_loading(self, show: bool):
        if show:
            self.reset_view()
            self.loading.show()
            self.movie.start()
        else:
            self.movie.stop()
            self.loading.hide()

    # =========================
    # RESET VIEW
    # =========================
    def reset_view(self):
        self.manga_title.clear()
        self.manga_thumb.clear()
        self.tree.setHeaderHidden(True)
        self.tree.clear()


class _ConfigDialog(QDialog):
    """Modal to edit the values in config.json."""

    # (i18n label key, config key, type, i18n description key)
    FIELDS = [
        ("field_max_workers", "max_workers", int, "field_max_workers_desc"),
        ("field_max_concurrent", "max_concurrent_downloads", int, "field_max_concurrent_desc"),
        ("field_download_retry", "download_retry", int, "field_download_retry_desc"),
        ("field_chapter_retry", "chapter_retry", int, "field_chapter_retry_desc"),
        ("field_timeout", "request_timeout", int, "field_timeout_desc"),
    ]

    @staticmethod
    def _make_help_button(callback) -> QToolButton:
        """Create a "?" icon button with the shared hover style,
        used to open a _HelpDialog with more detail about an option."""
        btn = QToolButton()
        btn.setText("?")
        btn.setFixedSize(24, 24)
        btn.setAutoRaise(True)
        btn.setStyleSheet(HELP_BUTTON_STYLE)
        btn.clicked.connect(callback)
        return btn

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("settings_title"))
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setStyleSheet(CONFIG_DIALOG_STYLE)

        self._inputs = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # ===== LANGUAGE COMBOBOX =====
        self.cb_lang = QComboBox()
        self.cb_lang.addItem(tr("lang_vi"), "vi")
        self.cb_lang.addItem(tr("lang_en"), "en")
        idx = self.cb_lang.findData(get_lang())
        self.cb_lang.setCurrentIndex(idx if idx >= 0 else 0)

        # Wrap in a stretching row so the width matches the text boxes below
        # (the other rows have a "?" button 24px at the end -> leave exactly 24px)
        lang_row = QWidget()
        lang_layout = QHBoxLayout(lang_row)
        lang_layout.setContentsMargins(0, 0, 0, 0)
        lang_layout.setSpacing(4)
        lang_layout.addWidget(self.cb_lang, 1)
        lang_spacer = QWidget()
        lang_spacer.setFixedWidth(24)
        lang_layout.addWidget(lang_spacer)

        form.addRow(tr("language_label"), lang_row)

        for label_key, key, cast, desc_key in self.FIELDS:
            label = tr(label_key)
            desc = tr(desc_key)
            value = CONFIG.get(key, "")

            if cast is int:
                widget = QSpinBox()
                widget.setMinimum(1)
                widget.setMaximum(9999)
                try:
                    widget.setValue(int(value))
                except (TypeError, ValueError):
                    widget.setValue(1)
            else:
                widget = QLineEdit(str(value))

            self._inputs[key] = widget

            # "?" icon — click to open the option detail modal
            btn_help = self._make_help_button(
                lambda _=False, t=label, d=desc: _HelpDialog(t, d, self).exec()
            )

            row = QWidget()
            row.setFixedHeight(26)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)
            
            row_layout.addWidget(widget, 1)
            row_layout.addWidget(btn_help)

            form.addRow(label, row)

        layout.addLayout(form)

        # ===== RADIO: SAVE THUMBNAIL WHEN DOWNLOADING =====
        thumb_row = QWidget()
        thumb_row.setFixedHeight(26)

        thumb_layout = QHBoxLayout(thumb_row)
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        thumb_layout.setSpacing(4)

        self.rb_thumb_yes = make_radio_button(tr("thumb_yes"))
        self.rb_thumb_no = make_radio_button(tr("thumb_no"))
        self._thumb_group = QButtonGroup(self)
        self._thumb_group.addButton(self.rb_thumb_yes)
        self._thumb_group.addButton(self.rb_thumb_no)

        download_thumb = CONFIG.get("download_thumb", True)
        (self.rb_thumb_yes if download_thumb else self.rb_thumb_no).setChecked(True)

        thumb_layout.addWidget(self.rb_thumb_yes)
        thumb_layout.addSpacing(24)
        thumb_layout.addWidget(self.rb_thumb_no)
        thumb_layout.addStretch()

        btn_thumb_help = self._make_help_button(
            lambda _=False: _HelpDialog(
                tr("thumb_help_title"),
                tr("thumb_help_desc"),
                self,
            ).exec()
        )

        thumb_layout.addWidget(btn_thumb_help)
        form.addRow(tr("save_thumb"), thumb_row)

        buttons = QDialogButtonBox()
        btn_apply = buttons.addButton(tr("apply"), QDialogButtonBox.ButtonRole.AcceptRole)
        btn_cancel = buttons.addButton(tr("cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        btn_apply.clicked.connect(self._on_apply)
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(buttons)

        apply_pointer_cursors(self)

        # Don't auto-focus cb_lang (the first widget) when the dialog opens.
        self.setFocus()

    def _on_apply(self):
        new_config = dict(CONFIG)
        for label_key, key, cast, desc_key in self.FIELDS:
            widget = self._inputs[key]
            if cast is int:
                new_config[key] = widget.value()
            else:
                text = widget.text().strip()
                if text:
                    new_config[key] = text

        new_config["download_thumb"] = self.rb_thumb_yes.isChecked()
        new_config["language"] = self.cb_lang.currentData()

        if save_config(new_config):
            # Update the in-memory CONFIG + language so the change applies immediately
            CONFIG.clear()
            CONFIG.update(new_config)
            set_lang(new_config["language"])
            self.accept()
        else:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(
                self,
                tr("error"),
                tr("save_error")
            )


class _HelpDialog(QDialog):
    """Modal showing the detail + recommendation of an option."""

    def __init__(self, title: str, description: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("settings_help_title"))
        self.setModal(True)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        title_label = QLabel(title)
        title_label.setStyleSheet(HELP_TITLE_STYLE)
        title_label.setWordWrap(True)

        desc_label = QLabel(description)
        desc_label.setWordWrap(True)
        desc_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        buttons = QDialogButtonBox()
        btn_ok = buttons.addButton(tr("ok"), QDialogButtonBox.ButtonRole.AcceptRole)
        btn_ok.clicked.connect(self.accept)

        layout.addWidget(title_label)
        layout.addWidget(desc_label)
        layout.addWidget(buttons)

        apply_pointer_cursors(self)
