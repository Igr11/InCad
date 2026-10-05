"""Light/dark palettes, the InCad Qt stylesheet, icons and the 3D-view background colors."""
import os

from incad.core import prefs

PALETTES = {
    "light": dict(window="#ececec", panel="#f7f7f7", panel_alt="#f3f3f3", border="#c8c8c8", text="#1d1d1f",
                  text_dim="#888888", accent="#0a64d6", accent_soft="#dbe9fb", selection_text="#ffffff",
                  error="#b00020", rolled_back="#999999", eop="#b00020",
                  view_top="#cfd8e3", view_bottom="#f4f6f9"),
    "dark": dict(window="#1e1e1e", panel="#323234", panel_alt="#262628", border="#111111", text="#e6e6e6",
                 text_dim="#888888", accent="#5aa2ff", accent_soft="#1f3b5e", selection_text="#ffffff",
                 error="#ff6b7f", rolled_back="#777777", eop="#ff6b7f",
                 view_top="#2b3440", view_bottom="#14181e"),
}
ICON_PX = {"small": 16, "medium": 24, "large": 32}
ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", "icons")

STYLE = """
QWidget#InCadTitle {{ background: {window}; color: {text}; border-bottom: 1px solid {border}; }}
QLabel#InCadDocName {{ color: {text}; font-weight: 600; }}
QWidget#InCadRibbon {{ background: {panel}; color: {text}; border-bottom: 1px solid {border}; }}
QTabBar#InCadRibbonTabs {{ background: {window}; }}
QTabBar#InCadRibbonTabs::tab {{ background: {window}; color: {text}; padding: 5px 14px; border: none; }}
QTabBar#InCadRibbonTabs::tab:selected {{ background: {panel}; color: {accent}; font-weight: 600; }}
QFrame#InCadRibbonGroup {{ border: none; border-right: 1px solid {border}; }}
QLabel#InCadRibbonGroupLabel {{ color: {text_dim}; font-size: 10px; }}
QToolButton {{ color: {text}; border: none; border-radius: 6px; padding: 3px; background: transparent; }}
QToolButton:hover {{ background: {accent_soft}; }}
QToolButton:checked {{ background: {accent_soft}; }}
QWidget#InCadBrowser {{ background: {panel_alt}; color: {text}; }}
QTreeWidget#InCadTree, QTableWidget#InCadParams {{ background: {panel_alt}; color: {text}; border: none; }}
QTreeWidget#InCadTree::item:selected {{ background: {accent}; color: {selection_text}; }}
QLabel#InCadPanelHeader {{ color: {text_dim}; font-weight: 600; font-size: 11px; padding: 6px 8px; }}
QHeaderView::section {{ background: {panel}; color: {text_dim}; border: none; padding: 2px 6px; }}
QWidget#InCadStatus {{ background: {window}; color: {text_dim}; border-top: 1px solid {border}; }}
QWidget#InCadStatus QLabel {{ color: {text_dim}; padding: 0 8px; }}
QDialog#InCadNewDialog {{ background: {panel}; color: {text}; }}
QDialog#InCadNewDialog QLabel, QDialog#InCadNewDialog QCheckBox {{ color: {text}; }}
QPushButton#InCadTile {{ background: {panel_alt}; color: {text}; border: 1px solid {border}; border-radius: 9px; padding: 12px; }}
QPushButton#InCadTile:checked {{ border: 2px solid {accent}; }}
QPushButton#InCadTile:disabled {{ color: {text_dim}; }}
"""

VIEW_GROUP = "User parameter:BaseApp/Preferences/View"
VIEW_KEYS = {"Simple": "Bool", "Gradient": "Bool", "RadialGradient": "Bool", "UseBackgroundColorMid": "Bool",
             "BackgroundColor2": "Unsigned", "BackgroundColor3": "Unsigned"}


def resolve(pref, system_dark):
    if pref in ("light", "dark"):
        return pref
    return "dark" if system_dark else "light"


def system_is_dark():
    from incad.qt import QtCore, QtWidgets
    app = QtWidgets.QApplication.instance()
    if app is None:
        return False
    return app.styleHints().colorScheme() == QtCore.Qt.ColorScheme.Dark


def current():
    return resolve(prefs.theme(), system_is_dark())


def toggled(theme):
    return "light" if theme == "dark" else "dark"


def icon_path(name, theme):
    return os.path.join(ICON_DIR, theme, name + ".svg")


def icon(name, theme):
    from incad.qt import QtGui
    return QtGui.QIcon(icon_path(name, theme))


def stylesheet(theme):
    return STYLE.format(**PALETTES[theme])


def _rgba(hex_color):
    return (int(hex_color.lstrip("#"), 16) << 8) | 0xFF


def view_params(theme):
    """FreeCAD 'View' parameters that give the 3D view InCad's gradient background."""
    p = PALETTES[theme]
    return {"Simple": ("Bool", False), "Gradient": ("Bool", True), "RadialGradient": ("Bool", False),
            "UseBackgroundColorMid": ("Bool", False),
            "BackgroundColor2": ("Unsigned", _rgba(p["view_top"])),
            "BackgroundColor3": ("Unsigned", _rgba(p["view_bottom"]))}
