"""The recipe queue: jobs, chain dependencies, persistence. No Qt, no processes.

The Status Console owns a :class:`JobQueue`, asks it for the next runnable job,
starts a runner process for it, and reports the result back with
:meth:`JobQueue.mark_finished`. Chained recipes (recipe k+1 runs on the outputs
of recipe k) are jobs that depend on each other; a failure skips the rest of its
chain.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field

from .progress import ProgressParser
from .queue_items import QueueRequest
from .recipes import Recipe

__all__ = ["RecipeJob", "JobQueue", "STATUSES", "queue_dir"]

STATUSES = ("waiting", "running", "done", "failed", "aborted", "skipped")


def queue_dir() -> str:
    d = os.environ.get("CORGIDRP_GUI_HOME") or os.path.join(os.path.expanduser("~"), ".corgidrp_gui")
    d = os.path.join(d, "queue")
    os.makedirs(d, exist_ok=True)
    return d


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name) or "recipe"


@dataclass
class RecipeJob:
    id: str
    recipe: Recipe
    recipe_path: str                       # JSON written at enqueue time; what the runner reads
    outputdir: str
    chain_id: str
    chain_index: int
    chain_length: int
    depends_on: str | None = None          # job id whose outputs become our inputs
    source: str = "parser"
    status: str = "waiting"
    created: float = field(default_factory=time.time)
    started: float | None = None
    ended: float | None = None
    returncode: int | None = None
    pid: int | None = None
    outputs: list[str] = field(default_factory=list)
    inputs_from: str | None = None         # list file handed to the runner for chained jobs
    message: str = ""
    parser: ProgressParser = field(default_factory=ProgressParser, repr=False)
    log: list[str] = field(default_factory=list, repr=False)
    max_log_lines: int = 5000

    # -- derived ------------------------------------------------------------
    @property
    def name(self) -> str:
        return self.recipe.name

    @property
    def n_inputs(self) -> int:
        return len(self.recipe.inputs)

    @property
    def is_chained(self) -> bool:
        return self.chain_length > 1

    @property
    def chain_label(self) -> str:
        return f"{self.chain_index + 1}/{self.chain_length}" if self.is_chained else ""

    @property
    def elapsed(self) -> float | None:
        if self.started is None:
            return None
        return (self.ended or time.time()) - self.started

    @property
    def active(self) -> bool:
        return self.status in ("waiting", "running")

    def progress_text(self) -> str:
        p = self.parser
        total = p.total_steps or len(self.recipe.steps)
        if self.status == "waiting":
            return "—"
        done = len([s for s in p.steps if s.ended is not None])
        if self.status == "done":
            return f"{total}/{total}"
        if self.status == "running":
            cur = p.current_step
            return f"{cur.index}/{cur.total}" if cur else f"0/{total}"
        return f"{done}/{total}"

    def append_log(self, line: str):
        self.log.append(line)
        if len(self.log) > self.max_log_lines:
            del self.log[: len(self.log) - self.max_log_lines]

    def step_states(self) -> list[tuple[str, str, float | None]]:
        """(step name, done|running|pending|skipped, elapsed) per recipe step, for the step strip."""
        names = self.recipe.step_names
        timings = {s.index - 1: s for s in self.parser.steps}
        out = []
        cur = self.parser.current_step.index - 1 if self.parser.current_step else None
        for i, n in enumerate(names):
            st = self.recipe.steps[i]
            if st.skip:
                out.append((n, "skipped", None))
                continue
            t = timings.get(i)
            if t is not None and (t.ended is not None or self.status in ("done",)):
                out.append((n, "done", t.elapsed))
            elif t is not None and self.status == "running" and i == cur:
                out.append((n, "running", t.elapsed))
            elif t is not None and self.status in ("failed", "aborted"):
                out.append((n, "failed", t.elapsed))
            else:
                out.append((n, "pending", None))
        return out

    def resolved_calibs(self) -> list[tuple[str, str, str]]:
        """(step, label, file) for calibrations the recipe names explicitly."""
        out = []
        for s in self.recipe.steps:
            for label, spec in (s.calibs or {}).items():
                if isinstance(spec, str) and "AUTOMATIC" not in spec.upper():
                    out.append((s.name, label, spec))
                elif spec is None:
                    out.append((s.name, label, "(none)"))
        return out

    def to_record(self) -> dict:
        return {
            "id": self.id, "name": self.name, "recipe_path": self.recipe_path, "outputdir": self.outputdir,
            "chain_id": self.chain_id, "chain_index": self.chain_index, "chain_length": self.chain_length,
            "depends_on": self.depends_on, "source": self.source, "status": self.status,
            "created": self.created, "started": self.started, "ended": self.ended,
            "returncode": self.returncode, "outputs": self.outputs, "inputs_from": self.inputs_from,
            "message": self.message, "n_inputs": self.n_inputs, "n_steps": len(self.recipe.steps),
        }


class JobQueue:
    """Ordered jobs plus the rules for which may run next."""

    def __init__(self, store_dir: str | None = None):
        self.store_dir = store_dir or queue_dir()
        self.jobs: list[RecipeJob] = []
        self.paused = False
        self.max_workers = 1
        self.listeners: list = []          # callables(event: str, job: RecipeJob | None)

    # -- events --------------------------------------------------------------
    def _emit(self, event: str, job: RecipeJob | None = None):
        for cb in list(self.listeners):
            cb(event, job)

    # -- enqueue -------------------------------------------------------------
    def add_request(self, req: QueueRequest) -> list[RecipeJob]:
        """Write each recipe to the queue folder and create its job(s)."""
        added = []
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        for chain in req.chains:
            chain_id = uuid.uuid4().hex[:8]
            prev: RecipeJob | None = None
            for k, recipe in enumerate(chain):
                r = recipe.copy()
                if not r.outputdir:
                    r.outputdir = req.outputdir
                job_id = f"{stamp}_{uuid.uuid4().hex[:6]}"
                path = os.path.join(self.store_dir, f"{job_id}_{_safe(r.name)}.json")
                r.save(path)
                job = RecipeJob(id=job_id, recipe=r, recipe_path=path, outputdir=r.outputdir or req.outputdir,
                                chain_id=chain_id, chain_index=k, chain_length=len(chain),
                                depends_on=prev.id if prev else None, source=req.source)
                if req.cpgs_xml:
                    job.message = f"CPGS XML: {req.cpgs_xml}"
                self.jobs.append(job)
                added.append(job)
                prev = job
        for j in added:
            self._emit("added", j)
        return added

    # -- scheduling ------------------------------------------------------------
    def get(self, job_id: str) -> RecipeJob | None:
        return next((j for j in self.jobs if j.id == job_id), None)

    @property
    def running(self) -> list[RecipeJob]:
        return [j for j in self.jobs if j.status == "running"]

    @property
    def waiting(self) -> list[RecipeJob]:
        return [j for j in self.jobs if j.status == "waiting"]

    def counts(self) -> dict[str, int]:
        c = {s: 0 for s in STATUSES}
        for j in self.jobs:
            c[j.status] += 1
        return c

    def next_runnable(self) -> RecipeJob | None:
        if self.paused or len(self.running) >= self.max_workers:
            return None
        for j in self.jobs:
            if j.status != "waiting":
                continue
            if j.depends_on is None:
                return j
            dep = self.get(j.depends_on)
            if dep is None or dep.status == "done":
                return j
        return None

    def prepare_launch(self, job: RecipeJob) -> RecipeJob:
        """Resolve chained inputs (writes the --inputs-from list) and mark running."""
        if job.depends_on:
            dep = self.get(job.depends_on)
            if dep is not None and dep.outputs:
                lst = os.path.join(self.store_dir, f"{job.id}_inputs.txt")
                with open(lst, "w") as f:
                    f.write("\n".join(dep.outputs) + "\n")
                job.inputs_from = lst
                job.recipe.inputs = list(dep.outputs)
        job.status = "running"
        job.started = time.time()
        job.ended = None
        job.parser = ProgressParser()
        job.log = []
        self._emit("started", job)
        return job

    def mark_finished(self, job: RecipeJob, returncode: int | None, aborted: bool = False):
        job.ended = time.time()
        job.returncode = returncode
        p = job.parser
        if aborted:
            job.status = "aborted"
            job.message = "aborted by user"
        elif returncode == 0 and p.finished is not False:
            job.status = "done"
            job.outputs = list(p.outputs)
            job.message = f"{len(job.outputs)} output file{'s' if len(job.outputs) != 1 else ''}"
        else:
            job.status = "failed"
            fail = p.failing_step()
            err = p.errors[-1] if p.errors else f"exit code {returncode}"
            job.message = (f"step {fail.index}/{fail.total} {fail.name}: " if fail else "") + err
        if job.status != "done":
            self._skip_dependents(job)
        self._emit("finished", job)

    def _skip_dependents(self, job: RecipeJob):
        for j in self.jobs:
            if j.status == "waiting" and j.depends_on == job.id:
                j.status = "skipped"
                j.message = f"skipped: {job.name} did not finish"
                self._emit("finished", j)
                self._skip_dependents(j)

    # -- user actions ----------------------------------------------------------
    def requeue(self, job: RecipeJob) -> RecipeJob:
        """Put a finished job back at the end of the queue (same recipe file)."""
        if job.status == "running":
            return job
        job.status = "waiting"
        job.started = job.ended = None
        job.returncode = None
        job.outputs = []
        job.message = ""
        job.parser = ProgressParser()
        job.log = []
        self.jobs.remove(job)
        self.jobs.append(job)
        # a re-queued chain head re-enables its skipped dependents
        for j in self.jobs:
            if j.depends_on == job.id and j.status == "skipped":
                self.requeue(j)
        self._emit("added", job)
        return job

    def remove(self, job: RecipeJob):
        if job.status == "running":
            return
        self.jobs.remove(job)
        self._emit("removed", job)

    def clear_finished(self):
        for j in [j for j in self.jobs if j.status in ("done", "failed", "aborted", "skipped")]:
            self.jobs.remove(j)
        self._emit("cleared", None)

    def move(self, job: RecipeJob, delta: int):
        i = self.jobs.index(job)
        k = max(0, min(len(self.jobs) - 1, i + delta))
        if k != i and job.status == "waiting":
            self.jobs.insert(k, self.jobs.pop(i))
            self._emit("reordered", job)

    # -- persistence -----------------------------------------------------------
    def state_path(self) -> str:
        return os.path.join(self.store_dir, "queue_state.json")

    def save(self):
        data = {"saved": _dt.datetime.now().isoformat(timespec="seconds"), "max_workers": self.max_workers,
                "jobs": [j.to_record() for j in self.jobs][-300:]}
        tmp = self.state_path() + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, self.state_path())

    def load(self) -> int:
        """Restore waiting jobs (and recent history) from disk. Running jobs become 'aborted'."""
        p = self.state_path()
        if not os.path.exists(p):
            return 0
        try:
            with open(p) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return 0
        self.max_workers = int(data.get("max_workers", 1))
        n = 0
        for rec in data.get("jobs", []):
            if not os.path.exists(rec.get("recipe_path", "")):
                continue
            try:
                recipe = Recipe.load(rec["recipe_path"])
            except (OSError, ValueError):
                continue
            job = RecipeJob(id=rec["id"], recipe=recipe, recipe_path=rec["recipe_path"], outputdir=rec.get("outputdir", ""),
                            chain_id=rec.get("chain_id", ""), chain_index=rec.get("chain_index", 0),
                            chain_length=rec.get("chain_length", 1), depends_on=rec.get("depends_on"),
                            source=rec.get("source", "parser"), status=rec.get("status", "waiting"),
                            created=rec.get("created", time.time()), started=rec.get("started"), ended=rec.get("ended"),
                            returncode=rec.get("returncode"), outputs=list(rec.get("outputs", [])),
                            inputs_from=rec.get("inputs_from"), message=rec.get("message", ""))
            if job.status == "running":
                job.status = "aborted"
                job.message = "GUI closed while running"
                job.ended = job.ended or time.time()
            self.jobs.append(job)
            n += 1
        self._emit("cleared", None)
        return n
