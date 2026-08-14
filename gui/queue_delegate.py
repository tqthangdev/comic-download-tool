from PyQt6.QtWidgets import QStyledItemDelegate
from PyQt6.QtGui import QPainter, QColor, QFontMetrics, QFont
from PyQt6.QtCore import Qt, QRect


class QueueDelegate(QStyledItemDelegate):
    # chiều rộng tối đa/tối thiểu dành cho vùng status bên phải
    STATUS_WIDTH_MAX = 200
    STATUS_WIDTH_MIN = 150
    LEFT_PADDING = 5
    GAP = 10  # khoảng cách giữa title và status

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

        # ================= TÍNH STATUS WIDTH ĐỘNG =================
        # status chiếm tối đa ~30% chiều rộng khung, nhưng không vượt STATUS_WIDTH_MAX
        # và không nhỏ hơn STATUS_WIDTH_MIN, để luôn vừa trong khung hiện có
        status_width = max(
            self.STATUS_WIDTH_MIN,
            min(self.STATUS_WIDTH_MAX, int(rect.width() * 0.3))
        )

        # ================= VÙNG STATUS (cố định bên phải) =================
        status_rect = QRect(
            rect.right() - status_width,
            rect.top(),
            status_width,
            rect.height()
        )

        # ================= VÙNG TITLE (phần còn lại bên trái) =================
        title_width = max(
            0,
            status_rect.left() - rect.left() - self.LEFT_PADDING - self.GAP
        )
        title_rect = QRect(
            rect.left() + self.LEFT_PADDING,
            rect.top(),
            title_width,
            rect.height()
        )

        # elide title nếu quá dài để không đè lên status
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

        # Nếu status dài (VD "Downloading...(2/10): 100%") -> co giãn font cho
        # vừa vùng status thay vì bị cắt mất phần cuối.
        font = painter.font()
        if status_rect.width() < metrics.horizontalAdvance(status):
            shrink = font
            shrink.setPointSizeF(max(6.0, font.pointSizeF() - 1))
            while shrink.pointSizeF() > 6.0:
                if QFontMetrics(shrink).horizontalAdvance(status) <= status_rect.width():
                    break
                shrink.setPointSizeF(shrink.pointSizeF() - 0.5)
            painter.setFont(shrink)

        painter.drawText(
            status_rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            status
        )

        painter.restore()
