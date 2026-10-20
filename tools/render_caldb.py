"""Offscreen screenshot of the CalDB viewer on the configured (read-only here) database."""
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
from corgidrp_gui.ui.caldb_window import CalDBWindow  # noqa: E402

app = make_app([], restore=False)
import corgidrp.mocks as mocks  # noqa: E402
frame = sorted(f.filepath for f in mocks.create_prescan_files(filedir=tempfile.mkdtemp(), numfiles=1))[0]
shots = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "screenshots")
for key in sys.argv[1:] or ["roman"]:
    theming.theme_manager().set_theme(key, persist=False)
    win = CalDBWindow()
    win.resize(1280, 820)
    win.show()
    win.frame_edit.setText(frame)
    win.run_which()
    win.jobs.wait_idle(300000)
    win.table.selectRow(0)
    app.processEvents()
    win.grab().save(os.path.join(shots, f"{key}_caldb.png"))
    print("wrote", f"{key}_caldb.png")
    win.close()
