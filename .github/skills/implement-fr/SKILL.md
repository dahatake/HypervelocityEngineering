---
name: implement-fr
description: implementer が、conductor から渡された承認済みの要求（ID 1〜5 個）を、プールの git worktree の中で実装する手順書。単体・結合テスト、カタログの行、`verify.py --quick` と System Test のゲートまでを行う。要求定義書と tests/system/・台帳は変更せず、不整合は `CONFLICTS:` で返す。画面を持つ要求は ui-design.md を併せて読む。
---
# implement-fr（implementer の手順書）

この手順書は、利用者の原本「RD-FR_Prompt」の本文（同じフォルダーの別ファイルにある「原本」）に、conductor による無人の連続実行につなぐための読み替えと規則を加えたものです。

## 読み替え表（原本の指示 → この実行での扱い）

原本は、利用者が 1 本ずつ手で投入する前提で書かれています。conductor が無人で連続実行するため、次のとおり読み替えます。**読み替えと原本が食い違うときは、読み替えを優先します。**

| 原本の指示 | 読み替え | 理由 |
|---|---|---|
| RequirementDefinition「commit と push は行わない。利用者が差分をレビュー」 | rd-author は統合ブランチに `[RD] <要約>` で commit します。利用者のレビューは、最終報告（run-report）と取り込みの判断で行います。 | 無人で連続実行するため |
| RD-FR「依頼をもって承認」「要求定義書を作成または更新」 | implementer は要求定義書を変更しません。要求の誤りや不足は、結果の `CONFLICTS:` に書き、conductor が rd-author に回します。 | 要求の書き手を 1 つにする（GAP-1、H1） |
| RD-FR「テストが誤っていると判断した場合は、理由を記録して直す」 | 単体・結合テストに限ります。`tests/system/` と台帳は変更しません。理由は要求定義書ではなく、結果とコミットメッセージに書きます。 | System Test を不変にする（H4、R-5） |
| SystemTest「自動修正は `systemtest-autofix/<日時>` ブランチ」 | 統合ブランチの上で、conductor が implementer に修正を依頼します。test-designer は修正しません。 | ブランチを増やさない |
| SystemTest「対象 AC はシステム全体を通して確かめるもの」 | 「検証レベル: system」の AC にします。 | 判断のぶれをなくす（GAP-5） |
| 3 Prompt「最終報告はチャットで」 | `work/runs/<run-id>/run-report.md` に書きます（conductor）。作業役は 10 行以内の結果を返します。残すべき情報は `/docs` と台帳に転記します。依頼に関係しない既存の問題は、要求定義書の「監査指摘」に書きます。 | 監査結果を消さない（GAP-7） |
| 3 Prompt・SystemTest「ログ、証跡（スクリーンショット）、実行結果の保存先」 | `work/runs/<run-id>/logs/`、`evidence/`、`results.json` にします。台帳には最新の状態（status、last_commit、last_run_at、evidence、history）だけを書きます。 | /docs と tests を永続のものだけにする |
| 3 Prompt「新しい ID は最大番号の続き」 | `python scripts/next-id.py <種別>` で採番します（FR、NFR-<区分>、AC、Q、PARAM、E2E、IT）。 | 並行作業での ID の衝突を防ぐ（GAP-6） |
| RD-FR・SystemTest「承認済みの要求だけを実装・テスト」 | approval_policy で包括承認したものを含みます。決定記録に「包括承認」と書きます。 | 承認待ちで止まらない（§承認ポリシー） |
| 3 Prompt「質問せずに最後まで進める」「<request> <answers> <references> <execution_options> <run_options>」 | 利用者が毎回書く部分は、conductor が作業役への依頼の本文で渡します。原本の入力欄（`<request>` など）は、その置き場所を示すだけです。 | 利用者の Prompt を 1 回にする |

## この役割で追加する規則

### 原本のどこを使うか
- implementer が行うのは、原本の `<implementation>`、`<catalog>`（機能の表の実装ファイル・テスト・共通部品の列と、API・テーブル・共通部品の表）、`<boundaries>` です。
- 原本の `<investigation>` は、渡された要求 ID・AC と、カタログに載っている関連資産の範囲で行います（`python scripts/rdcheck.py show <ID>` で必要な節だけ読む）。
- 原本の `<audit>`・`<questionnaire>`・`<requirements_document>` の作業（要求定義書の作成・更新、質問票の追加、決定状態の変更）は行いません。見つけた不整合・不足・要求の誤りは、結果の `CONFLICTS:` に 1 行ずつ書きます。原本の `<implementation>` の「理由を要求定義書に記録」「競合として記録し質問票に挙げる」、`<communication>` の「要求定義書が更新され」も、同じく `CONFLICTS:` と結果への記載に読み替えます。
- `<execution_options>` は conductor が run_options から渡します（implement_scope ← scope、ほかは同名）。

### 検証スクリプトと CI
- 原本の「検証スクリプト」は `scripts/verify.py`（`verify.ps1` / `verify.sh` から呼ぶ）として既にあります。管理データの整合（CHK-01〜27）はそこで検査されます。
- ビルド・静的検査・テストのコマンドは、`scripts/ebak.config.json` の `verify.commands` に登録します。例: `{"name": "unit", "run": "npm test"}`。時間のかかるものには `"slow": true` を付けます（作業役のゲートは `--quick` で省きます）。
- 原本の「CI」は `.github/workflows/ebak-verify.yml` として既にあります。CodeQL・依存関係の確認を加える場合はこのワークフローに追記します。

### worktree とゲート
- 作業は渡された worktree（`work/worktrees/<run-id>-w<N>/`。項目をまたいで再利用されるプール。ブランチ `work/<run-id>/<item>`）の中だけで行います。ignore されたビルドの生成物は消さずに増分ビルドに使います。
- ゲート: `python scripts/verify.py --quick` と、関係する System Test を `python scripts/ledger.py run --cases <ケース ID> --no-record` で実行します（台帳は conductor が統合後に更新します）。どのテストを実行するかは `python scripts/select-tests.py` で選べます。
- 依存パッケージ（`npm ci` など）: `integrate.py prepare` が `SHARED:` と出したディレクトリは主の作業ツリーと共有済みなので、導入しない（消さない・上書きしない）。`NOTE:` が出たときだけ、ロックファイルが変わった場合に限り導入する。同時に複数の `npm ci` を走らせない（並列の `npm ci` は各 45 分かかった実測がある）。
- `verify.py --no-cache` と全件回帰は実行しない（キャッシュが効かないと 1 回で 2 時間超かかった実測がある）。1 コマンドが 20 分を超えそうなら止めて、conductor に結果を返す。
- 基点（実装前）から落ちているテストは、自分の項目の失敗と区別し、直さずに `BASELINE-FAIL: <テスト ID>` として返す（原因調査に時間を使わない）。
- AC のゲートが通ったら、無関係な不安定テストを直さず、結果に `UNRELATED-FLAKY: <テスト名と症状>` として報告して終えます。1 項目の作業は 60 分（PARAM-045）を超えません。
- 長いログは `python scripts/summarize.py <log>` で要約してから読みます。
- commit は `[<要求 ID>] <要約>` で、作業ブランチにだけ行います。push はしません。

### 画面の見た目（UI デザインの基盤）
画面を持つ要求を実装するときは、同じフォルダーの `ui-design.md` を読んで従います（デザインシステムの選定、デザイン基盤、見た目の規則、ゲートの前の確認）。画面のない項目では読みません。

### 削除の依頼（廃止の要求）
- 原本どおり、その機能だけが使っていたコード、テスト、設定、カタログの行を取り除きます。`tests/system/` のケースは削除せず、`CONFLICTS:` に「<ケース ID> を blocked にする必要」と書きます（test-designer が `ledger.py block` で扱います）。
- 要求定義書の本文から外す作業は rd-author が行います。

---

## 原本 RD-FR_Prompt の読み方（起動のたびに全文を読まない）

原本の全文は同じフォルダーの `original-fr.md` にあります（内容は変更していません。読み替え表と、この手順書の規則が優先です）。起動のたびに全文を読むと、読み込む量が増えて起動が遅くなります。次の表の「必ず読む」節だけを、`view` の行範囲で読みます。「必要なとき」の節は、その場合だけ読みます。表の行範囲は `tests/toolkit/test_skill_index.py` が原本のタグの位置と照合します（ずれたらテストが落ちます）。

| 節 | 位置 | 読むとき |
|---|---|---|
| `<terms>` | 58〜67 行 | 必ず読む |
| `<implementation>` | 110〜129 行 | 必ず読む |
| `<catalog>` | 131〜139 行 | 必ず読む |
| `<boundaries>` | 141〜162 行 | 必ず読む |
| `<communication>` | 164〜183 行 | 必ず読む |
| `<turn_endings>` | 185〜192 行 | 必ず読む |
| `<investigation>` | 80〜106 行 | 要求の調査が必要なとき（渡された要求・AC・カタログの範囲を超えて確かめるとき） |
| `<workflow>` | 69〜78 行 | 原本の全体の流れを確かめたいとき |
| `<execution_options>` | 28〜38 行 | 実行オプションの定義を確かめたいとき（この手順書の規則で足りる） |
| `<context>` | 50〜56 行 | 管理データの位置づけを確かめたいとき |
