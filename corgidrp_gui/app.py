"""Application entry point: ``corgidrp-gui``."""

from __future__ import annotations

import sys

from qtpy import QtWidgets

from . import theming


def make_app(argv: list[str] | None = None, theme: str | None = None,
             restore: bool = True) -> QtWidgets.QApplication:
    """Create (or reuse) the QApplication and apply a theme.

    ``theme`` forces a theme without persisting it; otherwise the saved theme
    (QSettings key ``theme``, default ``roman``) is restored when ``restore`` is true.
    """
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(list(argv if argv is not None else sys.argv))
    app.setApplicationName("corgidrp GUI")
    app.setOrganizationName(theming.SETTINGS_ORG)
    manager = theming.theme_manager()
    if theme is not None:
        manager.set_theme(theme, persist=False)
    elif restore:
        manager.restore()
    else:
        manager.set_theme(theming.DEFAULT_THEME, persist=False)
    return app


def main(argv: list[str] | None = None) -> int:
    from .ui.launcher import LauncherWindow

    app = make_app(argv)
    win = LauncherWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
