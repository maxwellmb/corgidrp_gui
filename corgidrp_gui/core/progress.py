"""Turn the walker's console output into progress events.

corgidrp's walker prints, among other things::

    Executing recipe: l1_to_l2a_basic
    number of frames:  14
    Processing frames in chunks of 200 frames
    Walker step 3/6: detect_cosmic_rays

and the runner (``corgidrp_gui.runner``) adds its own marker lines prefixed
with ``corgidrp_gui ``. Everything else is passed through as log text.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Event", "ProgressParser", "StepTiming"]

RUNNER_PREFIX = "corgidrp_gui "

_RE = {
    "recipe_start": re.compile(r"^Executing recipe:\s*(?P<name>.+?)\s*$"),
    "n_frames": re.compile(r"^number of frames:\s*(?P<n>\d+)\s*$"),
    "chunks": re.compile(r"^Processing frames in chunks of (?P<n>\d+) frames"),
    "ram_heavy": re.compile(r"^Processing frames in RAM-heavy mode"),
    "step": re.compile(r"^Walker step (?P<i>\d+)/(?P<n>\d+):\s*(?P<name>\S+)"),
    "traceback": re.compile(r"^Traceback \(most recent call last\):"),
    "exception": re.compile(r"^(?P<type>[A-Za-z_][\w.]*(?:Error|Exception|Warning|Interrupt|Exit))\s*:\s*(?P<msg>.*)$"),
    "warning": re.compile(r"^.*?:\d+:\s*(?P<type>\w*Warning):\s*(?P<msg>.*)$"),
    "runner": re.compile(r"^corgidrp_gui (?P<kind>[a-z_]+):\s*(?P<rest>.*)$"),
}


@dataclass
class Event:
    kind: str                       # recipe_start, n_frames, step, log, warning, error, output, runner, finished
    text: str
    data: dict[str, Any] = field(default_factory=dict)
    stream: str = "stdout"
    time: float = 0.0


@dataclass
class StepTiming:
    index: int
    total: int
    name: str
    started: float
    ended: float | None = None

    @property
    def elapsed(self) -> float:
        return (self.ended or time.monotonic()) - self.started


class ProgressParser:
    """Feed lines in; get :class:`Event` objects and running state out.

    One parser per runner process. ``feed`` returns the events for that line
    (usually one); state is kept in attributes the console can read:
    ``recipe_name``, ``n_frames``, ``current_step``, ``total_steps``,
    ``steps`` (list of :class:`StepTiming`), ``outputs``, ``errors``.
    """

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self.recipe_name: str | None = None
        self.n_frames: int | None = None
        self.total_steps: int | None = None
        self.current_step: StepTiming | None = None
        self.steps: list[StepTiming] = []
        self.outputs: list[str] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.finished: bool | None = None       # None = still running, True ok, False failed
        self._in_traceback = False
        self._traceback_lines: list[str] = []

    # -- public -------------------------------------------------------------
    def feed(self, line: str, stream: str = "stdout") -> list[Event]:
        line = line.rstrip("\r\n")
        now = self._clock()
        ev = self._classify(line, stream, now)
        ev.time = now
        return [ev]

    def feed_text(self, text: str, stream: str = "stdout") -> list[Event]:
        out = []
        for line in text.splitlines():
            out.extend(self.feed(line, stream))
        return out

    @property
    def fraction_done(self) -> float | None:
        if not self.total_steps:
            return None
        done = len([s for s in self.steps if s.ended is not None])
        return min(1.0, done / self.total_steps)

    def traceback_text(self) -> str:
        return "\n".join(self._traceback_lines)

    def failing_step(self) -> StepTiming | None:
        return self.current_step if self.errors else None

    # -- internals ------------------------------------------------------------
    def _close_step(self, now):
        if self.current_step is not None and self.current_step.ended is None:
            self.current_step.ended = now

    def _classify(self, line: str, stream: str, now: float) -> Event:
        s = line.strip()

        # traceback accumulation (stderr normally, but be lenient)
        if self._in_traceback:
            self._traceback_lines.append(line)
            m = _RE["exception"].match(s)
            if m and not line.startswith(" "):
                self._in_traceback = False
                self.errors.append(s)
                self.finished = False
                self._close_step(now)
                return Event("error", line, {"type": m.group("type"), "message": m.group("msg"),
                                             "step": self.current_step.name if self.current_step else None}, stream)
            return Event("log", line, {"traceback": True}, stream)
        if _RE["traceback"].match(s):
            self._in_traceback = True
            self._traceback_lines = [line]
            return Event("log", line, {"traceback": True}, stream)

        m = _RE["runner"].match(s)
        if m:
            return self._runner_event(m.group("kind"), m.group("rest"), line, stream, now)

        m = _RE["recipe_start"].match(s)
        if m:
            self.recipe_name = m.group("name")
            return Event("recipe_start", line, {"name": self.recipe_name}, stream)
        m = _RE["n_frames"].match(s)
        if m:
            self.n_frames = int(m.group("n"))
            return Event("n_frames", line, {"n": self.n_frames}, stream)
        m = _RE["step"].match(s)
        if m:
            self._close_step(now)
            i, n, name = int(m.group("i")), int(m.group("n")), m.group("name")
            self.total_steps = n
            self.current_step = StepTiming(i, n, name, now)
            self.steps.append(self.current_step)
            return Event("step", line, {"index": i, "total": n, "name": name}, stream)
        if _RE["chunks"].match(s) or _RE["ram_heavy"].match(s):
            return Event("log", line, {"mode": s}, stream)
        m = _RE["warning"].match(s)
        if m:
            self.warnings.append(m.group("msg"))
            return Event("warning", line, {"type": m.group("type"), "message": m.group("msg")}, stream)
        return Event("log", line, {}, stream)

    def _runner_event(self, kind, rest, line, stream, now) -> Event:
        data: dict[str, Any] = {"raw": rest}
        if kind == "output":
            self.outputs.append(rest.strip())
            data["path"] = rest.strip()
            return Event("output", line, data, stream)
        if kind == "finished":
            self._close_step(now)
            fields = dict(kv.split("=", 1) for kv in rest.split() if "=" in kv)
            data.update(fields)
            ok = fields.get("status") == "ok"
            self.finished = ok if self.finished is None or ok is False else self.finished
            if not ok and not self.errors:
                self.errors.append(fields.get("error", "runner reported failure"))
            return Event("finished", line, data, stream)
        if kind == "recipe":
            fields = dict(kv.split("=", 1) for kv in rest.split() if "=" in kv)
            data.update(fields)
            if "steps" in fields and fields["steps"].isdigit():
                self.total_steps = int(fields["steps"])
            if "name" in fields and self.recipe_name is None:
                self.recipe_name = fields["name"]
            return Event("runner", line, data, stream)
        return Event("runner", line, data, stream)
