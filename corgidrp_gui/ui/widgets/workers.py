"""Run a blocking function on a QThread and get its result back as signals."""
from __future__ import annotations

import inspect
import traceback

from qtpy import QtCore


class Job(QtCore.QThread):
    progressed = QtCore.Signal(int, int, str)
    done = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, fn, *args, parent=None, **kwargs):
        super().__init__(parent)
        self._fn, self._args, self._kwargs = fn, args, kwargs
        try:
            self._wants_progress = "progress" in inspect.signature(fn).parameters
        except (TypeError, ValueError):
            self._wants_progress = False
        self.result = None
        self.error: str | None = None

    def _progress(self, i, n, label=""):
        self.progressed.emit(int(i), int(n), str(label))

    def run(self):
        try:
            if self._wants_progress:
                self.result = self._fn(*self._args, progress=self._progress, **self._kwargs)
            else:
                self.result = self._fn(*self._args, **self._kwargs)
        except BaseException:  # noqa: BLE001 - report anything to the GUI
            self.error = traceback.format_exc()
            self.failed.emit(self.error)
            return
        self.done.emit(self.result)


class JobRunner:
    """Owns running jobs so they are not garbage collected; ``busy`` tells if any run."""

    def __init__(self):
        self._jobs: set[Job] = set()

    @property
    def busy(self) -> bool:
        return any(j.isRunning() for j in self._jobs)

    def start(self, fn, *args, on_done=None, on_fail=None, on_progress=None, **kwargs) -> Job:
        job = Job(fn, *args, **kwargs)
        self._jobs.add(job)
        if on_done:
            job.done.connect(on_done)
        if on_fail:
            job.failed.connect(on_fail)
        if on_progress:
            job.progressed.connect(on_progress)
        job.finished.connect(lambda j=job: self._jobs.discard(j))
        job.start()
        return job

    def wait_all(self, timeout_ms: int = 60000) -> bool:
        """Block the calling thread (tests) until every job has finished."""
        ok = True
        for j in list(self._jobs):
            ok = j.wait(timeout_ms) and ok
        return ok

    def wait_idle(self, timeout_ms: int = 60000) -> bool:
        """Spin the event loop until no job runs (so queued signals are delivered)."""
        from qtpy import QtWidgets
        deadline = QtCore.QDeadlineTimer(timeout_ms)
        app = QtWidgets.QApplication.instance()
        while self.busy and not deadline.hasExpired():
            app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 50)
            QtCore.QThread.msleep(10)
        app.processEvents()
        return not self.busy
