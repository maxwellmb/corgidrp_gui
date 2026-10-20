"""Read-only view of corgidrp's calibration database CSV (no pandas, no corgidrp import
needed beyond its config paths)."""
from __future__ import annotations

import csv
import datetime as _dt
import os

__all__ = ["caldb_path", "default_cal_dir", "read_caldb", "caldb_type_for_label", "entries_for",
           "suggest_dir", "mjd_to_iso", "DISPLAY_COLUMNS"]

DISPLAY_COLUMNS = ["Type", "Date Created", "MJD", "EXPTIME", "EMGAIN_C", "CFAMNAME", "DPAMNAME", "FPAMNAME", "DRPVERSN", "Files Used"]
_LABEL_ALIASES = {"NDFilterSweetSpotDataset": "NDFilterSweetSpot"}


def _cfg(name: str, fallback: str) -> str:
    try:
        import corgidrp
        v = getattr(corgidrp, name, None)
        return v or fallback
    except Exception:  # noqa: BLE001
        return fallback


def caldb_path() -> str:
    return _cfg("caldb_filepath", os.path.join(os.path.expanduser("~"), ".corgidrp", "corgidrp_caldb.csv"))


def default_cal_dir() -> str:
    return _cfg("default_cal_dir", os.path.join(os.path.expanduser("~"), ".corgidrp", "default_calibs"))


def read_caldb(path: str | None = None) -> list[dict]:
    """Rows of the CalDB CSV as dicts (strings), plus 'Filename', 'Folder' and 'exists'."""
    path = path or caldb_path()
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        fp = r.get("Filepath", "") or ""
        r["Filename"] = os.path.basename(fp)
        r["Folder"] = os.path.dirname(fp)
        r["exists"] = os.path.exists(fp)
    return rows


def caldb_type_for_label(label: str) -> str:
    """Recipe calib label -> CalDB 'Type' value (FlatFieldPOL0 -> FlatField)."""
    for suffix in ("POL0", "POL45"):
        if label.endswith(suffix):
            label = label[: -len(suffix)]
    return _LABEL_ALIASES.get(label, label)


def _created(r: dict) -> float:
    try:
        return float(r.get("Date Created") or 0)
    except ValueError:
        return 0.0


def entries_for(label: str | None, rows: list[dict] | None = None, newest_first: bool = True) -> list[dict]:
    rows = read_caldb() if rows is None else rows
    if label:
        t = caldb_type_for_label(label)
        rows = [r for r in rows if r.get("Type") == t]
    return sorted(rows, key=_created, reverse=newest_first)


def suggest_dir(label: str | None = None, rows: list[dict] | None = None) -> str:
    """Where a file chooser for this calibration type should start: the folder of the
    newest CalDB entry of that type, else the default calibrations folder."""
    for r in entries_for(label, rows):
        if r.get("Folder") and os.path.isdir(r["Folder"]):
            return r["Folder"]
    d = default_cal_dir()
    if os.path.isdir(d):
        return d
    return os.path.dirname(caldb_path()) if os.path.isdir(os.path.dirname(caldb_path())) else os.path.expanduser("~")


def mjd_to_iso(mjd) -> str:
    try:
        m = float(mjd)
    except (TypeError, ValueError):
        return str(mjd or "")
    if m <= 0:
        return ""
    return (_dt.datetime(1858, 11, 17) + _dt.timedelta(days=m)).strftime("%Y-%m-%d %H:%M")
