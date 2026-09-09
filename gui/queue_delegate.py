from PyQt6.QtWidgets import QStyledItemDelegate
from PyQt6.QtGui import QColor, QFontMetrics, QPixmap
from PyQt6.QtCore import Qt, QRect, QEvent, pyqtSignal


class QueueDelegate(QStyledItemDelegate):
    # Emits the job url when the user clicks the trash icon,
    # so somewhere else (MainWindow) can actually call engine.del_job(url).
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

        self.trash_pixmap = QPixmap("assets/trash.svg")

        # `parent` must be the view (QListView/QListWidget/etc.) so we can
        # grab its viewport, enable mouse tracking, and install an event
        # filter on it. QPixmap has no setCursor(), so the cursor has to be
        # handled at the view/viewport level instead.
        self._view = parent
        if self._view is not None:
            self._view.setMouseTracking(True)
            self._view.viewport().setMouseTracking(True)
            self._view.viewport().installEventFilter(self)
            # Clear the reference the moment Qt destroys the C++ side, so we
            # never try to touch a dangling wrapped object afterwards.
            self._view.destroyed.connect(self._on_view_destroyed)

    def _on_view_destroyed(self, *_):
        self._view = None

    def _trash_rect(self, row_rect: QRect) -> QRect:
        """Return the area occupied by the trash icon, given the row's rect."""
        return QRect(
            row_rect.left() + self.LEFT_PADDING,
            row_rect.top() + (row_rect.height() - self.TRASH_SIZE) // 2 + self.TRASH_TOP_PADDING,
            self.TRASH_SIZE,
            self.TRASH_SIZE,
        )

    def eventFilter(self, obj, event):
        # Switch to a pointing-hand cursor while hovering over the trash
        # icon, and reset it back to the default cursor otherwise.
        #
        # Guarded with try/except: during app teardown the view's C++ object
        # can be destroyed while a queued event still triggers this filter,
        # which raises RuntimeError on any attribute access. If that happens
        # we just drop the reference and let the event pass through.
        try:
            if self._view is not None and obj is self._view.viewport():
                if event.type() == QEvent.Type.MouseMove:
                    index = self._view.indexAt(event.pos())

                    if index.isValid():
                        row_rect = self._view.visualRect(index)
                        trash_rect = self._trash_rect(row_rect)

                        if trash_rect.contains(event.pos()):
                            self._view.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
                        else:
                            self._view.viewport().unsetCursor()
                    else:
                        self._view.viewport().unsetCursor()
                elif event.type() == QEvent.Type.Leave:
                    self._view.viewport().unsetCursor()
        except RuntimeError:
            self._view = None

        return super().eventFilter(obj, event)

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
        trash_rect = self._trash_rect(rect)

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
                trash_rect = self._trash_rect(option.rect)

                if trash_rect.contains(event.pos()):
                    data = index.data(Qt.ItemDataRole.UserRole)
                    job_url = data.get("url") if data else None

                    if job_url:
                        # Do not removeRow here: MainWindow listens for
                        # deleteRequested, calls engine.del_job(url) and only
                        # then removes the item from the queue list once the
                        # DB record is gone.
                        self.deleteRequested.emit(job_url)
                    return True

        return super().editorEvent(event, model, option, index)