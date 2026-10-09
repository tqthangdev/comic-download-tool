"""Preview area of the left column.

Shows the loading spinner, the cover + title, the output-format picker
(Image / PDF) and the chapter list. Kept out of ``ui_left`` so that panel is
just the input form.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFontMetrics, QMovie
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.utils import get_resource_path

# Values carried by the format combobox (persisted as `convert_to_pdf`).
IMAGE_FORMAT = "image"
PDF_FORMAT = "pdf"

THUMBNAIL_SIZE = QSize(100, 150)

class PreviewChapter(QWidget):
    """Cover + title + output format + chapter tree for the loaded story."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("detail_chapter")

        self._title_full = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # ================= HEADER (spinner, cover+title, format) =================
        header = QWidget()
        header_main = QVBoxLayout(header)
        header_main.setContentsMargins(4, 4, 4, 4)
        header_main.setSpacing(4)

        loading_layout = QHBoxLayout()
        self.loading = QLabel()
        self.loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.movie = QMovie(str(get_resource_path("assets/spinners/loading.gif")))
        self.movie.setScaledSize(QSize(48, 48))
        self.loading.setMovie(self.movie)
        loading_layout.addStretch()
        loading_layout.addWidget(self.loading)
        loading_layout.addStretch()

        info_layout = QHBoxLayout()
        self.thumb = QLabel()
        self.thumb.setFixedSize(THUMBNAIL_SIZE)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_label = QLabel("")
        self.title_label.setObjectName("manga_title")
        self.title_label.setWordWrap(True)
        # Fixed to the cover height: a longer title is cut with an ellipsis
        # (see _fit_title) instead of growing the row.
        self.title_label.setFixedHeight(self.thumb.height())
        self.title_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )

        info_layout.addWidget(self.thumb)
        info_layout.addWidget(self.title_label, 1)

        format_area = QWidget()
        format_layout = QHBoxLayout(format_area)

        format_layout.setContentsMargins(0, 0, 0, 0)
        format_layout.setSpacing(6)

        self.format_label = QLabel(tr("output_format"))

        self.format_combo = QComboBox()
        self.format_combo.addItem(tr("format_image"), IMAGE_FORMAT)
        self.format_combo.addItem(tr("format_pdf"), PDF_FORMAT)

        format_layout.addWidget(self.format_label)
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()

        self.format_area = format_area
        self.format_area.hide()

        header_main.addLayout(loading_layout)
        header_main.addLayout(info_layout)
        header_main.addWidget(self.format_area)

        # ================= CHAPTER TREE =================
        self.tree = QTreeWidget()
        self.tree.setObjectName("detail_tree")
        self.tree.setHeaderLabels(["Chapter", "Time"])
        self.tree.setHeaderHidden(True)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )

        root.addWidget(header, 0)
        root.addWidget(self.tree, 1)

    # ---- cover / title --------------------------------------------------- #

    def set_title(self, text: str) -> None:
        self._title_full = text or ""
        self._fit_title()

    def title_text(self) -> str:
        return self._title_full

    def set_thumb(self, pixmap) -> None:
        if pixmap is None:
            self.thumb.clear()
        else:
            self.thumb.setPixmap(pixmap)

    def resizeEvent(self, event) -> None:  # noqa: N802
        # The title is cut to the cover height, so its wrapping depends on the
        # current width — redo it whenever the panel is resized.
        super().resizeEvent(event)
        self._fit_title()

    def _fit_title(self) -> None:
        """Wrap the title, then elide it if it does not fit the cover height."""
        if not self._title_full:
            self.title_label.setText("")
            return

        metrics = QFontMetrics(self.title_label.font())
        width = max(1, self.title_label.width())
        line_height = max(1, metrics.lineSpacing())
        max_lines = max(1, self.title_label.height() // line_height)

        lines = []
        current = ""
        for word in self._title_full.split():
            candidate = f"{current} {word}".strip()
            if not current or metrics.horizontalAdvance(candidate) <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)

        if len(lines) > max_lines:
            lines = lines[:max_lines]
            # Guarantee a trailing marker on the last kept line.
            ellipsis = "…"
            room = max(1, width - metrics.horizontalAdvance(ellipsis))
            trimmed = ""
            for word in lines[-1].split():
                candidate = f"{trimmed} {word}".strip()
                if metrics.horizontalAdvance(candidate) > room:
                    break
                trimmed = candidate
            lines[-1] = f"{trimmed}{ellipsis}" if trimmed else ellipsis

        self.title_label.setText("\n".join(lines))

    # ---- output format --------------------------------------------------- #

    def output_format(self) -> str:
        return self.format_combo.currentData() or IMAGE_FORMAT

    def set_output_format(self, fmt: str) -> None:
        index = self.format_combo.findData(fmt)
        if index >= 0:
            self.format_combo.setCurrentIndex(index)

    # ---- chapters / loading ---------------------------------------------- #

    def clear_chapters(self) -> None:
        self.tree.clear()

    def set_loading(self, show: bool) -> None:
        if show:
            self.reset()
            self.loading.show()
            self.movie.start()
        else:
            self.movie.stop()
            self.loading.hide()

    def reset(self) -> None:
        self.set_title("")
        self.thumb.clear()
        self.format_area.hide()
        self.tree.setHeaderHidden(True)
        self.tree.clear()

    # ---- i18n ------------------------------------------------------------ #

    def retranslate(self) -> None:
        self.format_label.setText(tr("output_format"))
        self.format_combo.setItemText(0, tr("format_image"))
        self.format_combo.setItemText(1, tr("format_pdf"))
