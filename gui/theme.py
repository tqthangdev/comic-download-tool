"""Application theme.

Every widget style in the app lives here as ONE stylesheet rendered from a
palette, applied to the QApplication (see ``apply``). Switching theme therefore
re-styles everything at once — there are no per-widget ``setStyleSheet`` calls
any more. Widgets that need their own rule expose an ``objectName`` (e.g.
``#detail_tree``, ``#queue_list``) which the stylesheet targets.

The active theme is ``system`` / ``light`` / ``dark`` (``system`` follows the
OS colour scheme via ``QStyleHints.colorScheme``).
"""

from __future__ import annotations

from string import Template
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication

from core.utils import CONFIG, get_resource_path, save_config

ASSETS = get_resource_path("assets").as_posix()

THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEMES = (THEME_SYSTEM, THEME_LIGHT, THEME_DARK)


def _asset(*parts: str) -> str:
    return f"{ASSETS}/{'/'.join(parts)}"


def _dark() -> dict:
    return {
        "bg": "#1e1e1e",
        "bg_alt": "#2d2d2d",
        "bg_input": "#2d2d2d",
        "bg_input_focus": "#333333",
        "bg_raise": "#3a3a3a",
        "bg_hover": "#4a4a4a",
        "bg_press": "#2f2f2f",
        "bg_disabled": "#262626",
        "border": "#555555",
        "border_disabled": "#3a3a3a",
        "border_input": "#ffffff",
        "border_soft": "#adadad",
        "fg": "#d4d4d4",
        "fg_strong": "#e0e0e0",
        "fg_muted": "#6e6e6e",
        "accent": "#4CAF50",
        "title": "#ff9800",
        "sel_bg": "#4fc3f7",
        "sel_fg": "#1e1e1e",
        "menu_bg": "#2a2a2a",
        "menu_hover_bg": "#4CAF50",
        "menu_hover_fg": "#1e1e1e",
        "separator": "#555555",
        "scroll_handle": "#4a4a4a",
        "scroll_arrow_bg": "#3a3a3a",
        "checkbox_checked": _asset("controls", "checkbox-checked.svg"),
        "checkbox_unchecked": _asset("controls", "checkbox-unchecked.svg"),
        "radio_checked": _asset("controls", "radio-checked.svg"),
        "radio_unchecked": _asset("controls", "radio-unchecked.svg"),
        "spin_up": _asset("spinners", "spin-up.svg"),
        "spin_down": _asset("spinners", "spin-down.svg"),
        "spin_up_active": _asset("spinners", "spin-up-active.svg"),
        "spin_down_active": _asset("spinners", "spin-down-active.svg"),
    }


def _light() -> dict:
    return {
        "bg": "#f4f4f4",
        "bg_alt": "#ffffff",
        "bg_input": "#ffffff",
        "bg_input_focus": "#ffffff",
        "bg_raise": "#e4e4e4",
        "bg_hover": "#d6d6d6",
        "bg_press": "#cfcfcf",
        "bg_disabled": "#ededed",
        "border": "#bcbcbc",
        "border_disabled": "#dcdcdc",
        "border_input": "#9e9e9e",
        "border_soft": "#b0b0b0",
        "fg": "#242424",
        "fg_strong": "#111111",
        "fg_muted": "#9a9a9a",
        "accent": "#2e7d32",
        "title": "#e65100",
        "sel_bg": "#1976d2",
        "sel_fg": "#ffffff",
        "menu_bg": "#ffffff",
        "menu_hover_bg": "#1976d2",
        "menu_hover_fg": "#ffffff",
        "separator": "#d0d0d0",
        "scroll_handle": "#b0b0b0",
        "scroll_arrow_bg": "#d0d0d0",
        "checkbox_checked": _asset("controls", "light", "checkbox-checked.svg"),
        "checkbox_unchecked": _asset("controls", "light", "checkbox-unchecked.svg"),
        "radio_checked": _asset("controls", "light", "radio-checked.svg"),
        "radio_unchecked": _asset("controls", "light", "radio-unchecked.svg"),
        "spin_up": _asset("spinners", "light", "spin-up.svg"),
        "spin_down": _asset("spinners", "light", "spin-down.svg"),
        "spin_up_active": _asset("spinners", "spin-up-active.svg"),
        "spin_down_active": _asset("spinners", "spin-down-active.svg"),
    }


PALETTES = {THEME_DARK: _dark, THEME_LIGHT: _light}


# ---------------------------------------------------------------------------
# Stylesheet (single source for the whole app)
# ---------------------------------------------------------------------------

_STYLESHEET = Template("""
QWidget {
    background-color: $bg;
    color: $fg;
}

/* ---------- buttons ---------- */
QPushButton {
    background-color: $bg_raise;
    border: 1px solid $border;
    border-radius: 4px;
    padding: 5px 12px;
    color: $fg_strong;
}
QPushButton:hover  { background-color: $bg_hover; }
QPushButton:pressed { background-color: $bg_press; }
QPushButton:disabled {
    background-color: $bg_disabled;
    border-color: $border_disabled;
    color: $fg_muted;
}
QPushButton#add_queue { margin-top: 6px; }

/* ---------- text inputs ---------- */
QLineEdit, QTextEdit {
    background-color: $bg_input;
    border: 1px solid $border_input;
    border-radius: 4px;
    padding: 5px 8px;
    color: $fg_strong;
}
QLineEdit:focus, QTextEdit:focus {
    border: 2px solid $accent;
    background-color: $bg_input_focus;
}
QLineEdit#shutdown_delay {
    border-radius: 3px;
    padding: 0px 4px;
}

/* ---------- radio / check boxes ---------- */
QRadioButton::indicator { width: 14px; height: 14px; }
QRadioButton::indicator:unchecked { image: url("$radio_unchecked"); }
QRadioButton::indicator:checked   { image: url("$radio_checked"); }
QCheckBox::indicator { width: 18px; height: 18px; }
QCheckBox::indicator:unchecked { image: url("$checkbox_unchecked"); }
QCheckBox::indicator:checked   { image: url("$checkbox_checked"); }

/* ---------- tool buttons ("?" help icons) ---------- */
QToolButton {
    color: $fg_strong;
    border: none;
    background: transparent;
}
QToolButton:hover {
    color: $accent;
    font-weight: bold;
}

/* ---------- group boxes ---------- */
QGroupBox {
    border: 1px solid $border_soft;
    border-radius: 4px;
    margin-top: 10px;
    padding: 8px 6px 6px 6px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0 4px;
    color: $fg_strong;
}

/* ---------- chapter tree (preview) ---------- */
QTreeWidget#detail_tree {
    background: transparent;
    border: 1px solid transparent;
}
QTreeWidget#detail_tree::item {
    background: transparent;
    color: $accent;
}
QTreeWidget#detail_tree::item:selected {
    background: $sel_bg;
    color: $sel_fg;
}
QHeaderView::section {
    background: transparent;
    color: $accent;
    border: none;
}
QWidget#detail_chapter {
    background: transparent;
    border: 1px solid $border_soft;
}
QLabel#manga_title { font-size: 16px; font-weight: bold; color: $title; }
QLabel#dialog_title { font-size: 14px; font-weight: bold; color: $title; }

/* ---------- queue list ---------- */
QWidget#queue_list {
    background: transparent;
    border: 1px solid $border_soft;
}

/* ---------- progress bar ---------- */
QProgressBar {
    border: 1px solid $bg_raise;
    border-radius: 4px;
    background-color: $bg;
}
QProgressBar::chunk {
    background-color: $accent;
    border-radius: 3px;
}

/* ---------- spin box ---------- */
QSpinBox {
    background-color: $bg_input;
    border: 1px solid $border_input;
    border-radius: 4px;
    padding: 4px 6px;
    color: $fg_strong;
}
QSpinBox:focus { border: 2px solid $accent; }
QSpinBox::up-button, QSpinBox::down-button {
    background-color: $bg_input;
    border: none;
    width: 16px;
}
QSpinBox::up-button   { subcontrol-position: top right;    border-top-right-radius: 4px; }
QSpinBox::down-button { subcontrol-position: bottom right; border-bottom-right-radius: 4px; }
QSpinBox::up-arrow, QSpinBox::down-arrow { width: 10px; height: 6px; }
QSpinBox::up-arrow   { image: url("$spin_up"); }
QSpinBox::down-arrow { image: url("$spin_down"); }
QSpinBox::up-arrow:pressed   { image: url("$spin_up_active"); }
QSpinBox::down-arrow:pressed { image: url("$spin_down_active"); }

/* ---------- combo box ---------- */
QComboBox {
    background-color: $bg_input;
    border: 1px solid $border_input;
    border-radius: 4px;
    padding: 4px 6px;
    color: $fg_strong;
}
QComboBox:focus { border: 2px solid $accent; }
QComboBox:on    { color: $accent; }
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid $bg_input;
    background-color: $bg_input;
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
}
QComboBox::down-arrow { image: url("$spin_down"); width: 10px; height: 6px; }
QComboBox QAbstractItemView {
    background-color: $menu_bg;
    color: $fg;
    border: 1px solid $border;
    selection-background-color: $menu_hover_bg;
    selection-color: $menu_hover_fg;
    outline: none;
}
QComboBox QAbstractItemView::item { padding: 3px 6px; }
QComboBox QAbstractItemView::item:hover,
QComboBox QAbstractItemView::item:selected {
    background-color: $menu_hover_bg;
    color: $menu_hover_fg;
}

/* ---------- menu bar + menus ---------- */
QMenuBar {
    background-color: $bg;
    color: $fg;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
}
QMenuBar::item:selected {
    background-color: $menu_hover_bg;
    color: $menu_hover_fg;
}
QMenu {
    background-color: $menu_bg;
    border: 1px solid $border;
    color: $fg;
}
QMenu::item {
    padding: 4px 24px 4px 20px;
}
QMenu::item:selected {
    background-color: $menu_hover_bg;
    color: $menu_hover_fg;
}
QMenu::item:disabled { color: $fg_muted; }
QMenu::separator {
    height: 1px;
    background: $separator;
    margin: 4px 8px;
}

/* ---------- dialogs ---------- */
QDialog { background-color: $bg; color: $fg; }

/* ---------- scroll bars ---------- */
QScrollBar:vertical {
    background: transparent;
    width: 12px;
    margin: 12px 0px 12px 0px;
}
QScrollBar::handle:vertical {
    background: $scroll_handle;
    border-radius: 0px;
    min-height: 36px;
}
QScrollBar::add-line:vertical {
    subcontrol-position: bottom;
    subcontrol-origin: margin;
    height: 12px;
    background: $scroll_arrow_bg;
    border-bottom-left-radius: 4px;
    border-bottom-right-radius: 4px;
}
QScrollBar::sub-line:vertical {
    subcontrol-position: top;
    subcontrol-origin: margin;
    height: 12px;
    background: $scroll_arrow_bg;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QScrollBar::add-line:vertical:hover, QScrollBar::sub-line:vertical:hover {
    background: $scroll_handle;
}
QScrollBar::up-arrow:vertical   { image: url("$spin_up");   width: 8px; height: 5px; }
QScrollBar::down-arrow:vertical { image: url("$spin_down"); width: 8px; height: 5px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QScrollBar:horizontal {
    background: transparent;
    height: 12px;
    margin: 0px 12px 0px 12px;
}
QScrollBar::handle:horizontal {
    background: $scroll_handle;
    border-radius: 5px;
    min-width: 24px;
}
QScrollBar::add-line:horizontal {
    subcontrol-position: right;
    subcontrol-origin: margin;
    width: 12px;
    background: $scroll_arrow_bg;
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
}
QScrollBar::sub-line:horizontal {
    subcontrol-position: left;
    subcontrol-origin: margin;
    width: 12px;
    background: $scroll_arrow_bg;
    border-top-left-radius: 4px;
    border-bottom-left-radius: 4px;
}
QScrollBar::add-line:horizontal:hover, QScrollBar::sub-line:horizontal:hover {
    background: $scroll_handle;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
""")


def build_stylesheet(palette: dict) -> str:
    """Render the full application stylesheet from a palette."""
    return _STYLESHEET.substitute(palette)


# ---------------------------------------------------------------------------
# Active theme
# ---------------------------------------------------------------------------

_listeners: list[Callable[[], None]] = []
_watch_installed = False


def current_name() -> str:
    """The configured theme name (``system`` / ``light`` / ``dark``)."""
    name = CONFIG.get("theme", THEME_SYSTEM)
    return name if name in THEMES else THEME_SYSTEM


def effective_name() -> str:
    """The theme actually in use, resolving ``system`` via the OS scheme."""
    name = current_name()
    if name != THEME_SYSTEM:
        return name

    app = QGuiApplication.instance()
    if app is None:
        return THEME_DARK
    try:
        scheme = app.styleHints().colorScheme()
    except Exception:
        return THEME_DARK
    return THEME_LIGHT if scheme == Qt.ColorScheme.Light else THEME_DARK


def palette() -> dict:
    return PALETTES[effective_name()]()


def add_listener(callback: Callable[[], None]) -> None:
    _listeners.append(callback)


def apply(name: str | None = None, save: bool = True) -> None:
    """Apply a theme. Pass a name to switch (and persist it)."""
    if name is not None:
        if name not in THEMES:
            name = THEME_SYSTEM
        if name != CONFIG.get("theme"):
            if save:
                new_config = dict(CONFIG)
                new_config["theme"] = name
                save_config(new_config)
            CONFIG["theme"] = name

    _install_system_watch()

    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(build_stylesheet(palette()))

    for callback in list(_listeners):
        try:
            callback()
        except Exception:
            pass


def _install_system_watch() -> None:
    """Re-apply when the OS colour scheme changes and ``system`` is selected."""
    global _watch_installed
    if _watch_installed:
        return

    app = QGuiApplication.instance()
    if app is None:
        return

    try:
        app.styleHints().colorSchemeChanged.connect(lambda _scheme: _on_scheme_changed())
    except Exception:
        return
    _watch_installed = True


def _on_scheme_changed() -> None:
    if current_name() == THEME_SYSTEM:
        apply()
