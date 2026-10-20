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


class ToolWindows:
    """Creates each tool window once and raises it on later requests."""

    def __init__(self, launcher):
        self.launcher = launcher
        self.windows: dict[str, QtWidgets.QMainWindow] = {}
        launcher.set_tool_handler("parser", self.open_parser)
        launcher.set_tool_handler("builder", self.open_builder)
        launcher.set_tool_handler("console", self.open_console)
        launcher.catalog_rebuilt.connect(self._on_catalog_rebuilt)

    def _show(self, key, factory):
        win = self.windows.get(key)
        if win is None:
            win = factory()
            self.windows[key] = win
        win.show()
        win.raise_()
        win.activateWindow()
        return win

    def open_parser(self):
        from .ui.parser_window import ParserWindow

        def factory():
            w = ParserWindow()
            w.builder_handler = lambda recipe: self.open_builder().load_recipe(recipe)
            w.queue_handler = self._queue
            return w
        return self._show("parser", factory)

    def open_builder(self):
        from .ui.builder_window import BuilderWindow

        def factory():
            w = BuilderWindow()
            w.queue_handler = self._queue
            return w
        return self._show("builder", factory)

    def open_console(self):
        from .ui.console_window import ConsoleWindow

        def factory():
            w = ConsoleWindow()
            w.builder_handler = lambda recipe: self.open_builder().load_recipe(recipe)
            return w
        return self._show("console", factory)

    def _queue(self, req) -> bool:
        """Parser/Builder queue handler: hand the request to the console and show it."""
        self.open_console().enqueue(req)
        return True

    def _on_catalog_rebuilt(self):
        b = self.windows.get("builder")
        if b is not None:
            b.reload_catalog()
        p = self.windows.get("parser")
        if p is not None:
            p._fill_override_combo()


def main(argv: list[str] | None = None) -> int:
    from .ui.launcher import LauncherWindow

    app = make_app(argv)
    win = LauncherWindow()
    win.tools = ToolWindows(win)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
