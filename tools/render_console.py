"""Offscreen screenshot of the Status Console mid-run and after a failure, per theme."""
import json
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qtpy import QtCore  # noqa: E402

QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat, QtCore.QSettings.Scope.UserScope, tempfile.mkdtemp())
os.environ["CORGIDRP_GUI_HOME"] = tempfile.mkdtemp()
from corgidrp_gui import theming  # noqa: E402
from corgidrp_gui.app import make_app  # noqa: E402
from corgidrp_gui.core.queue import JobQueue  # noqa: E402
from corgidrp_gui.core.queue_items import QueueRequest  # noqa: E402
from corgidrp_gui.core.recipes import Recipe, RecipeStep  # noqa: E402
from corgidrp_gui.ui.console_window import ConsoleWindow  # noqa: E402

app = make_app([], restore=False)
tmp = tempfile.mkdtemp()
import corgidrp.mocks as mocks  # noqa: E402
files = sorted(f.filepath for f in mocks.create_prescan_files(filedir=tmp, numfiles=4))
out = os.path.join(tmp, "reduced")


def tiny(name, inputs, suffix, steps=None):
    return Recipe(name=name, inputs=list(inputs), outputdir=out, steps=steps or [
        RecipeStep("discard_setup_frames", keywords={"keywords_to_check": ["ISACQ"]}),
        RecipeStep("frame_select"), RecipeStep("save", keywords={"suffix": suffix})])


shots = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "screenshots")
for key in sys.argv[1:] or ["roman", "console", "neon", "homepage", "midnight"]:
    theming.theme_manager().set_theme(key, persist=False)
    win = ConsoleWindow(queue=JobQueue(tempfile.mkdtemp()), restore=False)
    win.resize(1240, 800)
    win.show()
    bad = tiny("l2a_to_l2b_pc_1", files, "x", [RecipeStep("frame_select"), RecipeStep("no_such_step"), RecipeStep("save")])
    win.enqueue(QueueRequest(chains=[[tiny("l1_to_l2a_basic", files, "l2a"), tiny("l2a_to_l2b", [], "l2b")],
                                     [bad, tiny("l2a_to_l2b_pc_2", [], "pc")]], outputdir=out, source="parser"))
    win.wait_idle(300000)
    win.table.selectRow(0)
    app.processEvents()
    win.grab().save(os.path.join(shots, f"{key}_console.png"))
    print("wrote", f"{key}_console.png", [j.status for j in win.queue.jobs])
    win.close()
