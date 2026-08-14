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
)
from PyQt6.QtCore import Qt, QSize, QSettings

from core.utils import get_resource_path


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
        self.url_input.setPlaceholderText("Paste comic URL...")
        self.url_input.setReadOnly(True)

        self.btn_paste = QPushButton("Paste")
        self.btn_paste.setFixedWidth(80)

        url_layout = QHBoxLayout(url_area)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.setSpacing(6)

        url_layout.addWidget(self.url_input, 1)
        url_layout.addWidget(self.btn_paste)

        # ================= CHECKBOX =================
        self.remember_path_cb = QCheckBox("Use this path by default")
        remember_path_saved = self.settings.value("remember_path", True, type=bool)
        self.remember_path_cb.setChecked(remember_path_saved)
        self.remember_path_cb.toggled.connect(self.on_remember_path)

        self.auto_queue_cb = QCheckBox("Automatically add to queue")
        auto_queue_saved = self.settings.value("auto_queue", False, type=bool)
        self.auto_queue_cb.setChecked(auto_queue_saved)
        self.auto_queue_cb.toggled.connect(self.on_auto_queue_toggled)

        # ================= PATH AREA =================
        path_area = QWidget()
        path_layout = QHBoxLayout(path_area)

        self.btn_folder = QPushButton("Folder")
        self.btn_folder.setFixedWidth(80)
        self.btn_folder.setDisabled(self.remember_path_cb.isChecked())

        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(6)

        self.path_input = QLineEdit()
        default_path = self.settings.value("save_path", str(Path.home() / "Documents"))

        self.path_input.setPlaceholderText("Đường dẫn lưu...")
        self.path_input.setText(default_path)
        self.path_input.setEnabled(not self.remember_path_cb.isChecked())

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
        self.btn_add = QPushButton("Add Queue")
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
        layout.addWidget(QLabel("URL"))
        layout.addWidget(url_area)
        layout.addWidget(path_area)
        layout.addWidget(self.remember_path_cb)
        layout.addWidget(self.auto_queue_cb)
        layout.addWidget(self.btn_add)
        layout.addWidget(self.detail_chapter)

        # events that only affect this panel's own widgets
        self.btn_folder.clicked.connect(self.pick_folder)

    # =========================
    # checkbox "Use this path by default"
    # =========================
    def on_remember_path(self, checked):
        self.path_input.setEnabled(not checked)
        self.btn_folder.setDisabled(checked)

        self.settings.setValue("remember_path", checked)  # <-- thêm dòng này

        if checked:
            self.settings.setValue("save_path", self.path_input.text())

    # =========================
    # checkbox "Automatically add to queue"
    # =========================
    def on_auto_queue_toggled(self, checked):
        self.settings.setValue("auto_queue", checked)

    # =========================
    # FOLDER PICKER
    # =========================
    def pick_folder(self):
        from PyQt6.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(self, "Chọn folder")
        if folder:
            self.path_input.setText(folder)

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
