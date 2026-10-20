"""Where queued recipes go until (and besides) the Status Console."""
from __future__ import annotations

import datetime as _dt
import os
import re

from ..backend import default_backend
from ..core.queue_items import QueueRequest


def dump_recipes(req: QueueRequest, folder: str | None = None, backend=None) -> list[str]:
    """Write every recipe of the request as JSON under ``<outputdir>/recipes``; return the paths."""
    backend = backend or default_backend()
    folder = folder or os.path.join(req.outputdir, "recipes")
    backend.makedirs(folder)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    written = []
    for ci, chain in enumerate(req.chains):
        for ri, r in enumerate(chain):
            safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", r.name) or "recipe"
            path = os.path.join(folder, f"{stamp}_{ci + 1:02d}_{ri + 1:02d}_{safe}.json")
            r.save(path)
            written.append(path)
    return written
