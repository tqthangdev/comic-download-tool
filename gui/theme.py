"""Shared Qt Style Sheet fragments, so the same look (scrollbars, etc.)
doesn't have to be copy-pasted into every widget's stylesheet across the app.
"""

# Thin, flat scrollbar matching the app's dark theme (#1e1e1e / #4a4a4a),
# with a green highlight on hover to match the app's accent color (#4CAF50).
SCROLLBAR_STYLE = """
QScrollBar:vertical {
    background: transparent;
    width: 12px;
    margin: 12px 0px 12px 0px;
}
QScrollBar::handle:vertical {
    background: #4a4a4a;
    border-radius: 0px;
    min-height: 36px;
}
QScrollBar::add-line:vertical {
    subcontrol-position: bottom;
    subcontrol-origin: margin;
    height: 12px;
    background: #3a3a3a;
    border-bottom-left-radius: 4px;
    border-bottom-right-radius: 4px;
}
QScrollBar::sub-line:vertical {
    subcontrol-position: top;
    subcontrol-origin: margin;
    height: 12px;
    background: #3a3a3a;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QScrollBar::add-line:vertical:hover, QScrollBar::sub-line:vertical:hover {
    background: #4a4a4a;
}
QScrollBar::up-arrow:vertical {
    image: url(assets/spin-up.svg);
    width: 8px;
    height: 5px;
}
QScrollBar::down-arrow:vertical {
    image: url(assets/spin-down.svg);
    width: 8px;
    height: 5px;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

QScrollBar:horizontal {
    background: transparent;
    height: 12px;
    margin: 0px 12px 0px 12px;
}
QScrollBar::handle:horizontal {
    background: #4a4a4a;
    border-radius: 5px;
    min-width: 24px;
}
QScrollBar::add-line:horizontal {
    subcontrol-position: right;
    subcontrol-origin: margin;
    width: 12px;
    background: #3a3a3a;
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
}
QScrollBar::sub-line:horizontal {
    subcontrol-position: left;
    subcontrol-origin: margin;
    width: 12px;
    background: #3a3a3a;
    border-top-left-radius: 4px;
    border-bottom-left-radius: 4px;
}
QScrollBar::add-line:horizontal:hover, QScrollBar::sub-line:horizontal:hover {
    background: #4a4a4a;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}
"""