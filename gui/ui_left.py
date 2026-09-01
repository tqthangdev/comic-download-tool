from pathlib import Path

from PyQt6.QtGui import QMovie
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
    QComboBox,
)
from PyQt6.QtCore import Qt, QSize, QSettings

from core.utils import get_resource_path, CONFIG, save_config
from core.i18n import tr, set_lang, get_lang


class LeftPanel(QWidget):
    """
    Left side of the main window:
    - URL input + paste button
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

        # ================= URL AREA =================
        url_area = QWidget()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(tr("url_placeholder"))
        self.url_input.setReadOnly(True)

        self.btn_paste = QPushButton(tr("paste"))
        self.btn_paste.setFixedWidth(80)

        url_layout = QHBoxLayout(url_area)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.setSpacing(6)

        url_layout.addWidget(self.url_input, 1)
        url_layout.addWidget(self.btn_paste)

        # ================= CHECKBOX + SETTINGS =================
        settings_row = QWidget()
        settings_layout = QHBoxLayout(settings_row)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(6)

        checkbox_col = QVBoxLayout()
        checkbox_col.setContentsMargins(0, 0, 0, 0)
        checkbox_col.setSpacing(2)

        self.shutdown_cb = QCheckBox(tr("shutdown_after_done"))
        shutdown_saved = self.settings.value("shutdown_after_done", False, type=bool)
        self.shutdown_cb.setChecked(shutdown_saved)
        self.shutdown_cb.toggled.connect(self.on_shutdown_toggled)

        self.auto_queue_cb = QCheckBox(tr("auto_queue"))
        auto_queue_saved = self.settings.value("auto_queue", False, type=bool)
        self.auto_queue_cb.setChecked(auto_queue_saved)
        self.auto_queue_cb.toggled.connect(self.on_auto_queue_toggled)

        checkbox_col.addWidget(self.shutdown_cb)
        checkbox_col.addWidget(self.auto_queue_cb)

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
        self.tree.setStyleSheet("""
        QWidget#detail_tree {
            background: transparent;
            border: 1px solid transparent;
        }
        QTreeWidget#detail_tree::item {
            background: transparent;
            color: #00e5ff;
        }
        """)
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
        self.manga_title.setStyleSheet("font-size:16px; font-weight:bold; color:#ff9800;")
        self.manga_title.setWordWrap(True)

        info_layout.addWidget(self.manga_thumb)
        info_layout.addWidget(self.manga_title)
        info_layout.addStretch()

        header_main.addLayout(loading_layout)
        header_main.addLayout(info_layout)

        # ================= DETAIL CHAPTER PANEL =================
        self.detail_chapter = QWidget()
        self.detail_chapter.setObjectName("detail_chapter")
        self.detail_chapter.setStyleSheet("""
        QWidget#detail_chapter {
            background: transparent;
            border: 1px solid #adadad;
        }
        QHeaderView::section {
            background: transparent;
            color: #00e5ff;
            border: none;
        }
        """)
        detail_layout = QVBoxLayout(self.detail_chapter)

        detail_layout.addWidget(self.chapter_header)
        detail_layout.addWidget(self.tree)

        # ================= ASSEMBLE LEFT PANEL =================
        layout.addWidget(QLabel(" "))
        layout.addWidget(url_area)
        layout.addWidget(path_area)
        layout.addWidget(settings_row)
        layout.addWidget(self.btn_add)
        layout.addWidget(self.detail_chapter)

        # events that only affect this panel's own widgets
        self.btn_folder.clicked.connect(self.pick_folder)

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

    # =========================
    # UPDATE TEXT WHEN THE LANGUAGE CHANGES
    # =========================
    def retranslate(self):
        self.url_input.setPlaceholderText(tr("url_placeholder"))
        self.path_input.setPlaceholderText(tr("path_placeholder"))
        self.btn_paste.setText(tr("paste"))
        self.btn_folder.setText(tr("folder"))
        self.btn_settings.setText(tr("settings"))
        self.btn_add.setText(tr("add_queue"))
        self.auto_queue_cb.setText(tr("auto_queue"))
        self.shutdown_cb.setText(tr("shutdown_after_done"))

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("settings_title"))
        self.setModal(True)
        self.setMinimumWidth(480)

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
            btn_help = QToolButton()
            btn_help.setText("?")
            btn_help.setFixedSize(24, 24)
            btn_help.setAutoRaise(True)
            btn_help.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_help.clicked.connect(
                lambda _=False, t=label, d=desc: _HelpDialog(t, d, self).exec()
            )

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)
            row_layout.addWidget(widget, 1)
            row_layout.addWidget(btn_help)

            form.addRow(label, row)

        layout.addLayout(form)

        # ===== RADIO: SAVE THUMBNAIL WHEN DOWNLOADING =====
        thumb_row = QWidget()
        thumb_layout = QHBoxLayout(thumb_row)
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        thumb_layout.setSpacing(4)

        self.rb_thumb_yes = QRadioButton(tr("thumb_yes"))
        self.rb_thumb_no = QRadioButton(tr("thumb_no"))
        self._thumb_group = QButtonGroup(self)
        self._thumb_group.addButton(self.rb_thumb_yes)
        self._thumb_group.addButton(self.rb_thumb_no)

        download_thumb = CONFIG.get("download_thumb", True)
        (self.rb_thumb_yes if download_thumb else self.rb_thumb_no).setChecked(True)

        thumb_layout.addWidget(self.rb_thumb_yes)
        thumb_layout.addSpacing(24)
        thumb_layout.addWidget(self.rb_thumb_no)
        thumb_layout.addStretch()

        btn_thumb_help = QToolButton()
        btn_thumb_help.setText("?")
        btn_thumb_help.setFixedSize(24, 24)
        btn_thumb_help.setAutoRaise(True)
        btn_thumb_help.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_thumb_help.clicked.connect(
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
        title_label.setStyleSheet("font-size:14px; font-weight:bold; color:#ff9800;")
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
