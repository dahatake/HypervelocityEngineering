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
- 全設定項目を Prompt 版から到達可能かで分類し、有限な値域は全値、自由文字列・数値は
  明示した同値クラスと境界値へ正規化したうえで組合せを作る。
- 長時間実行を小さなチェックポイント単位へ分割し、停止後は完了済み単位を再実行せず再開できるようにする。
- 各タスク完了後に敵対的レビューを実施し、有効な指摘をテスト成果物へ反映してから次へ進む。

## 対象

### 実行品質

- モデル: `Auto` 固定
- Prompt 版の実行面: HVE GUI 内 Copilot CLI / standalone GitHub Copilot CLI /
  VS Code Copilot Chat のうち、今回使用した面を記録する

### Workflow / Step

- `ard`: GUI 表示グループ `2, 3, 4`
  - request へ GUI グループ ID をそのまま書かない。
  - 実行時に `hve.workflow_registry.expand_group_step_ids("ard", ["2", "3", "4"])` で
    実 Step ID を取得し、その実測値を request に使う。
  - 現行想定は `2`, `2.1`, `3.1`, `3.2`, `3.3` だが、registry の実測値を正とする。
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

### 組合せ規則

- bool / tri-state / enum は、Prompt 版で受理される全値を対象にする。
- 数値は最小・既定・代表値・最大、文字列は空・代表的な正常値・境界長・不正値など、
  正本から導ける有限の同値クラスへ分ける。根拠なく値を作らない。
- 分類後、有限化した全値の直積件数を算出する。
- 全直積を実行する場合は、件数・予測時間・予測 Token / AI Credit・Azure 予測費用・
  並列数を計画へ明記する。
- 利用者が許容ケース数・時間・Token / AI Credit・Azure 費用の上限を指定していない場合は、
  上限を推測せず Phase 0 の計画で確認する。
- 全直積が利用者の承認済み上限を超える場合、勝手に pairwise 等へ縮退しない。
  全直積案と、削減案（例: pairwise + 境界値）を別々に提示し、利用者が明示承認した案だけを実行する。
- `model` は本テストでは `Auto` 固定とし、組合せ軸へ含めない。
- `hve/.settings.txt` を組合せごとに書き換えない。Prompt 共有設定は request の
  `settings_overrides` を使い、Workflow 固有値は `params` を使う。

## Phase 0. 計画のみ（承認前）

承認前は次だけを実施する。

1. 全要件 ID と status を `hve-dev/hve-feature-inventory.csv` から列挙する。
2. active 要件を機能要件 / 非機能要件、および Prompt 版への
   `APPLICABLE` / `NOT_APPLICABLE` / `BLOCKED` 候補へ分類する。
  非 active 要件は現行要件へ昇格させず、status と除外理由を記録する。
3. 対象 Workflow / Step の現在値、入出力、依存、Azure 書き込み有無、承認 gate を registry から取得する。
4. 設定分類表と有限化した組合せ表を作り、総ケース数を算出する。
5. テストを、原則として **1 Workflow × 1実Step × 1設定ケース** の小単位へ分割する。
6. 入出力依存から DAG と wave を作り、同一ファイル・同一 Azure リソース・同一設定を共有するケースは直列化する。
7. 読み取り専用で出力先も分離されたケースだけを並列化する。
8. 各テストケースに一意な `CASE-ID`、対象要件、request path、期待結果、測定項目、成果物、
   predecessor を割り当てる。
9. 各 case の typed request v1 を run-scoped `artifacts/requests/` に保存し、
   `hve prompt plan` を実行して plan と SHA-256 を取得する。
10. case 一覧、plan SHA-256、実行順、総件数、並列 wave、推定時間、推定 Token / AI Credit、
    Azure scope と予測費用、停止・再開方法を利用者へ提示する。
11. **ここで停止して明示承認を待つ。**

計画が `task_scope=multi` / `context_size=large` でも、承認後は Prompt Edition controller 自身が
成果物を直接編集せず、承認済み plan を既存 `hve prompt run` へ委譲する。

## Azure 実行前の追加ゲート

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
- 利用者が承認した plan SHA-256 だけを `--expected-sha256` へ転記し、各 case を
  `hve prompt run` で non-dry-run 実行する。
- 終了コード `2` と `計画が承認時と一致しません（stale）` が返った場合は、子 `orchestrate` が
  起動していないことを確認する。旧 hash を流用せず、再plan・再提示・再承認する。
- Prompt Edition controller は `docs/` / `src/` / `knowledge/` / `qa/` 等の対象成果物を
  直接編集しない。既存 Workflow / Step へ委譲する。
- case が失敗したら、その case の後続だけを停止する。独立 wave は、共有状態を持たず安全な場合だけ継続できる。
- テストを通す目的で product code、要求定義、期待値を変更しない。不具合はレポートへ記録する。

## チェックポイントと再開

作業ディレクトリは次とする。

```text
work/run/<run-id>/Issue-prompt-full-systemtest/
├── README.md
├── plan.md
├── artifacts/
│   ├── requests/
│   ├── reviews/
│   ├── systemtest-checkpoint.json
│   └── <yyyy-MM-dd-HH-mm>-systemtest-result.md
└── completion-report.md
```

`systemtest-checkpoint.json` は case 完了ごとに更新し、最低限次を保持する。

- source HEAD
- settings matrix の SHA-256
- CASE-ID
- Workflow / Step
- request path
- plan SHA-256
- HVE run-id
- status (`planned` / `running` / `passed` / `failed` / `blocked` / `interrupted`)
- evidence path
- review status

形式は次の version 1 object とし、case は配列へ追記・更新する。

```json
{
  "schema_version": 1,
  "source_head": "<commit-sha>",
  "settings_matrix_sha256": "<sha256>",
  "cases": [
    {
      "case_id": "CASE-001",
      "workflow": "ard",
      "step": "2",
      "request_path": "artifacts/requests/CASE-001.json",
      "plan_sha256": "<sha256>",
      "hve_run_id": "<run-id-or-empty>",
      "status": "planned|running|passed|failed|blocked|interrupted",
      "evidence_paths": ["artifacts/evidence/CASE-001.log"],
      "review_status": "pending|reviewed-and-reflected|critical-unresolved"
    }
  ]
}
```

case 更新は `case_id` をキーに同一要素を置換し、重複追加しない。`evidence_paths` は
run-scoped のリポジトリ相対パス配列とし、本文や秘密情報を埋め込まない。

停止・再開時は source HEAD と settings matrix hash を照合する。

- 一致する場合: `passed` の case を再実行せず、`interrupted` / 未完了 case から再開する。
- 一致しない場合: 旧 hash と承認を流用せず、未完了 case を再plan・再提示・再承認する。
- 実行中に停止した case を成功と推測しない。証跡が無ければ `interrupted` としてその Step から再実行する。

## 各 case の検証と敵対的レビュー

各 case で次を行う。

1. 終了コード、stdout / stderr、生成・変更ファイル、HVE run-id を保存する。
2. 宣言 `output_paths` が実行完了時点で存在し、空でないことを確認する。
3. 可能なら実行前後の hash / mtime を比較する。既存成果物が存在しただけで「今回生成した」と判定しない。
4. 対応要件の期待結果と実測結果を照合する。
5. latency、経過時間、Token、AI Credit、tool / skill 呼び出し回数など、実際に取得できる値を記録する。
6. 取得できない指標は `NOT_MEASURED` とし、0 や推定値を実測値として書かない。
7. case 完了後に読み取り専用の敵対的レビューを行う。
8. レビュー指摘は、テスト手順・証跡・判定の誤りなら当該テスト成果物へ反映して再検証する。
   product code の修正が必要なら、その場で変更せず不具合として記録し、別タスク候補とする。
9. Critical / Major の未解決指摘があれば、その依存先 case へ進まない。
10. 同一 wave ですでに実行中の独立 case は強制中断せず完了結果を保存するが、新しい case / wave は開始しない。
  影響を受けないことを依存・出力・Azure リソース・設定の分離で確認した case だけを個別レビューし、
  それ以外は `blocked` とする。

## 最終レポート

`artifacts/<yyyy-MM-dd-HH-mm>-systemtest-result.md` に最低限次を記載する。

1. source identity（HEAD、実施面、OS、Python/HVE版、モデル）
2. 対象 Workflow / Step の実測一覧
3. 設定分類・値域・組合せ方式・総ケース数・実施数・未実施数
4. 要件 coverage 表

```markdown
| Requirement-ID | 種別 | Prompt適用性 | CASE-ID | Status | Evidence | 根拠 / 制約 |
```

5. case 結果表

```markdown
| CASE-ID | Workflow | Step | Settings | Status | Duration | Tokens | AI Credit | Evidence |
```

6. 機能要件の PASS / FAIL / BLOCKED / NOT_APPLICABLE 集計
7. 非機能要件の PASS / FAIL / BLOCKED / NOT_APPLICABLE / NOT_MEASURED 集計
8. パフォーマンス・Token / AI Credit・tool利用量の実測
9. Azure 作成リソース一覧、費用、cleanup 状態（秘密情報なし）
10. 各タスクの敵対的レビュー結果と反映内容
11. 未解決の Critical / Major / Minor
12. 既知の制約、未測定理由、再開位置
13. 次の推奨タスク

inventory 上の全要件 ID が coverage 表に **ちょうど 1 回以上**現れることを確認する。
active 要件は実測判定を持ち、非 active 要件は inventory status と `NOT_APPLICABLE` 理由を持つことを確認する。
適用外は `NOT_APPLICABLE`、前提不足は `BLOCKED`、未測定は `NOT_MEASURED` とし、
PASS へ丸めない。情報源には実在するファイルパス・要件 ID・run-id・ログ path を示し、
存在しない問題、ID、URL、数値、実行結果を作らない。

## 完了条件

- 利用者が承認した実行範囲を non-dry-run で完了している。
- 全 case が終端状態で、checkpoint とレポートの status が一致している。
- 全 active 要件が coverage 表に載り、機能 / 非機能要件へ分類されている。
- Critical 指摘は全件解消または依存 case を停止済み。
- Major を未修正とした場合は理由がある。
- Token・性能・Azure費用を含む数値は実測または明示した推定であり、両者を混同していない。
- `<!-- validation-confirmed -->` を最終レポートへ記載している。

## 重要

- **捏造は絶対に禁止**です。存在しない問題を指摘せず、未確認を PASS / FAIL にしないでください。
- Prompt 版の計画承認と、Azure・権限・デプロイ承認を混同しないでください。
- 計画に無い Workflow / Step /設定ケース / Azure リソースを暗黙追加しないでください。
- 長時間でもチェックポイントを省略せず、利用者が停止したら安全に終了し、再開位置を記録してください。
````
