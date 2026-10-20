"""Offscreen screenshots of the Recipe Builder with a template loaded, per theme."""
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
from corgidrp_gui.ui.builder_window import BuilderWindow  # noqa: E402

app = make_app([], restore=False)
out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "screenshots")
for key in sys.argv[1:] or ["roman", "console", "neon", "homepage"]:
    theming.theme_manager().set_theme(key, persist=False)
    w = BuilderWindow()
    w.resize(1320, 820)
    w.show()
    w.load_template("l1_to_l2b_pol.json")
    row = w.recipe.step_names.index("frame_select")
    w.steps_view.setCurrentIndex(w.steps_model.index(row))
    w.args_model.setData(w.args_model.index(0, 1), "0.05")
    w.args_model.setData(w.args_model.index(2, 1), "True")
    w.outputdir_edit.setText("/data/cgi/20261020/reduced")
    app.processEvents()
    w.grab().save(os.path.join(out, f"{key}_builder.png"))
    print("wrote", f"{key}_builder.png")
    w._dirty = False
    w.close()
