[日本語](03-requirements-format.md) | **English**

# 3. Format of the Managed Data

The managed data consists of documents meant for humans to read, but they are written in a format that `scripts/verify.py` can check mechanically. Normally rd-author, test-designer, and implementer write them, so users do not need to write them by hand. This page is a reference for when you fix them by hand or migrate existing documents.

Note: field names, decision-state values, and other keywords in the examples and tables below (such as `要求`, `決定状態`, `承認済み`) are literal strings that the verifier checks, so they are kept in Japanese, with an English gloss in parentheses where needed.

## 3.1 Requirements definition document (`docs/requirements-definition.md`)

### Section structure

The sections of the template (created at install time) are as follows.

Document information and change history / Overview (goal `G-001`) / Scope and out of scope / Premises and constraints (**default constraints**, **PARAM**, **glossary**, states) / **Personas** / Usage scenarios / **Requirements** / Information presentation by workspace and persona / External integrations, masters, and IDs / Decision log / Assumptions and open issues (**questionnaire**, approval requests, ASSUMPTION / TBD / conflicts, **audit findings**, proposals and hypotheses) / Source ledger (`SRC-001`)

When requirements exceed 150 items, 300 KB, or 3 business boundaries, the requirements definition document becomes an index and is split into per-boundary files `docs/requirements/<boundary name>.md`. verify reads both.

### One requirement, one heading, and structured fields (Rule B)

```markdown
#### FR-012 入力の中断と再開
- 要求: 申請を入力している利用者は、入力を中断して後で再開したときに、入力済みの内容と未完了の項目を確認できる。
- 決定状態: 承認済み（依頼 2026-10-08）　出自: 依頼原文　優先度: MUST（中断のたびの再入力が離脱の原因）
- 上位: G-002　出典: SRC-003 §2.1
- 対象エンティティ: 申請　関係する状態: 下書き→提出済み　参照パラメータ: PARAM-004
- 関連する既存資産: 共通部品「下書き保存」
- 受入基準 AC-031: 入力途中で画面を閉じた利用者が、同じアカウントで再び開いたとき、入力済みの値が失われず、未完了の項目が識別できる。保持期間は {PARAM-004} とする。
  - 検証レベル: system
- 受入基準 AC-032: 保持期間を過ぎた下書きは一覧に表示されない。
  - 検証レベル: integration
  - BLOCKED: Q-007（保持期間の起点が TBD）
```

(Example gist: FR-012 "Interrupting and resuming input" — a user who is entering an application can, after interrupting and later resuming, see what has been entered and which items remain incomplete. AC-031: a user who closed the screen mid-entry and reopens it with the same account does not lose entered values and can identify incomplete items; the retention period is {PARAM-004}. AC-032: drafts past the retention period are not shown in the list; BLOCKED by Q-007 because the starting point of the retention period is TBD.)

| Field | Required | How to write |
|---|---|---|
| Heading | ○ | `#### <requirement ID> <short title>`. Functional requirements are `FR-001`; non-functional requirements are `NFR-<category>-001` (categories: PERF, SEC, OPS, A11Y, UX, etc.) |
| 要求 (requirement) | ○ | In the form "[Target person/system] satisfies [result] in [situation/condition]." Write only one subject per requirement |
| 決定状態 (decision state) | ○ | One of `承認済み（依頼 YYYY-MM-DD）` (approved by request), `承認済み（Q-### YYYY-MM-DD）` (approved by questionnaire answer), `承認済み（承認依頼 YYYY-MM-DD）` (approved by approval request), `承認済み（包括承認 YYYY-MM-DD・approval_policy）` (blanket approval), `AI提案／承認待ち` (AI proposal / awaiting approval), `保留` (on hold), `却下` (rejected), `廃止（依頼 YYYY-MM-DD）` (retired by request) |
| 出自 (origin) | ○ | 依頼原文 (original request) / 利用者決定 (user decision) / AI提案 (AI proposal) |
| 優先度 (priority) | ○ | MUST / SHOULD / MAY, and the reason |
| 上位 (parent) | ○ | A goal such as `G-001`, or "既定制約" (default constraints) |
| 出典 (source) | | `SRC-xxx §…` (an ID defined in the source ledger. CHK-24) or "依頼原文" (original request), etc. |
| 対象エンティティ (target entity), 関係する状態 (related states), 参照パラメータ (referenced parameters) | ○ | Write "なし" (none) if there is no value. Target entities must be only those defined in the glossary table or the state table; related states only those defined in that entity's state table. Referenced parameters lists every PARAM used as `{PARAM-xxx}` in the body and acceptance criteria (CHK-25). They are used for clustering at audit time (cross-checking requirements that share the same target, state, or PARAM) and for impact analysis |
| 関連する既存資産 (related existing assets) | | Written in the form `共通部品「…」` (common component), `API「…」`, `テーブル「…」` (table); it is checked that they actually exist in the corresponding table of the catalog (CHK-27) |
| エンティティの使い方 (entity usage) | | Optional. In the form `注文（作成）、顧客（参照/更新）`, write one or more of 作成 (create), 参照 (read), 更新 (update), 削除 (delete) per entity. Entities without a definition and words other than these are CHK-25 errors (it becomes the "使い方" (usage) shown by `scripts/entities.py list`) |
| 利用シナリオ (usage scenarios) | | Optional. In the form `1、2`, write the numbers of the numbered items in section 5. Nonexistent numbers are CHK-25 errors |
| エンティティの関係 (entity relationships) | | Optional. In the form `注文→商品（参照）、注文→顧客（外部キー）`, write the relationships between entities and their kind (参照 = reference, 外部キー = foreign key). Entities without a definition, entries lacking a kind, and words other than the above are CHK-25 errors. When a column's foreign key points to a column of another entity, a relationship for the same pair is derived automatically (duplicates are merged into one) |
| 列 (columns; optional catalog section) | | Optional. For each table listed in the table-of-tables in the catalog (`docs/catalog.md`), write the heading `### 列: <table name>`, `対象エンティティ: 注文` (may be omitted for a table tied to a single entity), and the table `\| 列名 \| 型 \| キー \| 参照先 \| 説明 \|` (column name, type, key, reference target, description). Key is `主キー` (primary key) / `外部キー` (foreign key) / `なし` (none), and the reference target is `顧客.id` (entity.column). Wrong words, nonexistent reference targets, and tables not in the table-of-tables are CHK-25 errors (with location). Entities without columns are shown as "列未記載" (columns not described), and values are not guessed. If the repository has DDL (CREATE TABLE in `*.sql`) or JSON Schema (`*.schema.json`, `*.json` under `schema(s)/`), columns, types, keys, and foreign keys are supplemented read-only (the managed data's values take precedence and discrepancies are shown. No external communication or rewriting is done) |
| 受入基準 (acceptance criteria) | ○ for MUST | `受入基準 AC-xxx: <observable result and judgment condition>`. Write `検証レベル` (verification level) beneath it |
| 検証レベル (verification level) | ○ for approved | `system` (corresponds to the System Test ledger), `integration`, `unit`, `manual` (verified in `docs/manual-tests.md`) |
| BLOCKED | When applicable | Write the cause of the block (an unanswered `Q-xxx`, `TBD`, `競合` (conflict)) |

When writing multiple fields on one line, separate them with a **full-width space** (`　`).

### PARAM, glossary, and questionnaire

```markdown
| ID | 名前 | 値 | 単位 | 根拠 | 決定状態 |
|---|---|---|---|---|---|
| PARAM-004 | 下書きの保持期間 | 30 | 日 | 依頼原文 | 承認済み |

| 用語 | 定義 | 禁止同義語 |
|---|---|---|
| 申請 | 利用者が提出する書類 | 申込、エントリー |

| 対象エンティティ | 状態 | 遷移の条件 |
|---|---|---|
| 申請 | 下書き | 入力を始めたとき |
| 申請 | 提出済み | 提出ボタンを押したとき |

| ID | 重要度 | 質問 | 選択肢 | 推奨 | 状態 | 回答 |
|---|---|---|---|---|---|---|
| Q-007 | 高 | 保持期間の起点は | A: 作成時 / B: 最終更新時 | B | 未回答 | |
```

(Column headers, in order — PARAM: ID, name, value, unit, basis, decision state. Glossary: term, definition, prohibited synonyms. State table: target entity, state, transition condition. Questionnaire: ID, importance, question, options, recommendation, status, answer. In the example, PARAM-004 is "draft retention period" = 30 days, from the original request, approved; the term 申請 (application) is "a document the user submits," with prohibited synonyms 申込 and エントリー; states 下書き (draft: when input starts) and 提出済み (submitted: when the submit button is pressed); Q-007 asks "what is the starting point of the retention period" with options A: at creation / B: at last update, recommending B, status 未回答 (unanswered).)

- Do not hard-code thresholds, periods, or counts in the body; refer to a PARAM in the form `{PARAM-004}` (CHK-14). If the value is undecided, write `TBD（Q-007）`.
- Using a prohibited synonym triggers a warning from CHK-15.
- If you set a questionnaire's "状態" (status) to "回答済み" (answered), BLOCKED entries that reference that Q become errors in CHK-18 (a prompt to reflect the answer and remove BLOCKED).
- The state table has one state per row (you may also list them in one cell such as `下書き、提出済み`). A requirement's "関係する状態" can also be written as a transition such as `下書き→提出済み`.

### Rules for connections (consistency as a system)

The requirements definition document and the catalog are treated not as separate documents but as a single body of data connected by IDs and names. verify checks the following connections in both directions.

| Connection | Rule | Check |
|---|---|---|
| Goal → requirement → acceptance criterion | A requirement has a parent G, and an acceptance criterion has a requirement. A G with no approved requirement gets a warning | CHK-03, 04 |
| Acceptance criterion ⇔ System Test ledger ⇔ tests | A system AC and a ledger case are 1:1. The IDs of implemented MUSTs appear in tests | CHK-09, 10, 11 |
| Requirement → glossary, state, PARAM, source | Structured fields point to definitions. Definitions not used anywhere get a warning | CHK-16, 24, 25, 26 |
| Requirement ⇔ catalog | Approved, awaiting-approval, and on-hold requirements each have one row in the features table. Decision state and title match | CHK-07 |
| Catalog tables among themselves | The "common components used" in the features table match the "requirement IDs using it" in the common components table. The requirement IDs in the API, table, and common component tables exist | CHK-24, 27 |
| All IDs | IDs written in the body, tables, and catalog are defined (no links to nonexistent targets) | CHK-19, 24 |

You can check connections with `python scripts/rdcheck.py trace FR-012` (a requirement's upstream G and source, lateral glossary / state / PARAM, and downstream AC, ledger cases, catalog, and code), `trace G-002`, `trace 申請`, `trace PARAM-004`, and `trace 下書き保存`. Use this to check the impact range when changing a requirement.

### Metadata definition, areas, and the relationship index (FR-1057 to FR-1059, NFR-UX-014)

- **Metadata definition**: `scripts/metadata.json` is the single definition of a requirement's fields (field names, required/optional, allowed values). Fields not in the definition and values outside the allowed values are reported by CHK-29 with `file:line`. You can write "領域" (area), "更新日（YYYY-MM-DD）" (updated date), and "版（整数）" (version, integer) as optional fields. To add a field, change metadata.json (checks, listings, and Studio all read the same definition).
- **Area**: A functional area beneath a goal (G). It is written with the area list table `| 領域名 | 上位 G-ID | 含む要求数 |` (area name, parent G-ID, number of requirements included), the requirement's `- 領域: <name>`, and the heading `#### 領域: <name>` immediately before the catalog's features table. It is optional until an area assignment table (`| 要求 ID | 領域 |`) appears in the decision log; unassigned ones are reported only as a count at `INFO`. After it appears, it becomes required, and CHK-30 reports unassigned requirements, mismatches between the table and the field, and mismatches with the catalog's divisions. You can view by area with `rdcheck.py list --area <name>` / `--by-area`.
- **Relationship index**: `rdcheck.py index [ID ...] [--kind 上位|出典|参照|実装|検証|使用] [--json]` (kinds: parent / source / reference / implementation / verification / usage). It is generated on each check or query from the requirements definition document (parent, source, reference), the catalog (implementation, usage), and the ledger (verification). It is not saved as a file. Passing an ID gives a reverse lookup (relationships where that ID is the start or end point).
- **Browsability**: Catalog tables of the same kind keep the same column names and order (CHK-31). When the number of items directly under a section divided into areas exceeds PARAM-043 (default 20), CHK-32 warns (only after the assignment table is approved).

### Default constraints (ui_policy)

The UI policies that the original Prompt always requires (a UI whose layout the user can change, and information presentation by persona) are written in the "default constraints" section. An app with no screens (batch or API only) can omit them by writing the fact and its basis as "画面を持たない" (has no screens) in the premises and constraints (CHK-20).

## 3.2 Catalog (`docs/catalog.md`)

It consists of 4 tables. Write one item per row and leave the details to the linked destinations.

```markdown
## 機能
| 要求 ID | 題名 | 決定状態 | 実装ファイル | テスト | 使っている共通部品 |
|---|---|---|---|---|---|
| FR-012 | 入力の中断と再開 | 承認済み | src/drafts/service.ts | tests/unit/drafts.test.ts | 下書き保存 |
| FR-013 | 申請の取消 | 承認済み | 未実装 | 未実装 | なし |

## API・イベント
| 名前 | 定義ファイル | 関連する要求 ID |
## テーブル
| テーブル名 | 定義ファイル | 正本のシステム | 関連する要求 ID |
## 共通部品
| 部品名 | ファイル | 用途 | 使っている要求 ID |
```

(Table headers: 機能 (features): requirement ID, title, decision state, implementation file, test, common components used. API・イベント (APIs and events): name, definition file, related requirement IDs. テーブル (tables): table name, definition file, system of record, related requirement IDs. 共通部品 (common components): component name, file, purpose, requirement IDs using it. "未実装" means not implemented; "なし" means none.)

- Keep the decision state and title consistent with the requirements definition document, and list every approved, awaiting-approval, and on-hold requirement as one row in the features table (CHK-07). Paths written in the file columns must actually exist (CHK-08).
- Components written in the features table's "使っている共通部品" must be listed in the common components table, and the common components table's "使っている要求 ID" must match the features table (CHK-27. You can align it to the features table with `rdfix.py --only catalog --apply`). The "関連する要求 ID" of the API, table, and common component tables must be IDs that exist in the requirements definition document (CHK-24).
- Write "未実装" for unimplemented requirements. The ID of an implemented MUST requirement must appear in test code (the test name or the immediately preceding comment) or in `docs/manual-tests.md` (CHK-09).

## 3.2.1 External integration catalog (`docs/integrations.md`; optional)

Create it only if the app integrates with external apps or data through APIs, files, DBs, events, and so on (apps with no external integrations need not create it, and the behavior of checks, Studio, and cleanup is unchanged when it is absent). On install, a template containing a format description and an empty index table is created **only when it does not exist yet** (an existing file is not overwritten). The path can be changed with `management_files.integrations` in `scripts/ebak.config.json`. rd-author performs additions, changes, and retirements, and changes are recorded in the change history of the requirements definition document.

One item per integration: under a heading `#### INT-001 <name>`, write a bulleted list of "field name: value," and place an index table (ID, name, integration partner, direction, status, related requirements) at the top.

- Fields that must always have a value: integration partner (連携先), direction (方向: 受信 inbound / 送信 outbound / 双方向 bidirectional), method (方式), data classification (データ分類), personal information (個人情報), authentication and authorization (認証認可), responsibility boundary (責任分界), status (状態: 検討中 under consideration / 運用中 in operation / 廃止 retired), and related requirements (関連する要求: FR-xxx / NFR-xxx-xxx).
- Fill in the other fields for the 16 perspectives (frequency and volume, availability and SLA, rate limits, errors / retries / idempotency, contract and versioning, change notification, monitoring, data retention, fallback on failure, legal and licensing) with one of a value, `なし`, or `TBD（Q-xxx）`. The meaning of the fields and how to verify them are in `.github/skills/requirement-definition/integration-checklist.md` in the adopting repository.
- Do not write credential values (tokens, passwords, keys, connection strings). For authentication and authorization, write the name of the method; for "秘密の保管場所" (secret storage location), write only the name of the storage location. Strings that look like values are violations.

Procedure:

1. Add: Allocate an ID with `python scripts/next-id.py INT` (`--peek` to only check), add the item and an index table row, and reference `INT-xxx` from the related requirements.
2. Change: Fix the item's fields and record it in the change history.
3. Retire: Set the status to "廃止". Do not delete the item, and do not reuse the ID.
4. Check: `python scripts/verify.py --docs-only` (CHK-28). Duplicate or malformed IDs, missing required fields or perspective fields, malformed values, TBD Q-IDs, direction and status, related requirements, and strings that look like credential values are errors (exit 1; outputs the INT-ID and `docs/integrations.md:<line>`). If the requirements definition document references a nonexistent INT-xxx, that is an undefined-reference error; cases such as being in operation while the related requirement is not approved are warnings. `python scripts/rdcheck.py trace INT-xxx` lists the requirements and acceptance criteria that reference that integration.

## 3.3 ID registry (`docs/id-registry.md`)

Only `scripts/next-id.py` may add rows. Editing by hand is rejected by a hook (G-3).

| State | Meaning |
|---|---|
| 採番済み (allocated) | Allocated but not yet in the body |
| 使用中 (in use) | In the body |
| 廃止 (retired) | Remains in the body as "廃止" |
| 削除済み (deleted) | Removed from the body. **Reuse prohibited** (CHK-02) |
| 欠番 (skipped) | Allocated but not used. Reuse prohibited |

So that parallel branches do not conflict when adding rows at the same time, `merge=union` is specified in `.gitattributes`. ID allocation across worktrees is mutually exclusive via `ebak-id-alloc.json` in git's common directory.

## 3.4 System Test ledger (`tests/system/ledger.json`)

```json
{
  "version": 1,
  "ac_digests": { "AC-031": "sha256:3f6c0a1b2c3d4e5f" },
  "cases": [
    {
      "id": "E2E-001",
      "requirement_ids": ["FR-012"],
      "ac_ids": ["AC-031"],
      "title": "中断した入力を再開できる",
      "layer": "e2e",
      "command": "npx playwright test tests/system/e2e/fr-012.spec.ts",
      "canary": true,
      "status": "pass",
      "last_commit": "a1b2c3d",
      "last_run_at": "2026-10-08T10:15:00+09:00",
      "evidence": "work/runs/202610080900/logs/system-test/E2E-001-202610081015.log",
      "history": [{ "at": "…", "by": "test-designer", "change": "追加", "reason": "受入基準からケースを作成" }]
    }
  ]
}
```

(In the example, `title` is "Interrupted input can be resumed," `change` is "追加" (added), and `reason` is "Created the case from the acceptance criterion.")

| Key | Meaning |
|---|---|
| `id` | `E2E-001` if layer is e2e, otherwise `IT-001`. Not reused even after deletion |
| `layer` | e2e, api, contract, data, nonfunctional, ai_eval |
| `command` | A command that can be run non-interactively from the repository root and returns exit 0 on success |
| `canary` | The main flow run first (smoke test) |
| `status` | not_run, pass, fail, blocked (pass/fail are set only by actual execution results) |
| `evidence` | The log of the last run (under `/work`. It is deleted after the retention period, so re-run to recreate it if needed) |
| `ac_digests` | Digest of the AC body (with PARAM expanded). CHK-11 detects when an AC changes |

**Definition of "1:1"**: The state in which approved, non-BLOCKED ACs with verification level system and ledger cases correspond in both directions (one AC may have multiple cases), and the digests match.

The ledger is updated only via `scripts/ledger.py` (direct edits are rejected by hook G-2). Cases cannot be deleted. A case that is no longer needed is set to blocked with `ledger.py block --reason`, and the reason is left in history.

Keep the number of requirements, acceptance criteria, and cases optimal (so as not to increase the amount each role reads, tokens, and test execution time). When a request overlaps an existing requirement, rd-author looks for similar items with `rdcheck.py similar` and changes the existing item instead of creating a new one. `ledger.py add` refuses to add if there is a valid case that already guarantees the same acceptance criterion (extend the existing case with `ledger.py update`. Add `--new-case-reason "reason"` only when the layer differs and a separate case is truly needed).

## 3.5 Run history (`docs/run-history.md`)

`run-state.py finish` appends one row per run. The columns are run-id, start, end, HEAD, result, implemented requirement IDs, BLOCKED, AC pass rate, elapsed time, first-time gate pass rate, AI credits, human interventions, and verified requirements. The run-id must be unique (CHK-23). When appending to a table from 1.1.0 or earlier, the "人の介入" (human interventions) and "検証済み要求" (verified requirements) columns are added automatically, and `-` is entered in past rows.
