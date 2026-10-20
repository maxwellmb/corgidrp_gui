"""Models behind the Recipe Builder: the step catalog tree, the recipe's step list
(drag-reorderable, accepts drops from the catalog) and the argument table."""
from __future__ import annotations

import json

from qtpy import QtCore, QtGui, QtWidgets

from .. import theming
from ..core.recipes import Recipe, RecipeStep
from ..core.steps import MISSING, SAVE_STEP_NAME, StepCatalog, StepInfo
from ..core.values import format_value, parse_value, values_equal

Qt = QtCore.Qt
STEP_MIME = "application/x-corgidrp-step"          # a step name dragged out of the catalog
ROWS_MIME = "application/x-corgidrp-recipe-rows"   # internal reorder
StepInfoRole = Qt.ItemDataRole.UserRole + 1


# --------------------------------------------------------------------------- #
# catalog tree
# --------------------------------------------------------------------------- #
class StepCatalogModel(QtGui.QStandardItemModel):
    """Categories as top-level rows, steps underneath; steps are drag sources."""

    def __init__(self, catalog: StepCatalog | None = None, parent=None):
        super().__init__(parent)
        self.catalog = catalog
        self.setHorizontalHeaderLabels(["Step"])
        if catalog is not None:
            self.set_catalog(catalog)

    def set_catalog(self, catalog: StepCatalog):
        self.catalog = catalog
        self.clear()
        self.setHorizontalHeaderLabels(["Step"])
        for cat, steps in catalog.by_category().items():
            parent = QtGui.QStandardItem(f"{cat}  ({len(steps)})")
            parent.setFlags(Qt.ItemFlag.ItemIsEnabled)
            f = parent.font()
            f.setBold(True)
            parent.setFont(f)
            for info in steps:
                it = QtGui.QStandardItem(info.name)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
                it.setData(info, StepInfoRole)
                tip = info.summary
                if info.levels:
                    tip += f"\n\nInput level in templates: {', '.join(info.levels)}"
                if info.calibs:
                    tip += "\nCalibrations: " + ", ".join(c.label for c in info.calibs)
                tip += f"\nUsed in {info.n_templates} template{'s' if info.n_templates != 1 else ''}"
                it.setToolTip(tip)
                parent.appendRow(it)
            self.appendRow(parent)

    def supportedDragActions(self):
        return Qt.DropAction.CopyAction

    def mimeTypes(self):
        return [STEP_MIME]

    def mimeData(self, indexes):
        names = [self.data(i, Qt.ItemDataRole.DisplayRole) for i in indexes if i.isValid() and i.parent().isValid()]
        md = QtCore.QMimeData()
        md.setData(STEP_MIME, "\n".join(names).encode())
        md.setText("\n".join(names))
        return md


class CatalogFilter(QtCore.QSortFilterProxyModel):
    """Case-insensitive filter on step name/summary that keeps matching categories."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRecursiveFilteringEnabled(True)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def filterAcceptsRow(self, row, parent):
        idx = self.sourceModel().index(row, 0, parent)
        if not parent.isValid():      # category: accepted if any child matches (recursive filtering)
            return super().filterAcceptsRow(row, parent)
        pat = self.filterRegularExpression().pattern().lower()
        if not pat:
            return True
        info = idx.data(StepInfoRole)
        hay = idx.data(Qt.ItemDataRole.DisplayRole).lower() + " " + (info.summary.lower() if info else "")
        hay += " " + " ".join(a.name for a in info.args) if info else ""
        return pat in hay


# --------------------------------------------------------------------------- #
# recipe steps list
# --------------------------------------------------------------------------- #
class RecipeStepsModel(QtCore.QAbstractListModel):
    """The recipe's steps. Edits go straight into the :class:`Recipe`."""

    changed = QtCore.Signal()          # any structural or value change

    def __init__(self, catalog: StepCatalog, recipe: Recipe | None = None, parent=None):
        super().__init__(parent)
        self.catalog = catalog
        self.recipe = recipe or Recipe()
        self.issues_by_step: dict[int, list] = {}

    # -- recipe access -------------------------------------------------------
    def set_recipe(self, recipe: Recipe):
        self.beginResetModel()
        self.recipe = recipe
        self.issues_by_step = {}
        self.endResetModel()
        self.changed.emit()

    def set_issues(self, issues):
        by = {}
        for i in issues:
            if i.step_index is not None:
                by.setdefault(i.step_index, []).append(i)
        self.issues_by_step = by
        if self.recipe.steps:
            self.dataChanged.emit(self.index(0), self.index(len(self.recipe.steps) - 1))

    def step(self, row: int) -> RecipeStep | None:
        if 0 <= row < len(self.recipe.steps):
            return self.recipe.steps[row]
        return None

    def info(self, row: int) -> StepInfo | None:
        s = self.step(row)
        return self.catalog.get(s.name) if s else None

    # -- mutations -----------------------------------------------------------
    def insert_step(self, row: int, step: RecipeStep) -> int:
        row = max(0, min(row, len(self.recipe.steps)))
        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        self.recipe.steps.insert(row, step)
        self.endInsertRows()
        self.changed.emit()
        return row

    def insert_new(self, step_name: str, row: int | None = None) -> tuple[int, str]:
        info = self.catalog.get(step_name)
        if info is None:
            raise KeyError(step_name)
        reason = ""
        if row is None:
            row, reason = self.catalog.suggest_index(self.recipe.step_names, step_name)
        return self.insert_step(row, RecipeStep.new(info)), reason

    def remove_rows_list(self, rows: list[int]):
        for r in sorted(set(rows), reverse=True):
            if 0 <= r < len(self.recipe.steps):
                self.beginRemoveRows(QtCore.QModelIndex(), r, r)
                del self.recipe.steps[r]
                self.endRemoveRows()
        self.changed.emit()

    def move_rows(self, rows: list[int], dest: int) -> list[int]:
        """Move ``rows`` so the block starts at ``dest`` (index before the move). Returns new rows."""
        rows = sorted(set(r for r in rows if 0 <= r < len(self.recipe.steps)))
        if not rows:
            return []
        steps = self.recipe.steps
        block = [steps[r] for r in rows]
        dest = max(0, min(dest, len(steps)))
        n_before = sum(1 for r in rows if r < dest)
        new_start = dest - n_before
        self.beginResetModel()
        for r in reversed(rows):
            del steps[r]
        for i, s in enumerate(block):
            steps.insert(new_start + i, s)
        self.endResetModel()
        self.changed.emit()
        return list(range(new_start, new_start + len(block)))

    def toggle_skip(self, rows: list[int]):
        for r in rows:
            s = self.step(r)
            if s and s.name != SAVE_STEP_NAME:
                s.skip = (not s.skip) or None
        self._emit_rows(rows)

    def notify_step_changed(self, row: int):
        self._emit_rows([row])

    def _emit_rows(self, rows):
        for r in rows:
            self.dataChanged.emit(self.index(r), self.index(r))
        self.changed.emit()

    # -- display -------------------------------------------------------------
    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.recipe.steps)

    def flags(self, index):
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDropEnabled
        if index.isValid():
            return base | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled
        return base

    def summary_for(self, step: RecipeStep, info: StepInfo | None) -> str:
        bits = []
        for label, spec in (step.calibs or {}).items():
            if spec is None:
                bits.append(f"{label}: none")
            elif "AUTOMATIC" in str(spec).upper():
                bits.append(f"{label}: AUTO" + ("?" if "OPTIONAL" in str(spec).upper() else ""))
            else:
                bits.append(f"{label}: file")
        if step.keywords:
            n = 0
            for k, v in step.keywords.items():
                a = info.arg(k) if info else None
                if a is None or a.default is MISSING or not values_equal(a.default, v):
                    n += 1
            if n:
                bits.append(f"{n} kwarg{'s' if n != 1 else ''} set")
        return " · ".join(bits)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        step = self.recipe.steps[row]
        info = self.catalog.get(step.name)
        pal = theming.current_theme().palette
        if role == Qt.ItemDataRole.DisplayRole:
            text = f"{row + 1:>2}  {step.name}"
            summ = self.summary_for(step, info)
            if summ:
                text += f"    {summ}"
            if step.skip:
                text += "    (skipped)"
            return text
        if role == Qt.ItemDataRole.ToolTipRole:
            lines = [info.summary] if info else [f"unknown step '{step.name}'"]
            for i in self.issues_by_step.get(row, []):
                lines.append(f"{i.severity}: {i.message}")
            return "\n".join(l for l in lines if l)
        if role == Qt.ItemDataRole.ForegroundRole:
            if info is None or any(i.severity == "error" for i in self.issues_by_step.get(row, [])):
                return QtGui.QColor(pal.err)
            if step.skip:
                return QtGui.QColor(pal.muted)
            if self.issues_by_step.get(row):
                return QtGui.QColor(pal.warn)
        if role == Qt.ItemDataRole.FontRole and step.skip:
            f = QtGui.QFont()
            f.setStrikeOut(True)
            return f
        if role == StepInfoRole:
            return info
        return None

    # -- drag & drop ---------------------------------------------------------
    def supportedDropActions(self):
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

    def supportedDragActions(self):
        return Qt.DropAction.MoveAction

    def mimeTypes(self):
        return [ROWS_MIME, STEP_MIME]

    def mimeData(self, indexes):
        rows = sorted({i.row() for i in indexes if i.isValid()})
        md = QtCore.QMimeData()
        md.setData(ROWS_MIME, json.dumps(rows).encode())
        return md

    def canDropMimeData(self, data, action, row, column, parent):
        return data.hasFormat(STEP_MIME) or data.hasFormat(ROWS_MIME)

    def dropMimeData(self, data, action, row, column, parent):
        if row < 0:
            row = parent.row() if parent.isValid() else len(self.recipe.steps)
        if data.hasFormat(STEP_MIME):
            names = bytes(data.data(STEP_MIME)).decode().split("\n")
            for i, n in enumerate(n for n in names if n):
                self.insert_new(n, row + i)
            return True
        if data.hasFormat(ROWS_MIME):
            rows = json.loads(bytes(data.data(ROWS_MIME)).decode())
            self.move_rows(rows, row)
            return True
        return False


class RecipeStepsView(QtWidgets.QListView):
    """List view whose internal moves are done by the model (no Qt auto-removal)."""

    rows_moved = QtCore.Signal(list)
    steps_dropped = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropOverwriteMode(False)
        self.setUniformItemSizes(True)

    def _drop_row(self, event) -> int:
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        idx = self.indexAt(pos)
        if not idx.isValid():
            return self.model().rowCount()
        rect = self.visualRect(idx)
        return idx.row() + (1 if pos.y() > rect.center().y() else 0)

    def dropEvent(self, event):
        md = event.mimeData()
        model = self.model()
        row = self._drop_row(event)
        if md.hasFormat(ROWS_MIME) and event.source() is self:
            rows = json.loads(bytes(md.data(ROWS_MIME)).decode())
            new_rows = model.move_rows(rows, row)
            event.setDropAction(Qt.DropAction.IgnoreAction)   # we moved it; don't let Qt remove the source
            event.accept()
            self._select_rows(new_rows)
            self.rows_moved.emit(new_rows)
            return
        if md.hasFormat(STEP_MIME):
            n_before = model.rowCount()
            model.dropMimeData(md, Qt.DropAction.CopyAction, row, 0, QtCore.QModelIndex())
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            added = model.rowCount() - n_before
            self._select_rows(list(range(row, row + added)))
            self.steps_dropped.emit(row)
            return
        event.ignore()

    def _select_rows(self, rows):
        sm = self.selectionModel()
        sm.clearSelection()
        for r in rows:
            sm.select(self.model().index(r), QtCore.QItemSelectionModel.SelectionFlag.Select)
        if rows:
            self.setCurrentIndex(self.model().index(rows[0]))


# --------------------------------------------------------------------------- #
# argument table
# --------------------------------------------------------------------------- #
class ArgTableModel(QtCore.QAbstractTableModel):
    HEADERS = ["Argument", "Value", "Default", "Type", "Description"]
    value_changed = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.step: RecipeStep | None = None
        self.info: StepInfo | None = None
        self.rows: list = []           # ArgSpec list plus pseudo-specs for unknown keywords

    def set_step(self, step: RecipeStep | None, info: StepInfo | None):
        self.beginResetModel()
        self.step, self.info = step, info
        self.rows = list(info.args) if info else []
        if step and step.keywords:
            known = {a.name for a in self.rows}
            from ..core.steps import ArgSpec
            for k in step.keywords:
                if k not in known:
                    self.rows.append(ArgSpec(k, MISSING, "", "(not an argument of this step)" if info and not info.accepts_var_kwargs else "(passed through **kwargs)"))
        self.endResetModel()

    def current_value(self, spec):
        if self.step and self.step.keywords and spec.name in self.step.keywords:
            return self.step.keywords[spec.name], True
        return spec.default, False

    def is_changed(self, spec) -> bool:
        v, explicit = self.current_value(spec)
        return explicit and (spec.default is MISSING or not values_equal(v, spec.default))

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def flags(self, index):
        f = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 1 and self.step is not None:
            f |= Qt.ItemFlag.ItemIsEditable
        return f

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        spec = self.rows[index.row()]
        col = index.column()
        v, explicit = self.current_value(spec)
        pal = theming.current_theme().palette
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if col == 0:
                return spec.name
            if col == 1:
                if v is MISSING:
                    return "" if role == Qt.ItemDataRole.EditRole else "(required)"
                return format_value(v)
            if col == 2:
                return "" if spec.default is MISSING else format_value(spec.default)
            if col == 3:
                return spec.type_str
            if col == 4:
                return spec.description
        if role == Qt.ItemDataRole.ToolTipRole:
            tip = f"{spec.name}"
            if spec.type_str:
                tip += f" ({spec.type_str})"
            if spec.description:
                tip += f"\n{spec.description}"
            if explicit:
                tip += "\n\nSet in this recipe" + ("" if self.is_changed(spec) else " (same as default)")
            return tip
        if role == Qt.ItemDataRole.FontRole and col in (0, 1) and self.is_changed(spec):
            f = QtGui.QFont()
            f.setBold(True)
            return f
        if role == Qt.ItemDataRole.ForegroundRole:
            if col == 1 and (v is MISSING):
                return QtGui.QColor(pal.err)
            if col == 1 and self.is_changed(spec):
                return QtGui.QColor(pal.action if pal.action != pal.text else pal.primary)
            if col in (2, 3, 4):
                return QtGui.QColor(pal.muted)
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or index.column() != 1 or self.step is None:
            return False
        spec = self.rows[index.row()]
        text = str(value)
        if text.strip() == "" and spec.default is not MISSING:
            self.step.unset_keyword(spec.name)        # empty = back to default
        else:
            self.step.set_keyword(spec.name, parse_value(text, spec.type_str))
        self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), self.columnCount() - 1))
        self.value_changed.emit(spec.name)
        return True

    def reset_row(self, row: int):
        if self.step is None:
            return
        spec = self.rows[row]
        self.step.unset_keyword(spec.name)
        if spec.default is MISSING and spec.name not in {a.name for a in (self.info.args if self.info else [])}:
            self.set_step(self.step, self.info)       # unknown keyword removed entirely
        else:
            self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount() - 1))
        self.value_changed.emit(spec.name)

    def reset_all(self):
        if self.step is None:
            return
        self.step.keywords = None
        self.set_step(self.step, self.info)
        self.value_changed.emit("*")


class ValueDelegate(QtWidgets.QStyledItemDelegate):
    """Bool arguments get a True/False/None combo; everything else a line edit."""

    def createEditor(self, parent, option, index):
        model = index.model()
        spec = model.rows[index.row()]
        hint = (spec.type_str or "").lower()
        if hint.startswith("bool") and not isinstance(spec.default, (int, float)) or isinstance(spec.default, bool):
            cb = QtWidgets.QComboBox(parent)
            cb.addItems(["True", "False", "None"])
            cb.setEditable(True)
            return cb
        ed = QtWidgets.QLineEdit(parent)
        ed.setPlaceholderText("empty = default")
        return ed

    def setEditorData(self, editor, index):
        text = index.data(Qt.ItemDataRole.EditRole) or ""
        if isinstance(editor, QtWidgets.QComboBox):
            editor.setCurrentText(text)
        else:
            editor.setText(text)

    def setModelData(self, editor, model, index):
        text = editor.currentText() if isinstance(editor, QtWidgets.QComboBox) else editor.text()
        model.setData(index, text, Qt.ItemDataRole.EditRole)
