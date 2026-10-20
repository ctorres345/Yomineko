"""Slow work (the dictionary download, analysing a game) runs in a background thread.

The page shows a progress fragment that the browser polls. One job runs at a time: the steps are
heavy, and two at once would only slow each other down.
"""

from __future__ import annotations

import logging
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from yomineko.errors import YominekoError

log = logging.getLogger("yomineko.web")

Status = Literal["running", "done", "failed"]


@dataclass
class Job:
    id: str
    label: str
    status: Status = "running"
    message: str = ""  # what it is doing now
    notes: list[str] = field(default_factory=list)  # what it reports when done
    error: str = ""
    next_url: str = "/"  # where "Continue" leads


@dataclass
class Outcome:
    """What a finished job reports."""

    next_url: str
    notes: list[str] = field(default_factory=list)


Work = Callable[[Callable[[str], None]], Outcome]


class Busy(YominekoError):
    """Another job is still running."""

    def __init__(self, running: Job):
        super().__init__(f"{running.label} is still running.")
        self.running = running


class Jobs:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def running(self) -> Job | None:
        return next((j for j in self._jobs.values() if j.status == "running"), None)

    def start(self, label: str, work: Work) -> Job:
        """Run ``work`` in a thread. Raises ``Busy`` if a job is already running."""
        with self._lock:
            running = self.running()
            if running is not None:
                raise Busy(running)
            job = Job(id=secrets.token_urlsafe(8), label=label)
            self._jobs[job.id] = job
        threading.Thread(target=self._run, args=(job, work), daemon=True).start()
        return job

    def _run(self, job: Job, work: Work) -> None:
        def say(message: str) -> None:
            job.message = message

        try:
            outcome = work(say)
        except YominekoError as e:
            job.error, job.status = str(e), "failed"
        except Exception:  # a bug: keep the details in the log, show something short
            log.exception("job %r failed", job.label)
            job.error = "Something went wrong. The details are in the terminal."
            job.status = "failed"
        else:
            job.next_url, job.notes, job.status = outcome.next_url, outcome.notes, "done"
