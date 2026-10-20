"""ThemedWindow: the main-window base class every corgidrp_gui window derives from.

It provides the Theme menu (radio actions for every available theme), the Help menu
with an About box, the optional rainbow rule under the menu bar, and re-decoration
(panel shadows, glows, label case/tracking, row heights) when the theme changes.
"""

from __future__ import annotations

import platform
import sys

from qtpy import QtCore, QtGui, QtWidgets

from .. import __version__, theming
from .widgets.themed import RainbowRule


def version_info() -> dict[str, str]:
    """Versions shown in the About box."""
    info = {"corgidrp_gui": __version__}
    try:
        import corgidrp
        info["corgidrp"] = getattr(corgidrp, "__version__", "unknown")
    except Exception as exc:  # pragma: no cover - depends on the environment
        info["corgidrp"] = f"not importable ({type(exc).__name__})"
    try:
        import qtpy
        info["Qt"] = f"{QtCore.qVersion()} ({qtpy.API_NAME})"
    except Exception:  # pragma: no cover
        info["Qt"] = QtCore.qVersion()
    info["Python"] = f"{platform.python_version()} ({sys.platform})"
    return info


class ThemedWindow(QtWidgets.QMainWindow):
    """QMainWindow with theme plumbing. Subclasses build menus via :meth:`add_menu`."""

    def __init__(self, parent=None, title: str = "corgidrp GUI"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._menubar = QtWidgets.QMenuBar()
        self._rainbow = RainbowRule()
        header = QtWidgets.QWidget()
        header.setObjectName("menuHeader")
        lay = QtWidgets.QVBoxLayout(header)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._menubar)
        lay.addWidget(self._rainbow)
        self.setMenuWidget(header)
        self._theme_menu: QtWidgets.QMenu | None = None
        self._theme_group = QtGui.QActionGroup(self)
        self._theme_group.setExclusive(True)
        self._theme_group.triggered.connect(self._on_theme_action)
        self._manager = theming.theme_manager()
        self._manager.changed.connect(self._on_theme_changed)
        self._update_rainbow(theming.current_theme())

    # QMainWindow.menuBar() would replace our header widget; hand out ours instead.
    def menuBar(self):  # noqa: N802 - Qt naming
        return self._menubar

    @property
    def rainbow_rule(self) -> RainbowRule:
        return self._rainbow

    # ---------------------------------------------------------------- menus
    def add_menu(self, title: str) -> QtWidgets.QMenu:
        return self._menubar.addMenu(title)

    def add_theme_menu(self) -> QtWidgets.QMenu:
        menu = self.add_menu("&Theme")
        self._theme_menu = menu
        current = theming.current_theme().key
        for theme in theming.available_themes():
            act = menu.addAction(theme.name)
            act.setCheckable(True)
            act.setData(theme.key)
            act.setToolTip(theme.meta.description)
            act.setChecked(theme.key == current)
            self._theme_group.addAction(act)
        return menu

    def add_help_menu(self) -> QtWidgets.QMenu:
        menu = self.add_menu("&Help")
        about = menu.addAction("About corgidrp_gui")
        about.setMenuRole(QtGui.QAction.MenuRole.AboutRole)
        about.triggered.connect(self.show_about)
        return menu

    def show_about(self) -> None:
        rows = "".join(f"<tr><td><b>{k}</b>&nbsp;&nbsp;</td><td>{v}</td></tr>"
                       for k, v in version_info().items())
        QtWidgets.QMessageBox.about(
            self, "About corgidrp_gui",
            "<p><b>corgidrp_gui</b> - a desktop wrapper around the corgidrp pipeline.</p>"
            f"<table>{rows}</table>")

    # ---------------------------------------------------------------- theming
    def _on_theme_action(self, action) -> None:
        key = action.data()
        if key and key != theming.current_theme().key:
            self._manager.set_theme(key)

    def _sync_theme_menu(self, theme) -> None:
        for act in self._theme_group.actions():
            act.setChecked(act.data() == theme.key)

    def _update_rainbow(self, theme) -> None:
        self._rainbow.setVisible(bool(theme.extra("rainbow_rule", False)))

    def _on_theme_changed(self, theme) -> None:
        self._sync_theme_menu(theme)
        self._update_rainbow(theme)
        self.redecorate(theme)
        self.theme_changed(theme)

    def redecorate(self, theme=None) -> None:
        """Re-apply the Python-side parts of the theme to this window's widgets."""
        theming.decorate_tree(self, theme or theming.current_theme())

    def theme_changed(self, theme) -> None:
        """Hook for subclasses."""

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_decorated_once", False):
            self._decorated_once = True
            self.redecorate()
