import csv
import os

import pytest

from corgidrp_gui.core import caldb_info

COLS = ["Filepath", "Type", "MJD", "EXPTIME", "Files Used", "Date Created", "Hash", "DRPVERSN", "OBSNUM", "NAXIS1", "NAXIS2",
        "OPMODE", "EMGAIN_C", "EXCAMT", "CFAMNAME", "DPAMNAME", "FPAMNAME", "FSAMNAME", "SPAMNAME", "PC_STAT"]


@pytest.fixture
def fake_caldb(tmp_path, monkeypatch):
    import corgidrp
    d1, d2 = tmp_path / "cals_old", tmp_path / "cals_new"
    d1.mkdir(); d2.mkdir()
    (d1 / "flat_a.fits").write_bytes(b"")
    (d2 / "flat_b.fits").write_bytes(b"")
    (d2 / "kgain.fits").write_bytes(b"")
    rows = [
        dict.fromkeys(COLS, "-999") | {"Filepath": str(d1 / "flat_a.fits"), "Type": "FlatField", "Date Created": "61000.5", "MJD": "60990.0", "DRPVERSN": "5.0"},
        dict.fromkeys(COLS, "-999") | {"Filepath": str(d2 / "flat_b.fits"), "Type": "FlatField", "Date Created": "61100.5", "MJD": "61090.0", "DRPVERSN": "5.1"},
        dict.fromkeys(COLS, "-999") | {"Filepath": str(d2 / "kgain.fits"), "Type": "KGain", "Date Created": "61050.0", "MJD": "61000.0"},
        dict.fromkeys(COLS, "-999") | {"Filepath": str(tmp_path / "gone.fits"), "Type": "Dark", "Date Created": "61200.0"},
    ]
    p = tmp_path / "caldb.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    monkeypatch.setattr(corgidrp, "caldb_filepath", str(p))
    monkeypatch.setattr(corgidrp, "default_cal_dir", str(tmp_path / "default_calibs"))
    return tmp_path


def test_read_and_suggest(fake_caldb):
    rows = caldb_info.read_caldb()
    assert len(rows) == 4 and rows[0]["Filename"] == "flat_a.fits" and rows[0]["exists"]
    assert not [r for r in rows if r["Type"] == "Dark"][0]["exists"]
    flats = caldb_info.entries_for("FlatFieldPOL0")           # POL label maps to the FlatField type
    assert [r["Filename"] for r in flats] == ["flat_b.fits", "flat_a.fits"]   # newest first
    assert caldb_info.suggest_dir("FlatField") == str(fake_caldb / "cals_new")
    assert caldb_info.suggest_dir("KGain") == str(fake_caldb / "cals_new")
    # no entries of that type and no default dir -> the caldb's own folder
    assert caldb_info.suggest_dir("TrapCalibration") == str(fake_caldb)
    assert caldb_info.mjd_to_iso("61041.0") == "2026-01-01 00:00"
    assert caldb_info.caldb_type_for_label("NDFilterSweetSpotDataset") == "NDFilterSweetSpot"


def test_chooser_dialog(fake_caldb):
    pytest.importorskip("qtpy")
    from qtpy import QtCore
    QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
    from corgidrp_gui.app import make_app
    make_app([], restore=False)
    from corgidrp_gui.ui.dialogs import CalibChooserDialog
    d = CalibChooserDialog("FlatFieldPOL45")
    assert d.table.rowCount() == 2 and "of type FlatField" in d.info.text()
    assert d.table.item(0, 0).text() == "flat_b.fits"
    assert d._start_dir == str(fake_caldb / "cals_new")
    d.all_cb.setChecked(True)
    assert d.table.rowCount() == 4
    d.table.selectRow(2)
    d.accept()
    assert d.path and d.path.endswith("kgain.fits")
