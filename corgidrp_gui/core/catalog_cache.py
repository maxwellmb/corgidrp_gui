"""Disk cache for the step catalog, with explicit rebuild.

Introspecting corgidrp is cheap, but importing it is not (about 1.5 s), so the
GUI loads the catalog from ``~/.corgidrp_gui/step_catalog.json`` and only
rebuilds when asked (Launcher → Tools → Rebuild step catalog). The cache records
what it was built from, so the GUI can *tell* the user that corgidrp changed
without rebuilding behind their back.
"""
from __future__ import annotations

import collections
import datetime as _dt
import glob
import json
import os
import subprocess
from dataclasses import dataclass

from .steps import MISSING, ArgSpec, CalibSlot, StepCatalog, StepInfo

__all__ = ["cache_path", "CatalogStatus", "catalog_status", "load_catalog", "rebuild_catalog",
           "save_catalog", "catalog_from_dict", "catalog_to_dict"]

CACHE_VERSION = 1


def config_dir() -> str:
    d = os.environ.get("CORGIDRP_GUI_HOME") or os.path.join(os.path.expanduser("~"), ".corgidrp_gui")
    os.makedirs(d, exist_ok=True)
    return d


def cache_path() -> str:
    return os.path.join(config_dir(), "step_catalog.json")


# --------------------------------------------------------------------------- #
# fingerprint of the corgidrp install the catalog describes
# --------------------------------------------------------------------------- #
def _corgidrp_fingerprint() -> dict:
    """Version, path, git commit and newest source mtime of the live corgidrp."""
    import corgidrp
    pkg_dir = os.path.dirname(corgidrp.__file__)
    py_files = glob.glob(os.path.join(pkg_dir, "*.py"))
    tpl_files = glob.glob(os.path.join(pkg_dir, "recipe_templates", "*.json"))
    user_dir = getattr(corgidrp, "user_templates_dir", "") or ""
    user_files = glob.glob(os.path.join(user_dir, "*.json")) if user_dir and os.path.isdir(user_dir) else []
    commit = ""
    try:
        commit = subprocess.run(["git", "-C", pkg_dir, "rev-parse", "--short", "HEAD"],
                                capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    newest = max((os.path.getmtime(f) for f in py_files + tpl_files + user_files), default=0.0)
    return {
        "version": getattr(corgidrp, "__version__", "?"),
        "path": pkg_dir,
        "commit": commit,
        "n_source_files": len(py_files),
        "n_templates": len(tpl_files),
        "n_user_templates": len(user_files),
        "newest_mtime": newest,
    }


@dataclass
class CatalogStatus:
    exists: bool
    path: str
    built_at: str = ""
    built_from: dict | None = None
    n_steps: int = 0
    n_templates: int = 0
    stale_reasons: list[str] | None = None

    @property
    def stale(self) -> bool:
        return bool(self.stale_reasons)

    def one_line(self) -> str:
        if not self.exists:
            return "no step catalog yet; build it from Tools → Rebuild step catalog"
        bf = self.built_from or {}
        s = f"{self.n_steps} steps, {self.n_templates} templates, built {self.built_at[:16].replace('T', ' ')} from corgidrp {bf.get('version', '?')}"
        if bf.get("commit"):
            s += f" ({bf['commit']})"
        if self.stale:
            s += " — corgidrp has changed since: " + "; ".join(self.stale_reasons)
        return s


def catalog_status(check_corgidrp: bool = True) -> CatalogStatus:
    """Describe the cache. With ``check_corgidrp`` the live install is fingerprinted (imports corgidrp)."""
    p = cache_path()
    if not os.path.exists(p):
        return CatalogStatus(False, p)
    try:
        with open(p) as f:
            meta = json.load(f).get("meta", {})
    except (OSError, json.JSONDecodeError):
        return CatalogStatus(False, p)
    st = CatalogStatus(True, p, meta.get("built_at", ""), meta.get("built_from"), meta.get("n_steps", 0), meta.get("n_templates", 0))
    if check_corgidrp:
        try:
            now = _corgidrp_fingerprint()
        except Exception as exc:  # noqa: BLE001
            st.stale_reasons = [f"corgidrp cannot be imported ({type(exc).__name__})"]
            return st
        was = st.built_from or {}
        reasons = []
        if now["version"] != was.get("version"):
            reasons.append(f"version {was.get('version')} → {now['version']}")
        if now["commit"] and now["commit"] != was.get("commit"):
            reasons.append(f"commit {was.get('commit') or '?'} → {now['commit']}")
        if now["path"] != was.get("path"):
            reasons.append("installed in a different location")
        if now["newest_mtime"] > (was.get("newest_mtime") or 0) + 1:
            reasons.append("source or template files modified")
        if now["n_templates"] != was.get("n_templates") or now["n_user_templates"] != was.get("n_user_templates"):
            reasons.append("templates added or removed")
        st.stale_reasons = reasons
    return st


# --------------------------------------------------------------------------- #
# (de)serialisation
# --------------------------------------------------------------------------- #
def _default_to_json(v):
    if v is MISSING:
        return {"__missing__": True}
    if isinstance(v, tuple):
        return {"__tuple__": list(v)}
    return v


def _default_from_json(v):
    if isinstance(v, dict):
        if v.get("__missing__"):
            return MISSING
        if "__tuple__" in v:
            return tuple(v["__tuple__"])
    return v


def catalog_to_dict(cat: StepCatalog) -> dict:
    steps = []
    for s in cat.steps.values():
        steps.append({
            "name": s.name, "module": s.module, "category": s.category, "summary": s.summary,
            "description": s.description, "dataset_param": s.dataset_param,
            "args": [{"name": a.name, "default": _default_to_json(a.default), "type_str": a.type_str, "description": a.description} for a in s.args],
            "calibs": [{"param": c.param, "index": c.index, "datatypes": list(c.datatypes), "type_str": c.type_str,
                        "description": c.description, "template_specs": dict(c.template_specs)} for c in s.calibs],
            "accepts_var_kwargs": s.accepts_var_kwargs, "returns": s.returns, "levels": list(s.levels),
            "n_templates": s.n_templates, "template_keywords": s.template_keywords,
            "predecessors": dict(s.predecessors), "successors": dict(s.successors),
            "source_file": s.source_file, "source_line": s.source_line,
        })
    return {
        "meta": {
            "cache_version": CACHE_VERSION,
            "built_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "built_from": _corgidrp_fingerprint(),
            "n_steps": len(cat.steps), "n_templates": len(cat.templates),
        },
        "template_dirs": cat.template_dirs,
        "datatypes": sorted(cat.datatypes),
        "templates": cat.templates,
        "template_paths": cat.template_paths,
        "steps": steps,
    }


def catalog_from_dict(d: dict) -> StepCatalog:
    """Rebuild a StepCatalog from its cached form without importing corgidrp."""
    cat = StepCatalog.__new__(StepCatalog)
    cat._all_steps = {}
    cat.template_dirs = list(d.get("template_dirs", []))
    cat.datatypes = set(d.get("datatypes", []))
    cat.templates = dict(d.get("templates", {}))
    cat.template_paths = dict(d.get("template_paths", {}))
    cat.steps = {}
    for s in d.get("steps", []):
        info = StepInfo(
            name=s["name"], module=s["module"], category=s["category"], summary=s["summary"],
            description=s["description"], dataset_param=s["dataset_param"],
            args=[ArgSpec(a["name"], _default_from_json(a["default"]), a["type_str"], a["description"]) for a in s["args"]],
            calibs=[CalibSlot(c["param"], c["index"], tuple(c["datatypes"]), c["type_str"], c["description"], dict(c["template_specs"])) for c in s["calibs"]],
            accepts_var_kwargs=s["accepts_var_kwargs"], returns=s["returns"], levels=tuple(s["levels"]),
            n_templates=s["n_templates"], template_keywords=s["template_keywords"],
            predecessors=collections.Counter(s["predecessors"]), successors=collections.Counter(s["successors"]),
            source_file=s["source_file"], source_line=s["source_line"],
        )
        cat.steps[info.name] = info
    cat.cache_meta = d.get("meta", {})
    return cat


def save_catalog(cat: StepCatalog, path: str | None = None) -> str:
    path = path or cache_path()
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(catalog_to_dict(cat), f, indent=1)
    os.replace(tmp, path)
    return path


def rebuild_catalog(path: str | None = None) -> StepCatalog:
    """Introspect the live corgidrp (imports it) and overwrite the cache."""
    cat = StepCatalog()
    save_catalog(cat, path)
    cat.cache_meta = {"built_at": _dt.datetime.now().isoformat(timespec="seconds")}
    return cat


def load_catalog(rebuild: bool = False, path: str | None = None) -> StepCatalog:
    """The catalog to use: from cache if present, else built and cached."""
    path = path or cache_path()
    if not rebuild and os.path.exists(path):
        try:
            with open(path) as f:
                d = json.load(f)
            if d.get("meta", {}).get("cache_version") == CACHE_VERSION:
                return catalog_from_dict(d)
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            pass
    return rebuild_catalog(path)
