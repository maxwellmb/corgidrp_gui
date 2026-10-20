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


class InputsDialog(QtWidgets.QDialog):
    """Edit a recipe's input file list."""

    def __init__(self, inputs: list[str], parent=None, start_dir: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Recipe inputs")
        self.resize(720, 460)
        self._start = start_dir or os.path.expanduser("~")
        lay = QtWidgets.QVBoxLayout(self)
        self.list = QtWidgets.QListWidget()
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.addItems(list(inputs))
        lay.addWidget(self.list, 1)
        row = QtWidgets.QHBoxLayout()
        for text, slot in (("Add files…", self.add_files), ("Add folder…", self.add_folder),
                           ("Remove", self.remove_selected), ("Clear", self.list.clear)):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(lambda _=False, s=slot: s())
            row.addWidget(b)
        row.addStretch(1)
        self.count = QtWidgets.QLabel()
        row.addWidget(self.count)
        lay.addLayout(row)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.list.model().rowsInserted.connect(self._update_count)
        self.list.model().rowsRemoved.connect(self._update_count)
        self._update_count()

    def _update_count(self, *_):
        n = self.list.count()
        self.count.setText(f"{n} file{'s' if n != 1 else ''}")

    def add_files(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Add input files", self._start, "FITS files (*.fits *.fit *.fits.gz);;All files (*)")
        self._add(paths)

    def add_folder(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Add every FITS file in a folder", self._start)
        if d:
            import glob as _glob
            self._add(sorted(_glob.glob(os.path.join(d, "*.fits"))))

    def _add(self, paths):
        have = set(self.inputs())
        for p in paths:
            if p not in have:
                self.list.addItem(p)
                have.add(p)
        if paths:
            self._start = os.path.dirname(paths[0])

    def remove_selected(self):
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))

    def inputs(self) -> list[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]
