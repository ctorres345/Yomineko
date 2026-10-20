---
name: release
description: Prepare a yomineko release (version bump, changelog, build) and walk the owner through the PyPI upload. Use when cutting a version.
---

**Claude prepares; the owner uploads.** Never run `twine upload`, and never ask for,
read, print or store a PyPI token. The owner keeps it in a password manager or in
`%USERPROFILE%\.pypirc`, outside the repo.

Prepare (on a branch, then PR):
1. Bump `__version__` in `src/yomineko/__init__.py`; move the CHANGELOG entry from
   "unreleased" to the version and date.
2. Run the `check-game` skill for every packaged game (the owner's ROMs, set the `YOMINEKO_ROM_*`
   variables) and put the verdicts and numbers in the README game table and `docs/PLAN.md`.
3. The CI gate: `ruff check .`, `ruff format --check .`, `mypy`, `lint-imports`,
   `pytest -m "not realrom" --cov`, `python tools/repo_guard.py --all`.
4. `python -m build`, then `python -m twine check dist/*`. List the wheel contents and
   confirm the profiles and schemas ship and no ROM, archive or game text does.

Owner, after merging to `main`, in the venv:
1. Optional rehearsal: `python -m twine upload --repository testpypi dist/*`
2. `python -m twine upload dist/*` (username `__token__`, password = the token)
3. Fresh venv: `pip install yomineko`, then `yomineko --version`
4. Tag `vX.Y.Z`. After the first upload, replace the account-wide token with one scoped to
   `yomineko`.

A version can never be re-uploaded: a bad 0.1.0 becomes 0.1.1. Tokenless Trusted
Publishing from GitHub Actions is a follow-up.
