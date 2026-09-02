# 09. Prompt 版フルシステムテスト（要件全件・実 run・Azure 許可）

## GitHub Copilot に貼り付ける Prompt

以下のコードブロック全体をコピーして貼り付けてください。

````markdown
このリポジトリで、HVE Prompt 版のフルシステムテストを実施してください。
必要なコマンド、request の保存、plan SHA-256 の転記、チェックポイント更新はすべてあなたが行い、
利用者にコマンド・ファイルパス・SHA-256 の入力を求めないでください。

**この依頼を実行承認として扱ってはいけません。** 最初は調査と実行計画の提示だけを行い、
利用者が計画を確認して明示的に承認するまで `hve prompt run`、Azure への書き込み、
成果物の生成・変更へ進まないでください。

開始前に次を確認してください。

- `tests/prompt-version/README.md` の共通前提・禁止事項
- `.github/skills/hve-prompt-edition/SKILL.md`
- `hve-dev/requirement-definition.md` §5.20（FR-PROMPT-01〜10）
- `hve-dev/hve-feature-inventory.csv`
- `hve-dev/requirement-test-mapping.md`
- `hve/workflow_registry.py`

## 目的

- HVE の **Prompt 版**について、要求定義書の要件 ID を status を含めて全件棚卸しし、各要件を
  `PASS` / `FAIL` / `BLOCKED` / `NOT_APPLICABLE` / `NOT_MEASURED` のいずれかで判定する。
- `source=hve-dev/requirement-definition.md` かつ `active-or-described` の要件だけを現行の適用候補とする。
  deprecated / removed / partial / TBD / 履歴項目は現行要件として試験せず、inventory の status と
  適用しない理由を付けて `NOT_APPLICABLE` とする。
- 機能要件と非機能要件を分類し、適用可能な要件は実動作で確認する。
- 対象 Workflow を実際に non-dry-run で実行し、成果物・エラー・所要時間・Token 消費量・
  AI Credit・tool 呼び出しなど、実際に取得できる性能・利用量を測定する。
- 各 `CASE-ID` を controller-level の schedulable task とし、plan / run / 検証 / 敵対的レビューを
  含む 1 case の見積を原則 60 分以内とする。
- predecessor と共有状態を確認して安全に並列実行できる ready case は、承認済みの
  controller-level 最大同時 case 数まで必ず同一 wave で同時開始する。
- 全設定項目を Prompt 版から到達可能かで分類し、有限な値域は全値、自由文字列・数値は
  明示した同値クラスと境界値へ正規化したうえで組合せを作る。
- 長時間実行を case / lane 単位の小さなチェックポイントへ分割し、停止影響を当該 case と
  依存する lane に局所化したうえで、完了済み case を再実行せず再開できるようにする。
- 各 case 完了後に敵対的レビューを実施し、有効な指摘をテスト成果物へ反映してから次へ進む。

## 対象

### 実行品質

- モデル: `Auto` 固定
- Prompt 版の実行面: HVE GUI 内 Copilot CLI / standalone GitHub Copilot CLI /
  VS Code Copilot Chat のうち、今回使用した面を記録する

### Workflow / Step

- `ard`: GUI 表示グループ `2, 3, 4, 5`
  - request へ GUI グループ ID をそのまま書かない。
  - 実行時に `hve.workflow_registry.expand_group_step_ids("ard", ["2", "3", "4", "5"])` で
    実 Step ID を取得し、その実測値を request に使う。
  - 現行想定は `2`, `2.1`, `3.1`, `3.2`, `3.3`, `4.1`, `4.2` だが、registry の実測値を正とする。
- `aas`: registry に存在する全 executable Step
- `aad-web`: registry に存在する全 executable Step
- `asdw-web`: registry に存在する全 executable Step
- container / display group は実行単位として数えず、展開後の実 Step をテスト単位とする。
- optional / conditional Step は、対応する設定組合せで有効になる場合に含める。
- 未選択 Workflow を暗黙追加しない。必要な上流 Workflow は対象一覧へ明示し、依存順は
  `get_meta_dependencies()` の実測結果から決める。

## Prompt 版への設定変換

GUI の全設定を無条件に request へ入れてはならない。次の正本を実測し、各設定を分類する。

1. `hve.gui.settings_store.defaults()` — 保存設定
2. `hve.gui.settings_apply._SECTION_FIELDS` — GUI から編集可能な設定
3. `hve.prompt_request.ALLOWED_SETTINGS_OVERRIDES` — Prompt request で上書き可能な共有設定
4. `hve.workflow_registry.WorkflowDef.params` — Workflow 固有パラメータ
5. `hve/tests/fixtures/option_parity_matrix.yaml` — 面ごとの分類と除外理由

各設定を次のいずれかへ分類する。

| 分類 | テスト方法 |
|---|---|
| Prompt 共有設定 | `settings_overrides` で値を変え、生成 argv と実行結果を確認 |
| Workflow 固有パラメータ | 対象 Workflow の `workflows[].params` で指定 |
| derived / semantic alias | 正本が定める入力から導出し、重複指定しない |
| GUI-only / Prompt 対象外 | `NOT_APPLICABLE` とし、理由・正本・代替確認方法を記録 |
| credential / secret | request やレポートへ値を書かず、既存認証経路だけを使用 |

組合せ軸へ含めるのは、Prompt 版が受理する **Prompt 共有設定**と対象 Workflow の
**Workflow 固有パラメータ**の有限化した値だけとする。derived / semantic alias は導出元と重複させず、
GUI-only / Prompt 対象外と credential / secret は分類・根拠を記録するが直積へ含めない。

### 組合せ規則

- bool / tri-state / enum は、Prompt 版で受理される全値を対象にする。
- 数値は最小・既定・代表値・最大、文字列は空・代表的な正常値・境界長・不正値など、
  正本から導ける有限の同値クラスへ分ける。根拠なく値を作らない。
- 分類後、有限化した全値の直積件数を算出する。
- 全直積を実行する場合は、件数・予測時間・予測 Token / AI Credit・Azure 予測費用・
  controller-level 最大同時 case 数を計画へ明記する。
- Phase 0 では controller-level 最大同時 case 数を具体値で提示し、許容ケース数、各 case / 全体の
  時間、Token、AI Credit、Azure 費用、ホスト能力の各上限および根拠とともに明示承認を得る。
- 利用者指定、実測値、正本のいずれにも根拠がない上限は推測せず `NOT_MEASURED` / `BLOCKED` とし、
  必要な具体値が提示され、すべて明示承認されるまで `hve prompt run` を実行しない。
- 全直積が利用者の承認済み上限を超える場合、勝手に pairwise 等へ縮退しない。
  全直積案と、削減案（例: pairwise + 境界値）を別々に提示し、利用者が明示承認した案だけを実行する。
- `model` は本テストでは `Auto` 固定とし、組合せ軸へ含めない。
- `hve/.settings.txt` を組合せごとに書き換えない。Prompt 共有設定は request の
  `settings_overrides` を使い、Workflow 固有値は `params` を使う。

## 実行単位・時間・並列化

### CASE-ID と見積

- controller-level の `CASE-ID` をスケジュール可能な task とし、原則として
  **1 Workflow × 1 実 Step × 1 設定ケース**を 1 case とする。
- 各 case の `estimated_minutes` は plan / run / 検証 / 敵対的レビューの内訳を示し、過去の実測、
  registry・テスト・既存成果物などの正本、または再現可能な測定結果を `estimate_basis` に記録する。
  根拠が不足する内訳と合計は数値を作らず `NOT_MEASURED` とする。
- plan は request 保存から `hve prompt plan` の終了・出力検証・SHA-256 保存まで、run は
  `hve prompt run` の開始から終端まで、検証は後述する各 case の手順 1〜6、敵対的レビューは
  同手順 7〜10 とする。失敗した case も実施できた工程の実時間を記録し、未実施工程は未実施とする。
- 合計見積が 60 分を超える、または見積不能な case は、Step、設定ケース、独立して判定可能な
  検証単位でさらに分割し、分割後の各 case に一意な `CASE-ID` と 4 工程の見積を割り当てる。
- 1 回の `hve prompt run` は atomic run として途中分割しない。atomic run が分割後も 60 分を
  超える、または見積不能なら当該 case を `BLOCKED` とし、例外範囲、最大時間、Token / AI Credit、
  Azure 費用、ホスト占有上限、停止・再開方法を提示して別途明示承認を得る。
- 例外 case とその上限は Phase 0 の計画に明示する。別途承認は当該 case に対する自然言語の
  明示承認だけを指し、approval store、期限管理、自動再開などの新しい承認機構を追加しない。
- 60 分は分割判断の基準であり、自動タイムアウトや強制終了を導入しない。
- この分割と再開は既存の `hve prompt plan` / `hve prompt run` と controller の checkpoint を使う。
  新実行エンジン、新 CLI flag、新 request schema、新 HVE Resume、product code 変更を導入しない。

### Controller DAG・wave・lane

- controller-level の case DAG / wave は system-test の実行計画であり、FR-PROMPT-06 の
  request 内任意 DAG ではない。case 間依存を request v1 の新フィールドとして追加しない。
- atomic run 内では HVE 内部の DAG と `max_parallel` を実行正本とし、特に registry 宣言値を
  controller-level 計画から上書きしない。
- 並列安全判定では、各 case の predecessor、`required_input_paths`、`output_paths` /
  `output_paths_template`、worktree、`hve/.settings.txt`、Azure resource group・リソース名・データ、
  branch / PR / port などの共有状態、および承認済み予算・ホスト上限を照合する。
- 競合がない ready case は、承認済み controller-level 最大同時 case 数まで同一 wave で必ず
  同時開始する。無言の直列化は禁止し、枠を超える場合だけ決定的な sub-wave に分ける。
  並列化した理由、直列化した理由、競合対象を case ごとに記録する。
- mutating lane は専用の隔離 worktree、互いに衝突しない run-scoped request / evidence / review /
  checkpoint、設定 snapshot を持つ。同時実行する mutating case は互いに別 lane / worktree とし、
  上流 case の成果物を引き継ぐ依存 chain だけを同一 lane / worktree で直列実行する。
- Azure 書き込み時は承認済みの case 専用 scope（resource group・リソース名・データ）を割り当てる。
  read-only case も output path と証跡保存先を case ごとに分離し、共有出力を並列更新しない。
- case の失敗・中断・未解決レビューは当該 case と依存する同一 lane だけを停止対象とし、
  独立 lane の開始可否は同じ並列安全判定で決める。
- 各 case の敵対的レビューは、**目的適合性**、**内容妥当性**、**整合性**、**品質・運用性**、
  **根拠性・不確実性**、**オーバーエンジニアリング**の 6 軸で短く行う。汎用レビュー
  テンプレートや新しい実行基盤は追加せず、case の run-scoped review 証跡へ結果を記録する。

## Phase 0. 計画のみ（承認前）

承認前は次だけを実施する。

1. 全要件 ID と status を `hve-dev/hve-feature-inventory.csv` から列挙する。
2. active 要件を機能要件 / 非機能要件、および Prompt 版への
   `APPLICABLE` / `NOT_APPLICABLE` / `BLOCKED` 候補へ分類する。
  非 active 要件は現行要件へ昇格させず、status と除外理由を記録する。
3. 対象 Workflow / Step の現在値、入出力、依存、Azure 書き込み有無、承認 gate を registry から取得する。
4. 設定分類表と有限化した組合せ表を作り、総ケース数を算出する。
5. controller-level 最大同時 case 数と、許容ケース数、時間、Token、AI Credit、Azure 費用、
   ホスト能力の各上限を、利用者指定・実測・正本に基づく具体値と根拠で整理する。
  最大同時 case 数は根拠を確認できた各上限の最小値とする。必要な上限が 1 つでも不明なら
  `NOT_MEASURED` / `BLOCKED` とし、値を推測しない。
6. 組合せを schedulable case へ分割し、各 case の plan / run / 検証 / 敵対的レビューの
   `estimated_minutes` と `estimate_basis` を作成する。60 分超または見積不能なら、前節に従い
   分割または `BLOCKED` とする。
7. predecessor と全競合対象を照合し、case DAG、critical path、wave / sub-wave、lane を作る。
  `plan.md` の `## Case DAG` に `CASE-ID | Predecessor | Wave / Sub-wave | Lane | 競合対象 |
  Parallel / Serial 理由`の Markdown 表として保存する。安全な ready case を承認候補の最大同時
  case 数まで同一 wave に配置し、無言で直列化しない。
8. mutating case の専用 worktree・設定 snapshot・Azure scope と、全 case の衝突しない
   run-scoped request / evidence / review / checkpoint path を割り当てる。
9. 各 case に `CASE-ID`、対象要件、request path、期待結果、測定項目、成果物、predecessor、wave、
   lane、`estimated_minutes` とその 4 工程の内訳、`estimate_basis`、並列 / 直列理由、競合対象を割り当てる。
10. 各 case の typed request v1 を run-scoped `artifacts/requests/` に保存し、
   `hve prompt plan` を実行して plan と SHA-256 を取得する。
11. 手順 1〜10 の結果と case DAG / wave / lane を `plan.md` へ保存する。その case 一覧と各 case の
  plan SHA-256 に加え、保存した `plan.md` の UTF-8 bytes に対する
  controller plan SHA-256、総件数、wave / sub-wave、controller-level 最大同時 case 数、
    critical path、各 case と全体の推定時間、推定 Token / AI Credit、Azure scope・予測費用、
    承認対象の各上限、ホスト能力、case / lane 単位の停止・再開方法を利用者へ提示する。
12. **ここで停止し、提示した計画・各 case と controller plan の SHA-256・上限への自然言語による
  明示承認を待つ。**
    この依頼文自体や無応答を承認として扱わない。
13. 明示承認を受けた後にだけ、controller が提示済みの各 case の SHA-256 を変更せず
    `--expected-sha256` へ転記し、Phase 1 の `hve prompt run` へ進む。

計画が `task_scope=multi` / `context_size=large` でも、承認後は Prompt Edition controller 自身が
成果物を直接編集せず、承認済み plan を既存 `hve prompt run` へ委譲する。

## Azure 実行前の追加ゲート

以下の情報は Phase 0 の計画へ含め、計画全体の承認後も、Azure 書き込みを含む各 case の
開始直前に当該 case 専用の具体値を再提示して追加承認を得る。

Microsoft Azure リソースの作成は本テストで許可されているが、Prompt 版の承認は既存の
認証・権限・Azure・デプロイ承認を代替しない。

Azure 書き込みを含む case の実行前に、次を具体値で提示し、既存 gate の承認を得る。

- subscription ID / name（秘密値は出力しない）
- 専用 resource group
- region
- 作成予定リソース一覧・SKU・数量
- case 専用の命名規則とタグ
- 予測費用と最大実行時間
- cleanup 対象と、cleanup が別の破壊的操作であること

値が不明なら推測せず `BLOCKED` とする。既存・共有リソースを変更・削除しない。
cleanup はこの依頼の「作成許可」に含めず、対象一覧を提示して別途明示承認を得た場合だけ行う。
認証情報、接続文字列、token、secret を request・ログ・レポートへ保存しない。

## Phase 1. 承認後の実 run

- `hve prompt plan` が内部で実行する `orchestrate --dry-run` は Prompt 版の必須承認ゲートであり、
  原文の「DryRun は行わない」の対象外とする。ただし dry-run の結果をシステムテストの
  PASS 根拠にしてはならない。
- 各 wave の開始前に predecessor、review status、および前節の並列安全判定で列挙した共有状態、
  承認済み予算・ホスト上限を再確認する。
  安全な ready case は、承認済み controller-level 最大同時 case 数まで一括して同時開始する。
- 各 case は承認済み lane で、利用者が承認した当該 case の plan SHA-256 だけを
  `--expected-sha256` へ転記し、`hve prompt run` で non-dry-run 実行する。
- 終了コード `2` と `計画が承認時と一致しません（stale）` が返った場合は、子 `orchestrate` が
  起動していないことを確認する。旧 hash を流用せず、当該 case とその未実行の依存 case を
  再plan・再提示し、再承認を得るまで開始しない。
- Prompt Edition controller は `docs/` / `src/` / `knowledge/` / `qa/` 等の対象成果物を
  直接編集しない。既存 Workflow / Step へ委譲する。
- case が失敗したら、その case の依存先だけを停止する。独立 lane は、依存・出力・Azure scope・
  設定が分離され、承認済み上限内であることを再確認できた場合だけ継続できる。
- 利用者から停止要求を受けたら新しい case / wave の開始を直ちに止める。既定では停止要求時点で
  すでに実行中の case を強制終了せず、完了、証跡保存、敵対的レビュー、checkpoint 更新まで行って停止する。
  利用者が即時停止を明示した場合だけ実行中 case を停止し、成功と推測せず `interrupted` とする。
- テストを通す目的で product code、要求定義、期待値を変更しない。不具合はレポートへ記録する。

## チェックポイントと再開

ここで定義する checkpoint は、このフルシステムテストを調整する controller の run-scoped な
作業記録であり、HVE アプリケーションの Resume / checkpoint 機能ではない。HVE 側へ状態管理、
自動 skip、自動再開、CLI flag、request field を追加してはならない。

作業ディレクトリは次とする。

```text
work/run/<run-id>/Issue-prompt-full-systemtest/
├── README.md
├── plan.md
├── artifacts/
│   ├── requests/
│   ├── settings/
│   ├── evidence/
│   │   └── <CASE-ID>/
│   ├── reviews/
│   │   └── <CASE-ID>.md
│   ├── checkpoints/
│   │   └── <CASE-ID>.json
│   ├── systemtest-checkpoint.json
│   └── <yyyy-MM-dd-HH-mm>-systemtest-result.md
└── completion-report.md
```

並列 case は共有 JSON を直接更新しない。各 case は `artifacts/checkpoints/<CASE-ID>.json` の
自分専用 shard だけを、計画確定時の `planned`、command 起動直前の `running`、終了確認後の
終端状態で更新する。coordinator だけを
`systemtest-checkpoint.json` の単一 writer とし、case shard を `case_id` で順次集約する。
coordinator が中断した場合は、再開時に全 shard から aggregate を再構築する。

case を担当する controller task は、終了後に shard の完全な JSON object が存在することを確認して
から完了結果を coordinator へ返す。新しい IPC や常駐監視は追加しない。coordinator は task の
完了結果を受けた後にだけ当該 shard を読み、JSON 構文、必須 field、`case_id`、source HEAD、
settings matrix hash、controller plan hash を検証する。不正・欠損・重複があれば自動修復や
読み飛ばしをせず集約を停止し、当該 case を `interrupted` または `blocked` として根拠を記録する。

checkpoint の作成・更新は `work/` の規則に従い、既存ファイルを削除してから完全な JSON object を
新規作成する。共有ファイルへの append、複数 writer、in-place update は行わない。

各 case shard と aggregate は最低限次を保持する。

- source HEAD
- settings matrix の SHA-256
- controller plan の SHA-256
- CASE-ID
- Workflow / Step
- request path
- plan SHA-256
- HVE run-id
- status (`planned` / `running` / `passed` / `failed` / `blocked` / `interrupted`)
- status reason
- evidence path
- review status

`hve_run_id` field は常に含め、HVE run-id をまだ観測していない `planned` / `running` / `blocked`
では空文字列、観測後は実測した値を記録する。値を推測せず、`null` や field 省略と混在させない。

`review_status` は開始時を `pending` とし、レビューと有効指摘の反映確認後に
`reviewed-and-reflected`、Critical / Major が未解決なら `critical-unresolved` とする。
未解決指摘を反映した場合は再レビューしてから `reviewed-and-reflected` へ更新する。

case の run が非 0、宣言 `output_paths` が欠落・空、または期待結果との照合が不合格なら
`failed` とする。run 前の前提・承認・上限不足は `blocked`、利用者の即時停止で終端まで
到達しなかった場合は `interrupted` とし、いずれも `status_reason` に実測根拠を記録する。

終端証跡は、実際に観測した終了コードと stdout / stderr を保存した case 専用 run log、および
その終了コードに対応する終端 status とする。`failed` も終端状態であり、PASS へ丸めない。

case shard は次の version 1 object とする。

```json
{
  "schema_version": 1,
  "source_head": "<commit-sha>",
  "settings_matrix_sha256": "<sha256>",
  "controller_plan_sha256": "<sha256>",
  "case": {
    "case_id": "CASE-001",
    "workflow": "ard",
    "step": "2",
    "wave": "<wave-or-sub-wave-id>",
    "lane": "<lane-id>",
    "request_path": "artifacts/requests/CASE-001.json",
    "plan_sha256": "<sha256>",
    "hve_run_id": "<run-id-or-empty>",
    "status": "planned|running|passed|failed|blocked|interrupted",
    "status_reason": "<empty-or-reason>",
    "evidence_paths": ["artifacts/evidence/CASE-001/run.log"],
    "review_status": "pending|reviewed-and-reflected|critical-unresolved"
  }
}
```

aggregate は同じ case object を `cases` 配列へ `case_id` の決定的な順序で集約する。

```json
{
  "schema_version": 1,
  "source_head": "<commit-sha>",
  "settings_matrix_sha256": "<sha256>",
  "controller_plan_sha256": "<sha256>",
  "cases": [
    {
      "case_id": "CASE-001",
      "workflow": "ard",
      "step": "2",
      "wave": "<wave-or-sub-wave-id>",
      "lane": "<lane-id>",
      "request_path": "artifacts/requests/CASE-001.json",
      "plan_sha256": "<sha256>",
      "hve_run_id": "<run-id-or-empty>",
      "status": "planned|running|passed|failed|blocked|interrupted",
      "status_reason": "<empty-or-reason>",
      "evidence_paths": ["artifacts/evidence/CASE-001/run.log"],
      "review_status": "pending|reviewed-and-reflected|critical-unresolved"
    }
  ]
}
```

coordinator は `case_id` をキーに同一要素を置換し、`case_id` 文字列の昇順で aggregate を
完全再生成して重複追加しない。
`evidence_paths` は run-scoped のリポジトリ相対パス配列とし、本文や秘密情報を埋め込まない。

停止・再開時は aggregate を shard から再構築し、source HEAD、settings matrix hash、controller plan
hash、各 case の plan SHA-256 を照合する。

- 一致する場合: `passed` かつ `reviewed-and-reflected` の case を再実行しない。`passed` かつ
  `pending` の case は run を再実行せず敵対的レビューから再開する。その後、ready な未完了 case から
  承認済み wave を再開する。`failed` / `blocked` は自動再実行せず、再実行ごとに原因を確認して
  再plan・再提示・明示承認を得る。回数上限を推測せず、暗黙の再試行ループを作らない。
- 一致しない場合: 旧 hash と承認を流用せず、影響を受ける未完了 case とその依存先を
  再plan・再提示・再承認する。完了済み case の旧証跡を現在の HEAD の PASS 根拠へ流用しない。
- `running` の shard が残り終端証跡が無い case、または即時停止した case は `interrupted` とする。
  再開は HVE の途中状態からではなく、当該 `hve prompt run` の Step 先頭から行う。
- 即時停止により終了コードを観測できなかった場合は値を作らず、終了コードを
  `NOT_MEASURED` として理由を run log と shard の `status_reason` に記録する。
- 停止後も新しい case を暗黙に開始せず、再開時点の ready set と承認済み並列上限を再計算する。

## 各 case の検証と敵対的レビュー

各 case で次を行う。

1. 終了コード、stdout / stderr、生成・変更ファイル、HVE run-id を保存する。
2. 宣言 `output_paths` が実行完了時点で存在し、空でないことを確認する。
3. 可能なら実行前後の hash / mtime を比較する。既存成果物が存在しただけで「今回生成した」と判定しない。
4. 対応要件の期待結果と実測結果を照合する。
5. latency、経過時間、Token、AI Credit、tool / skill 呼び出し回数など、実際に取得できる値を記録する。
6. 取得できない指標は `NOT_MEASURED` とし、0 や推定値を実測値として書かない。
7. case 完了後に、前述の 6 軸で読み取り専用の敵対的レビューを行う。問題は 0 件でもよく、
  件数を満たすために存在しない問題を作らない。各指摘へ重大度、根拠 path、説明、修正案を付ける。
8. レビュー指摘は、テスト手順・証跡・判定の誤りなら run-scoped の当該 case のテスト成果物へ
  反映して再検証する。Workflow が生成した恒久成果物や product code の修正が必要なら、
  その場で変更せず不具合として記録し、別タスク候補とする。
9. 反映後に同じ観点を再確認し、結果と反映内容を case 専用 review 証跡へ保存してから
  `review_status` を更新する。再レビューは最大 2 サイクルとし、それでも Critical / Major が
  未解決なら `critical-unresolved` とする。実施した cycle 数は review 証跡へ記録し、checkpoint の
  schema は増やさない。predecessor の review が終わるまで依存 case を開始しない。
  指摘反映で request、設定、case plan、controller plan のいずれかが変わった場合は旧承認を流用せず、
  影響 case を再plan・再提示・再承認してから再実行する。
10. Critical / Major の未解決指摘があれば `critical-unresolved` とし、その依存先 case へ進まない。
   Major を修正しない場合は理由を記録する。
11. 同一 wave ですでに実行中の独立 case は強制中断せず、完了結果の保存と case 単位レビューを行う。
   停止要求後は、影響を受けない独立 case であっても新しく開始しない。

## 最終レポート

`artifacts/<yyyy-MM-dd-HH-mm>-systemtest-result.md` に最低限次を記載する。

1. source identity（HEAD、実施面、OS、Python/HVE版、モデル）
2. 対象 Workflow / Step の実測一覧
3. 設定分類・値域・組合せ方式・総ケース数・実施数・未実施数
4. controller-level 最大同時 case 数の承認値と実使用値、DAG / wave / sub-wave / lane、critical path、
  並列可能な ready case の実行実績、直列化理由、計画からの deviation
5. 要件 coverage 表

```markdown
| Requirement-ID | 種別 | Prompt適用性 | CASE-ID | Status | Evidence | 根拠 / 制約 |
```

6. case 結果表

```markdown
| CASE-ID | Wave / Sub-wave | Lane | Workflow | Step | Settings | Parallel / Serial 理由 | Status | Estimated (Plan / Run / Verification / Review) | Duration | Deviation | Tokens | AI Credit | Evidence |
```

7. 機能要件の PASS / FAIL / BLOCKED / NOT_APPLICABLE 集計
8. 非機能要件の PASS / FAIL / BLOCKED / NOT_APPLICABLE / NOT_MEASURED 集計
9. パフォーマンス・Token / AI Credit・tool利用量の実測
10. Azure 作成リソース一覧、費用、cleanup 状態（秘密情報なし）
11. 各 case の敵対的レビュー結果と反映内容
12. 未解決の Critical / Major / Minor
13. checkpoint shard と aggregate の照合結果、停止履歴、既知の制約、未測定理由、再開位置。
  identity 不一致時は旧値 / 新値、影響 case、再plan・再提示・再承認の状態も記録する。
  停止・再開が無かった場合も `該当なし` と記録する
14. 次の推奨タスク

inventory 上の全要件 ID が coverage 表に **ちょうど 1 回以上**現れることを確認する。
active 要件は実測判定を持ち、非 active 要件は inventory status と `NOT_APPLICABLE` 理由を持つことを確認する。
適用外は `NOT_APPLICABLE`、前提不足は `BLOCKED`、未測定は `NOT_MEASURED` とし、
PASS へ丸めない。情報源には実在するファイルパス・要件 ID・run-id・ログ path を示し、
存在しない問題、ID、URL、数値、実行結果を作らない。

## 完了条件

- 利用者が承認した実行範囲を non-dry-run で完了している。
- 各 case は、4 工程を含む見積が原則 60 分以内、`BLOCKED`、または上限を提示して
  個別承認された atomic 例外のいずれかである。
- 安全に並列可能な ready case は承認済み上限まで同時実行され、理由のない直列化がない。
- 全 case が終端状態で、case shard、aggregate checkpoint、レポートの status が一致し、
  aggregate を shard から重複なく再構築できる。
- 全 active 要件が coverage 表に載り、機能 / 非機能要件へ分類されている。
- Critical 指摘は全件解消または依存 case を停止済み。
- Major を未修正とした場合は理由がある。
- `interrupted` を PASS とせず、廃止済み HVE Resume で途中状態から再開したと記録していない。
- Token・性能・Azure費用を含む数値は実測または明示した推定であり、両者を混同していない。
- `<!-- validation-confirmed -->` を最終レポートへ記載している。

## 重要

- **捏造は絶対に禁止**です。存在しない問題を指摘せず、未確認を PASS / FAIL にしないでください。
- Prompt 版の計画承認と、Azure・権限・デプロイ承認を混同しないでください。
- 計画に無い Workflow / Step /設定ケース / Azure リソースを暗黙追加しないでください。
- 長時間でも case shard を省略せず、利用者が停止したら新規 dispatch を止め、実行中 case の
  終了方針と再開位置を記録してください。
````
