from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
)
from PyQt6.QtCore import QSize, Qt, pyqtSignal

from gui.queue_delegate import QueueDelegate
from core.i18n import tr


class RightPanel(QWidget):
    """
    Right side of the main window:
    - Start / Pause / Clear Done buttons (top)
    - Queue list (bottom)
    """

    # Emitted when the user clicks the trash icon on a job in the queue list.
    # MainWindow connects this signal to call engine.del_job(url).
    deleteRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ================= BUTTON ROW (top) =================
        self.btn_start = QPushButton(tr("start"))
        self.btn_resume = QPushButton(tr("resume"))
        self.btn_pause = QPushButton(tr("pause"))
        self.btn_clear = QPushButton(tr("clear_done"))

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(6)

        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_resume)
        btn_row.addWidget(self.btn_pause)
        btn_row.addWidget(self.btn_clear)

        # ================= QUEUE LIST =================
        self.queue_list = QListWidget()
        self.queue_list.setObjectName("queue_list")
        self.queue_list.setStyleSheet("""
        QWidget#queue_list {
            background: transparent;
            border: 1px solid #adadad;
            padding-right: 5px;
        }
        """)
        self._delegate = QueueDelegate()
        self.queue_list.setItemDelegate(self._delegate)
        self._delegate.deleteRequested.connect(self.deleteRequested)
        self.queue_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.queue_label = QLabel(tr("queue"))
        layout.addWidget(self.queue_label)
        layout.addLayout(btn_row)
        layout.addWidget(self.queue_list)

        self.btn_clear.clicked.connect(self.clear_done)

    def retranslate(self):
        self.btn_start.setText(tr("start"))
        self.btn_resume.setText(tr("resume"))
        self.btn_pause.setText(tr("pause"))
        self.btn_clear.setText(tr("clear_done"))
        self.queue_label.setText(tr("queue"))

    def exists_in_queue(self, url):
        result = {"exists": False, "data": None}
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)

            if data["url"] == url:
                result["exists"] = True
                result["data"] = data
                return result

        return result

    def add_queue_item(self, job, status="Waiting"):
        result = self.exists_in_queue(job.url)
        if result["exists"]:
            return

        item = QListWidgetItem(job.title)
        item.setSizeHint(QSize(0, 28))

        item.setData(
            Qt.ItemDataRole.UserRole,
            {
                "url": job.url,
                "title": job.title,
                "status": status,
                "path": str(job.save_path),
                "chapters": job.chapters,
                "referer": job.referer,
            }
        )

        self.queue_list.addItem(item)

    def update_queue_item(self, url, job, status):
        result = self.exists_in_queue(job.url)
        if not result["exists"]:
            self.add_queue_item(job, status)
            return
        else:
            item = result["data"]
            item["status"] = status
            self.queue_list.viewport().update()
            return

    def update_progress(self, title, status):
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)

            if data["title"] == title:
                data["status"] = status
                item.setData(Qt.ItemDataRole.UserRole, data)
                self.queue_list.viewport().update()
                return

    def remove_queue_item(self, url):
        """Remove the item with the given url from the queue list, if present."""
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)

            if data and data.get("url") == url:
                self.queue_list.takeItem(i)
                return

    def clear_done(self):
        """Remove all queue items with status 'Done', 'Done with missing images' """
        for i in range(self.queue_list.count() - 1, -1, -1):  # iterate backwards
            item = self.queue_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)

            if data and data.get("status") in ["Done", "Done with missing images"]:
                self.queue_list.takeItem(i)
