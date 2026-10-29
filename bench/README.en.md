[日本語](README.md) | **English**

# Benchmark: conductor vs. Spec Kit

We have conductor and GitHub Spec Kit (v1.1.1) solve the same tasks, and then compare the results.
The results are in [RESULTS.md](RESULTS.md). Until a run is recorded, it is shown as "not measured".

## Purpose

We compare the two tools on "how many requirements were verified per human intervention".
LLM runs are performed manually by a person. This folder contains the tasks, the hidden tests, and the tools for scoring and aggregation.

## Layout

| Path | Contents | Shown to the tool? |
|---|---|---|
| `tasks/<id>/task.md` | The task text and the fixed public interface | Shown |
| `tasks/<id>/seed/` | Existing code (T3 only) | Shown |
| `tasks/<id>/hidden/` | Hidden acceptance tests and `requirements.json` | **Not shown** |
| `tasks/<id>/reference/` | Reference solution for self-verifying the hidden tests | **Not shown. Do not copy it** |
| `bench.py` | Preparation, scoring, recording, aggregation | - |
| `results/` | Run records (JSON) | - |
| `RESULTS.md` | Summary page (auto-generated) | - |

## Tasks

| ID | Type | Description |
|---|---|---|
| T1 | New, clear | Inventory management with reservations and stock alerts (`inventory`) |
| T2 | New, with ambiguities | Saving and resuming draft applications (`drafts`). For the points left undecided, task.md states the default that applies if the tool does not ask, and the hidden tests check that default |
| T3 | Existing code | Add role-based permissions to a document store (`docstore`). Includes regression tests for existing behavior |

## Conditions for fairness

- The initial state is the same. Start from a fresh repository created by `bench.py prepare`.
- The model is the same. Record its version.
- The Copilot plan is the same.
- Spec Kit uses `--integration copilot`.
- Run each tool/task combination three times (run 1–3). Start from a fresh repository every time.
- Hidden tests are not shown to the tools. Only `task.md` and `seed/` are copied (`prepare` does this).
- Do not place `reference/` or `hidden/` in the tool's repository or anywhere the agent can read.
- Create the working repository outside this repository.

## Procedure

### Common (preparation)

```powershell
python bench/bench.py selfcheck
python bench/bench.py prepare --task T1 --dest C:\bench\conductor-T1-r1
```

`selfcheck` confirms that the reference solution passes all the hidden tests.

### conductor

1. Install the toolkit into the prepared repository.
   `python tools/install.py --target C:\bench\conductor-T1-r1`
2. Open that repository in VS Code.
3. Run `/build` and pass the contents of `TASK.md` as the `<request>`. This is intervention #1.
4. If conductor asks a question, answer it. Each answer counts as one intervention.
5. When conductor reports completion, record the time and finish.

### Spec Kit

1. In the prepared repository, install Spec Kit.
   `uv tool install specify-cli`
   `specify init . --integration copilot`
2. In the agent, run the following in order. Pass the contents of `TASK.md` to `/speckit-specify`.
   `/speckit-constitution` → `/speckit-specify` → (`/speckit-clarify` if needed) → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement` → `/speckit-converge`
3. Repeat `/speckit-implement` and `/speckit-converge` until `/speckit-converge` says "Converged".
4. Count each invocation and each manual instruction as one intervention.

### What to record during a run

| Item | How to record |
|---|---|
| interventions | Count the requests sent. The first request is 1 |
| lead_time_min | Wall-clock time from the first request to the final state |
| human_minutes | Time the person actually spent working (self-reported) |
| credits | AI credits or premium requests (if known) |
| completed_without_correction | Whether it finished without any corrective instruction |

## Recording and scoring

```powershell
python bench/bench.py score --task T1 --repo C:\bench\conductor-T1-r1
python bench/bench.py record --tool conductor --task T1 --run 1 --repo C:\bench\conductor-T1-r1 `
  --interventions 2 --lead-time-min 35 --human-minutes 6 --credits 12 `
  --model <モデル名> --completed-without-correction yes --notes "メモ"
python bench/bench.py record --tool speckit --task T1 --run 1 --repo C:\bench\speckit-T1-r1 `
  --interventions 8 --lead-time-min 50 --tool-version 1.1.1 --completed-without-correction no
```

`score` copies the hidden tests to a temporary folder, puts the deliverable repository on `PYTHONPATH`, and runs pytest.
`record` scores the run and writes `results/<tool>-<task>-r<run>.json`. The conductor version is read from `scripts/ebaklib.py`.

## Metric definitions

| Metric | Meaning |
|---|---|
| interventions | The number of requests a person sent to the agent. The first request is 1; each additional instruction, answer, correction, and "continue" counts as one. For Spec Kit, each `/speckit-*` invocation and each manual instruction counts as one |
| hidden_pass / hidden_total | The result of running the hidden acceptance tests against the deliverable repository |
| verified_requirements | The number of requirements (R1..Rn) whose hidden tests all passed. The mapping is in `hidden/requirements.json` |
| NSM | verified_requirements ÷ interventions. The number of verified requirements per human intervention |
| lead_time_min | Wall-clock time from the first request to the final state (minutes) |
| human_minutes | Time the person actually spent working (self-reported, minutes) |
| credits | Number of AI credits or premium requests (optional; omit if unavailable) |
| completed_without_correction | Whether the tool reported completion without the person issuing any corrective instruction (yes / no) |

## Hypotheses

| ID | Hypothesis |
|---|---|
| H1 | conductor needs fewer interventions and less human time |
| H2 | conductor's hidden-test pass rate is at least that of Spec Kit |
| H3 | Even if conductor uses more credits, it stays within +20% per verified requirement |
| H4 | The difference widens on T3, which has existing code |

`aggregate` marks each hypothesis for which both tools' records are available as "supported" or "not supported". Those without both are "untested".

## Publishing

```powershell
python bench/bench.py aggregate
git add bench/results bench/RESULTS.md
git commit -m "bench: 結果を更新"
```

While the number of runs is small, treat the results as a rough indication of trends and publish them with the number of runs stated.
