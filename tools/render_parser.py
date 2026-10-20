"""Offscreen screenshots of the Recipe Parser with mock L1 files loaded, per theme."""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qtpy import QtCore  # noqa: E402

QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat, QtCore.QSettings.Scope.UserScope, tempfile.mkdtemp())

from corgidrp_gui import theming  # noqa: E402
from corgidrp_gui.app import make_app  # noqa: E402
from corgidrp_gui.ui.parser_window import ParserWindow  # noqa: E402

app = make_app([], restore=False)
tmp = tempfile.mkdtemp()
import corgidrp.mocks as mocks  # noqa: E402
files = sorted(f.filepath for f in mocks.create_prescan_files(filedir=tmp, numfiles=3))
out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "screenshots")
os.makedirs(out, exist_ok=True)
for key in sys.argv[1:] or ["roman", "console", "neon", "homepage"]:
    theming.theme_manager().set_theme(key, persist=False)
    win = ParserWindow()
    win.resize(1180, 760)
    win.outputdir_edit.setText("/data/cgi/20261020/reduced")
    win.show()
    win.add_files(files)
    win.jobs.wait_idle(120000)
    app.processEvents()
    win.grab().save(os.path.join(out, f"{key}_parser.png"))
    print("wrote", f"{key}_parser.png", "status:", win.group_model.rows[0].status, win.group_model.rows[0].message)
    win.close()
