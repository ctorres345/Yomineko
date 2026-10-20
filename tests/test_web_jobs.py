import threading

import pytest

from yomineko.errors import YominekoError
from yomineko.web.jobs import Busy, Jobs, Outcome
from yomineko.web.paging import PAGE_SIZE, paginate


def wait(job, timeout=5):
    done = threading.Event()
    for _ in range(int(timeout * 100)):
        if job.status != "running":
            done.set()
            break
        threading.Event().wait(0.01)
    assert done.is_set(), "the job did not finish"


def test_a_job_reports_progress_and_its_outcome():
    gate = threading.Event()

    def work(say):
        say("step one")
        gate.wait(5)
        return Outcome("/next", ["all good"])

    jobs = Jobs()
    job = jobs.start("Doing it", work)
    for _ in range(500):
        if job.message:
            break
        threading.Event().wait(0.01)
    assert (job.status, job.message) == ("running", "step one")
    assert jobs.running() is job and jobs.get(job.id) is job
    gate.set()
    wait(job)
    assert (job.status, job.next_url, job.notes) == ("done", "/next", ["all good"])
    assert jobs.running() is None


def test_only_one_job_runs_at_a_time():
    gate = threading.Event()
    jobs = Jobs()
    first = jobs.start("First", lambda say: (gate.wait(5), Outcome("/"))[1])
    with pytest.raises(Busy, match="First is still running") as busy:
        jobs.start("Second", lambda say: Outcome("/"))
    assert busy.value.running is first
    gate.set()
    wait(first)
    wait(jobs.start("Third", lambda say: Outcome("/")))


def test_an_expected_failure_shows_its_message():
    def work(say):
        raise YominekoError("the dictionary is missing")

    job = Jobs().start("Failing", work)
    wait(job)
    assert (job.status, job.error) == ("failed", "the dictionary is missing")


def test_a_bug_shows_a_short_message_and_is_logged(caplog):
    def work(say):
        raise ZeroDivisionError("secret details")

    job = Jobs().start("Buggy", work)
    wait(job)
    assert job.status == "failed" and "secret details" not in job.error
    assert "secret details" in caplog.text


def test_an_unknown_job_is_none():
    assert Jobs().get("nope") is None


# --------------------------------------------------------------------- paging


def test_paginate_splits_and_clamps():
    items = list(range(120))
    first = paginate(items, 1)
    assert (first.number, first.pages, first.total) == (1, 3, 120)
    assert first.items == items[:PAGE_SIZE] and first.has_next and not first.has_previous
    last = paginate(items, 99)
    assert last.number == 3 and last.items == items[100:] and last.has_previous
    assert paginate(items, -5).number == 1


def test_paginate_of_nothing_is_one_empty_page():
    page = paginate([], 1)
    assert (page.items, page.pages, page.has_next, page.has_previous) == ([], 1, False, False)
