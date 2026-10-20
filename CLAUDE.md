# corgidrp_gui — notes for coding agents

A PySide6 desktop wrapper around `corgidrp` (the Roman Coronagraph DRP). Design doc with
approved mockups: https://claude.ai/artifact/7YrhdbQVzsr1ZNKWgrQf9P

## Hard rules
- **Never modify `../corgidrp`.** This package only imports it. No monkeypatching of corgidrp
  internals either: progress comes from parsing the walker's console output.
- Python for everything: `/opt/anaconda3/envs/corgidrp/bin/python` (corgidrp importable, PySide6,
  pytest). The base anaconda python cannot import corgidrp (old scipy).
- Qt code imports through `qtpy` (`from qtpy import QtWidgets, QtCore, QtGui`).
- `corgidrp_gui/core/` and `corgidrp_gui/backend/` must stay Qt-free and unit-tested.
- Windows never call `os`/`subprocess` for files or processes directly; they go through
  `corgidrp_gui.backend.default_backend()`.
- Step catalog: load with `core.catalog_cache.load_catalog()` (cached JSON, no corgidrp import).
  Never rebuild automatically; only from the user's explicit Rebuild action.
- Recipes run as `python -u -m corgidrp_gui.runner recipe.json`; `core.progress.ProgressParser`
  turns its stdout/stderr into events. Keep the runner a thin wrapper around `walker.run_recipe`.

## Themes
A theme is a whole style system (palette, type, shape, outline density, surface, density) in a
TOML file under `corgidrp_gui/themes/`, rendered to QSS by `corgidrp_gui/theming.py`. Use widget
properties for roles: `QPushButton[role="primary"]`, `QLabel[role="section"]`,
`QFrame[role="panel"]`, `QLabel[chip="ok|warn|err|run|dim"]`, `QTextEdit[role="log"]`.
Call `theming.decorate_panel()` on panel frames so shadow themes work.

## Tests
    /opt/anaconda3/envs/corgidrp/bin/python -m pytest -q
Core tests exercise the real corgidrp install and all of its recipe templates; GUI tests run
with `QT_QPA_PLATFORM=offscreen` (set in tests/conftest.py).

## Phases
0 scaffold + themes + launcher · 1 core · 2 Recipe Parser window · 3 Recipe Builder window ·
4 Status Console + queue · 5 CalDB viewer · 6 docs (xpra notes), packaging.
