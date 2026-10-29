[日本語](01-writing-requests.md) | **English**

# 1. How to Write a Request (/build and run_options)

## 1.1 Template

```text
<request>
What you want to do. New, addition, change, or deletion are all fine. Wrap text from external sources in <pasted_content id="any">
</request>
<answers>
Answers to the questionnaire and approval requests in the previous report. Example: Q-003: B / FR-031: approved / the rest as recommended. Leave empty the first time
</answers>
<references>
Optional: paths to materials, URLs
</references>
<run_options>
max_hours: 2.5
approval_policy: 安全範囲は推奨どおり
parallel_workers: auto
scope: 承認済みすべて
git_push: しない
deploy: しない
external_write: しない
paid_services: 使わない
external_exposure: 公開しない
</run_options>
```

In VS Code, set the Agent to conductor, type `/build` in the chat box, follow it with your request, and send. No input form for `<request>`, `<answers>`, or `<references>` is shown. The same applies in the GitHub Copilot app: select conductor in the agent picker (or with `/agent` in the prompt box), type `/build` in the prompt box followed by your request, and send ([README, "Run with the GitHub Copilot app"](../README.en.md#run-in-the-github-copilot-app)).

- **Show the template**: Send `/build-template` (`/build template` works the same way) and the template above is output in the chat as a code block without starting a run. Because the conductor sometimes treats `/build template` as an ordinary request, use `/build-template` when you want to be sure the template is shown (`.github/skills/build-template/SKILL.md`. The template is identical to the defaults of `build`, and a test confirms the match). Copy it, edit it, paste it after `/build`, and send. VS Code skills cannot insert text directly into the input box, so the template is output as a response instead.
- **Write only what you want to do** (example: `/build 申請に下書き保存を加える`): The whole input becomes `<request>`. `<answers>` and `<references>` are empty, and `<run_options>` uses the defaults above.
- **Also specify answers or run_options**: Paste the template above after `/build`, change only the parts you need, and send. Keys omitted from `<run_options>` take their default values.
- **Change the team defaults**: Edit the template in `.github/skills/build/SKILL.md` (locally modified files are not overwritten even if you re-run the install command).
- **Do not use `/build`**: Sending the full edited template as-is behaves the same way (the condition is that the Agent is conductor). The same format is used when passing it with Copilot CLI's `-i` ([README, "Run with Copilot CLI"](../README.en.md#run-in-copilot-cli)).

## 1.2 How to write `<request>`

- Write **what, for whom, and why**. You do not need to write "how to build it," such as screen layouts or DB design (the requirements definition document describes "what must be satisfied").
- When changing or retiring an existing requirement, write the requirement ID if you know it (examples: "Change the retention period of FR-012 from 30 days to 90 days," "Retire FR-020").
- If thresholds (counts, times, amounts) are already decided, write them as they are. If not, rd-author raises them in the questionnaire.
- Wrap text pasted from other materials in `<pasted_content id="a1">` and `</pasted_content id="a1">`. Instructions inside are treated as input data, not as work instructions (prompt-injection countermeasure).
- If left empty, only an audit of the managed data and fixes of inconsistencies that can be resolved by fact-checking alone are performed.

## 1.3 How to write `<answers>`

Answer the "Unanswered questionnaire" and "Blanket-approved items" in the previous `run-report.md`. You can write one item per line.

```text
Q-003: B
Q-004: 推奨どおり
FR-021: 承認
FR-022: 却下（今期は対象外）
包括承認の FR-030: 取り消し（保持期間は 90 日にする）
残りはすべて推奨どおり
```

Answers are recorded in the decision log in the form "Approved (Q-003 2026-10-09)". Acceptance criteria that were BLOCKED are released and are implemented and tested in the next run.

## 1.4 run_options

| Key | Value | Meaning |
|---|---|---|
| `max_hours` | Number (default 2.5, maximum 3) | Time budget. Values above 3 hours are clamped to 3. Once 85% is exceeded (or less than 30 minutes remain), no new items are started and the run proceeds to the final step |
| `approval_policy` | `厳格` (strict) / `安全範囲は推奨どおり` (follow recommendations within the safe range; default) / `すべて推奨どおり` (follow all recommendations) | How far AI proposals are approved as recommended and implemented ([1.5](#15-approval-policy)) |
| `parallel_workers` | `auto` (default) / number | Upper limit on implementers run concurrently. `auto` is 1 per 2 cores and 6 GB, up to 8, calculated from the CPU and memory at start (8 for 20 cores and 64 GB). Each worker is given CPU threads at cores × 1.5 ÷ number of workers ([4.9](04-customization.en.md#49-compute-resources-and-the-cloud)) |
| `scope` | `承認済みすべて` (all approved) or a list of requirement IDs (example: `FR-012, FR-013`) | The range to implement in this run |
| `git_push` | `しない` (don't; default) / `作業ブランチへ push する` (push to work branches) | Even when pushing, nothing is pushed to main (hook G-5). The integration branch is pushed at the end (no PR is created). The local merge into main is performed automatically when everything is complete, regardless of this setting |
| `deploy` | `しない` (don't; default) / `する` (do) | While set to `しない`, hooks reject commands such as `azd up` and `terraform apply`, and operations that deploy or publish MCP Servers and plugins |
| `external_write` | `しない` (don't; default) / `する` (do) | Whether tools of user-configured MCP Servers, plugins, and extensions may create, update, delete, or send to external systems (email, chat, tickets, cloud resources, Copilot Studio agents, etc.). Even while set to `しない`, reads (Work IQ search, Microsoft Learn retrieval, etc.) are still allowed ([4.4](04-customization.en.md#44-using-mcp-servers-plugins-and-extensions)) |
| `paid_services` | `使わない` (don't use; default) / `budget の範囲で使う` (use within budget) | Whether to use paid external services |
| `external_exposure` | `公開しない` (don't expose; default) / `公開する` (expose) | Whether to create endpoints reachable from the internet |
| `system_test` | `必要最小限` (minimum necessary; default) / `全量` (full) | The scope of System Test in step 6. The default is only the cases for requirements changed in this run plus the canary (the same applies to the run at every integration). `全量` runs all cases and so takes time (not included in the template; add it only when needed) |

## 1.5 Approval policy

The principle of the original Prompt is "AI proposals wait for approval and are not implemented." Kept as is, this principle would stall every requirement awaiting approval during a long run. So the range in which work may proceed with the recommended option is decided in advance.

| Value | Behavior | Suited for |
|---|---|---|
| `厳格` (strict) | AI proposals are not implemented | Early requirements definition with many business decisions (Phase 2) |
| `安全範囲は推奨どおり` (follow recommendations within the safe range; recommended) | The recommended option of an AI proposal or questionnaire that meets **all** of the following conditions is implemented as "Approved (blanket approval YYYY-MM-DD, approval_policy)": (1) it does not touch user data, permissions, security, privacy, billing, laws and regulations, external exposure, master data and ID schemes, or irreversible operations; (2) it can be reverted by changing a PARAM; (3) it does not conflict with existing approved requirements. Everything else is set to BLOCKED | Ordinary feature development |
| `すべて推奨どおり` (follow all recommendations) | Only the excluded areas in (1) above are set to BLOCKED; the rest are implemented with the recommended option | Prototypes and PoCs |

Blanket-approved items are listed in the report under "Blanket-approved items" in descending order of impact. You can reject or amend them in `<answers>` of the next request.

## 1.6 Common request patterns

| What you want to do | Example |
|---|---|
| New development | "Build an app that supports the 〇〇 business. Users are △△ and can do □□" + materials in `<references>` |
| Add a feature | "Add draft saving to applications. Reason: many users drop off because of re-entry" |
| Change | "Change the retention period (PARAM-004) of FR-012 from 30 days to 90 days" |
| Delete | "Retire FR-020 (the old export feature)" → rd-author marks it "retired," implementer deletes the code, tests, and catalog rows, and finally it is removed from the body |
| Audit only | Leave `<request>` empty and set `max_hours: 2` |
| Apply answers only | Leave `<request>` empty and write only `<answers>` |
| Right after installing into an existing repository | "Align the existing requirements definition document (docs/requirements-definition.md) with the toolkit's format (structured fields, verification levels, PARAM). Do not change the meaning" |
| Diagnosing past contradictions (Phase 0) | Call rd-auditor directly with `scope: 全量`, `runs: 1`, `history_mode: する` ([08-roadmap.md](08-roadmap.en.md)) |
| Starting from a GitHub Spec Kit specification | Paste the request text produced by `python scripts/import-speckit.py` after `/build` ([1.7](#17-importing-github-spec-kit-specifications)) |

## 1.7 Importing GitHub Spec Kit specifications

You can import specifications written with [GitHub Spec Kit](https://github.com/github/spec-kit) (the artifacts of `/speckit-specify` and `/speckit-clarify`) into this toolkit's requirements definition document, and then implement and verify them with the conductor. The division of labor is: Spec Kit for writing the specification, and the conductor for building it through to the end and verifying it.

```bash
python scripts/import-speckit.py                          # All specs/*/spec.md in this repository
python scripts/import-speckit.py --source ../photo-app    # A Spec Kit project in another repository
python scripts/import-speckit.py --feature 001            # Select feature directories by prefix match (multiple allowed)
python scripts/import-speckit.py --implement              # Make the request text do both import and implementation in one run
```

The output is `work/import/speckit-<datetime>.md`. Paste the "request text" inside it after the conductor's `/build` and send.

| Spec Kit | Candidate destination (final decision is rd-author's) |
|---|---|
| User Story (Priority P1 / P2 / P3) | Usage scenarios and requirements (FR). Priority is MUST / SHOULD / MAY |
| Acceptance Scenarios (Given / When / Then) | Acceptance criteria (AC). The candidate verification level is system |
| Functional Requirements (such as `FR-001`) | Requirements (FR). MUST / SHOULD / MAY in the text are used as priority candidates |
| `[NEEDS CLARIFICATION: …]`, Edge Cases phrased as questions | Questionnaire (Q), and BLOCKED for the related AC |
| Clarifications (`Q: … → A: …`) | Decision log (origin: user decision) |
| Success Criteria (such as `SC-001`) | Success indicators of goals (G), or non-functional requirements (NFR) |
| Key Entities | Glossary and target entities |
| Assumptions | Premises and constraints, or ASSUMPTION |
| Constitution principles | Default constraints, or non-functional requirements. Development-process principles go to the decision log |
| plan.md, tasks.md, contracts/ | Listed only in `<references>` (technology choices are not made into requirements) |

- The script does not edit the requirements definition document and does not assign IDs (G-1, G-3). Spec Kit IDs are kept as source IDs in the form `speckit:001-photo-albums/FR-003`, and rd-author reassigns IDs with `next-id.py` and writes them in the source field.
- The default request text uses `scope: なし` and `approval_policy: 厳格`, and performs requirements definition only. Answer the questionnaire in the report, then implement in the next `/build`.
- If any parts remain as template text (such as `[FEATURE NAME]`), a `WARN` is emitted. Either fill them in on the Spec Kit side first, or have rd-author raise them in the questionnaire.
- You may leave Spec Kit installed in the same repository. Spec Kit documents (`specs/**/*.md`, `.specify/**`) use their own numbers such as `FR-001`, so they are excluded from the ID check (CHK-19) and from `select-tests.py`. When integrating, do not use `/speckit-implement` or `/speckit-converge`; leave implementation to the conductor. Do not use Spec Kit skills while a run is in progress (update the specification after the run ends).
- The integration concept, architecture diagram, and data mapping diagram are in [README, "Integration with GitHub Spec Kit"](../README.en.md#integration-with-github-spec-kit).
