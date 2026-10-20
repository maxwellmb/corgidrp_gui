"""Step catalog: everything the GUI knows about corgidrp step functions.

Built from three read-only sources inside corgidrp:

* ``corgidrp.walker.all_steps`` - the registry of step functions,
* each function's signature and Google-style docstring,
* the recipe templates shipped with corgidrp (plus the user's own), which tell
  us which calibration products each step takes, the usual keyword values, and
  the usual ordering of steps.

Nothing here imports Qt and nothing here modifies corgidrp.
"""
from __future__ import annotations

import collections
import glob
import inspect
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

__all__ = [
    "MISSING", "ArgSpec", "CalibSlot", "StepInfo", "StepCatalog",
    "SAVE_STEP_NAME", "parse_google_args",
]


class _Missing:
    """Sentinel for 'no default' (a required argument)."""

    def __repr__(self):
        return "MISSING"

    def __bool__(self):
        return False


MISSING = _Missing()
SAVE_STEP_NAME = "save"

#: display category per corgidrp module, in pipeline order
_MODULE_CATEGORY = [
    ("l1_to_l2a", "L1 → L2a"),
    ("l2a_to_l2b", "L2a → L2b"),
    ("l2b_to_l3", "L2b → L3"),
    ("l3_to_l4", "L3 → L4"),
    ("l4_to_tda", "L4 → TDA"),
    ("combine", "Combining & sorting"),
    ("sorting", "Combining & sorting"),
    ("photon_counting", "Combining & sorting"),
    ("darks", "Calibration products"),
    ("calibrate_kgain", "Calibration products"),
    ("calibrate_nonlin", "Calibration products"),
    ("bad_pixel_calibration", "Calibration products"),
    ("flat", "Calibration products"),
    ("pump_trap_calibration", "Calibration products"),
    ("detector", "Calibration products"),
    ("astrom", "Astrometry"),
    ("fluxcal", "Flux calibration"),
    ("nd_filter_calibration", "Flux calibration"),
    ("corethroughput", "Core throughput"),
    ("pol", "Polarimetry"),
    ("spec", "Spectroscopy"),
]
CATEGORY_ORDER = []
for _m, _c in _MODULE_CATEGORY:
    if _c not in CATEGORY_ORDER:
        CATEGORY_ORDER.append(_c)
CATEGORY_ORDER.append("Other")

#: docstring type names that differ from the data.datatypes label
_DATATYPE_ALIASES = {
    "NonLinearityCorrection": "NonLinearityCalibration",
    "FluxCalibration": "FluxcalFactor",
    "NDFilterSweetSpot": "NDFilterSweetSpotDataset",
}
#: corgidrp.data classes that are not calibration products
_NOT_CALIB = {"Dataset", "Image"}

#: step name -> data level of the frames *after* it runs
_LEVEL_AFTER = {
    "update_to_l2a": "L2a",
    "update_to_intermediate": "L2a",
    "update_to_l2b": "L2b",
    "update_to_l3": "L3",
    "update_to_l4": "L4",
    "update_to_l4_pol": "L4",
}
_TEMPLATE_LEVEL_RE = re.compile(r"^(l1|l2a|l2b|l3|l4)_", re.I)
_LEVEL_ORDER = ["L1", "L2a", "L2b", "L3", "L4"]


# --------------------------------------------------------------------------- #
# dataclasses
# --------------------------------------------------------------------------- #
@dataclass
class ArgSpec:
    """One keyword argument of a step function."""
    name: str
    default: Any = MISSING
    type_str: str = ""
    description: str = ""

    @property
    def required(self) -> bool:
        return self.default is MISSING

    def default_repr(self) -> str:
        return "" if self.required else repr(self.default)


@dataclass
class CalibSlot:
    """One positional calibration-product argument of a step function."""
    param: str
    index: int                      # position among the args after the dataset
    datatypes: tuple[str, ...]      # labels usable as keys in a recipe's "calibs"
    type_str: str = ""
    description: str = ""
    template_specs: dict[str, str] = field(default_factory=dict)  # label -> "AUTOMATIC" etc.

    @property
    def label(self) -> str:
        return self.datatypes[0] if self.datatypes else self.param

    @property
    def optional_in_templates(self) -> bool:
        specs = [s.upper() for s in self.template_specs.values()]
        return bool(specs) and all("OPTIONAL" in s for s in specs)


@dataclass
class StepInfo:
    """Everything the GUI shows about one step."""
    name: str
    module: str
    category: str
    summary: str
    description: str
    dataset_param: str
    args: list[ArgSpec]
    calibs: list[CalibSlot]
    accepts_var_kwargs: bool = False
    returns: str = ""
    levels: tuple[str, ...] = ()               # input data levels seen in templates, most common first
    n_templates: int = 0
    template_keywords: dict[str, Any] = field(default_factory=dict)
    predecessors: collections.Counter = field(default_factory=collections.Counter)
    successors: collections.Counter = field(default_factory=collections.Counter)
    source_file: str = ""
    source_line: int = 0

    @property
    def qualname(self) -> str:
        return f"corgidrp.{self.module}.{self.name}"

    def arg(self, name: str) -> ArgSpec | None:
        for a in self.args:
            if a.name == name:
                return a
        return None

    def default_calibs(self) -> dict[str, str]:
        """The 'calibs' dict a new instance of this step should start with."""
        out = {}
        for slot in self.calibs:
            if slot.template_specs:
                # most common label in templates, with its most common spec
                label = next(iter(slot.template_specs))
                out[label] = slot.template_specs[label]
            else:
                out[slot.label] = "AUTOMATIC"
        return out

    def default_keywords(self) -> dict[str, Any]:
        """Keywords a new instance should carry: what templates usually set."""
        return dict(self.template_keywords)


# --------------------------------------------------------------------------- #
# docstring parsing
# --------------------------------------------------------------------------- #
_ARG_LINE = re.compile(r"^(?P<indent>\s*)(?P<name>\*{0,2}[A-Za-z_]\w*)\s*(?:\((?P<type>[^)]*)\))?\s*:\s*(?P<desc>.*)$")
_SECTION = re.compile(r"^(Args|Arguments|Parameters|Returns|Return|Raises|Yields|Notes?|Examples?|References?|See Also|Attributes|Todo)\s*:\s*$", re.I)


def parse_google_args(doc: str) -> tuple[dict[str, tuple[str, str]], str, str]:
    """Parse a Google-style docstring.

    Returns ``(args, summary, returns)`` where ``args`` maps a parameter name
    to ``(type_str, description)``, ``summary`` is the text before the first
    section, and ``returns`` is the text of the Returns section.
    """
    doc = inspect.cleandoc(doc or "")
    lines = doc.splitlines()
    args: dict[str, tuple[str, str]] = {}
    summary_lines: list[str] = []
    returns_lines: list[str] = []
    section = "summary"
    current: str | None = None
    cur_indent = 0
    for raw in lines:
        m = _SECTION.match(raw.strip())
        if m and (not raw.startswith(" ") or raw.strip() == raw.strip()):
            section = m.group(1).lower()
            current = None
            continue
        if section == "summary":
            summary_lines.append(raw)
        elif section in ("args", "arguments", "parameters"):
            if not raw.strip():
                continue
            indent = len(raw) - len(raw.lstrip())
            am = _ARG_LINE.match(raw)
            if am and (current is None or indent <= cur_indent):
                current = am.group("name").lstrip("*")
                cur_indent = indent
                args[current] = ((am.group("type") or "").strip(), am.group("desc").strip())
            elif current is not None:
                t, d = args[current]
                args[current] = (t, (d + " " + raw.strip()).strip())
        elif section in ("returns", "return"):
            returns_lines.append(raw.strip())
    summary = "\n".join(summary_lines).strip()
    return args, summary, " ".join(l for l in returns_lines if l).strip()


def _datatypes_from_type_str(type_str: str, known: Iterable[str]) -> tuple[str, ...]:
    """'corgidrp.data.Dark or corgidrp.data.DetectorNoiseMaps' -> ('Dark', 'DetectorNoiseMaps')."""
    known = set(known)
    out = []
    for m in re.finditer(r"(?:corgidrp\.)?[Dd]ata\.([A-Za-z_]\w*)", type_str or ""):
        cls = _DATATYPE_ALIASES.get(m.group(1), m.group(1))
        if cls in known and cls not in _NOT_CALIB and cls not in out:
            out.append(cls)
    return tuple(out)


# --------------------------------------------------------------------------- #
# catalog
# --------------------------------------------------------------------------- #
class StepCatalog:
    """Catalog of corgidrp steps, built lazily from the live corgidrp install.

    Parameters
    ----------
    all_steps : mapping, optional
        Defaults to ``corgidrp.walker.all_steps``.
    template_dirs : list of str, optional
        Directories of recipe templates, later ones override earlier ones by
        filename. Defaults to corgidrp's shipped templates then the user's.
    """

    def __init__(self, all_steps=None, template_dirs=None, datatypes=None):
        if all_steps is None or template_dirs is None or datatypes is None:
            import corgidrp
            import corgidrp.data as cdata
            import corgidrp.walker as walker
            if all_steps is None:
                all_steps = walker.all_steps
            if template_dirs is None:
                template_dirs = [walker.recipe_dir]
                if getattr(corgidrp, "user_templates_dir", None) and os.path.isdir(corgidrp.user_templates_dir):
                    template_dirs.append(corgidrp.user_templates_dir)
            if datatypes is None:
                datatypes = set(cdata.datatypes.keys())
        self._all_steps = dict(all_steps)
        self.template_dirs = list(template_dirs)
        self.datatypes = set(datatypes)
        self.templates: dict[str, dict] = {}
        self.template_paths: dict[str, str] = {}
        self._load_templates()
        self.steps: dict[str, StepInfo] = {}
        self._build()

    # -- templates ---------------------------------------------------------
    def _load_templates(self):
        for d in self.template_dirs:
            for path in sorted(glob.glob(os.path.join(d, "*.json"))):
                try:
                    with open(path) as f:
                        tpl = json.load(f)
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(tpl, dict) or "steps" not in tpl:
                    continue
                name = os.path.basename(path)
                self.templates[name] = tpl
                self.template_paths[name] = path

    def is_user_template(self, filename: str) -> bool:
        path = self.template_paths.get(filename, "")
        return bool(path) and len(self.template_dirs) > 1 and path.startswith(self.template_dirs[-1])

    @staticmethod
    def _template_start_level(filename: str, tpl: dict) -> str | None:
        m = _TEMPLATE_LEVEL_RE.match(filename)
        if m:
            return m.group(1).upper().replace("L2A", "L2a").replace("L2B", "L2b")
        first = tpl["steps"][0]["name"] if tpl.get("steps") else ""
        if first in ("prescan_biassub", "sort_pupilimg_frames", "calibrate_trap_pump"):
            return "L1"
        return None

    # -- build ---------------------------------------------------------------
    def _build(self):
        # 1. per-step template statistics
        calib_slots: dict[str, dict[int, collections.Counter]] = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
        calib_specs: dict[str, dict[str, collections.Counter]] = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
        kw_values: dict[str, dict[str, collections.Counter]] = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
        levels: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        n_templates: collections.Counter = collections.Counter()
        preds: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        succs: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)

        for fname, tpl in self.templates.items():
            level = self._template_start_level(fname, tpl)
            names = [s.get("name", "") for s in tpl.get("steps", [])]
            for i, step in enumerate(tpl.get("steps", [])):
                n = step.get("name", "")
                n_templates[n] += 1
                if level:
                    levels[n][level] += 1
                for j, (label, spec) in enumerate((step.get("calibs") or {}).items()):
                    calib_slots[n][j][label] += 1
                    calib_specs[n][label][str(spec)] += 1
                for k, v in (step.get("keywords") or {}).items():
                    kw_values[n][k][json.dumps(v, sort_keys=True)] += 1
                if i > 0:
                    preds[n][names[i - 1]] += 1
                if i + 1 < len(names):
                    succs[n][names[i + 1]] += 1
                level = _LEVEL_AFTER.get(n, level)

        # 2. per-step introspection
        for name, func in self._all_steps.items():
            info = self._introspect(name, func, calib_slots.get(name, {}), calib_specs.get(name, {}))
            info.n_templates = n_templates.get(name, 0)
            info.levels = tuple(l for l, _ in levels.get(name, collections.Counter()).most_common())
            info.predecessors = preds.get(name, collections.Counter())
            info.successors = succs.get(name, collections.Counter())
            tk = {}
            for k, counter in kw_values.get(name, {}).items():
                tk[k] = json.loads(counter.most_common(1)[0][0])
            info.template_keywords = tk
            self.steps[name] = info

        # 3. the special 'save' instruction handled by the walker itself
        save = StepInfo(
            name=SAVE_STEP_NAME, module="walker", category="Output",
            summary="Write the current dataset to the recipe's output directory.",
            description=("Special walker instruction: saves every frame of the current dataset "
                         "to the recipe's outputdir. The walker handles it directly; it is not a "
                         "step function."),
            dataset_param="dataset", args=[
                ArgSpec("suffix", "", "str", "string appended to each output filename before .fits"),
                ArgSpec("ram_heavy_save", False, "bool", "read frames from disk one at a time while saving (ram_heavy recipes only)"),
            ], calibs=[], n_templates=n_templates.get(SAVE_STEP_NAME, 0),
        )
        save.predecessors = preds.get(SAVE_STEP_NAME, collections.Counter())
        save.successors = succs.get(SAVE_STEP_NAME, collections.Counter())
        save.levels = tuple(l for l, _ in levels.get(SAVE_STEP_NAME, collections.Counter()).most_common())
        self.steps[SAVE_STEP_NAME] = save

    def _introspect(self, name, func, slot_labels, slot_specs) -> StepInfo:
        sig = inspect.signature(func)
        params = list(sig.parameters.values())
        doc_args, summary, returns = parse_google_args(inspect.getdoc(func) or "")
        module = (func.__module__ or "").split(".")[-1]
        category = dict(_MODULE_CATEGORY).get(module, "Other")

        dataset_param = params[0].name if params else "input_dataset"
        rest = params[1:]
        positional = [p for p in rest if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        accepts_var_kwargs = any(p.kind == p.VAR_KEYWORD for p in rest)

        # which params are calibration slots?
        calib_params: dict[str, CalibSlot] = {}
        for idx, p in enumerate(positional):
            type_str, desc = doc_args.get(p.name, ("", ""))
            from_doc = _datatypes_from_type_str(type_str, self.datatypes)
            from_tpl = tuple(l for l, _ in slot_labels.get(idx, collections.Counter()).most_common())
            if not from_doc and not from_tpl:
                continue
            labels = list(from_tpl) + [d for d in from_doc if d not in from_tpl]
            specs = {}
            for label in from_tpl:          # only labels templates actually pass at this slot
                c = slot_specs.get(label)
                if c:
                    specs[label] = c.most_common(1)[0][0]
            calib_params[p.name] = CalibSlot(p.name, idx, tuple(labels), type_str, desc, specs)

        args: list[ArgSpec] = []
        for p in rest:
            if p.name in calib_params or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                continue
            type_str, desc = doc_args.get(p.name, ("", ""))
            default = MISSING if p.default is inspect.Parameter.empty else p.default
            args.append(ArgSpec(p.name, default, type_str, desc))

        try:
            src_file = inspect.getsourcefile(func) or ""
            src_line = inspect.getsourcelines(func)[1]
        except (OSError, TypeError):
            src_file, src_line = "", 0

        return StepInfo(
            name=name, module=module, category=category,
            summary=summary.split("\n\n")[0].strip() if summary else "",
            description=inspect.getdoc(func) or "",
            dataset_param=dataset_param, args=args,
            calibs=sorted(calib_params.values(), key=lambda s: s.index),
            accepts_var_kwargs=accepts_var_kwargs, returns=returns,
            source_file=src_file, source_line=src_line,
        )

    # -- queries -------------------------------------------------------------
    def __iter__(self):
        return iter(self.steps.values())

    def __len__(self):
        return len(self.steps)

    def __contains__(self, name):
        return name in self.steps

    def get(self, name: str) -> StepInfo | None:
        return self.steps.get(name)

    def names(self) -> list[str]:
        return list(self.steps)

    def by_category(self) -> dict[str, list[StepInfo]]:
        """Steps grouped for display, categories in pipeline order, steps in registry order."""
        groups: dict[str, list[StepInfo]] = {c: [] for c in CATEGORY_ORDER}
        groups.setdefault("Output", [])
        for info in self.steps.values():
            groups.setdefault(info.category, []).append(info)
        return {c: s for c, s in groups.items() if s}

    def search(self, text: str) -> list[StepInfo]:
        t = text.lower().strip()
        if not t:
            return list(self.steps.values())
        out = []
        for info in self.steps.values():
            hay = " ".join([info.name, info.summary, info.category, info.module] + [a.name for a in info.args])
            if t in hay.lower():
                out.append(info)
        return out

    def level_at(self, step_names: list[str], index: int, start_level: str | None) -> str | None:
        """Data level of the frames entering ``step_names[index]``."""
        level = start_level
        for n in step_names[:index]:
            level = _LEVEL_AFTER.get(n, level)
        return level

    def suggest_index(self, current: list[str], new_step: str) -> tuple[int, str]:
        """Where to insert ``new_step`` into ``current``; returns (index, reason)."""
        info = self.get(new_step)
        n = len(current)
        if info is None or n == 0:
            return n, "appended"
        # best anchor among present steps: strongest predecessor, else strongest successor
        best_pred = max(((current.index(p), c) for p, c in info.predecessors.items() if p in current),
                        default=None, key=lambda t: (t[1], t[0]))
        best_succ = min(((current.index(s), c) for s, c in info.successors.items() if s in current),
                        default=None, key=lambda t: (-t[1], t[0]))
        if best_pred and (not best_succ or best_pred[1] >= best_succ[1]):
            # after the *last* occurrence of that predecessor
            pname = current[best_pred[0]]
            idx = max(i for i, s in enumerate(current) if s == pname) + 1
            return idx, f"usually follows {pname} ({best_pred[1]} template{'s' if best_pred[1] != 1 else ''})"
        if best_succ:
            sname = current[best_succ[0]]
            idx = min(i for i, s in enumerate(current) if s == sname)
            return idx, f"usually precedes {sname} ({best_succ[1]} template{'s' if best_succ[1] != 1 else ''})"
        # no evidence: before a trailing save
        idx = n
        while idx > 0 and current[idx - 1] == SAVE_STEP_NAME:
            idx -= 1
        return idx, "no template evidence; placed before the final save"

    def order_warnings(self, step_names: list[str], start_level: str | None = None) -> list[tuple[int, str]]:
        """Soft warnings about step ordering, as (step_index, message)."""
        out = []
        level = start_level
        for i, n in enumerate(step_names):
            info = self.get(n)
            if info is None:
                out.append((i, f"unknown step '{n}'"))
                continue
            if level and info.levels and level not in info.levels and n != SAVE_STEP_NAME:
                out.append((i, f"{n} is used on {'/'.join(info.levels)} data in templates, but frames here are {level}"))
            if i > 0 and info.predecessors and n != SAVE_STEP_NAME:
                prev = step_names[i - 1]
                if prev not in info.predecessors and prev != SAVE_STEP_NAME and info.n_templates >= 3:
                    top = info.predecessors.most_common(1)[0][0]
                    out.append((i, f"{n} never directly follows {prev} in templates (usually follows {top})"))
            level = _LEVEL_AFTER.get(n, level)
        if step_names and step_names[-1] != SAVE_STEP_NAME:
            out.append((len(step_names) - 1, "recipe does not end with a save step; nothing will be written"))
        return out
