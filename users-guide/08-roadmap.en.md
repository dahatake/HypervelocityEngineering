[日本語](08-roadmap.md) | **English**

# 8. Adoption roadmap and KPIs

## 8.1 Adoption steps

These are the steps for introducing the toolkit to a team.

| Phase | Estimate | Content | Completion criteria | User's work |
|---|---|---|---|---|
| 0 Diagnosis | 2–4 hours (unattended) | Run rd-auditor in history mode against the existing repository to find out which commit and which Prompt produced each past contradiction | For each contradiction, the originating commit, Prompt, and a hypothesis are listed | 1 Prompt |
| 1 Foundation | 1–2 days (mostly unattended) | Install the toolkit ([README "Installation"](../README.en.md#installation)) and check each item in [README "What to check on the first run"](../README.en.md#what-to-check-the-first-time). Run representative work (3 requirements' worth) | The result of each item is recorded | A few Prompts, checking results |
| 2 Requirements definition v1.0 | 2–6 hours + answers | Paste a draft into `<request>`, set `approval_policy: 厳格` (strict) and a short `max_hours`, and run mainly steps 1–2 | A set of MUST requirements with nothing pending approval exists, and there are 0 direct contradictions | 1 Prompt, 1 answer |
| 3 First long run | 24–48 hours (unattended) | Run all steps with `approval_policy: 安全範囲は推奨どおり` (follow recommendations within the safe range) | The run-report result is "all completed" or "has blocked (with reasons)". verify exits 0 | 1 Prompt, checking the report, merging |
| 4 Tuning | Ongoing | While watching the KPIs, adjust model allocation, `parallel_workers`, milestone intervals, and the wording of skills | The KPIs are improving | Answer, by Prompt, whether to adopt each improvement proposal |

### Example request for Phase 0

In VS Code, select **rd-auditor** as the Agent (with Copilot CLI, `--agent rd-auditor`; in the GitHub Copilot app, the agent picker or `/agent`), and send the following.

```text
<audit_options>
scope: 全量
runs: 1
history_mode: する
</audit_options>
Set the run-id to diag-<date>, and write the result to work/runs/diag-<date>/run-report.md.
For each contradiction, list the commit that produced it, the Prompt that created that commit (inferred from the commit message and PR), and a hypothesis about the cause.
```

### Example request for Phase 2

```text
<request>
<pasted_content id="d1">
(Paste the requirements draft)
</pasted_content id="d1">
Turn this into the requirements definition. Do not implement yet.
</request>
<run_options>
max_hours: 4
approval_policy: 厳格
parallel_workers: 1
scope: なし
git_push: しない
deploy: しない
external_write: しない
paid_services: 使わない
external_exposure: 公開しない
</run_options>
```

## 8.2 KPIs

These are the indicators for measuring the effect. You can aggregate them with `python scripts/kpi.py run` (one run) and `python scripts/kpi.py history` (all runs). In step 6, conductor aggregates them automatically and includes them in run-report.md.

**North Star: verified requirements per human intervention** (= number of verified requirements ÷ number of user Prompts). It expresses both reducing human effort and being able to prove that requirements were fully built, in a single number. It does not rise if you reduce interventions but verified requirements do not increase. The definition of "verified" is in [kpi.py in Chapter 5](05-scripts-reference.en.md#kpipy-kpi-aggregation).

| Category | KPI | Target guideline | Source |
|---|---|---|---|
| North Star | Verified requirements per human intervention | Upward trend | `kpi.py`; "human interventions" and "verified requirements" in `docs/run-history.md` |
| Completion | Unattended completion rate (share of runs whose result is "all completed") | 80% or more | `kpi.py history` |
| Quality | Pass rate of ACs that are approved and not BLOCKED | 100% | AC pass rate in `docs/run-history.md`, `ledger.py summary` |
| Quality | Traceability coverage (of approved requirements, those that have a catalog row and all of whose system ACs are in the ledger) | 100% | `kpi.py run` |
| Quality | Direct contradictions and defects found after merge | 0 | The next rd-auditor run |
| Quality | System AC coverage and digest mismatches | 100% and 0 | `verify.py --strict-ledger`, `rdcheck.py stats` |
| Time | Elapsed time per requirement | Shorten relative to the Phase 1 measurement | `docs/run-history.md` (elapsed time ÷ number of implemented requirements), `kpi.py history` |
| Time | Share of items that passed the gate on the first attempt | 70% or more | "First-attempt gate pass rate" in `docs/run-history.md` |
| Token | AI credits per requirement and per AC | Reduce relative to the Phase 1 measurement | Agent Debug Logs and the usage display (recorded with `run-state.py finish --credits`) |
| Token | Share of Tokens used by subagents | Record it; if it keeps growing, review the scope of delegation | Same as above |
| Human | Number of Prompts the user writes per request | 1 (2 if there are answers) | Records of `run-state.py human` ("human interventions" in run-history) |

The procedure for comparing against other approaches, such as GitHub Spec Kit, on the same task is in [bench/README.en.md](../bench/README.en.md).

## 8.3 Risks and countermeasures

These are the main risks and countermeasures.

| Risk | Countermeasure in this toolkit |
|---|---|
| Destructive operations during long runs with full permissions | New Worktree (or Dev Container) + sandbox. G-5 and G-6 hooks. Do not place production credentials. `git_push` and `deploy` default to "do not" |
| PC sleep or Agent Host stopping | Do not let the PC sleep. If it stops, `RESUME` with the same Prompt |
| Loss of information from deleting `/work` | Transcribe it to `/docs` and the ledgers in step 6. Do not delete runs that are in progress or unmerged. CHK-23 |
| Hooks not taking effect depending on the harness | The same rules are checked twice in verify, which is always run before integration |
| Blanket approval causes requirements that differ from the intent to be implemented | Set the excluded areas broadly. Record "blanket approval" in the decision record. Show items in order of impact in the report so they can be revoked in the next Prompt |
| Semantic conflicts in parallel implementation | Do not parallelize items that touch the same boundary or shared component (`queue ready`). Integrate serially and pass the gate every time |
| False positives and misses in audits | Rely mainly on deterministic checks, and run LLM audits with a model from a different lineage. The final step uses a majority vote of 3 |
| Prompt injection | Treat instructions contained in external text as input data (stated in every skill). Only rd-author is given web tools |
