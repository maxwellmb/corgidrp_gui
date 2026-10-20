"""Small dialogs shared by the windows."""
from __future__ import annotations

import os

from qtpy import QtCore, QtGui, QtWidgets

from ..core.recipes import Recipe
from .widgets.themed import SectionLabel


class RecipePreviewDialog(QtWidgets.QDialog):
    """Read-only JSON of one or more recipes (one tab each), with Save as…"""

    def __init__(self, chains: list[list[Recipe]], parent=None, title="Recipe preview"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 640)
        self._recipes: list[Recipe] = [r for chain in chains for r in chain]
        lay = QtWidgets.QVBoxLayout(self)
        if len(chains) > 1 or (chains and len(chains[0]) > 1):
            lay.addWidget(SectionLabel(self._describe(chains)))
        self.tabs = QtWidgets.QTabWidget()
        for ci, chain in enumerate(chains):
            for ri, r in enumerate(chain):
                ed = QtWidgets.QPlainTextEdit()
                ed.setProperty("role", "log")
                ed.setReadOnly(True)
                ed.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
                ed.setPlainText(r.to_json())
                label = r.name if len(chains) == 1 else f"{ci + 1}.{ri + 1} {r.name}"
                self.tabs.addTab(ed, label)
        lay.addWidget(self.tabs, 1)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        save = QtWidgets.QPushButton("Save this recipe as…")
        save.clicked.connect(self.save_current)
        close = QtWidgets.QPushButton("Close")
        close.setProperty("role", "primary")
        close.clicked.connect(self.accept)
        row.addWidget(save)
        row.addWidget(close)
        lay.addLayout(row)

    @staticmethod
    def _describe(chains) -> str:
        if len(chains) == 1:
            return f"chain of {len(chains[0])} recipes; each runs on the outputs of the previous"
        return f"{len(chains)} separate chains"

    def current_recipe(self) -> Recipe | None:
        i = self.tabs.currentIndex()
        return self._recipes[i] if 0 <= i < len(self._recipes) else None

    def save_current(self):
        r = self.current_recipe()
        if r is None:
            return
        start = os.path.join(r.outputdir or os.path.expanduser("~"), f"{r.name}_recipe.json")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save recipe", start, "Recipe JSON (*.json)")
        if path:
            r.save(path)


def text_dialog(parent, title: str, text: str, mono: bool = True):
    """A scrollable read-only text box (tracebacks, logs)."""
    d = QtWidgets.QDialog(parent)
    d.setWindowTitle(title)
    d.resize(720, 480)
    lay = QtWidgets.QVBoxLayout(d)
    ed = QtWidgets.QPlainTextEdit()
    if mono:
        ed.setProperty("role", "log")
    ed.setReadOnly(True)
    ed.setPlainText(text)
    lay.addWidget(ed, 1)
    bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
    bb.rejected.connect(d.reject)
    bb.accepted.connect(d.accept)
    lay.addWidget(bb)
    d.open()
    return d
