---
name: release
description: Prepare a yomineko release (version bump, changelog, build) and hand the owner the tag that publishes it through the Release workflow. Use when cutting a version.
---

**Claude prepares; the owner releases by pushing the tag.** Never run `twine upload` or push a
release tag, and never ask for, read, print or store a PyPI token: publishing is the Release
workflow's job, through Trusted Publishing.

Prepare (on a branch, then PR):
1. Bump `__version__` in `src/yomineko/__init__.py`; move the CHANGELOG entry from
   "unreleased" to the version and date.
2. Run the `check-game` skill for every packaged game (the owner's ROMs, set the `YOMINEKO_ROM_*`
   variables) and put the verdicts and numbers in the README game table and each game's `docs/games/<game>.md`.
3. The CI gate: `ruff check .`, `ruff format --check .`, `mypy`, `lint-imports`,
   `pytest -m "not realrom" --cov`, `python tools/repo_guard.py --all`.
4. `python -m build`, then `python -m twine check dist/*`. List the wheel contents and
   confirm the profiles and schemas ship and no ROM, archive or game text does.

Owner, after merging the bump to `main`: push the tag. That is the whole release.

```bash
git checkout main && git pull origin main
git tag vX.Y.Z && git push origin vX.Y.Z
```

The **Release** workflow (`.github/workflows/release.yml`) then checks that the tag matches
`__version__` and has a CHANGELOG section (`tools/release_notes.py`) and that the commit is on
`main`, runs the CI checks, builds the package and the Windows, macOS and Linux app, publishes to
PyPI with Trusted Publishing (no token), and creates the GitHub release with the changelog section
as notes and the app downloads and package files attached (a pre-release for a PEP 440
pre-release version).
Nothing is published unless every check and build passed. Afterwards: fresh venv, `pip install yomineko`,
`yomineko --version`.

One-time setup (owner, on pypi.org): the `yomineko` project, *Publishing*, *Add a new publisher*,
GitHub: owner `ctorres345`, repository `Yomineko`, workflow `release.yml`, environment `pypi`.
Once it works, delete the PyPI API token: nothing needs it any more.

If the workflow fails before the PyPI job, cancel the run if it is still going, delete the tag
(`git push origin :vX.Y.Z`, `git tag -d vX.Y.Z`), fix the problem in a PR and merge it, then tag
the new commit on main (`git pull`, `git tag vX.Y.Z`, `git push origin vX.Y.Z`). Once
the PyPI job has uploaded, never move the tag: if only the GitHub release job failed, re-run it
and it completes the release. If the PyPI job failed after uploading only one of the two files,
its re-runs fail too (PyPI refuses a file it already has): release the next patch version. A version can never be re-uploaded, so a bad 0.1.0 becomes 0.1.1.
