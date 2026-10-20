# corgidrp GUI — developer notes

## Principles

- **Never modify corgidrp.** Import it, read it, call it. No monkeypatching: progress comes from
  parsing the walker's prints, not from wrapping its functions.
- **`core/` and `backend/` are Qt-free** and carry the logic; `ui/` is layout and plumbing.
  Tests exercise `core/` against the real corgidrp install and all of its recipe templates.
- Windows go through `backend.default_backend()` for file and process access.
- Python for everything: `/opt/anaconda3/envs/corgidrp/bin/python` on the development Mac.

## Layout

    corgidrp_gui/
      core/
        steps.py          StepCatalog: all_steps + inspect + Google-docstring parse + template statistics
        catalog_cache.py  JSON cache of the catalog, staleness report, rebuild on request
        recipes.py        Recipe/RecipeStep dataclasses <-> recipe JSON; validate_recipe; guess_start_level
        parser.py         scan headers, group files, recommend (guess_template), explain, build_recipes (autogen_recipe), analyze
        progress.py       ProgressParser: walker prints -> events, step timings, failing step
        queue.py          JobQueue / RecipeJob: chain dependencies, skip-on-failure, re-queue, persistence
        queue_items.py    QueueRequest handed from Parser/Builder to the console
        caldb_info.py     read the CalDB CSV (no pandas), suggest folders, label -> Type mapping
        caldb_ops.py      scan/add/remove/which-calib through corgidrp's CalDB API
        values.py         parse/format argument values (JSON, then Python literal, else string)
      backend/            Backend interface + LocalBackend
      runner.py           python -u -m corgidrp_gui.runner recipe.json  (thin wrapper around run_recipe)
      theming.py          theme files -> QSS (Jinja), palette, fonts, decoration helpers, ThemeManager
      themes/             base.qss.j2 + roman/console/neon/homepage .toml
      ui/                 launcher, parser_window, builder_window, console_window, caldb_window, theme_gallery,
                          base (ThemedWindow), models, builder_models, dialogs, queue_bridge, widgets/
      app.py              CLI, ToolWindows (one instance per tool, cross-wiring)
    tools/render_*.py     offscreen screenshots for docs/screenshots
    tests/                76+ tests; `pytest -q`

## How the pieces talk

- Parser → Builder: `ParserWindow.builder_handler(recipe)`; Builder → Console and Parser →
  Console: `queue_handler(QueueRequest) -> bool` (set by `app.ToolWindows`); Console → Builder:
  `builder_handler(recipe)`. Each window also emits a Qt signal with the same payload.
- Launcher `catalog_rebuilt` → Builder `reload_catalog()` and Parser template list refresh.

## The step catalog

`StepCatalog` derives, per step: the dataset parameter, calibration slots (positional
parameters whose docstring type names a `corgidrp.data` class, cross-checked with the `calibs`
dicts of every template at the same position), keyword arguments with signature defaults and
docstring type/description, the data level at which templates use the step, the most common
template keyword values, and predecessor/successor counts. `suggest_index` and `order_warnings`
are built on those counts. Templates agree with signatures completely as of corgidrp 5.1.1
(tests enforce it), so a mismatch after an upgrade points at a real change.

## Progress parsing

`ProgressParser.feed(line, stream)` recognises `Executing recipe:`, `number of frames:`,
`Walker step i/n: name`, Python tracebacks and `*Warning:` lines, plus the runner's own
marker lines (`corgidrp_gui recipe:`, `corgidrp_gui output:`, `corgidrp_gui finished:`). Step
end time is the next step's start or the finish marker. If the walker's prints change, update
`_RE` in `core/progress.py` and the fixtures in `tests/test_core_progress.py`.

## Themes

A theme TOML has `[meta] [palette] [type] [shape] [structure] [surface] [density]` and
optional `[extras]`. Axes:

| section | keys | effect |
|---|---|---|
| palette | bg surface surface_alt text muted primary action secondary selection selection_text ok warn err line title_bg title_fg field | all colors |
| type | ui heading data size label_case label_tracking label_size label_weight label_color | fonts, label case/tracking |
| shape | radius border_width border_style(line/bevel/none) button(pill/flat/bevel/outline) | corners, borders, buttons |
| structure | panel_frame list_frame field_frame (none/line/bevel) | how many things get a box |
| surface | shadow(none/soft) gradient glow | shading |
| density | padding row_height gap | spacing |
| extras | rainbow_rule selection_marker | theme-specific motifs |

`theming.render_qss` feeds the theme and derived colors into `themes/base.qss.j2`. Things QSS
cannot do are done in Python: letter-spacing and text case (`SectionLabel`), shadows and glows
(`decorate_panel`, `decorate_glow`), table row heights (`decorate_tree`). Use widget properties
for roles: `QPushButton[role="primary"]`, `QLabel[role="section"]`, `QFrame[role="panel"]`,
`QLabel[chip="ok|warn|err|run|dim"]`, `QLabel[step="done|running|pending"]`,
`QTextEdit[role="log"]`. User themes go in `~/.corgidrp_gui/themes/`.

## Tests and screenshots

    /opt/anaconda3/envs/corgidrp/bin/python -m pytest -q
    /opt/anaconda3/envs/corgidrp/bin/python tools/render_all.py        # all themes, all windows

GUI tests run offscreen (`QT_QPA_PLATFORM=offscreen`, set in `tests/conftest.py`) and redirect
QSettings to a temp file so they never touch your real preferences. The console tests start real
runner subprocesses on mock L1 frames made with `corgidrp.mocks`.

## Adding a window

Subclass `ui.base.ThemedWindow`, build menus with `add_menu`, `add_theme_menu`,
`add_help_menu`, use `Panel` + `SectionLabel` for the outline-density axis to work, run anything
that imports corgidrp in `widgets.workers.JobRunner`, register it in `app.ToolWindows`, and add
an offscreen test plus a `tools/render_*.py` entry.
