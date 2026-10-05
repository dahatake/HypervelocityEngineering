# HVE システムテスト実施方式の調査レポート（一括実行 vs 分割実行）

調査日: 2026-10-03 / 種別: 調査（コード・要求定義・テスト資産は変更していない）

## 1. 問い

「ケースが多すぎて一度に実行すると時間がかかる。全ケースを先に作成し、実行のたびに未実施のケースを範囲指定して分割実行する方式がよいか」

## 2. 結論

**はい。分割実行が妥当。** ただし「ケース番号の範囲指定」だけでは不十分で、次の 4 点を併用すべき。

1. 全ケースを安定 ID 付きの台帳（ledger）として最初に確定し、状態を持たせる。
2. 実行対象は番号範囲ではなく「未実施かつ前提を満たす」ケースを台帳から選ぶ（範囲指定は補助）。
3. 本命の Wave の前に、少数の canary（先行確認）ケースで全面阻害を検出する。
4. HEAD が変わったら plan の SHA-256 が全件変わるため、台帳に実行時 HEAD を記録し、再 plan が必要なケースを明示する。

## 3. 根拠（実測・既存証跡）

### 3.1 規模と時間（一括実行が非現実的）

| 項目 | 値 | 出典 |
|---|---|---|
| 要件 ID（inventory） | 532 | `tests/20260921-SystemTest-ResultAnalyticsReport.md` §7 |
| 登録 Workflow / Step | 13 Workflow / 131 Step | `tests/system-test/20261001-2100-CLI-surface-all-workflows-result.md` |
| 実モデル 1 Step の実測 | 約 7〜18 分、約 5〜10 AIU（失敗時は 85〜92 秒で停止） | `tests/system-test/20261001-2125-CLI-Prompt-real-run-resume-snippet-result.md` §2.1 |
| 全 131 Step を 1 設定で直列実行した場合の試算 | 約 15〜39 時間、約 655〜1,310 AIU | 上記 1 Step 値 × 131（試算。並列・設定違いは含まない） |
| 先行 Prompt 版テストの対象 46 Step の試算 | 約 5.4〜13.8 時間 | 同上 × 46 |
| 設定の全直積 | 上限未承認のため実行せず。過去の直積件数（82,944 / 3,815,424）は根拠不足で撤回済み | 分析レポート §4 |

- 試算は 1 Step の実測 2 点（Step 393 秒・1,085 秒）を一般化した概算であり、Step ごとのばらつきは未測定。
- 全直積は現実的でなく、既に「値域ごとの代表同値クラス抽出」へ切り替え済み。ケース数の主因は Step 数 × 代表設定である。

### 3.2 一括実行で失敗した実例（分割の必要性）

- 2026-09-21 の Prompt 版テストは 44 ケースを 1 回の計画で扱った。実行 5 件が全件 FAIL（D-01 の MCP resource routing など）となり、**29 件は未実行（planned）、10 件は Azure 承認待ち（blocked）**のまま終了した。
- 全面阻害（D-01）が最初の Wave で判明したため、残りを止めて損失は小さく済んだ。これは「Wave を分けて失敗を早く検出する」方式が既に効いた実例である。逆に言えば、全件を 1 回で流す方式なら、同じ阻害に全ケースが当たり、時間と課金を無駄にしていた。
- 同じ要因で、`ard` は 2026-09-15 の「修正済み」記録後も本 HEAD で再現した。**修正後の再テストが必ず発生する**ため、全ケースを毎回やり直さず、失敗・未実施だけを再実行できる台帳が要る。

### 3.3 既存基盤は分割実行・再実行に適している

- 保存ルートは `tests/run/<run-id>/<task>/` で、証跡は上書きせず**再実行は新しい run / attempt に分離**する（`tests/README.md`）。
- checkpoint は case 単位の shard と aggregate を持ち、単一 writer・欠損ゼロの照合実績がある（分析レポート §9）。非終端（`planned` / `running` / `interrupted`）を区別できる。
- 1 ケース = 1 Workflow × 1 Step × 1 設定、別 lane（worktree）で隔離済み。ケース間の出力衝突がなく、独立に実行・再実行できる。
- 実行は最大同時 3 ケースで実証済み。時間短縮は「分割」だけでなく「並列」でも得られる。

### 3.4 分割実行の注意点（リスク）

| リスク | 内容 | 対策 |
|---|---|---|
| HEAD 変更 | HEAD が変わると plan SHA-256 が全件変わり、再 plan・再提示・再承認が必要（分析レポート §12） | 台帳に `source_head` を記録。HEAD 変更後は「未実施」でも `needs-replan` とする |
| 回ごとの条件差 | 回ごとに HVE 版・設定・モデルが変わると結果が比較不能。lane 実行時 0.8.124 と作業ツリー 0.8.132 の不一致も未解明 | 回ごとに HVE 版・HEAD・設定 SHA・モデルを記録し、混在した回の集計を禁止 |
| 共有状態 | durable store（`%LOCALAPPDATA%\hve\state.sqlite3`）が全 lane 共有で、stale な `running` が多数残る。回をまたぐほど増える | 回の開始時に件数を記録。棚卸しは破壊的操作のため別途承認 |
| 全面阻害の見逃し | 一部の回だけ成功し、他の回が阻害される状態を「分割した」ことで後から気付く | canary（§4.2）を毎回先頭で実行 |
| Step 間依存 | 前 Step の成果物を後 Step が使う。範囲指定で飛ばすと前提欠落 | ケースに predecessor を持たせ、前提未完了は `blocked` として選択から除外 |
| 承認境界 | Azure 書き込み 10 ケースは個別承認が要る。範囲に混ぜると毎回止まる | 別 Wave として分離し、承認取得後のみ実行 |
| 数字の流用 | 失敗時の所要時間を成功時の見積に流用すると予算が誤る | 成功実測が出るまで `NOT_MEASURED`。回ごとに実測を台帳へ追記 |

## 4. 推奨運用

### 4.1 台帳（ledger）

全ケースを一度に生成し、1 ケース 1 行で次を持つ。

`CASE-ID` / Workflow / Step / 設定ケース / 対象要件 ID / predecessor / Wave / 必要承認（Azure 等）/ 状態 / 最終 attempt の run-id / 実行時 HEAD / 所要・Token・AIU / 証跡パス

状態: `planned` → `ready` → `running` → `pass` / `fail` / `blocked` / `interrupted` / `needs-replan`

`pass` / `fail` は確定結果として保持し、再実行は新 attempt の行として追加する（過去結果を書き換えない）。

### 4.2 回（session）の組み立て

1. **canary**: 各 Workflow から 1 Step ずつ（計 4 前後、最小コスト）。D-01 のような全面阻害をここで検出し、失敗なら本体を dispatch しない。
2. **本体**: 台帳から「`planned` / `needs-replan` / 前回 `fail` で修正済み」かつ predecessor 完了・承認不要のケースを選ぶ。1 回あたりの上限を時間（例: 2〜3 時間）または AIU で決める。
3. **選択方法**: 次のいずれかで指定。範囲指定（CASE-ID の区間）は便利だが、飛び番・再実行に弱いため補助とする。
   - 状態指定（`--status planned`）
   - Workflow / Wave 指定
   - ID 列挙または区間
4. **回の終了時**: 台帳へ結果を反映し、未着手数・残り見積・要再 plan 数を出す。

### 4.3 順序

1. canary → 2. 依存の浅い Workflow（`ard` → `aas`）→ 3. `aad-web` → 4. `asdw-web`（Azure 非書き込み）→ 5. Azure 書き込み（承認後）。
各 Wave の先頭ケースが全面失敗なら、その Wave の残りを止める（既存の dispatch 停止ルールと同じ）。

### 4.4 判定の取り扱い

- 全回の合算で要件 coverage を出し、未実行は `BLOCKED` / `NOT_MEASURED` に保つ（`PASS` へ丸めない）。
- 修正で影響を受ける要件のケースは `needs-replan` に戻して再実行する。

## 5. 本調査の限界

- 1 Step の時間・AIU は実測 2 点（`aas` Step 1 と `ada` Step 2）のみ。Workflow 間のばらつき、成功率が上がった場合の時間は未測定。
- 131 Step 全件を 1 設定で流す試算は概算で、ケース数の確定値ではない（代表設定の追加分は含まない）。
- 台帳ツールの実装は未調査・未作成。既存の checkpoint 機構を流用できるかは別途設計が必要。

## 6. 参照

- `tests/README.md`（保存ルート・attempt 分離・checkpoint 規約、FR-MAINT-12）
- `tests/20260921-SystemTest-ResultAnalyticsReport.md`
- `tests/system-test/20261001-2100-CLI-surface-all-workflows-result.md`
- `tests/system-test/20261001-2125-CLI-Prompt-real-run-resume-snippet-result.md`
- `tests/[cli]SystemTest - Full.txt`（全組合せを前提とする現行指示）
