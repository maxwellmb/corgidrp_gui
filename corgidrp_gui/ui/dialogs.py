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


class ValueEditorDialog(QtWidgets.QDialog):
    """Multi-line editor for one keyword argument: dicts, lists, long strings.

    The text is parsed the same way as the inline editor (JSON, then Python
    literal, else string); the status line says what it would become.
    """

    def __init__(self, name: str, value, default, type_str: str, description: str, parent=None):
        super().__init__(parent)
        from ..core.steps import MISSING
        from ..core.values import format_value
        self.setWindowTitle(f"Edit {name}")
        self.resize(640, 460)
        self._type = type_str or ""
        self._default = default
        self._missing = MISSING
        lay = QtWidgets.QVBoxLayout(self)
        head = QtWidgets.QLabel(f"<b>{name}</b>" + (f" &nbsp;<i>{type_str}</i>" if type_str else ""))
        head.setTextFormat(QtCore.Qt.TextFormat.RichText)
        lay.addWidget(head)
        if description:
            d = QtWidgets.QLabel(description)
            d.setWordWrap(True)
            lay.addWidget(d)
        self.edit = QtWidgets.QPlainTextEdit()
        self.edit.setProperty("role", "log")
        self.edit.setTabStopDistance(24)
        self.edit.setPlainText(self._initial_text(value))
        self.edit.textChanged.connect(self._update_status)
        lay.addWidget(self.edit, 1)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        row = QtWidgets.QHBoxLayout()
        fmt = QtWidgets.QPushButton("Format as JSON")
        fmt.setToolTip("Pretty-print the current text if it parses as JSON or a Python literal")
        fmt.clicked.connect(self.reformat)
        row.addWidget(fmt)
        if default is not MISSING:
            dflt = QtWidgets.QPushButton("Insert default")
            dflt.setToolTip(f"Default: {format_value(default)}")
            dflt.clicked.connect(lambda: self.edit.setPlainText(self._initial_text(default)))
            row.addWidget(dflt)
        row.addStretch(1)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        lay.addLayout(row)
        self._update_status()

    @staticmethod
    def _initial_text(value) -> str:
        import json
        from ..core.steps import MISSING
        if value is MISSING:
            return ""
        if isinstance(value, (dict, list, tuple)):
            try:
                return json.dumps(value, indent=2)
            except (TypeError, ValueError):
                return repr(value)
        if isinstance(value, str):
            return value
        from ..core.values import format_value
        return format_value(value)

    def text(self) -> str:
        return self.edit.toPlainText()

    def value(self):
        """The parsed value (empty text means 'use the default')."""
        from ..core.values import parse_value
        t = self.text()
        if t.strip() == "":
            return self._missing
        return parse_value(t, self._type)

    def reformat(self):
        import json
        v = self.value()
        if isinstance(v, (dict, list, tuple)):
            self.edit.setPlainText(json.dumps(v, indent=2))

    def _update_status(self):
        import json
        v = self.value()
        if v is self._missing:
            self.status.setText("Empty: the argument goes back to its default.")
            return
        kind = type(v).__name__
        if isinstance(v, dict):
            msg = f"dict with {len(v)} key{'s' if len(v) != 1 else ''}"
        elif isinstance(v, (list, tuple)):
            msg = f"{kind} with {len(v)} item{'s' if len(v) != 1 else ''}"
        elif isinstance(v, str):
            msg = f"string ({len(v)} chars)"
            t = self.text().strip()
            if t.startswith(("{", "[")):
                try:
                    json.loads(t)
                except ValueError as exc:
                    msg = f"not valid JSON ({exc}); would be stored as a string"
        else:
            msg = kind
        try:
            json.dumps(v)
            ok = ""
        except (TypeError, ValueError):
            ok = " — cannot be written to recipe JSON"
        self.status.setText(f"Will be stored as: {msg}{ok}")


class CalibChooserDialog(QtWidgets.QDialog):
    """Pick a calibration file: the CalDB entries of the right type first, or browse."""

    def __init__(self, label: str, parent=None, start_dir: str | None = None):
        super().__init__(parent)
        from ..core import caldb_info
        self._ci = caldb_info
        self.label = label
        self.path: str | None = None
        self.setWindowTitle(f"Choose a {label} file")
        self.resize(900, 460)
        self._rows_all = caldb_info.read_caldb()
        lay = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QHBoxLayout()
        self.info = QtWidgets.QLabel()
        top.addWidget(self.info, 1)
        self.all_cb = QtWidgets.QCheckBox("Show every type")
        self.all_cb.toggled.connect(self._fill)
        top.addWidget(self.all_cb)
        lay.addLayout(top)
        self.table = QtWidgets.QTableWidget(0, 3 + len(caldb_info.DISPLAY_COLUMNS))
        self.table.setHorizontalHeaderLabels(["File", "Created"] + caldb_info.DISPLAY_COLUMNS + ["Folder"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemDoubleClicked.connect(lambda _it: self.accept())
        self.table.itemSelectionChanged.connect(self._sync_ok)
        lay.addWidget(self.table, 1)
        row = QtWidgets.QHBoxLayout()
        browse = QtWidgets.QPushButton("Browse for another file…")
        browse.clicked.connect(self.browse)
        row.addWidget(browse)
        row.addStretch(1)
        self.bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)
        row.addWidget(self.bb)
        lay.addLayout(row)
        self._start_dir = start_dir or caldb_info.suggest_dir(label, self._rows_all)
        self._fill()

    def _fill(self, *_):
        ci = self._ci
        rows = ci.entries_for(None if self.all_cb.isChecked() else self.label, self._rows_all)
        t = ci.caldb_type_for_label(self.label)
        self.info.setText(f"{len(rows)} CalDB entr{'ies' if len(rows) != 1 else 'y'}"
                          + ("" if self.all_cb.isChecked() else f" of type {t}") + f" in {ci.caldb_path()}")
        self.table.setRowCount(0)
        for r in rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            vals = [r["Filename"], ci.mjd_to_iso(r.get("Date Created"))] + [r.get(c, "") for c in ci.DISPLAY_COLUMNS] + [r["Folder"]]
            for c, v in enumerate(vals):
                it = QtWidgets.QTableWidgetItem(str(v))
                if c == 0:
                    it.setData(QtCore.Qt.ItemDataRole.UserRole, r.get("Filepath"))
                    it.setToolTip(r.get("Filepath", ""))
                if not r["exists"]:
                    it.setForeground(QtGui.QColor("#b00000"))
                    it.setToolTip("file is missing on disk")
                self.table.setItem(i, c, it)
        self.table.resizeColumnsToContents()
        if self.table.rowCount():
            self.table.selectRow(0)
        self._sync_ok()

    def _sync_ok(self):
        self.bb.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.table.selectedItems()))

    def selected_path(self) -> str | None:
        items = self.table.selectedItems()
        if not items:
            return None
        return self.table.item(items[0].row(), 0).data(QtCore.Qt.ItemDataRole.UserRole)

    def browse(self):
        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, f"Choose a {self.label} file", self._start_dir, "FITS (*.fits);;All files (*)")
        if p:
            self.path = p
            QtWidgets.QDialog.accept(self)

    def accept(self):
        self.path = self.selected_path()
        if self.path:
            super().accept()
