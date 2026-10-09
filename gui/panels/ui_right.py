from PyQt6.QtWidgets import (
    QGroupBox,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
)
from PyQt6.QtCore import QSize, Qt, pyqtSignal

from gui.panels.queue_delegate import QueueDelegate
from core.i18n import tr
from core.utils import CONFIG


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
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)

        
        # ================= QUEUE GROUP =================
        queue_group = QGroupBox(tr("queue"))
        queue_layout = QVBoxLayout(queue_group)
        queue_layout.setContentsMargins(6, 6, 6, 6)
        queue_layout.setSpacing(6)
        self.queue_group = queue_group

        # ================= QUEUE BUTTONS =================
        self.btn_start = QPushButton(tr("start"))
        self.btn_resume = QPushButton(tr("resume"))
        self.btn_pause = QPushButton(tr("pause"))
        self.btn_clear = QPushButton(tr("clear_done"))

        self.row_buttons = QWidget()
        btn_row = QHBoxLayout(self.row_buttons)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(6)

        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_resume)
        btn_row.addWidget(self.btn_pause)
        btn_row.addWidget(self.btn_clear)

        # ================= QUEUE LIST =================
        self.queue_list = QListWidget()
        self.queue_list.setObjectName("queue_list")
        self._delegate = QueueDelegate(self.queue_list)
        self.queue_list.setItemDelegate(self._delegate)
        self._delegate.deleteRequested.connect(self.deleteRequested)
        self.queue_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        # ================= ADD WIDGETS =================
        queue_layout.addWidget(self.row_buttons)
        queue_layout.addWidget(self.queue_list, 1)

        layout.addWidget(queue_group, 1)

        self.btn_clear.clicked.connect(self.clear_done)
        self._update_queue_group()

    def retranslate(self):
        self.btn_start.setText(tr("start"))
        self.btn_resume.setText(tr("resume"))
        self.btn_pause.setText(tr("pause"))
        self.btn_clear.setText(tr("clear_done"))
        self._update_queue_group()

    def _update_queue_group(self):
        """Show the queue size in the header ("Queue has N comics")."""
        count = self.queue_list.count()
        if count:
            self.queue_group.setTitle(tr("queue_with_count").format(count=count))
        else:
            self.queue_group.setTitle(tr("queue"))

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
        item.setSizeHint(QSize(0, QueueDelegate.ROW_HEIGHT))

        item.setData(
            Qt.ItemDataRole.UserRole,
            {
                "url": job.url,
                "title": job.title,
                "status": status,
                "path": str(job.save_path),
                "chapters": job.chapters,
                "referer": job.referer,
                "convert_to_pdf": self._job_pdf(job),
            }
        )
        self._apply_error_tooltip(item, job)

        self.queue_list.addItem(item)
        self._update_queue_group()

    @staticmethod
    def _job_pdf(job) -> bool:
        """The job's output format, for the row's format tag (legacy jobs fall
        back to the config default)."""
        value = getattr(job, "convert_to_pdf", None)
        if value is None:
            return bool(CONFIG.get("convert_to_pdf", False))
        return bool(value)

    @staticmethod
    def _apply_error_tooltip(item, job):
        """Tooltip with the job's last error (the backend that produced it is
        deliberately not named — it is only logged)."""
        error = getattr(job, "engine_error", None)
        item.setToolTip(error or "")

    def update_queue_item(self, url, job, status):
        result = self.exists_in_queue(job.url)
        if not result["exists"]:
            self.add_queue_item(job, status)
            return

        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data["url"] != job.url:
                continue
            data["status"] = status
            data["convert_to_pdf"] = self._job_pdf(job)
            item.setData(Qt.ItemDataRole.UserRole, data)
            self._apply_error_tooltip(item, job)
            break

        self.queue_list.viewport().update()

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
                self._update_queue_group()
                return

    def clear_done(self):
        """Remove all queue items with status 'Done', 'Done with missing images' """
        for i in range(self.queue_list.count() - 1, -1, -1):  # iterate backwards
            item = self.queue_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)

            if data and data.get("status") in ["Done", "Done with missing images"]:
                self.queue_list.takeItem(i)
        self._update_queue_group()
