# Releasing to PyPI

`report-workflow` publishes to PyPI through **Trusted Publishing** (OIDC), so
no API token or secret is stored in this repository. The
[`release.yml`](../.github/workflows/release.yml) workflow builds and publishes
automatically when a version tag is pushed.

## One-time setup (maintainer, ~2 minutes)

Register this repository as a pending publisher on PyPI **before the first
release** (the project does not need to exist yet):

1. Sign in at <https://pypi.org> → **Account settings** → **Publishing**.
2. Under *Add a new pending publisher*, choose **GitHub** and enter exactly:
   - **PyPI Project Name:** `report-workflow`
   - **Owner:** `0Smallcat0`
   - **Repository name:** `report-workflow`
   - **Workflow name:** `release.yml`
   - **Environment name:** `pypi`
3. Save. (Optionally add the matching `pypi` environment under the GitHub repo
   settings for a manual approval gate; the workflow already targets it.)

That is the entire credential setup — nothing to paste into GitHub secrets.

## Cutting a release

```bash
# 1. Bump the version in BOTH places (they must match — the workflow enforces it):
#    - pyproject.toml           [project].version
#    - src/report_workflow/__init__.py   __version__
# 2. Update CHANGELOG.md with the new section.
# 3. Commit, then tag and push:
git commit -am "release: X.Y.Z — <headline>"
git tag vX.Y.Z
git push origin master
git push origin vX.Y.Z
```

Pushing the tag triggers `release.yml`, which:

1. **guard** — installs the package, asserts the tag matches
   `report_workflow.__version__`, then runs the seven-profile and adversarial
   benchmark `--check`s and the unit tests. A tag that would fail CI never
   publishes.
2. **build** — builds the sdist + wheel and runs `twine check`.
3. **publish** — uploads to PyPI via OIDC.

## Verify before tagging (optional but recommended)

```bash
python -m build
python -m twine check dist/*
# smoke-test the built wheel in a throwaway env:
python -m venv /tmp/rw && /tmp/rw/bin/pip install dist/*.whl
/tmp/rw/bin/python -c "from report_workflow import verify; print(verify('x fell to 0.2% [1].', {'1':'x fell to 3.5%.'})['sentence_results'][0]['status'])"
# expect: blocked
```

The external HaluEval benchmark (`scripts/run_external_benchmark.py`) is **not**
part of the release gate: it downloads a 6 MB dataset over the network, which
would make releases flaky for reasons unrelated to the code. Run it manually
when validating gate changes.
