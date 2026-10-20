"""Calibration DB viewer: browse the CalDB table, scan folders and add or remove
entries through corgidrp's API, and ask which file would be picked for a frame."""
from __future__ import annotations

import datetime as _dt
import os

from qtpy import QtCore, QtGui, QtWidgets

from .. import theming
from ..backend import default_backend
from ..core import caldb_info, caldb_ops
from .base import ThemedWindow
from .dialogs import text_dialog
from .widgets.themed import Chip, ElidedLabel, Panel, SectionLabel
from .widgets.workers import JobRunner

Qt = QtCore.Qt
COLUMNS = [("File", "Filename"), ("Type", "Type"), ("Created", "_created"), ("Observed", "_observed"),
           ("EXPTIME", "EXPTIME"), ("EMGAIN_C", "EMGAIN_C"), ("CFAM", "CFAMNAME"), ("DPAM", "DPAMNAME"),
           ("FPAM", "FPAMNAME"), ("DRP", "DRPVERSN"), ("N in", "Files Used"), ("Folder", "Folder")]
PathRole = Qt.ItemDataRole.UserRole + 1


class CalDBModel(QtCore.QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[dict] = []

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        for r in self.rows:
            r["_created"] = caldb_info.mjd_to_iso(r.get("Date Created"))
            r["_observed"] = caldb_info.mjd_to_iso(r.get("MJD"))
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section][0]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r = self.rows[index.row()]
        key = COLUMNS[index.column()][1]
        if role == Qt.ItemDataRole.DisplayRole:
            v = r.get(key, "")
            return "" if v in ("-999", "-999.0", None) else str(v)
        if role == Qt.ItemDataRole.ToolTipRole:
            return r.get("Filepath", "") + ("" if r.get("exists") else "\n(file is missing on disk)")
        if role == Qt.ItemDataRole.ForegroundRole and not r.get("exists"):
            return QtGui.QColor(theming.current_theme().palette.err)
        if role == PathRole:
            return r.get("Filepath")
        if role == Qt.ItemDataRole.TextAlignmentRole and key in ("EXPTIME", "EMGAIN_C", "Files Used"):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None


class CalDBFilter(QtCore.QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.type_filter = ""
        self.text = ""
        self.missing_only = False

    def filterAcceptsRow(self, row, parent):
        r = self.sourceModel().rows[row]
        if self.type_filter and r.get("Type") != self.type_filter:
            return False
        if self.missing_only and r.get("exists"):
            return False
        if self.text:
            hay = " ".join(str(v) for v in r.values()).lower()
            return self.text in hay
        return True


class CalDBWindow(ThemedWindow):
    def __init__(self, parent=None, backend=None, caldb_path: str | None = None):
        super().__init__(parent, title="Calibration DB")
        self.setObjectName("CalDBWindow")
        self.backend = backend or default_backend()
        self.settings = theming.theme_manager().settings()
        self.jobs = JobRunner()
        self.caldb_path = caldb_path          # None = corgidrp's configured one
        self.model = CalDBModel()
        self.proxy = CalDBFilter()
        self.proxy.setSourceModel(self.model)
        self._build_menus()
        self._build_body()
        self.resize(1280, 820)
        geo = self.settings.value("caldb/geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self.reload()

    # ------------------------------------------------------------------ menus
    def _build_menus(self):
        m = self.add_menu("&Database")
        self._act(m, "Reload", self.reload, "F5")
        self._act(m, "Scan folder for calibration files…", self.scan_folder_dialog)
        self._act(m, "Add files…", self.add_files_dialog, "Ctrl+O")
        self._act(m, "Remove selected entries", self.remove_selected, "Delete")
        self._act(m, "Remove entries whose file is missing", self.remove_missing)
        m.addSeparator()
        self._act(m, "Open CalDB CSV", lambda: self._open_path(self.path()))
        self._act(m, "Close", self.close, "Ctrl+W")
        e = self.add_menu("&Entry")
        self._act(e, "Show FITS header", self.show_header)
        self._act(e, "Open containing folder", self.open_folder)
        self._act(e, "Copy path", self.copy_path)
        self.add_theme_menu()
        self.add_help_menu()

    @staticmethod
    def _act(menu, text, slot, shortcut=None):
        a = menu.addAction(text)
        a.triggered.connect(lambda _=False: slot())
        if shortcut:
            a.setShortcut(QtGui.QKeySequence(shortcut))
        return a

    def _build_body(self):
        theme = theming.current_theme()
        gap = theme.density.gap
        central = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(central)
        outer.setContentsMargins(gap, gap, gap, gap)
        outer.setSpacing(gap)
        self.setCentralWidget(central)

        # ---- summary + table --------------------------------------------------
        tpanel = Panel(layout="v")
        head = QtWidgets.QGridLayout()
        head.addWidget(QtWidgets.QLabel("Database"), 0, 0)
        self.path_label = ElidedLabel("")
        head.addWidget(self.path_label, 0, 1)
        head.addWidget(QtWidgets.QLabel("Default calibs"), 1, 0)
        self.default_label = ElidedLabel("")
        head.addWidget(self.default_label, 1, 1)
        self.counts_label = QtWidgets.QLabel("")
        self.counts_label.setWordWrap(True)
        head.addWidget(self.counts_label, 2, 0, 1, 2)
        head.setColumnStretch(1, 1)
        tpanel.layout().addLayout(head)
        frow = QtWidgets.QHBoxLayout()
        frow.addWidget(QtWidgets.QLabel("Type"))
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.currentTextChanged.connect(self._apply_filter)
        frow.addWidget(self.type_combo)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("search any column…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        frow.addWidget(self.search, 1)
        self.missing_cb = QtWidgets.QCheckBox("Only entries whose file is missing")
        self.missing_cb.toggled.connect(self._apply_filter)
        frow.addWidget(self.missing_cb)
        self.exclude_missing_btn = QtWidgets.QPushButton("Remove missing entries")
        self.exclude_missing_btn.setToolTip("Drop every entry whose FITS file no longer exists on disk")
        self.exclude_missing_btn.clicked.connect(self.remove_missing)
        frow.addWidget(self.exclude_missing_btn)
        tpanel.layout().addLayout(frow)
        self.table = QtWidgets.QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(2, Qt.SortOrder.DescendingOrder)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(lambda _i: self.show_header())
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._update_buttons())
        tpanel.layout().addWidget(self.table, 1)
        brow = QtWidgets.QHBoxLayout()
        self.scan_btn = QtWidgets.QPushButton("Scan folder…")
        self.scan_btn.setToolTip("Add every calibration product found in a folder (corgidrp's scan_dir_for_new_entries)")
        self.scan_btn.clicked.connect(self.scan_folder_dialog)
        self.add_btn = QtWidgets.QPushButton("Add files…")
        self.add_btn.clicked.connect(self.add_files_dialog)
        self.remove_btn = QtWidgets.QPushButton("Remove selected")
        self.remove_btn.clicked.connect(self.remove_selected)
        self.header_btn = QtWidgets.QPushButton("FITS header")
        self.header_btn.clicked.connect(self.show_header)
        self.folder_btn = QtWidgets.QPushButton("Open folder")
        self.folder_btn.clicked.connect(self.open_folder)
        self.copy_btn = QtWidgets.QPushButton("Copy path")
        self.copy_btn.clicked.connect(self.copy_path)
        self.reload_btn = QtWidgets.QPushButton("Reload")
        self.reload_btn.clicked.connect(self.reload)
        for b in (self.scan_btn, self.add_btn, self.remove_btn, self.header_btn, self.folder_btn, self.copy_btn):
            brow.addWidget(b)
        brow.addStretch(1)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.hide()
        brow.addWidget(self.progress)
        brow.addWidget(self.reload_btn)
        tpanel.layout().addLayout(brow)
        self.table_label = SectionLabel("Calibration entries")
        tsection = self._section(self.table_label, tpanel)

        # ---- which-calib tester ----------------------------------------------
        wpanel = Panel(layout="v")
        hint = QtWidgets.QLabel("Pick a science frame and see which calibration file corgidrp's CalDB would hand "
                                "each step, using the same matching rules the walker uses.")
        hint.setWordWrap(True)
        wpanel.layout().addWidget(hint)
        wrow = QtWidgets.QHBoxLayout()
        wrow.addWidget(QtWidgets.QLabel("Frame"))
        self.frame_edit = QtWidgets.QLineEdit()
        self.frame_edit.setPlaceholderText("a FITS file to match calibrations against")
        wrow.addWidget(self.frame_edit, 1)
        b = QtWidgets.QPushButton("Browse…")
        b.clicked.connect(self.browse_frame)
        wrow.addWidget(b)
        wrow.addWidget(QtWidgets.QLabel("Type"))
        self.which_type = QtWidgets.QComboBox()
        wrow.addWidget(self.which_type)
        self.which_btn = QtWidgets.QPushButton("Which file would be used?")
        self.which_btn.setProperty("role", "primary")
        self.which_btn.clicked.connect(self.run_which)
        wrow.addWidget(self.which_btn)
        wpanel.layout().addLayout(wrow)
        self.which_table = QtWidgets.QTableWidget(0, 3)
        self.which_table.setHorizontalHeaderLabels(["Type", "Chosen file", "Note"])
        self.which_table.horizontalHeader().setStretchLastSection(True)
        self.which_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.which_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.which_table.verticalHeader().setVisible(False)
        self.which_table.itemSelectionChanged.connect(self._which_selected)
        wpanel.layout().addWidget(self.which_table, 1)
        wsection = self._section(SectionLabel("Which file would be chosen?"), wpanel)

        split = QtWidgets.QSplitter(Qt.Orientation.Vertical)
        split.addWidget(tsection)
        split.addWidget(wsection)
        split.setSizes([520, 280])
        split.setChildrenCollapsible(False)
        outer.addWidget(split, 1)
        self.status_chip = Chip("idle", "dim")
        self.statusBar().addPermanentWidget(self.status_chip)

    @staticmethod
    def _section(label, body):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(label)
        lay.addWidget(body, 1)
        return w

    # ------------------------------------------------------------------ data
    def path(self) -> str:
        return self.caldb_path or caldb_info.caldb_path()

    def reload(self):
        rows = caldb_info.read_caldb(self.path())
        self.model.set_rows(rows)
        self.path_label.setFullText(self.path())
        self.default_label.setFullText(caldb_info.default_cal_dir())
        counts: dict[str, int] = {}
        for r in rows:
            counts[r.get("Type", "?")] = counts.get(r.get("Type", "?"), 0) + 1
        missing = sum(1 for r in rows if not r.get("exists"))
        self.counts_label.setText(" · ".join(f"{t} {n}" for t, n in sorted(counts.items())) or "no entries")
        self.table_label.setRawText(f"Calibration entries · {len(rows)}" + (f" · {missing} missing on disk" if missing else ""))
        cur = self.type_combo.currentText()
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        self.type_combo.addItem("All types")
        types = sorted(counts)
        self.type_combo.addItems(types)
        if cur in types:
            self.type_combo.setCurrentText(cur)
        self.type_combo.blockSignals(False)
        curw = self.which_type.currentText()
        self.which_type.clear()
        self.which_type.addItem("All types")
        try:
            all_labels = caldb_ops.calib_labels()
        except Exception:  # noqa: BLE001
            all_labels = types
        self.which_type.addItems(all_labels)
        if curw:
            self.which_type.setCurrentText(curw)
        self._apply_filter()
        self.table.resizeColumnsToContents()
        self.exclude_missing_btn.setEnabled(missing > 0)
        self.exclude_missing_btn.setText(f"Remove {missing} missing entr{'ies' if missing != 1 else 'y'}" if missing else "Remove missing entries")
        self._update_buttons()

    def _apply_filter(self, *_):
        t = self.type_combo.currentText()
        self.proxy.type_filter = "" if t in ("", "All types") else t
        self.proxy.text = self.search.text().strip().lower()
        self.proxy.missing_only = self.missing_cb.isChecked()
        self.proxy.invalidateFilter()
        self.statusBar().showMessage(f"{self.proxy.rowCount()} of {self.model.rowCount()} entries shown")

    def selected_paths(self) -> list[str]:
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        return [self.proxy.index(r, 0).data(PathRole) for r in rows]

    def select_path(self, path: str):
        for r in range(self.proxy.rowCount()):
            if self.proxy.index(r, 0).data(PathRole) == path:
                self.table.selectRow(r)
                self.table.scrollTo(self.proxy.index(r, 0))
                return True
        return False

    # --------------------------------------------------------------- actions
    def _busy(self, on: bool, text: str = ""):
        self.status_chip.setText(text or ("working" if on else "idle"))
        self.status_chip.set_kind("run" if on else "dim")
        self.progress.setVisible(on)
        for b in (self.scan_btn, self.add_btn, self.remove_btn, self.which_btn, self.reload_btn):
            b.setEnabled(not on)
        if not on:
            self._update_buttons()

    def _update_buttons(self):
        sel = self.selected_paths()
        for b in (self.remove_btn, self.header_btn, self.folder_btn, self.copy_btn):
            b.setEnabled(bool(sel) and not self.jobs.busy)

    def _on_progress(self, i, n, label):
        self.progress.setMaximum(max(n, 1))
        self.progress.setValue(i)
        self.progress.setFormat(f"{label}  %v/%m" if label and label != "done" else "%v/%m")

    def _finish(self, result: caldb_ops.OpResult, title: str):
        self._busy(False)
        self.reload()
        self.statusBar().showMessage(f"{title}: {result.message}", 10000)
        if result.details:
            text_dialog(self, title, result.message + "\n\n" + "\n".join(result.details))

    def scan_folder_dialog(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Folder to scan for calibration files",
                                                       caldb_info.default_cal_dir() if os.path.isdir(caldb_info.default_cal_dir()) else self.backend.home())
        if d:
            self.scan_folder(d, subfolders=True)

    def scan_folder(self, folder: str, subfolders: bool = True):
        self._busy(True, "scanning")
        self.jobs.start(caldb_ops.rescan_folder, folder, subfolders, self.caldb_path,
                        on_done=lambda r: self._finish(r, "Scan folder"), on_fail=self._fail, on_progress=self._on_progress)

    def add_files_dialog(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Add calibration files", caldb_info.suggest_dir(None), "FITS (*.fits);;All files (*)")
        if paths:
            self.add_files(paths)

    def add_files(self, paths: list[str]):
        self._busy(True, "adding")
        self.jobs.start(caldb_ops.add_files, paths, self.caldb_path,
                        on_done=lambda r: self._finish(r, "Add files"), on_fail=self._fail, on_progress=self._on_progress)

    def remove_selected(self):
        paths = self.selected_paths()
        if not paths:
            return
        r = QtWidgets.QMessageBox.question(self, "Remove entries", f"Remove {len(paths)} entr{'ies' if len(paths) != 1 else 'y'} from the CalDB?\n"
                                           "The FITS files themselves are not deleted.")
        if r != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.remove_paths(paths)

    def missing_paths(self) -> list[str]:
        return [r["Filepath"] for r in self.model.rows if not r.get("exists")]

    def remove_missing(self):
        paths = self.missing_paths()
        if not paths:
            self.statusBar().showMessage("Every entry's file exists; nothing to remove", 5000)
            return
        names = "\n".join(os.path.basename(p) for p in paths[:8]) + ("\n…" if len(paths) > 8 else "")
        r = QtWidgets.QMessageBox.question(
            self, "Remove missing entries",
            f"Remove {len(paths)} entr{'ies' if len(paths) != 1 else 'y'} whose file no longer exists?\n\n{names}")
        if r == QtWidgets.QMessageBox.StandardButton.Yes:
            self.remove_paths(paths)

    def remove_paths(self, paths: list[str]):
        self._busy(True, "removing")
        self.jobs.start(caldb_ops.remove_entries, paths, self.caldb_path,
                        on_done=lambda r: self._finish(r, "Remove entries"), on_fail=self._fail)

    def _fail(self, tb: str):
        self._busy(False)
        text_dialog(self, "CalDB error", tb)

    def show_header(self):
        paths = self.selected_paths()
        if not paths:
            return
        h = self.backend.read_headers(paths[0])
        if h.error:
            text_dialog(self, os.path.basename(paths[0]), h.error)
            return
        lines = [f"# primary header ({len(h.pri)} keys)"] + [f"{k:<8} = {v!r}" for k, v in h.pri.items()]
        lines += ["", f"# extension header ({len(h.ext)} keys)"] + [f"{k:<8} = {v!r}" for k, v in h.ext.items()]
        text_dialog(self, os.path.basename(paths[0]), "\n".join(lines))

    def open_folder(self):
        paths = self.selected_paths()
        if paths:
            self._open_path(os.path.dirname(paths[0]))

    def copy_path(self):
        paths = self.selected_paths()
        if paths:
            QtWidgets.QApplication.clipboard().setText("\n".join(paths))
            self.statusBar().showMessage(f"Copied {len(paths)} path{'s' if len(paths) != 1 else ''}", 4000)

    def _open_path(self, p: str):
        if p and self.backend.exists(p):
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(p))

    # ------------------------------------------------------------ which-calib
    def browse_frame(self):
        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Science frame", self.settings.value("parser/last_dir", self.backend.home(), type=str), "FITS (*.fits);;All files (*)")
        if p:
            self.frame_edit.setText(p)

    def run_which(self):
        frame = self.frame_edit.text().strip()
        if not frame or not self.backend.exists(frame):
            QtWidgets.QMessageBox.warning(self, "Which file", "Choose an existing FITS frame first.")
            return
        t = self.which_type.currentText()
        labels = None if t in ("", "All types") else [t]
        self._busy(True, "matching")
        self.which_table.setRowCount(0)
        self.jobs.start(caldb_ops.which_all, frame, labels, self.caldb_path,
                        on_done=self._show_which, on_fail=self._fail, on_progress=self._on_progress)

    def _show_which(self, results: dict):
        self._busy(False)
        pal = theming.current_theme().palette
        self.which_table.setRowCount(0)
        for label, res in results.items():
            i = self.which_table.rowCount()
            self.which_table.insertRow(i)
            self.which_table.setItem(i, 0, QtWidgets.QTableWidgetItem(label))
            f = QtWidgets.QTableWidgetItem(os.path.basename(res.message) if res.ok else "—")
            f.setData(PathRole, res.data.get("path") if res.ok else None)
            f.setToolTip(res.message)
            note = QtWidgets.QTableWidgetItem("" if res.ok else res.message)
            if not res.ok:
                note.setForeground(QtGui.QColor(pal.err if "Error" in res.message and "No valid" not in res.message else pal.warn))
                note.setToolTip("\n".join(res.details))
            else:
                f.setForeground(QtGui.QColor(pal.ok))
            self.which_table.setItem(i, 1, f)
            self.which_table.setItem(i, 2, note)
        self.which_table.resizeColumnsToContents()
        n_ok = sum(1 for r in results.values() if r.ok)
        self.statusBar().showMessage(f"{n_ok} of {len(results)} calibration types resolve for this frame", 10000)

    def _which_selected(self):
        items = self.which_table.selectedItems()
        if items:
            p = self.which_table.item(items[0].row(), 1).data(PathRole)
            if p:
                self.type_combo.setCurrentText("All types")
                self.select_path(p)

    def closeEvent(self, event):
        self.settings.setValue("caldb/geometry", self.saveGeometry())
        super().closeEvent(event)
