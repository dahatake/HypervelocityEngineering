[日本語](manual-tests.md) | **English**

# Acceptance criteria verified by procedure

A list of acceptance criteria that are hard to judge automatically with a command and are verified by following a procedure.

## NFR-COMPAT-002 AC-090 Behavior unchanged by performance improvements

1. For the commit before the improvement and the commit after it, run `python scripts/verify.py --docs-only` and `python scripts/rdcheck.py` against the same repository state, and record the standard output, standard error, and exit code.
2. Confirm that the two records match.
3. Confirm that `python -m pytest -q tests/toolkit` passes in full (`tests/toolkit/test_git_perf.py` automatically verifies the reproducibility of the output for the same state).

## FR-1087 AC-475 AC-476 AC-478 Installing and removing every version (toolkit maintenance, before a release)

The automated tests (`tests/toolkit/test_uninstall.py`) actually install only the oldest version and the current one. Every version is verified with this procedure (in a full clone of the toolkit repository).

1. Confirm that `python tools/build-uninstall-catalog.py --check` exits 0 (the catalog matches the git history).
2. Run `python tools/verify-uninstall-matrix.py`. Each representative version is installed with that version's own `tools/install.py` into a repository with committed user files, and `tools/uninstall.py --purge --runs` is run in 3 variants: as installed, with the manifest deleted, and after updating to the current version. Confirm that every row is `OK` and the exit code is 0.
3. Run `python tools/verify-uninstall-matrix.py --all`. Every version (including versions that came in through merges) is installed, its manifest deleted, and removed the same way. Confirm that every row is `OK` and the exit code is 0.
4. The oracle: after removal, `git status --porcelain --ignored --untracked-files=all` is empty (byte for byte the pre-install commit). Failure details are in `work/uninstall-matrix/log-<commit>-<variant>.txt`.
5. In another repository: outside a toolkit clone, run `tools/uninstall.ps1 -DryRun` (or `tools/uninstall.sh --dry-run`) in the form that downloads the 2 files from `main`, and confirm that it lists the items and changes nothing.
