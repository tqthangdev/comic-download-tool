from PyQt6.QtWidgets import QStyledItemDelegate
from PyQt6.QtGui import QPainter, QColor, QFontMetrics, QFont, QPixmap
from PyQt6.QtCore import Qt, QRect, QEvent, pyqtSignal


class QueueDelegate(QStyledItemDelegate):
    # Phát ra url của job khi người dùng bấm icon thùng rác,
    # để nơi khác (MainWindow) gọi engine.del_job(url) thật sự.
    deleteRequested = pyqtSignal(str)

    # max/min width reserved for the status area on the right
    STATUS_WIDTH_MAX = 200
    STATUS_WIDTH_MIN = 150
    LEFT_PADDING = 5
    GAP = 10  # gap between the title and the status

    TRASH_SIZE = 16
    TRASH_GAP = 5
    TRASH_TOP_PADDING = 2

    def __init__(self, parent=None):
        super().__init__(parent)

        self.trash_pixmap = QPixmap("assets/trash.png")

    def _trash_rect(self, option) -> QRect:
        """Return the area occupied by the trash icon."""
        rect = option.rect

        return QRect(
            rect.left() + self.LEFT_PADDING,
            rect.top() + (rect.height() - self.TRASH_SIZE) // 2 + self.TRASH_TOP_PADDING,
            self.TRASH_SIZE,
            self.TRASH_SIZE,
        )

    def paint(self, painter, option, index):

        data = index.data(
            Qt.ItemDataRole.UserRole
        )

        if not data:
            return

        title = data["title"]
        status = data["status"]

        painter.save()

        rect = option.rect

        # ================= TRASH ICON =================
        trash_rect = self._trash_rect(option)

        if not self.trash_pixmap.isNull():
            painter.drawPixmap(
                trash_rect,
                self.trash_pixmap
            )

        # ================= COMPUTE STATUS WIDTH DYNAMICALLY =================
        # status takes up to ~30% of the frame width, capped by STATUS_WIDTH_MAX
        # and floored by STATUS_WIDTH_MIN, so it always fits in the current frame
        status_width = max(
            self.STATUS_WIDTH_MIN,
            min(self.STATUS_WIDTH_MAX, int(rect.width() * 0.3))
        )

        # ================= STATUS AREA (fixed on the right) =================
        status_rect = QRect(
            rect.right() - status_width,
            rect.top() + self.TRASH_TOP_PADDING,
            status_width,
            rect.height()
        )

        # ================= TITLE AREA (remaining space on the left) =================
        title_left = trash_rect.right() + self.TRASH_GAP
        title_width = max(
            0,
            status_rect.left() - title_left - self.GAP
        )
        title_rect = QRect(
            title_left,
            rect.top() + self.TRASH_TOP_PADDING,
            title_width,
            rect.height()
        )

        # elide the title if it is too long so it does not overlap the status
        metrics = QFontMetrics(painter.font())
        elided_title = metrics.elidedText(
            title,
            Qt.TextElideMode.ElideRight,
            title_rect.width()
        )

        painter.setPen(QColor("#e0e0e0"))
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided_title
        )

        # ================= STATUS =================
        match status:
            case "Done" | "Finished":
                color = "#2196F3"
            case "Done with missing images" | "Done with missing":
                color = "#FF9800"
            case "Waiting":
                color = "#FFC107"
            case "Error" | "Failed":
                color = "#F44336"
            case "Resume":
                color = "#4CAF50"
            case "Paused":
                color = "#9E9E9E"
            case s if s.startswith("Downloading"):
                color = "#4CAF50"
            case _:
                color = "#e0e0e0"

        painter.setPen(QColor(color))

        # If the status is long (e.g. "Downloading...(2/10): 100%") shrink the font to
        # fit the status area instead of truncating the tail.
        MIN_FONT_SIZE = 2.0
        font = painter.font()
        if status_rect.width() < metrics.horizontalAdvance(status):
            shrink = font
            shrink.setPointSizeF(
                max(MIN_FONT_SIZE, font.pointSizeF() - 1)
            )
            while shrink.pointSizeF() > MIN_FONT_SIZE:
                if QFontMetrics(shrink).horizontalAdvance(status) <= status_rect.width():
                    break

                shrink.setPointSizeF(
                    max(
                        MIN_FONT_SIZE,
                        shrink.pointSizeF() - 0.5
                    )
                )

            painter.setFont(shrink)

        painter.drawText(
            status_rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            status
        )

        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                trash_rect = self._trash_rect(option)

                if trash_rect.contains(event.pos()):
                    data = index.data(Qt.ItemDataRole.UserRole)
                    job_url = data.get("url") if data else None

                    if job_url:
                        self.deleteRequested.emit(job_url)

                    model.removeRow(index.row())
                    return True

        return super().editorEvent(event, model, option, index)