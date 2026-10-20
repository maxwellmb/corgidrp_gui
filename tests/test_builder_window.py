"""Recipe Builder window and its models, offscreen."""
import json
import os

import pytest

pytest.importorskip("qtpy")
from qtpy import QtCore  # noqa: E402


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
    QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat, QtCore.QSettings.Scope.UserScope,
                             str(tmp_path_factory.mktemp("qsettings")))
    from corgidrp_gui.app import make_app
    return make_app([], restore=False)


@pytest.fixture
def builder(app, catalog):
    from corgidrp_gui.ui.builder_window import BuilderWindow
    w = BuilderWindow(catalog=catalog)
    w.show()
    yield w
    w._dirty = False
    w.close()


def _names(w):
    return w.recipe.step_names


def test_load_template_and_inspect(builder, catalog):
    w = builder
    w.load_template("l1_to_l2b.json")
    assert w.recipe.name == "l1_to_l2b" and not w.recipe.template
    assert w.level_chip.text() == "L1"
    assert w.steps_model.rowCount() == len(catalog.templates["l1_to_l2b.json"]["steps"])
    # select frame_select, see its args with defaults from the signature
    row = _names(w).index("frame_select")
    w.steps_view.setCurrentIndex(w.steps_model.index(row))
    am = w.args_model
    names = [am.rows[i].name for i in range(am.rowCount())]
    assert names[:3] == ["bpix_frac", "allowed_bpix", "overexp"]
    assert am.data(am.index(0, 2)) == "1.0"           # default column
    assert "frame_select" in w.step_title.text()
    assert "Selects the frames" in w.step_summary.text()
    # calibration rows for a step with slots
    row = _names(w).index("detect_cosmic_rays")
    w.steps_view.setCurrentIndex(w.steps_model.index(row))
    assert w.calib_grid.count() >= 6   # two slots x (label, type combo, spec combo)


def test_edit_argument_values(builder):
    w = builder
    w.load_template("l1_to_l2b.json")
    row = _names(w).index("frame_select")
    w.steps_view.setCurrentIndex(w.steps_model.index(row))
    am = w.args_model
    assert am.setData(am.index(0, 1), "0.05")
    step = w.recipe.steps[row]
    assert step.keywords["bpix_frac"] == 0.05 and am.is_changed(am.rows[0])
    assert am.setData(am.index(2, 1), "True")
    assert step.keywords["overexp"] is True
    assert "2 kwargs set" in w.steps_model.data(w.steps_model.index(row))
    am.setData(am.index(0, 1), "")                     # empty -> back to default
    assert "bpix_frac" not in step.keywords
    am.reset_all()
    assert step.keywords is None
    assert w._dirty and "modified" in w.status_chip.text()


def test_insert_move_remove_skip_undo(builder, catalog):
    w = builder
    w.load_template("l1_to_l2b.json")
    n = w.steps_model.rowCount()
    new_row = w.add_step("flat_division_pol")
    assert w.steps_model.rowCount() == n + 1
    assert _names(w)[new_row - 1] == "cti_correction"           # template-informed placement
    step = w.recipe.steps[new_row]
    assert step.calibs == {"FlatFieldPOL0": "AUTOMATIC", "FlatFieldPOL45": "AUTOMATIC"}
    w.steps_view._select_rows([new_row])
    w.move_selected(-1)
    assert _names(w)[new_row - 1] == "flat_division_pol"
    w.move_selected(+1)
    assert _names(w)[new_row] == "flat_division_pol"
    w.toggle_skip()
    assert w.recipe.steps[new_row].skip is True and "(skipped)" in w.steps_model.data(w.steps_model.index(new_row))
    w.toggle_skip()
    assert w.recipe.steps[new_row].skip is None
    w.duplicate_selected()
    assert _names(w)[new_row + 1] == "flat_division_pol"
    w.remove_selected()
    assert w.steps_model.rowCount() == n + 1
    w.undo()
    assert w.steps_model.rowCount() == n + 2
    # model-level drag/drop: move the block [1,2] to the end, and drop a catalog step at row 0
    m = w.steps_model
    first = _names(w)[:3]
    m.move_rows([1, 2], m.rowCount())
    assert _names(w)[-2:] == first[1:]
    from corgidrp_gui.ui.builder_models import STEP_MIME
    md = QtCore.QMimeData()
    md.setData(STEP_MIME, b"prescan_biassub")
    assert m.dropMimeData(md, QtCore.Qt.DropAction.CopyAction, 0, 0, QtCore.QModelIndex())
    assert _names(w)[0] == "prescan_biassub"


def test_issues_validation_and_json(builder):
    w = builder
    w.new_recipe()
    w.add_step("flat_division")
    txt = w.issues_label.text()
    assert "warning" in txt and "does not end with a save" in txt
    w.insert_save()
    assert "does not end with a save" not in w.issues_label.text()
    w.recipe.steps[0].keywords = {"nope": 1}
    w._refresh_issues()
    assert "1 error" in w.issues_label.text()
    d = json.loads(w.recipe.to_json())
    assert [s["name"] for s in d["steps"]] == ["flat_division", "save"]


def test_catalog_search_and_hint(builder):
    w = builder
    w.search.setText("polariz")
    f = w.catalog_filter
    shown = []
    for r in range(f.rowCount()):
        p = f.index(r, 0)
        shown += [f.index(c, 0, p).data() for c in range(f.rowCount(p))]
    assert "split_image_by_polarization_state" in shown and "prescan_biassub" not in shown, shown
    w.search.setText("")
    w.load_template("l1_to_l2b.json")
    src = w.catalog_model
    idx = None
    for r in range(src.rowCount()):
        p = src.index(r, 0)
        for c in range(src.rowCount(p)):
            if src.index(c, 0, p).data() == "flat_division_pol":
                idx = src.index(c, 0, p)
    w.catalog_view.selectionModel().select(w.catalog_filter.mapFromSource(idx), QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect)
    assert "cti_correction" in w.catalog_hint.text()


def test_save_template_queue_and_parser_handoff(builder, mock_l1_files, tmp_path, monkeypatch):
    import corgidrp
    from corgidrp_gui.core.queue_items import QueueRequest
    from corgidrp_gui.core.recipes import Recipe, RecipeStep
    w = builder
    monkeypatch.setattr(corgidrp, "user_templates_dir", str(tmp_path / "user_templates"))
    r = Recipe(name="tiny_from_parser", inputs=list(mock_l1_files), outputdir=str(tmp_path / "out"),
               steps=[RecipeStep("discard_setup_frames", keywords={"keywords_to_check": ["ISACQ"]}), RecipeStep("save")])
    w.load_recipe(r)                                   # what the Parser's button does
    assert w.recipe.name == "tiny_from_parser" and w.level_chip.text() == "L1"
    assert "2 files" in w.inputs_label.fullText()
    path = w.save_as_template(os.path.join(corgidrp.user_templates_dir, "tiny_from_parser.json"))
    saved = json.load(open(path))
    assert saved["template"] is True and saved["inputs"] == [] and saved["outputdir"] == ""
    assert w.recipe.inputs == list(mock_l1_files)      # editor copy untouched
    got = []
    w.recipes_queued.connect(got.append)
    w.queue_recipe()
    assert len(got) == 1 and isinstance(got[0], QueueRequest) and got[0].source == "builder"
    assert got[0].chains[0][0].inputs == list(mock_l1_files)
    assert os.listdir(tmp_path / "out" / "recipes")
    from qtpy import QtWidgets
    warned = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a[2]) or None))
    w.recipe.steps[0].keywords = {"bad": 1}
    w._refresh_issues()
    w.queue_recipe()
    assert len(got) == 1 and warned and "no keyword argument 'bad'" in warned[0]


def test_value_popout_dialog(app, catalog):
    from corgidrp_gui.ui.dialogs import ValueEditorDialog
    from corgidrp_gui.ui.builder_models import needs_popout
    from corgidrp_gui.core.steps import MISSING
    spec = catalog.get("prescan_biassub").arg("detector_regions")
    assert spec is not None
    regions = {"SCI": {"image": {"rows": 1024, "cols": 1024, "r0c0": [13, 1088]}}}
    assert needs_popout(spec, regions) and not needs_popout(spec, None)
    assert needs_popout(catalog.get("discard_setup_frames").arg("keywords_to_check"), ["ISACQ"])
    d = ValueEditorDialog("detector_regions", regions, None, "dict", "detector geometry")
    assert '"rows": 1024' in d.text() and "dict with 1 key" in d.status.text()
    d.edit.setPlainText('{"SCI": {"image": {"rows": 2048}}, ')
    assert "not valid JSON" in d.status.text()
    d.edit.setPlainText("{'a': (1, 2)}")
    d.reformat()
    assert d.value() == {"a": [1, 2]} and d.text().startswith("{\n")
    d.edit.setPlainText("")
    assert d.value() is MISSING and "default" in d.status.text()
