"""Shared widget helpers used across the GUI.

Small factory functions (consistently styled checkboxes/radio buttons) and the
cursor helper, since Qt Style Sheets cannot set the cursor property.
"""

from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QWidget, QPushButton, QCheckBox, QRadioButton, QToolButton
from PyQt6.QtCore import Qt

_POINTER_WIDGET_TYPES = (QPushButton, QCheckBox, QRadioButton, QToolButton)


def make_radio_button(text: str) -> QRadioButton:
    """Create a QRadioButton with the app's custom indicator icons
    (checked/unchecked SVGs) applied, so every radio button in the app
    looks consistent without repeating the same stylesheet everywhere.
    """
    btn = QRadioButton(text)
    return btn


def make_checkbox(text: str) -> QCheckBox:
    """Create a QCheckBox with the app's custom indicator icons
    (checked/unchecked SVGs) applied, so every checkbox in the app
    looks consistent without repeating the same stylesheet everywhere.
    """
    cb = QCheckBox(text)
    return cb


def apply_pointer_cursors(root: QWidget, event_filter: QWidget = None):
    """Recursively set a pointing-hand cursor on every clickable widget
    under `root` (buttons, checkboxes, radio buttons, tool buttons).

    Qt Style Sheets don't support the `cursor` CSS property, so this has
    to be done in code instead. If `event_filter` is given, it is
    installed on QPushButton/QToolButton instances so the cursor can be
    updated to "forbidden" when they become disabled.
    """
    pointer = QCursor(Qt.CursorShape.PointingHandCursor)

    for widget in root.findChildren(_POINTER_WIDGET_TYPES):
        widget.setCursor(pointer)
        if event_filter is not None and isinstance(widget, (QPushButton, QToolButton)):
            widget.installEventFilter(event_filter)
