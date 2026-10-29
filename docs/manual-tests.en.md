[日本語](manual-tests.md) | **English**

# Acceptance criteria verified by procedure

A list of acceptance criteria that are hard to judge automatically with a command and are verified by following a procedure.

## NFR-COMPAT-002 AC-090 Behavior unchanged by performance improvements

1. For the commit before the improvement and the commit after it, run `python scripts/verify.py --docs-only` and `python scripts/rdcheck.py` against the same repository state, and record the standard output, standard error, and exit code.
2. Confirm that the two records match.
3. Confirm that `python -m pytest -q tests/toolkit` passes in full (`tests/toolkit/test_git_perf.py` automatically verifies the reproducibility of the output for the same state).

## FR-1054 AC-293 RPG-style originality (no existing copyrighted work is reproduced)

1. Check each item in the "Checklist" of `docs/rpg-originality.md` one by one: start Studio with `python EABK-Studio/studio.py --repo <repository>`, switch the map to RPG style, and turn the sound on (see and hear the music for the three scenes of field, town, and castle, five or more sound effects, and three kinds of characters).
2. In the browser developer tools' Network tab, confirm that there are no requests to origins other than the same origin, and no fetches of image, audio, or font files.
3. Record that every checklist item is "Yes".
