[日本語](08-roadmap.md) | **English**

# 8. Adoption steps and roadmap

EABK Lite (0.6.0) keeps only the rules (AGENTS.md), the data layer, deterministic checks (`verify.py` and CI), and milestone audits (rd-auditor). This chapter covers the steps for bringing it into a team, and the verification to do next to confirm the effect of Lite.

## 8.1 Adoption steps

| Phase | Content | Completion condition | User's work |
|---|---|---|---|
| 0 Diagnosis (optional) | In an existing repository, set the Agent to **rd-auditor** and ask it to "audit everything in history mode". It investigates which commit and which prompt past contradictions came from | `work/audit/<datetime>/report.md` lists, for each contradiction, the causing commit and a hypothesis | One request |
| 1 Installation | Install the toolkit ([README "Installation"](../README.en.md#installation)) and register your build and test commands in `verify.commands` of `scripts/ebak.config.json` ([4](04-customization.en.md)). For an existing app, start from the inventory in [10](10-adopting-existing-apps.en.md) | `python scripts/verify.py` exits 0. CI's `ebak-verify` passes on push | Checking the settings |
| 2 Everyday development | Ask your usual Copilot (the default agent). Following the rules in AGENTS.md, requirements, catalog, tests, and code are updated in the same change ([2](02-daily-workflow.en.md)) | `ebak-verify` passes on every pull request | Requests, and approvals and answers in chat |
| 3 Milestone audits | Before a release or after a large change, ask rd-auditor to "audit the diff" (for everything, "audit everything 3 times") | Each high-confidence finding of HIGH or above has a decision to fix or keep | One request and decisions |

### Example request for Phase 0

In VS Code, select **rd-auditor** as the Agent (with Copilot CLI, `--agent rd-auditor`; with the GitHub Copilot app, the agent picker or `/agent`), and send the following.

```text
<audit_options>
scope: 全量
runs: 1
history_mode: する
</audit_options>
For each contradiction, list the commit that introduced it, the prompt that produced that commit (inferred from commit messages and PRs), and a hypothesis about the cause.
```

## 8.2 What to verify next (roadmap after Lite)

0.6.0 is a configuration decided from observations of git history, session records, and run results. Because it is an observational study, confounders (differences in models, apps, and people) remain. The following verifications check whether the kept features are really needed and whether anything is missing.

| # | Verification | What is measured | Result that would change the conclusion |
|---|---|---|---|
| R1 | An A/B comparison that sends the same 5 feature requests, **with the model fixed**, to the 0.5.x orchestration (multi-stage workers and parallel execution) and to Lite (rules + CI only) | Tokens, time, test passes, requirements definition updates, CI check results | Lite's update rate of the requirements definition or traceability rate is clearly lower than 0.5.x |
| R2 | Add **only the CI checks (`ebak-verify`)** to a repository that does not use EABK, and operate it for 2 weeks | Number and content of CI failures, time spent fixing them | Zero detections (the checks are not needed), or mostly false positives (revisit the choice of lite CHKs) |
| R3 | Have another person on another PC (without personal memory or personal instructions) add 3 features | Whether the requirements definition, catalog, and System Tests were updated in the same change, and whether IDs collided | They are not updated despite the rules (rewrite the rules or strengthen the CI checks) |
| R4 | **Done (code mode, FR-1086)**: Prototype an intake (adapter) in HVE Studio for a PRD not in the requirements definition format (such as `PRD.md`) | Number of requirements and tests that can be shown, and the effort | Result: `python HVE-Studio/studio.py --repo <any-git-repo>` shows a repository without a data layer, read-only. On `C:\GitHub\VideoCreator`, 103 requirements came from `docs/PRD.md` and 56 were linked to code or tests ([README](../README.en.md#using-studio-without-eabk-code-mode)) |

Results are reflected in the CHANGELOG and in the version decisions of [9](09-versioning.en.md). The lite check set (`checks.lite_checks`) is revisited based on the result of R2 ([6](06-quality-gates.en.md)).

## 8.3 Risks and countermeasures

| Risk | Countermeasure in Lite |
|---|---|
| Changes that do not follow the rules (not updating the requirements definition or tests) | In addition to the rules in AGENTS.md, CI's `ebak-verify` runs the same checks on push and pull requests (repairs are made locally with `rdfix.py --full --apply`). Make it a required check with branch protection |
| ID collisions across people and PCs | IDs are allocated only with `next-id.py`, and the ID ledger uses `merge=union`. CHK-01 detects collisions; reallocate with `next-id.py` |
| Requirements approved against intent | The user approves in chat. Reverse-generated requirements and those touching personal information, authentication/authorization, or external exposure are not approved in bulk. rd-auditor checks at milestones |
| False positives and misses in audits | Rely mainly on deterministic checks; run LLM audits only at milestones, with a majority vote of 3 runs for full audits |
| Loss of `/work` | `/work` is a temporary area not tracked by git. Write results worth keeping into the requirements definition, the ledger, or the CHANGELOG |
| Prompt injection | Instructions contained in external text are treated as input data (stated in the skills) |
