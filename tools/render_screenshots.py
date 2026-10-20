"""Render the Launcher and the Theme gallery under every theme to docs/screenshots/.

    /opt/anaconda3/envs/corgidrp/bin/python tools/render_screenshots.py [theme ...]

Runs with the offscreen Qt platform; does not change the saved theme.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qtpy import QtCore, QtGui, QtWidgets  # noqa: E402

from corgidrp_gui import theming  # noqa: E402
from corgidrp_gui.app import make_app  # noqa: E402

OUT = ROOT / "docs" / "screenshots"


def settle(app, n: int = 5) -> None:
    for _ in range(n):
        app.processEvents()


def main(argv: list[str]) -> int:
    messages: list[str] = []

    def handler(mode, ctx, msg):
        messages.append(msg)

    QtCore.qInstallMessageHandler(handler)
    app = make_app([], restore=False)
    from corgidrp_gui.ui.launcher import LauncherWindow
    from corgidrp_gui.ui.theme_gallery import ThemeGalleryWindow

    OUT.mkdir(parents=True, exist_ok=True)
    themes = [t for t in theming.available_themes() if not argv or t.key in argv]
    families = set(QtGui.QFontDatabase.families())
    for theme in themes:
        theming.theme_manager().set_theme(theme, persist=False)
        fonts = theming.theme_fonts(theme)
        wanted = {k: (theme.type.ui, theme.type.heading, theme.type.data)[i]
                  for i, k in enumerate(("ui", "heading", "data"))}
        report = ", ".join(
            f"{k}={v}{'' if v in families else ' (MISSING)'}"
            + ("" if (wanted[k] if isinstance(wanted[k], str) else wanted[k][0]) == v
               else f" [fallback for {wanted[k]}]")
            for k, v in fonts.items())
        print(f"{theme.key}: fonts {report}")
        for cls, size, name in ((ThemeGalleryWindow, (1100, 760), "gallery"),
                                (LauncherWindow, (560, 520), "launcher")):
            win = cls()
            win.resize(*size)
            win.show()
            settle(app)
            win.redecorate(theme)
            settle(app)
            path = OUT / f"{theme.key}_{name}.png"
            win.grab().save(str(path))
            print(f"  wrote {path.relative_to(ROOT)}  ({win.width()}x{win.height()})")
            win.hide()
            win.deleteLater()
            settle(app)
    bad = [m for m in messages if "Could not parse" in m or "Unknown property" in m]
    for m in bad:
        print("QSS WARNING:", m)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
