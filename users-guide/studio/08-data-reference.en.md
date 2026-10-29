[日本語](08-data-reference.md) | **English**

# S8 Data Reference (Which Feature Reads Which Data)

This is a list of **which file, which section, column, or field** each EABK Studio screen and feature reads, and **how it calculates** what it displays. Use it when you want to check the basis of a number or diagram ("What is this 62% a percentage of?").
The content was verified against the implementation (`EABK-Studio/eabk_model.py`, `studio.py`, `web/js/*.js`).

- Studio reads **only data-layer files**. It does not open the contents of source code. It uses the **path strings** written in the catalog and the ledger merely as names (S8.1, S8.8).
- Normal browsing is read-only. The only thing Studio writes is `docs/catalog.md`, and only when you confirm and run "Consistency maintenance" (S8.9).
- Communication is `127.0.0.1` only (S8.10).

## S8.1 Files Read

You can change the locations with `management_files` in the target repository's `scripts/ebak.config.json` (or `scripts/hve.config.json` if it does not exist). The values below are the defaults.

| Setting key | Default path | How it is read | Screens that use it |
|---|---|---|---|
| `requirements` | `docs/requirements-definition.md` | Parses headings, bullet lists, and tables | Almost all |
| `requirements_dir` | `docs/requirements/*.md` | Same as above (requirement files split by boundary; in file-name order) | Almost all |
| `catalog` | `docs/catalog.md` | Parses tables (features, APIs, tables, common parts) | 2D/3D, Placement, Source mapping, Consistency, Maintenance |
| `ledger` | `tests/system/ledger.json` | Parsed as JSON | Dashboard, Tables (test cases), Consistency, Structure |
| `id_registry` | `docs/id-registry.md` | Parses tables (counts and structure judgments) | Dashboard, Structure |
| `run_history` | `docs/run-history.md` | Parses tables | Dashboard, Tables (run history), Structure |
| `manual_tests` | `docs/manual-tests.md` | **Existence check only** (the contents are not parsed) | None (only the `--check` listing and the model's `meta.files`) |

- At startup, you can run `python EABK-Studio/studio.py --check` to see which files were found and how many items were parsed ([04-troubleshooting.en.md](04-troubleshooting.en.md)).
- Requirements are collected from **both** `docs/requirements-definition.md` and `docs/requirements/*.md`. If the same ID appears two or more times, the first one is used, and the rest are reported as duplicates on the Structure screen.
- How things look when a file is missing is described in S8.7.
- Basis for not reading code contents: the test `test_nothing_outside_the_data_layer_is_read` (`EABK-Studio/tests/test_studio.py`) verifies that requirement IDs written in files under `src/` are not read.

## S8.2 Items Extracted from the Requirements Definition

From `docs/requirements-definition.md` and `docs/requirements/*.md`, Studio extracts items in the following formats (code blocks are ignored). The formats follow the [management data format](../03-requirements-format.en.md) of EABK itself.

| What is extracted | Format | Model field |
|---|---|---|
| Requirement | Heading `## ` to `###### ` followed by `FR-nnn title`, `FR-<category>`, or `NFR-<category>-nnn` (bold is also accepted) | `id`, `title`, `kind` (FR/NFR), `cat` (NFR category) |
| Requirement body | `- 要求: …` directly under the heading (continues until the next item starts) | `text` |
| Decision status | `- 決定状態: 承認済み` etc. Classified by the leading word into 承認済み / AI提案 / 保留 / 却下 / 廃止 | `status`, `statusKind` |
| Priority | `- 優先度: MUST` etc. (MUST/SHOULD/MAY/COULD/WON'T are judged from the beginning) | `priority` |
| Parent goal | `- 上位: G-001` | `goal` |
| Origin / source | `- 出自:`, `- 出典:` | `origin`, `sources` |
| Data handled | `- 対象エンティティ: 申請、承認` | `entities` (split on `,` `、` `;` `・` `/`) |
| Related states, PARAMs, existing assets | `- 関係する状態:`, `- 参照パラメータ:`, `- 関連する既存資産:` | `states`, `params`, `assets` |
| Relations between entities | `- 関係: …` | `relation` (used for the ER diagram) |
| Acceptance criteria | `- AC-nnn: …`, `- 受入基準 AC-nnn: …`, or a heading `AC-nnn` | `acs[].id`, `text` |
| Verification level | Indented line under an AC: `- 検証レベル: system` | `acs[].level` (the leading word, lowercased) |
| BLOCKED | Indented line under an AC: `- BLOCKED: Q-003 …` | `acs[].blocked`, and the requirement's `blocked` (`Q-nnn` is extracted) |
| Index table | A table whose header row has `要求ID` and `題名`, plus `所属ファイル` or `優先度` | Fills in priority and decision status missing from headings; adds requirements that have no heading |
| Goals | A table (first column `ID` = `G-001`; columns 2–4 are title, metric, method), or a bullet `- 目的 G-001: …` | `goals` |
| PARAM | A table (`ID` = `PARAM-001`; columns name, value, unit, basis, decision status) | `params` |
| Questionnaire | A table (`ID` = `Q-001`; columns severity, question, options, recommendation, status, answer) | `questions` |
| Source table | A table (`ID` = `SRC-001`; columns document, version, date, category) | `sources` |
| Audit findings | A table (`ID` = `AUD-001`; columns date, category, severity, location, summary, status) | `audits` |
| Glossary | A table (first column `用語`; columns 1–3 are term, definition, expressions not to use) | `terms` |
| Personas | A table (first column `ペルソナ`; columns task, key decisions, data used, role) | `personas` |
| External integrations | A table (first column `連携先`; columns 1–5 are partner, method, meaning (direction), system of record, ID assignment), or a bullet `- 外部連携 名前: …` | `integrations` |
| Decision log | A table (first column `日付`, with a `対象ID…` column; columns 1–5 are date, target, decision, rationale, run) | `decisions` |
| State table | A table (the header has `対象エンティティ` and `状態`; if a `遷移…` column exists, it holds transition conditions) | `stateMachines` (states and transitions; `→` and `／` are interpreted) |

- `{PARAM-001}` in an acceptance criterion's body is not substituted on screen and is displayed as written (it is, however, replaced with the PARAM value when matching the AC digest in S8.5.8).
- Usage scenarios (bullets under a `利用シナリオ` heading) are parsed but **not shown on any screen**.

## S8.3 Items Extracted from the Catalog

Tables in `docs/catalog.md` are identified by the **column names in the header row**.

| Table | Identifying column names | Columns read | Model field |
|---|---|---|---|
| Features | `要求ID` and `実装ファイル` | Requirement ID, title, decision status, implementation files, tests, common parts used | `catalog.features` (`impl` and `tests` keep only path-like strings; `なし`, `未実装`, `—`, etc. become empty) |
| APIs / events | `名前` and `定義ファイル` | Name, definition file, related requirements (column 3) | `catalog.apis` |
| Tables | `テーブル名` and `定義ファイル` | Table name, definition file, system of record, related requirement IDs | `catalog.tables` |
| Common parts | `部品名` | Part name, file, purpose, requirement IDs that use it | `catalog.parts` |

- A "path-like string" is a string that contains `/`, or ends with `.` and a 1–6 character extension. Parenthetical notes `（…）` and `:line-number` suffixes are removed. **Whether the file actually exists is not checked.** If it is written in the catalog, it is "registered".
- Ranges and enumerations such as `FR-nnn〜mmm` and `FR-nnn・mmm・kkk` are expanded to defined requirement IDs.

## S8.4 Items Extracted from Other Files

| File | What is read |
|---|---|
| `tests/system/ledger.json` | In `cases[]`: `id`, `requirement_ids`, `ac_ids`, `title`, `layer`, `command`, `canary`, `status`, `last_commit`, `last_run_at`, `evidence`; plus `ac_digests`. A case's line number is derived from the position of its `"id"` in the file |
| `docs/id-registry.md` | All rows of tables whose leading columns are `ID`, `種別`, and `状態` (or `使用状態`) |
| `docs/run-history.md` | All rows of tables whose leading column is `run-id` (all columns are kept as strings) |

Paths written in `command` appear in the diagrams as **names** of test files (the files are not opened).

## S8.5 What Each Screen Reads

"Calculation" in the tables below describes how the numbers and diagrams on screen are derived. Take care, as numerators and denominators are easy to confuse.

### S8.5.1 Dashboard (`#/dashboard`)

| Display | Data read | Calculation |
|---|---|---|
| Requirements | Requirements in the requirements definition | Number of parsed requirements (FR and NFR). **All of them, regardless of decision status** |
| Approved % | The requirement's `決定状態` | Number whose status begins with "承認済み" ÷ number of requirements (to one decimal place) |
| Implementation registered % | Requirements × the catalog's features table | Number of requirements with at least one path in "実装ファイル" ÷ **number of requirements (all)**. Requirements with no catalog row, or with an empty implementation-files cell, are "unregistered". Whether the files exist is not checked |
| Acceptance criteria | The requirements' ACs | Total number of ACs across all requirements |
| Tests passed % | The ledger's `cases[].status` | Cases whose `status` is `pass` ÷ number of cases. `not_run` is not counted as passed |
| Unanswered questions | The questionnaire's `状態` | Number of questions whose status does not contain 回答済み, 解決済み, 取り下げ, or クローズ |
| BLOCKED requirements | The AC's `BLOCKED` | Number of requirements that have an AC with a BLOCKED containing `Q-nnn` |
| Files / Components | Catalog and ledger | Number of files shown in the diagram / number of their top-level components (S8.5.2) |
| Decision status, Priority | Requirements | Respective breakdowns (pie charts; clicking highlights the matching requirements on the 2D map) |
| Implementation progress by goal | Goals × requirements × catalog | For each goal (G), among requirements that have that goal as `上位`, the number with implementation registered ÷ the number of requirements for that goal |
| Implementation by boundary | Requirements' source file × catalog | For each file name (without extension) in which requirements are written, implementation-registered ÷ number of requirements |
| Verification level of acceptance criteria | The AC's `検証レベル` | Number of ACs per level (empty is `-`) |
| System Test and ID registry | Ledger / ID registry | Number of cases per `status`. For the ID registry, counts per type:status |
| Run history | `docs/run-history.md` | The last 8 rows, newest first. Up to the first 7 columns |
| Design/development history and progress | Decision log, run history, requirements, catalog, ledger | Counts by category (decision log / run history / requirement status / implementation registration / System Test) × status. Pressing one shows the file:line of the underlying records on the right (with links that open in VS Code) |

### S8.5.2 2D Map and 3D Map (`#/map2d`, `#/map3d`)

The same relationship graph is displayed flat and in 3D. The data behind the points (nodes) is as follows.

| Point type | Source data |
|---|---|
| Goal | Goals in the requirements definition |
| Requirement, acceptance criterion | Requirements definition (ACs are added via a "layer") |
| Parameter (PARAM), question | Tables in the requirements definition (added via a layer) |
| Entity | State table, glossary table, the requirement's `対象エンティティ` |
| Common part, API, table | Catalog |
| File, component | Catalog implementation files, tests, definition files of each table, and paths in the ledger's `command`. A component is the first 1–2 levels of the path (2 levels for `src`, `app`, `apps`, `packages`, `services`, `lib`, `libs`, `modules`, `internal`, `cmd`, `pkg`, `projects`, and for `tests`, `test`, `__tests__`, `spec`, `specs`; 1 level otherwise) |
| Test case | Ledger |
| Persona, external integration | Tables in the requirements definition (used by the context diagram; they do not appear in the 2D/3D layers) |

| Line (relationship) | Source data |
|---|---|
| Goal → requirement | The requirement's `上位` |
| Requirement → acceptance criterion | The requirement's ACs |
| Requirement → entity / PARAM / question | `対象エンティティ`, `参照パラメータ`, and `Q-nnn` in BLOCKED |
| Requirement → requirement (reference) | Another requirement ID written in a requirement's or AC's body |
| Requirement → implementation file / test | `実装ファイル` and `テスト` in the catalog's features table |
| Requirement → common part | `使っている共通部品` in the features table, and `使っている要求ID` in the common parts table |
| Requirement → API / table | Related requirements in the API and table tables |
| Common part, API, table → file | Their respective `ファイル` / `定義ファイル` |
| Requirement, AC → test case | The ledger's `requirement_ids` and `ac_ids` |
| Test case → test file | Paths contained in the ledger's `command` |
| File → component | Determined from the path |

- Color switching: kind (point type) / decision status (`statusKind`) / implementation status (done, none, unlisted).
- "Highlight": hovering over a point highlights direct relations; clicking highlights up to two hops (it does not traverse through `ref` relations or through points with more than 36 connections).
- Point positions (coordinates) are values computed for display and have no meaning.

### S8.5.3 Diagrams (`#/diagrams`; the type is specified with `kind=`)

| Diagram (`kind`) | Data read | How it is built |
|---|---|---|
| Context diagram (`ctx`) | Personas (table in 4.1), external integrations (table in 8), goals | The system in the center, personas on the left (line label = `業務`), external integrations on the right (label = `方式`). Goals are listed inside the central box |
| Goal tree (`goals`) | Goals, requirements, catalog | Requirements for each goal are laid out as rectangles. Color shows implementation registration or decision status. A teal-green border marks an NFR. Requirements with unknown parent are in a "no goal" column |
| State transition diagram (`states`) | State table (`対象エンティティ`, `状態`, `遷移…`) | States and transitions for each entity. A double border marks a state with no outgoing transition |
| Data relationship diagram (`entities`) | The requirement's `対象エンティティ`, state table | Entities that appear in the same requirement are connected by lines. Line thickness = number of shared requirements; circle = number of states |
| Component diagram (`components`) | Catalog paths | Components and the modules, common parts, APIs, and tables within them. Line = implements the same requirement |
| ER diagram (`er`; an auxiliary view not shown as a tab) | The requirement's `対象エンティティ` and `関係` | Only requirements that have `関係` written are shown, with their basis. For those without it, Studio **does not guess** and shows "insufficient relationship information" |

### S8.5.4 Placement (`#/placement`)

| Tab (`tab`) | Data read | Calculation |
|---|---|---|
| Business layer × component (`biz`) | Requirements, goals, catalog | Rows are chosen from goal / boundary (the file the requirement is in) / kind (FR, NFR-category). Columns are components (in descending order of number of implementation files). **Cell count = the number of requirements in that row that have an implementation file in that component**. "Include tests" also targets test components |
| Data × component (`data`) | The requirement's `対象エンティティ`, catalog | Rows are entities. Cell counts are computed the same way. A list of APIs and tables is shown below |
| Location of common parts, APIs, and tables (`items`) | Catalog | For each part, API, and table: the component containing its definition file and the number of requirements |
| App structure and data positioning (`kind=runtime`) | List of loaded files, catalog implementation files, external integrations | See S8.5.5 below |

### S8.5.5 Placement (Runtime Environment) (`#/placement?kind=runtime`)

A diagram of how Studio **itself** works, built from the files it loaded.

| Display | Data read |
|---|---|
| PC, browser, Studio server, target repository | Values from the startup environment (repository path, `/api/model`, `studio.py`). Fixed descriptions |
| Management data: <path> | Paths of management data that actually exist (S8.1; `requirements_dir` and `manual_tests` are also included if they exist) |
| Implementation file: <path> | Implementation file paths written in the catalog's features table (duplicates removed) |
| Flow table | Management data → Studio server (read), catalog → implementation files (read (registered location); names only), server → browser (read), Studio → target repository (write: none). Paths appear in the basis column on the right |
| External / cloud boundary | The requirements definition's external integrations (method, direction, system of record) |

### S8.5.6 Source Mapping (`#/source`)

| Display | Data read | Calculation |
|---|---|---|
| Treemap | Catalog paths (implementation, tests, parts, APIs, definition files of tables), paths in the ledger's `command` | Area = `1 + number of requirements linked to that file`. Large frames = components. Blue = implementation, green = tests |
| File list | Same as above | Collapsible by component. Shows the number of linked requirements and the names of parts, APIs, and tables. `↗` opens `vscode://file/<repository>/<path>` (Studio itself does not open it) |
| Filter | Path strings | Whether the path contains the term, ignoring full-width/half-width and upper/lower case differences |

### S8.5.7 Tables (`#/tables?tab=`)

On every tab, selecting a row highlights it in the diagram (you can narrow down with `選択に関連する行だけ`, "only rows related to the selection"), the headers sort, and `CSV` exports **all rows** of that tab (before filtering).

| Tab (`tab`) | Data read | Columns |
|---|---|---|
| Requirements (`reqs`) | Requirements definition + catalog (implementation) | ID, title, decision status, priority, goal, implementation (done/none/unlisted), number of ACs, BLOCKED, boundary (source file name) |
| Acceptance criteria (`acs`) | The requirements' ACs | ID, requirement, verification level, BLOCKED, body |
| Test cases (`cases`) | Ledger `cases[]` | ID, title, requirement, AC, layer (`layer`), status (`status`), last run (`last_run_at`) |
| Common parts (`parts`) | The catalog's common parts table | Name, purpose, file, number of requirements |
| APIs and tables (`apis`) | The catalog's API and table tables | Kind, name, system of record, definition file, requirements |
| Files (`files`) | Catalog and ledger paths | Path, component, module, role (impl/test), number of linked requirements |
| Parameters (`params`) | PARAM table | ID, name, value, unit, basis, decision status |
| Questionnaire (`questions`) | Questionnaire table | ID, severity, question, status, answer |
| Glossary (`terms`) | Glossary table | Term, definition, expressions not to use |
| Personas (`personas`) | Persona table | Name, task, key decisions, data used, role |
| External integrations (`integrations`) | External integration table | Name, method, meaning, system of record |
| Decision log (`decisions`) | Decision log table | Date, target, decision, rationale, run |
| Audit findings (`audits`) | Audit findings table | ID, date, category, severity, location, summary, status |
| Sources (`sources`) | Source table | ID, document, version, category |
| Run history (`runs`) | `docs/run-history.md` | The first 8 columns of the table (column names as in the file) |

### S8.5.8 Structure (`#/structure`)

This page does not appear in the navigation (open it by URL). For each of the **7 data layers**, it compares the current state (number of parsed items) with the ideal (the judgment criteria) and lists rows judged one record at a time.

| Layer | Data read | Main judgments (kind of difference) |
|---|---|---|
| Requirements definition / per-boundary requirements | Requirements, goals, ACs | Missing (no decision status or no AC), orphan (the goal in `上位` does not exist), reference inconsistency (an ID in an AC body is undefined), duplicate (same requirement ID), valid |
| Catalog | Features table × requirements | Surplus (a row with no matching requirement), duplicate (multiple rows for the same requirement), reference inconsistency (decision status differs from the requirement), valid |
| System Test | Ledger × requirements, ACs, PARAMs | Duplicate (case ID), reference inconsistency (undefined requirement or AC, AC's parent requirement mismatch, digest of AC body does not match the ledger's `ac_digests`), valid |
| ID registry | ID registry × requirements, ACs, goals | Surplus (an ID with no definition), reference inconsistency (prefix and kind mismatch), duplicate, valid |
| Run history | `run-history.md` × requirements, cases | Reference inconsistency (refers to a nonexistent requirement or case), duplicate (run-id), valid |
| Cross-boundary | External integration table | Missing (method, direction, or system of record is empty), duplicate, valid |

- Each row carries a `根拠` (basis; file:line).
- The AC digest is the first 16 hex digits of the SHA-256 of the AC body with `{PARAM-nnn}` replaced by its value and whitespace collapsed (prefixed with `sha256:`). If you change the body but do not update the ledger, it becomes a "reference inconsistency".
- The correctness of the content (such as semantic contradictions) is not judged. That is the role of `python scripts/verify.py` and rd-auditor.

### S8.5.9 Consistency (`#/consistency`)

This page does not appear in the navigation. For each requirement ID, it checks whether a record exists in each of five layers.

| Column | Condition for ○ (✓) |
|---|---|
| Requirement | The requirements definition has a requirement with that ID |
| AC | The requirement has at least one acceptance criterion |
| Test | The ID appears in the `requirement_ids` of a ledger case (`status` is not checked) |
| Catalog | The catalog's features table has a row for that ID |
| Implementation file | That row's `実装ファイル` has at least one path |

The judgment is "Normal" if all five are present, "One layer missing" if any one is missing, and "No referent" if the catalog has a row but there is no requirement.

### S8.5.10 Consistency Maintenance (`#/maintenance`)

| Display | Data read | Condition |
|---|---|---|
| Maintenance candidates | Catalog feature rows × requirements | Rows whose `題名` or `決定状態` **differs as a string** from the requirement source of truth (the heading title and `決定状態`). Rows that do not exist in the requirement source of truth are shown as "unmatched" |

The conditions for running (writing) are in S8.9.

### S8.5.11 Search, Detail Panel, CSV, and Auto-Refresh

| Feature | Data read | Behavior |
|---|---|---|
| Search (`/`, `Ctrl+K`) | ID, name, title, path, boundary, and status of diagram points (nodes); the requirement body, AC body, and data handled | In browser memory, finds points that contain all whitespace-separated terms, ignoring full-width/half-width and upper/lower case differences. Exact ID matches rank higher, with ordering by per-kind weights. Shows the top 40; Enter selects, Shift+Enter highlights all. It does not query the server |
| Detail panel (select a point) | Per point type (table below) | Shown on the right. `↗ VS Code` opens the definition location (`file:line`) |
| CSV | All rows of a table tab | Generated and saved by the browser as UTF-8 (with BOM). Not sent to the server |
| Auto-refresh | Modification time and size of the files in S8.1 | Queries `/api/fingerprint` every 4 seconds; if it has changed, reloads `/api/model` and redraws. Pauses while the screen is hidden and on the Consistency maintenance screen |
| Switching the target repository | Repository folder | From the repository name at the top right of the screen. A folder that lacks `docs/requirements-definition.md`, `docs/catalog.md`, or the ledger is not switched to |

Detail panel contents:

| Point type | Items shown (source data) |
|---|---|
| Requirement | Body; acceptance criteria (level, BLOCKED); notes on origin, source, related existing assets, and priority; data handled; parameters; questions; implementation files; tests and test cases; common parts, APIs, and tables; other requirements referenced in the body; definition location; original body (collapsible) |
| Goal | Metric and method; number of requirements belonging to it and number with implementation registered |
| Acceptance criterion | Body, verification level, BLOCKED, parent requirement |
| File | Path, component, module, role (impl/test) |
| Common part, API, table | Purpose, definition location |
| Test case | Status, layer, `command`, last run, commit, evidence |
| Question, parameter | Question, options, recommendation, status, answer / name, value, basis, status |
| Entity | Glossary definition, expressions not to use, list of states |
| Persona, external integration | Task, decisions, data used, role / method, meaning, system of record |

### S8.5.12 Implementation Status (`#/implstatus`)

This shows where approved requirements stand in terms of implementation registration and test pass/fail, using stacked progress bars by status (overall, by goal, and by priority), a kanban board, and a list table. The screen only reads management data and does not write to the target repository. When management data is updated, it recalculates statuses and counts after reloading.

Data read: the requirement's `決定状態`, the AC's `検証レベル` and `BLOCKED`, the `実装ファイル` of the catalog's features table (only paths that actually exist), and the ledger's `cases[].requirement_ids` and `cases[].status`.

| Status | Definition (judged from the top down) |
|---|---|
| Not started | No row in the catalog, or no existing path in the implementation files cell |
| Implementation registered, tests not registered | Has an implementation and an AC with `検証レベル: system`, but the ledger has no case for the requirement |
| Implementation registered, tests not passing | Has an implementation, and at least one ledger case is something other than `pass` (`fail`, `blocked`, `not_run`) |
| Tests passed | Has an implementation, the ledger has one or more cases, and all are `pass` |
| Implementation registered, not subject to system tests | Has an implementation, has no `system` AC, and the ledger has no case |

- Only requirements whose decision status is approved are targeted. Requirements that are pending approval, on hold, rejected, or deprecated are excluded from the denominator, and only the count of "out of scope" is shown separately.
- Requirements that cannot proceed to acceptance judgment because of unanswered questions, TBDs, or conflicts (requirements with an AC that has BLOCKED) get a "stopped" mark (⏸) in addition to the status.
- Statuses are distinguished not only by color but also by symbols (○ ◔ ✖ ✔ ◇) and status-name words. Kanban cards and table rows can be selected with the keyboard (Tab and Enter); selecting one opens the detail panel and syncs with the other views. Headings, status names, and the legend follow the JA/EN switch.
- **Difference from the Dashboard's "Tests passed %"**: Tests passed % is **per ledger case** (`pass` cases ÷ number of cases). Implementation status is **per requirement**: if even one case linked to the requirement is something other than `pass`, it does not count as tests passed. The numbers do not match even for the same data.
- The meaning of the existing node attribute `impl` (`done`, `none`, `unlisted`) is unchanged, and the 2D/3D map and Placement displays are unchanged. Implementation status is computed as a separate field (`implStatus`).

## S8.6 Screen-to-File Mapping (Quick Reference)

"◎" is a primary input; "○" is a supplementary input.

| Screen / feature | Requirements definition (including `requirements/`) | Catalog | Ledger | ID registry | Run history |
|---|---|---|---|---|---|
| Dashboard | ◎ | ◎ (implementation registration) | ◎ (pass rate) | ○ (counts) | ◎ |
| 2D / 3D map | ◎ | ◎ | ○ (cases) | | |
| Diagrams | ◎ | ○ (component diagram) | | | |
| Placement | ◎ | ◎ | | | |
| Placement (runtime environment) | ○ (external integrations) | ◎ (names of implementation files) | | | |
| Source mapping | ○ | ◎ | ○ (paths in command) | | |
| Tables | ◎ | ◎ | ◎ | | ◎ |
| Structure | ◎ | ◎ | ◎ | ◎ | ◎ |
| Consistency | ◎ | ◎ | ◎ | | |
| Consistency maintenance | ◎ (source of truth) | ◎ (target; written to) | | | |
| Search, detail panel | ◎ | ◎ | ○ | | |
| Implementation status | ◎ (decision status, AC) | ◎ (implementation files) | ◎ (case status) | | |

## S8.7 How Things Look When Something Is Missing

| What is missing | How it looks |
|---|---|
| No requirements definition or requirement files, and no catalog | `--check` exits with code 1. On startup it shows guidance and exits. If you switch after startup, it does not switch and shows "Data layer not found" |
| No catalog | Implementation registered % is 0. Source mapping and Placement are empty ("The catalog has no file mapping") |
| No ledger, or the JSON is broken | Tests passed % is 0 and there are 0 test cases. If it is broken, a warning (`ledger is not valid JSON`) is recorded |
| No ID registry or run history | The corresponding sections are empty. The Structure layers show "0 items to judge" |
| `実装ファイル` is `—` or 未実装 | The requirement's implementation is none (unregistered). Consistency shows "One layer missing" |
| Tables with different column names | Tables that cannot be identified are not read. See the `--check` count (0 items) and "画面に出ない" (nothing shows on screen) in `04-troubleshooting.en.md` |

## S8.8 What Is Not Read

- Source code, configuration, logs, and the contents of `work/` (run progress, evidence, audit results). The only things that appear as names are paths written in the catalog and the ledger.
- The contents of `docs/manual-tests.md` (existence check only).
- The contents of `.github/` (agents, skills, hooks).
- Usage scenarios in the requirements definition (parsed but not displayed).

## S8.9 What Is Written

Normal browsing, search, CSV, and repository switching write nothing.

The only thing written is **`docs/catalog.md`**, when you press `確認して実行` ("Confirm and run") in Consistency maintenance. The two cells `題名` and `決定状態` of the selected requirement's row are aligned to the requirement source of truth.

1. Preview: shows before and after and issues a token (the file is not changed).
2. Run: confirms that the file's contents have not changed since Studio started (or since the previous application). If they have, it stops with `preview-conflict` (after updating the catalog by another means, restart Studio).
3. Writes a temporary file (`.eabk-studio-*`) in the same folder and replaces the original with it, then runs `python scripts/verify.py --docs-only` (if `scripts/verify.py` does not exist, only the read-only checks run).
4. On failure (a check fails, the write fails, or a file outside the target points to the same entity), it **restores the original bytes, timestamps, and permissions** and shows an error.

## S8.10 HTTP API (`127.0.0.1` Only)

| Method and path | Description |
|---|---|
| `GET /` and `GET /<path>` | Static files in `EABK-Studio/web/` (paths outside it return 404) |
| `GET /api/model` | All parsed data (JSON). If the modification-time fingerprint is the same, returns the cache |
| `GET /api/fingerprint` | Modification fingerprint of the management data (repository path + modification time and size of each file) |
| `GET /api/repo` | Path of the current target repository |
| `POST /api/repo` | Switches the target repository (body `{"path": …}`). Requires `X-EABK-Studio: 1` |
| `POST /api/maintenance/preview` | Body `{"id": "<requirement ID>"}`. Requires the same header |
| `POST /api/maintenance/apply` | Body `{"token": …}`. Requires the same header |

- It listens on `127.0.0.1` (default port 8765; if in use, it tries the next numbers up to 20 times). Requests whose `Host` header is anything other than `127.0.0.1`, `localhost`, or `::1` are rejected with 403.
- A POST without the header `X-EABK-Studio: 1` gets 403 (to prevent submissions from other sites). The body is limited to 8 KB.
- Nothing is sent to external servers (no fonts, CDNs, or analytics are used; three.js for 3D is bundled).
