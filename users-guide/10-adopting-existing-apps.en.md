[日本語](10-adopting-existing-apps.md) | **English**

# 10. Adopting an existing app (Adopt)

This chapter gives the procedure for using this toolkit with an app that already has source code, design documents, and tests, and the rationale for the approach chosen. Unlike new development (building from requirements), **there is no source of truth for requirements yet**, so you prepare the data layer (the requirements definition, the catalog, and the System Test ledger) first.

## 10.1 Summary (the shortest way to use it)

```text
python tools/install.py --target <existing repository>     # Install the toolkit (does not break existing files)
python scripts/adopt.py scan                              # ① Inventory (facts only; no LLM) → docs/baseline/inventory.md
python scripts/adopt.py request                           # ② Create the /build request text → work/import/adopt-<datetime>.md
```

③ Paste the request text after `/build`, with the Agent set to conductor (this builds requirement hypotheses and pins current behavior; it does not change code).
④ For the requirements under "Pending approval (reverse-generated)" in the report, reply with `<answers>`, for example `FR-0xx: 承認` (approve).
⑤ After that it is the normal `/build` (changes and additions). Changed behavior is detected by `golden check`. To collect the next cluster, repeat from ②.

| Command | Role | Where it writes |
|---|---|---|
| `adopt.py scan [--since-days N]` | Collects files, roles, languages, routes, tables, tests, design documents, and churn, and orders feature clusters by hotspot | `docs/baseline/inventory.{json,md}` |
| `adopt.py request [--clusters N] [--cluster name] [--implement]` | Selects uncollected clusters and turns them into a `/build` request text (defaults to `scope: なし` and `approval_policy: 厳格`) | `work/import/` |
| `adopt.py anchor SRC-xxx file:start-end` | Pins the hash of a code range to a requirement's source (SRC) (whitespace-only changes are ignored) | `docs/baseline/evidence.json` |
| `adopt.py check [--strict] [--json]` | Checks evidence drift (DRIFT), the collection rate, reverse-generated requirements without a source, blanket-approval mistakes, and golden status | None (exit 1 = error) |
| `adopt.py golden add／record／check／list` | Characterization tests that record and replay current behavior (exit code, standard output, standard error) | `tests/system/golden/` |

The details of the procedure (the roles of rd-author, test-designer, rd-auditor, and implementer) are in the skill `adopt-existing`.

## 10.2 Three layers (do not mix things of different reliability)

| Layer | Content | Created by | Reliability | Decision status |
|---|---|---|---|---|
| 1 Facts | Inventory (files, routes, tables, tests, churn) | `scan` (deterministic) | High (a copy of the code) | Not a requirement |
| 2 Hypotheses | Reverse-generated requirements, ACs, and question sheet | rd-author | Medium (intent is inferred) | Always "pending approval", origin "reverse-generated". **No blanket approval** |
| 3 Pinning | Golden master of current behavior and reuse of existing tests | test-designer | High (measured). But it means "this is how it is now", not "this is correct" | Can also be attached to requirements pending approval |

Only the requirements the user has approved become the target of normal runs (the basis for changes).

## 10.3 Research, and verification of fit with this toolkit

The user's initial assumption was to "do Adaption / Analytics / Rebuild first, then prepare the data layer". We cross-checked published knowledge on four points.

### Approaches investigated

| Approach (source) | Key points | Adopted? | Reason |
|---|---|---|---|
| Taxonomy of reverse engineering (Chikofsky & Cross, 1990, *IEEE Software*) | Treats "redocumentation" and "design recovery", which recover more abstract representations (design, requirements) from an existing system, separately from modification (reengineering) | **Adopted** (layers 1 and 2) | Separating recovery from modification means the implementation need not change before approval. It points the same direction as EABK's "requirements are the source of truth" |
| Characterization tests (Feathers, *Working Effectively with Legacy Code*, 2004) / approval tests (golden master) | Record current behavior rather than correctness, and detect unintended differences caused by changes | **Adopted** (layer 3) | An existing app has no ACs, so System Tests cannot be created first. The recorded current state can serve as the expected value. Also consistent with Hyrum's Law (observable behavior will be depended on by someone) |
| Strangler Fig (Fowler) | Let old and new coexist and replace incrementally, one feature cluster at a time | **Adopted** (the policy for change runs) | Same shape as conductor's approach of handling one item at a time through worktree, integration, and verification. A "cluster" becomes the unit of `--boundary` |
| Hotspot analysis (Tornhill, *Your Code as a Crime Scene*, 2015) | Defects and changes concentrate where change frequency × complexity is high | **Adopted** (order of collection) | Do not collect everything at once (cost and errors grow), but start from where the value is highest. `scan` orders by churn × √lines |
| Decision records (Nygard, ADR, 2011) | Keep decisions in short documents | **Existing mechanisms suffice** | The decision record (§9), question sheet, and source ledger play the same role |
| LLM-based reverse generation of requirements and specifications (reported in 2024–2025 research) | Requirements and descriptions in prose can be generated from code. On the other hand, generating nonexistent requirements (hallucination) and omissions are problems, automated metrics are not trustworthy, and human review and grounding in the original code are required. A method of reconstructing the original from the generated output and comparing (reverse generation) has been proposed | **Adopted (with constraints)** | Layer 2 is bound by mandatory sources, evidence pinning (`anchor`), fixed pending-approval status, and confirmation of reverse-generation consistency in an independent audit |
| Doing a full rewrite (Rebuild) first | Reconstruct the specification and then rebuild | **Not done first** | Past fixes and implicit specifications are easily lost. Only once layers 1–3 are in place can a replacement that satisfies approved requirements and golden be verified (that is, Rebuild can be done after layer 3, cluster by cluster) |

### Verification of fit (against this toolkit's purpose)

| Purpose / rule | Why the approach satisfies it | Verification (test) |
|---|---|---|
| The only writer of the requirements definition is rd-author (G-1), and IDs come only from `next-id.py` (G-3) | `adopt.py` does not edit the requirements definition and does not assign IDs. It writes only the inventory, evidence, golden, and request text | `tests/toolkit/test_adopt.py` |
| Consistency between requirements and implementation/tests (sources, catalog, ledger) | Reverse-generated requirements require an SRC. An SRC cannot be approved without pinned evidence. The collection rate is computed from the catalog and requirements | `test_check_guards_reverse_generated_requirements` |
| Prevent misreading of intent (human approval) | `check` rejects blanket approval for reverse-generated requirements. Approval comes only from the user's `<answers>` | Same as above |
| Verifiability (System Tests come before implementation and implementers do not rewrite them) | golden is placed under `tests/system/`, so implementer and reviewer cannot change it (G-2). It is run twice when pinned, and recording is refused if the result is nondeterministic | `test_golden_rejects_nondeterministic` |
| Preventing regressions | If you make `golden check` a ledger case, it runs at every integration by the same mechanism as the canary | `test_golden_record_check_and_regression` |
| Minimum cost of change (Token, time) | The inventory does not use an LLM. A request covers about 6 clusters at most. Hotspot order | `test_scan_inventory`, `test_request_draft_is_unapproved_and_scope_none` |
| Detecting stale hypotheses | If the hash of the evidence range (ignoring whitespace) changes, DRIFT is raised | `test_anchor_drift_and_whitespace_insensitive` |

### Limitations (honestly)

- The quality of reverse-generated requirements depends on the LLM and the readability of the code. Independent audit (checking reverse generation) lowers the risk, but it does not reach zero. That is why approval is left to the user.
- `scan`'s detection of routes and tables relies on regular expressions for major frameworks. Configurations it cannot detect (such as dynamic routing) do not appear in the inventory. Not appearing is not proof of nonexistence. The "collection rate" is the proportion of paths written in the catalog and requirements, not semantic coverage.
- golden suits behavior that can be invoked as a command (CLI, scripts, small drivers). Behavior that goes through UI operations or external services should be a normal System Test (E2E) or manual.
- When design documents and code disagree, it does not decide which is right. It turns the disagreement into a conflict or a question sheet and returns it to the user.

## 10.4 When design documents exist

`scan` lists candidate design documents (files named like design, specification, ADR, OpenAPI, ER diagram) and the ID prefixes within documents (such as `REQ-` and `FUNC-`). rd-author reads the design documents **first** and handles them as follows.

- Statements in design documents are sources (category: design document). Statements in code are sources (category: code). A requirement for which **both** can be cited is the strongest hypothesis.
- Disagreements become a conflict or a question sheet. Never silently pick one.
- Keep existing IDs in the source and do not replace them with EABK IDs (FR, AC) (the correspondence can be traced in the source field).

## 10.5 Operation

- Collected clusters remain in `docs/baseline/evidence.json`. After changing code, check DRIFT with `adopt.py check` (run outside verify; `--strict` makes warnings fail too).
- Manage `docs/baseline/` and `tests/system/golden/` in git (share them across the team).
- `adopt.py scan` can be run any number of times (it overwrites). If the baseline commit differs from HEAD, `check` reports STALE.
