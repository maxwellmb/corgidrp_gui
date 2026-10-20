"""CalDB operations on a temporary database, and the viewer window, offscreen."""
import os

import numpy as np
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


@pytest.fixture(scope="module")
def flat_files(tmp_path_factory):
    """Two FlatField calibration products saved to disk (no CalDB entry yet)."""
    import corgidrp.data as d
    import corgidrp.mocks as mocks
    folder = tmp_path_factory.mktemp("flats")
    ds = mocks.create_flatfield_dummy(filedir=str(folder), numfiles=2)
    out = []
    for i, f in enumerate(ds):
        flat = d.FlatField(np.ones((1024, 1024), dtype=np.float32), pri_hdr=f.pri_hdr.copy(), ext_hdr=f.ext_hdr.copy(), input_dataset=ds)
        flat.save(filedir=str(folder), filename=f"flat_{i}.fits")
        out.append(flat.filepath)
    return str(folder), out


def test_ops_on_temp_caldb(tmp_path, flat_files, mock_l1_files):
    from corgidrp_gui.core import caldb_info, caldb_ops
    folder, flats = flat_files
    db = str(tmp_path / "caldb.csv")
    r = caldb_ops.rescan_folder(folder, True, db)
    assert r.ok and "2 new" in r.message, r.message
    rows = caldb_info.read_caldb(db)
    assert len(rows) == 2 and {x["Type"] for x in rows} == {"FlatField"}
    r = caldb_ops.add_files(mock_l1_files[:1] + flats[:1], db)      # an L1 frame is not a calibration product
    assert r.details and "not a calibration product" in r.details[0]
    assert len(caldb_info.read_caldb(db)) == 2                         # duplicate flat replaced, not doubled
    res = caldb_ops.which_calib(mock_l1_files[0], "KGain", db)
    assert not res.ok and "No valid KGain" in res.message
    allres = caldb_ops.which_all(mock_l1_files[0], ["KGain", "FlatField"], db)
    assert set(allres) == {"KGain", "FlatField"} and all(isinstance(v.message, str) for v in allres.values())
    r = caldb_ops.remove_entries([flats[0]], db)
    assert r.ok and len(caldb_info.read_caldb(db)) == 1
    # a row whose file vanished is dropped directly from the table
    os.rename(flats[1], flats[1] + ".moved")
    try:
        assert not caldb_info.read_caldb(db)[0]["exists"]
        r = caldb_ops.remove_entries([flats[1]], db)
        assert r.ok and caldb_info.read_caldb(db) == []
    finally:
        os.rename(flats[1] + ".moved", flats[1])


def test_caldb_window(app, tmp_path, flat_files, mock_l1_files):
    from corgidrp_gui.core import caldb_ops
    from corgidrp_gui.ui.caldb_window import CalDBWindow
    folder, flats = flat_files
    db = str(tmp_path / "caldb.csv")
    caldb_ops.rescan_folder(folder, True, db)
    win = CalDBWindow(caldb_path=db)
    win.show()
    assert win.model.rowCount() == 2 and "Calibration entries · 2" in win.table_label.raw_text()
    assert win.type_combo.count() == 2 and "FlatField 2" in win.counts_label.text()
    win.search.setText("flat_1")
    assert win.proxy.rowCount() == 1
    win.search.setText("")
    win.type_combo.setCurrentText("FlatField")
    assert win.proxy.rowCount() == 2
    assert win.select_path(flats[0]) and win.selected_paths() == [flats[0]]
    # which-calib run in the worker thread
    win.frame_edit.setText(mock_l1_files[0])
    win.which_type.setCurrentText("KGain")
    win.run_which()
    assert win.jobs.wait_idle(120000)
    assert win.which_table.rowCount() == 1 and "No valid KGain" in win.which_table.item(0, 2).text()
    # remove through the window (no confirmation path)
    win.remove_paths([flats[0]])
    assert win.jobs.wait_idle(120000)
    assert win.model.rowCount() == 1
    win.add_files([flats[0]])
    assert win.jobs.wait_idle(120000)
    assert win.model.rowCount() == 2
    win.close()
