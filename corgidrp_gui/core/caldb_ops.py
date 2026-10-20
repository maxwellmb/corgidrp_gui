"""Operations on corgidrp's calibration database, through its public API.

Every function here imports corgidrp (slow) and may take a while; the viewer
runs them in a worker thread. ``caldb_path`` may be given to work on a
database other than the configured one (tests do this).
"""
from __future__ import annotations

import os
import traceback
from dataclasses import dataclass, field

__all__ = ["OpResult", "rescan_folder", "add_files", "remove_entries", "which_calib", "which_all", "calib_labels"]


@dataclass
class OpResult:
    ok: bool
    message: str
    details: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)


def _db(caldb_path: str | None):
    import corgidrp.caldb as caldb
    return caldb.CalDB(filepath=caldb_path) if caldb_path else caldb.CalDB()


def calib_labels() -> list[str]:
    """CalDB 'Type' labels, sorted."""
    import corgidrp.caldb as caldb
    return sorted(set(caldb.labels.values()))


def rescan_folder(folder: str, subfolders: bool = True, caldb_path: str | None = None, progress=None) -> OpResult:
    """Add every calibration product found under ``folder`` (corgidrp's own scan)."""
    try:
        db = _db(caldb_path)
        before = len(db._db)
        if progress:
            progress(0, 1, os.path.basename(folder))
        db.scan_dir_for_new_entries(folder, look_in_subfolders=subfolders, to_disk=True)
        after = len(db._db)
        if progress:
            progress(1, 1, "done")
        return OpResult(True, f"scanned {folder}: {after - before} new entr{'ies' if after - before != 1 else 'y'}, {after} total")
    except Exception as exc:  # noqa: BLE001
        return OpResult(False, f"{type(exc).__name__}: {exc}", [traceback.format_exc()])


def add_files(paths: list[str], caldb_path: str | None = None, progress=None) -> OpResult:
    """Add specific files; each must load as a calibration product."""
    import corgidrp.caldb as caldb
    import corgidrp.data as data
    added, skipped = [], []
    try:
        db = _db(caldb_path)
    except Exception as exc:  # noqa: BLE001
        return OpResult(False, f"{type(exc).__name__}: {exc}", [traceback.format_exc()])
    for i, p in enumerate(paths):
        if progress:
            progress(i, len(paths), os.path.basename(p))
        try:
            frame = data.autoload(p)
            if frame.__class__ not in caldb.labels:
                skipped.append(f"{os.path.basename(p)}: {type(frame).__name__} is not a calibration product")
                continue
            db.create_entry(frame, to_disk=True)
            added.append(p)
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"{os.path.basename(p)}: {type(exc).__name__}: {exc}")
    if progress:
        progress(len(paths), len(paths), "done")
    return OpResult(not skipped or bool(added), f"added {len(added)}, skipped {len(skipped)}", skipped, {"added": added})


def remove_entries(paths: list[str], caldb_path: str | None = None) -> OpResult:
    """Remove rows by file path. Files that still load go through corgidrp's
    remove_entry; rows whose file is gone are dropped from the table directly."""
    import corgidrp.data as data
    removed, problems = [], []
    try:
        db = _db(caldb_path)
    except Exception as exc:  # noqa: BLE001
        return OpResult(False, f"{type(exc).__name__}: {exc}", [traceback.format_exc()])
    for p in paths:
        try:
            if os.path.exists(p):
                db.remove_entry(data.autoload(p), to_disk=True)
            else:
                db.load()
                mask = db._db["Filepath"] == p
                if not mask.any():
                    raise ValueError("not in the database")
                db._db = db._db[~mask].reset_index(drop=True)
                db.save()
            removed.append(p)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{os.path.basename(p)}: {type(exc).__name__}: {exc}")
    return OpResult(not problems, f"removed {len(removed)}" + (f", {len(problems)} problem(s)" if problems else ""), problems, {"removed": removed})


def which_calib(frame_path: str, label: str, caldb_path: str | None = None) -> OpResult:
    """What ``CalDB.get_calib`` would return for this frame and calibration type."""
    import corgidrp.data as data
    try:
        db = _db(caldb_path)
        frame = data.Image(frame_path)
        dtype = data.datatypes[label]
        best = db.get_calib(frame, dtype)
        return OpResult(True, best.filepath, data={"path": best.filepath})
    except Exception as exc:  # noqa: BLE001
        return OpResult(False, f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}", [traceback.format_exc()])


def which_all(frame_path: str, labels: list[str] | None = None, caldb_path: str | None = None, progress=None) -> dict[str, OpResult]:
    labels = labels or calib_labels()
    out = {}
    for i, lab in enumerate(labels):
        if progress:
            progress(i, len(labels), lab)
        out[lab] = which_calib(frame_path, lab, caldb_path)
    if progress:
        progress(len(labels), len(labels), "done")
    return out
