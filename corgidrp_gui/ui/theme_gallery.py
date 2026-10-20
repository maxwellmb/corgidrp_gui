"""Theme gallery: one window that exercises every styled widget with corgidrp-like content."""

from __future__ import annotations

from qtpy import QtCore, QtGui, QtWidgets

from .. import theming
from .base import ThemedWindow
from .widgets.themed import Chip, Panel, SectionLabel, step_label

FITS_COLUMNS = ["File", "DATALVL", "VISTYPE", "DPAMNAME", "ISPC", "EXPTIME", "EMGAIN_C"]
FITS_ROWS = [
    ["cgi_0001301_l1_.fits", "L1", "CGIVST_CAL_DRK", "PUPIL", "0", "100.0", "1.0"],
    ["cgi_0001302_l1_.fits", "L1", "CGIVST_CAL_DRK", "PUPIL", "0", "100.0", "1.0"],
    ["cgi_0001303_l1_.fits", "L1", "CGIVST_CAL_DRK", "PUPIL", "0", "100.0", "1.0"],
    ["cgi_0001304_l1_.fits", "L1", "CGIVST_TDD_DI", "IMAGING", "0", "5.0", "100.0"],
    ["cgi_0001305_l1_.fits", "L1", "CGIVST_TDD_DI", "IMAGING", "0", "5.0", "100.0"],
    ["cgi_0001306_l1_.fits", "L1", "CGIVST_TDD_DI", "IMAGING", "1", "0.1", "5000.0"],
    ["cgi_0001307_l1_.fits", "L1", "CGIVST_CAL_POL_SETUP", "POL0", "0", "10.0", "20.0"],
    ["cgi_0001308_l1_.fits", "L1", "CGIVST_CAL_POL_SETUP", "POL45", "0", "10.0", "20.0"],
]
STEPS = ["prescan_biassub", "detect_cosmic_rays", "correct_nonlinearity", "update_to_l2a", "save",
         "frame_select", "convert_to_electrons", "dark_subtraction", "flat_division",
         "correct_bad_pixels", "update_to_l2b"]
KWARGS = [
    ("bpix_frac", "1.0", "1.0", "Max fraction of bad pixels before a frame is dropped"),
    ("allowed_bpix", "0", "0", "DQ bit values that do not count as bad"),
    ("overexp", "False", "False", "Drop frames flagged as over-exposed"),
    ("tt_rms_thres", "None", "None", "Tip/tilt RMS threshold"),
    ("tt_bias_thres", "None", "None", "Tip/tilt bias threshold"),
    ("discard_bad", "True", "True", "Remove rejected frames instead of only flagging them"),
    ("record_selection", "True", "True", "Write the selection into the header history"),
]
LOG_LINES = [
    "Walker step 1/6: prescan_biassub",
    "  subtracted prescan bias from 3 frames",
    "Walker step 2/6: detect_cosmic_rays",
    "  flagged 1 412 pixels (0.013 %)",
    "Walker step 3/6: detect_cosmic_rays",
    "  sat_thresh=0.7  plat_thresh=0.7  cosm_filter=1",
    "WARNING optional calibration NonLinearityCalibration not found, step skipped",
]


def _table_model(headers, rows, parent=None) -> QtGui.QStandardItemModel:
    model = QtGui.QStandardItemModel(len(rows), len(headers), parent)
    model.setHorizontalHeaderLabels(headers)
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            it = QtGui.QStandardItem(val)
            it.setEditable(False)
            model.setItem(r, c, it)
    return model


class ThemeGalleryWindow(ThemedWindow):
    """Every widget the stylesheet covers, with realistic content."""

    def __init__(self, parent=None):
        super().__init__(parent, title="Theme gallery - corgidrp GUI")
        self.setObjectName("ThemeGalleryWindow")
        self._build_menus()
        self._build_toolbar()
        self._build_body()
        sb = self.statusBar()
        sb.showMessage("8 files · 3 recipes recommended · caldb 42 entries")
        self.resize(1100, 760)

    def _build_menus(self) -> None:
        m = self.add_menu("&File")
        m.addAction("Open FITS files…")
        m.addAction("Open recipe…")
        m.addSeparator()
        m.addAction("Close").triggered.connect(self.close)
        e = self.add_menu("&Edit")
        e.addAction("Copy")
        dis = e.addAction("Paste")
        dis.setEnabled(False)
        self.add_theme_menu()
        self.add_help_menu()

    def _build_toolbar(self) -> None:
        tb = QtWidgets.QToolBar("Main")
        tb.setMovable(False)
        tb.addAction("Open files")
        tb.addAction("Rescan")
        tb.addSeparator()
        tb.addAction("Preview recipe")
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                             QtWidgets.QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        stop = QtWidgets.QPushButton("Stop")
        stop.setEnabled(False)
        tb.addWidget(stop)
        run = QtWidgets.QPushButton("Queue 3 recipes")
        run.setProperty("role", "primary")
        run.setProperty("glow", True)
        tb.addWidget(run)
        self.addToolBar(tb)
        self.primary_button = run

    # ---------------------------------------------------------------- body
    def _build_body(self) -> None:
        central = QtWidgets.QWidget()
        central.setObjectName("central")
        outer = QtWidgets.QHBoxLayout(central)
        self._outer = outer
        split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        outer.addWidget(split)

        # left: step catalog -------------------------------------------------
        left = QtWidgets.QWidget()
        ll = QtWidgets.QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(SectionLabel("Step catalog"))
        p = Panel()
        search = QtWidgets.QLineEdit()
        search.setPlaceholderText("Filter steps")
        p.layout().addWidget(search)
        self.step_list = QtWidgets.QListView()
        self.step_list.setProperty("role", "steps")
        model = QtCore.QStringListModel(STEPS, self.step_list)
        self.step_list.setModel(model)
        self.step_list.setCurrentIndex(model.index(STEPS.index("frame_select")))
        p.layout().addWidget(self.step_list, 1)
        ll.addWidget(p, 1)
        split.addWidget(left)

        # middle: files + tabs ------------------------------------------------
        mid = QtWidgets.QWidget()
        ml = QtWidgets.QVBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(SectionLabel("Input files"))
        fp = Panel()
        self.files = QtWidgets.QTableView()
        self.files.setModel(_table_model(FITS_COLUMNS, FITS_ROWS, self.files))
        self.files.setAlternatingRowColors(True)
        self.files.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.files.verticalHeader().setVisible(False)
        self.files.horizontalHeader().setStretchLastSection(True)
        self.files.resizeColumnsToContents()
        self.files.selectRow(3)
        fp.layout().addWidget(self.files)
        ml.addWidget(fp, 5)

        ml.addWidget(SectionLabel("Selected step"))
        tabs = QtWidgets.QTabWidget()
        kw = QtWidgets.QTableView()
        kw.setModel(_table_model(["name", "value", "default", "description"], KWARGS, kw))
        kw.verticalHeader().setVisible(False)
        kw.horizontalHeader().setStretchLastSection(True)
        kw.resizeColumnsToContents()
        kw.selectionModel().select(  # select without scrolling the first rows away
            kw.model().index(5, 0),
            QtCore.QItemSelectionModel.SelectionFlag.Select
            | QtCore.QItemSelectionModel.SelectionFlag.Rows)
        self.kwargs_table = kw
        tabs.addTab(self._padded(kw), "frame_select arguments")
        tree = QtWidgets.QTreeView()
        tm = QtGui.QStandardItemModel(tree)
        tm.setHorizontalHeaderLabels(["Recipe", "Steps"])
        for name, steps in [("l1_to_l2a_basic", STEPS[:5]), ("l2a_to_l2b", STEPS[5:])]:
            parent = QtGui.QStandardItem(name)
            for s in steps:
                parent.appendRow([QtGui.QStandardItem(s), QtGui.QStandardItem("")])
            tm.appendRow([parent, QtGui.QStandardItem(str(len(steps)))])
        tree.setModel(tm)
        tree.expandAll()
        tree.setColumnWidth(0, 260)
        tabs.addTab(self._padded(tree), "Recipe tree")
        self.tabs = tabs
        ml.addWidget(tabs, 4)
        split.addWidget(mid)

        # right: status, controls, log ---------------------------------------------
        right = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(SectionLabel("Run status"))
        sp = Panel()
        chips = QtWidgets.QHBoxLayout()
        chips.setSpacing(4)
        for text, kind in [("done", "ok"), ("running", "run"), ("1 optional missing", "warn"),
                           ("failed", "err"), ("waiting", "dim")]:
            chips.addWidget(Chip(text, kind))
        chips.addStretch(1)
        sp.layout().addLayout(chips)
        prog_row = QtWidgets.QHBoxLayout()
        self.progress = QtWidgets.QProgressBar()
        self.progress.setValue(43)
        prog_row.addWidget(self.progress, 1)
        pl = QtWidgets.QLabel("step 3 of 6")
        pl.setProperty("role", "muted")
        prog_row.addWidget(pl)
        sp.layout().addLayout(prog_row)
        strip = QtWidgets.QHBoxLayout()
        strip.setSpacing(3)
        for name, state in [("bias", "done"), ("cosmics", "done"), ("nonlin", "running"),
                            ("l2a", "pending"), ("save", "pending"), ("frames", "pending")]:
            strip.addWidget(step_label(name, state))
        strip.addStretch(1)
        sp.layout().addLayout(strip)
        rl.addWidget(sp)

        rl.addWidget(SectionLabel("Run options"))
        op = Panel(layout="grid")
        g: QtWidgets.QGridLayout = op.layout()
        out = QtWidgets.QLineEdit("~/corgi/reduced/2026-10-20")
        out.setProperty("role", "data")
        g.addWidget(self._key("Output dir"), 0, 0)
        g.addWidget(out, 0, 1, 1, 2)
        combo = QtWidgets.QComboBox()
        combo.addItems(["l1_to_l2a_basic", "l1_to_l2b", "l2a_to_l2b", "build_trad_dark"])
        g.addWidget(self._key("Template"), 1, 0)
        g.addWidget(combo, 1, 1, 1, 2)
        spin = QtWidgets.QSpinBox()
        spin.setRange(1, 64)
        spin.setValue(4)
        g.addWidget(self._key("Workers"), 2, 0)
        g.addWidget(spin, 2, 1)
        g.addWidget(QtWidgets.QCheckBox("skip_missing_cal_steps"), 3, 0, 1, 3)
        jit = QtWidgets.QCheckBox("jit_calib_id")
        jit.setChecked(True)
        g.addWidget(jit, 4, 0, 1, 2)
        disabled_chk = QtWidgets.QCheckBox("enforce (locked)")
        disabled_chk.setEnabled(False)
        disabled_chk.setChecked(True)
        g.addWidget(disabled_chk, 4, 2)
        dbtn = QtWidgets.QPushButton("Validate recipe")
        dbtn.setEnabled(False)
        g.addWidget(dbtn, 5, 1, 1, 2)
        g.setColumnStretch(1, 1)
        rl.addWidget(op)

        rl.addWidget(SectionLabel("Walker log"))
        log = QtWidgets.QTextEdit()
        log.setProperty("role", "log")
        log.setReadOnly(True)
        log.setPlainText("\n".join(LOG_LINES))
        log.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.NoWrap)
        self.log = log
        rl.addWidget(log, 1)
        split.addWidget(right)

        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 5)
        split.setStretchFactor(2, 3)
        split.setSizes([210, 520, 330])
        self.splitter = split
        self._columns = (ll, ml, rl)
        self.setCentralWidget(central)
        self.theme_changed(theming.current_theme())

    @staticmethod
    def _key(text: str) -> QtWidgets.QLabel:
        lab = QtWidgets.QLabel(text)
        lab.setProperty("role", "key")
        return lab

    @staticmethod
    def _padded(widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        w.setObjectName("tabPage")
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(widget)
        return w

    def theme_changed(self, theme) -> None:
        pad, gap = theme.density.padding, theme.density.gap
        m = max(pad, 8)
        self._outer.setContentsMargins(m, m, m, m)
        for lay in self._columns:
            lay.setSpacing(max(4, gap // 2 + 2))
        for page in self.tabs.findChildren(QtWidgets.QWidget, "tabPage"):
            page.layout().setContentsMargins(pad, pad, pad, pad)
        self.splitter.setHandleWidth(gap)
