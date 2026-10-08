# 6. 品質ゲートと検査項目

品質ゲートは 2 層です。hook がツール実行の前と終了前に規則を強制し、verify が同じ規則を決定的に検査します（[README の「2 層の品質ゲート」](../README.md#2-層の品質ゲート)）。

## 6.1 hook のゲート

`.github/hooks/quality-gates.json`（Copilot CLI の形式。VS Code の Copilot harness と、Copilot CLI の上に構築された GitHub Copilot app も読み込みます）が `scripts/hooks/gate.py` を呼び出します。GitHub Copilot app でローカル サンドボックスを有効にすると、hook もサンドボックスの中で、エージェントのシェルと同じ権限で動きます。

| ゲート | 対象 | 動作 |
|---|---|---|
| **G-1** 要求の書き手を 1 つに限定 | rd-author 以外 | run の実行中、`docs/requirements*` の編集を拒否します。作業役の worktree からの編集は常に拒否します |
| **G-2** System Test の変更禁止 | implementer、reviewer、作業役の worktree | `tests/system/**` の編集・削除と、台帳を更新する `ledger.py` の操作を拒否します。台帳 `ledger.json` の直接編集は、誰であっても拒否します（`ledger.py` を使う） |
| **G-3** ID の採番 | 全エージェント | `docs/id-registry.md` の直接編集を拒否します（`next-id.py` を使う）。手で振った ID は CHK-01 が検出します |
| **G-4** 終了前の検証 | implementer、test-designer、rd-author | 作業役の終了前に verify を実行し、失敗していれば差し戻します（最大 3 回）。implementer の場合は、結果に含まれる `WORKTREE:` の worktree で検査します |
| **G-5** 危険な操作の拒否 | 全エージェント | main への push、force push、履歴の書き換え、run 実行中の main への直接 commit、`deploy: しない` の間のデプロイ、`git_push: しない` の間の push、作業ディレクトリ外への書き込み、実行中の hook の変更、実行中のブランチ名の変更（GitHub Copilot app の `rename_branch`）を拒否します。あわせて役割ごとの書き込み範囲を強制します（conductor は `work/` と run-history、rd-author は `docs/`、test-designer は `tests/system/`、rd-auditor・reviewer は読み取り専用）。利用者が設定した MCP Server・plugin・拡張機能のツールによる外部のシステムの変更（名前に `create`・`update`・`delete`・`send` などを含むツール）は、run 中は `external_write: する` のときだけ、デプロイ・公開（`deploy`・`publish` など）は `deploy: する` のときだけ許可します。rd-auditor・reviewer の外部の変更は常に拒否します（[4.4](04-customization.md#44-mcp-serverplugin拡張機能を使う)） |
| **G-7** モデルの強制 | conductor | run の実行中、`scripts/ebak.config.json` の `models` に値のある作業役を、`task` の `model` 引数なし、または違うモデルで呼ぶことを拒否します（`implementer` は `implementer-escalation` のモデルも可）。呼び出しはすべて `work/runs/<run-id>/models.jsonl` に記録します。`gates.enforce_models: false` で無効にできます |
| **G-6** 一時ファイルの置き場所 | 全エージェント | ログ・証跡・実行結果（`*.log`、`*.har`、`*.trace`、`trace*.zip`、`results*.json`、`evidence/`、`screenshots/`、`test-results/`、`playwright-report/`）を `/work` 以外に書くことを拒否します。`/work` の削除は、`clean-work.py` と `git worktree remove` にだけ許可します |
| 完了判定 | conductor | 完了条件（queue に todo・doing がない、工程 6 が完了、run-report.md がある）を満たすまで、ターンの終了を差し戻します（最大 40 回。時間予算の 125% を超えたら差し戻しません） |
| 再開の案内 | 全エージェント | セッション開始時に、実行中の run があれば run-id と再開手順を表示します |
| `/build template` | 全エージェント | Prompt が `/build template` だけのターンでは、読み取りと skill 以外のツール（コマンド・書き込み・作業役の呼び出し）を拒否し、実行中の run があってもターンの終了を差し戻しません。雛形の表示が run の開始・再開に変わるのを防ぎます（`userPromptSubmitted` イベントで判定し、`work/.ebak/template-request.json` に記録します） |

**エージェントの識別方法**: Copilot の hook の `preToolUse` イベントには、呼び出し元のエージェント名が含まれません。そこで、`subagentStart` / `subagentStop` イベントで実行中の custom agent を `work/.ebak/active-agents.json` に記録し、書き込み先のパス、作業役の worktree（`work/worktrees/…`）、ブランチ（`work/<run-id>/<item>`）と合わせて判定します。

**フェイルオープンの設計**: gate.py の内部エラーや不正な入力は「許可」として扱い、ログに記録します（ゲートの不具合でセッション全体が止まるのを防ぐためです）。同じ規則を verify でも検査するので、統合の時点では必ず止まります。

hook の速さ: pre-tool は 1 回の run で数千回呼ばれます。読み取りだけの組み込みツール（view・grep・glob・read_powershell など）は、どのゲートの対象にもならないため、gate.py が設定ファイルの読み込みや git の呼び出しの前に許可を返します。hook は `python -S` で起動し、site-packages の初期化も省きます（gate.py は標準ライブラリだけを使います）。

## 6.2 verify の検査項目

`scripts/verify.py` が実行する検査です。

| ID | 検査内容 | 重大度 | 直し方 |
|---|---|---|---|
| CHK-00 | 要求定義書がない | warn（`--strict` では error） | 最初の run で rd-author が作成します |
| CHK-01 | ID の重複。ID 台帳にない ID（手で振った ID） | error | `next-id.py` で振り直す。既存のドキュメントは `next-id.py --sync --adopt` |
| CHK-02 | 削除済み・欠番の ID の再利用 | error | 新しい ID を採番する |
| CHK-03 | AC が実在する要求を参照していない | error | 要求の見出しの下に書くか、`対応する要求:` を付ける |
| CHK-04 | 要求に上位の G-ID（または既定制約）がない。存在しない G-ID を参照している。承認済みの要求を持たない G-ID がある | error / warn | 上位の欄を直す |
| CHK-05 | MUST 要求に AC も未回答の Q もない | error | AC を追加するか、Q を挙げる |
| CHK-06 | 承認済みの要求に決定記録（根拠と日付）がない | error | `承認済み（依頼 YYYY-MM-DD）` の形にする |
| CHK-07 | カタログの要求 ID が要求定義書にない／決定状態・題名が一致しない／承認済み・承認待ち・保留の要求の行がない／同じ要求の行が重複している／機能の表がない | error | `rdfix.py --apply` で要求定義書に合わせる（6.3） |
| CHK-08 | カタログに書かれたファイルが存在しない | error | パスを直すか「未実装」にする。名前の変更・削除は `rdfix.py --apply` で追従できる |
| CHK-09 | 実装済みの MUST 要求の ID が、テストコードにも manual-tests にもない（未実装なら warn） | error / warn | テスト名かコメントに `FR-012 AC-031` を書く |
| CHK-10 | system の AC と台帳のケースが双方向に対応していない | warn（工程 4 以降と `--strict-ledger` では error） | test-designer がケースを追加する。対象外になった AC のケースは block する |
| CHK-11 | `ac_digests` が AC の本文と一致しない | 同上 | test-designer がケースを見直し、`ledger.py digests --update` を実行する |
| CHK-12 | 台帳のケースの削除、理由のない command・ac_ids の変更、tests/system の assert の減少、作業役のブランチによる tests/system の変更 | error | 元に戻す。変更は `ledger.py update --reason` で行う |
| CHK-13 | 新規・変更した要求・AC に曖昧な語がある | warn（`--strict` では MUST 要求は error） | 観察可能な表現に言い換える |
| CHK-14 | 数値と単位がハードコードされている | warn | PARAM にして `{PARAM-xxx}` で参照する |
| CHK-15 | 用語集の禁止同義語を使っている | warn | 正しい用語に直す |
| CHK-16 | 未定義の PARAM の参照、PARAM の表にない PARAM | error | PARAM の表に追加する |
| CHK-17 | 廃止した要求に対して、コード・テスト・カタログが残っている（不整合） | error / warn | 削除し終えたら本文から外す |
| CHK-18 | BLOCKED の AC が、未回答の Q・TBD・競合を参照していない／回答済みの Q を参照している | error | ブロックの原因を書く／回答を反映して BLOCKED を外す |
| CHK-19 | コード・テストにある要求 ID・AC ID が要求定義書にない（`checks.id_scan_exclude` のパスは対象外。既定で docs・scripts・SVG の図・Spec Kit の `specs/**/*.md`・`.specify/**` などを除外） | error | ID を直す（廃止した ID の残骸は削除する） |
| CHK-20 | 既定制約の節、ペルソナ表の必須列、要求の構造化欄、承認済み AC の検証レベルがない。決定状態が規定の値でない | error | [03-requirements-format.md](03-requirements-format.md) の形式にする |
| CHK-21 | （`--run` 指定時）done の項目の要求がカタログに実装済みとして載り、その system AC のケースが pass になっているか | error | 統合をやり直す |
| CHK-22 | 承認済みの決定記録が、依頼・Q・承認依頼・包括承認のどれも根拠として指していない（または、存在しない Q を指している） | error | 根拠を直す |
| CHK-23 | `/work` が .gitignore にない。docs・tests に一時ファイルが commit されている。run-history の run-id が重複している | error | .gitignore に `/work/` を追加する。一時ファイルを /work に移す |
| CHK-24 | 参照先がない: 要求定義書の本文・表（出典・関連・決定記録など）やカタログの API・テーブル・共通部品の表に書いた ID が、要求定義書に定義されていない。変更履歴・決定記録・監査指摘の中の、ID 台帳で削除済み・廃止の ID だけは許す。カタログが廃止・却下の要求を参照している（warn） | error / warn | ID を直すか、参照先を定義する |
| CHK-25 | 構造化欄が定義を指していない: 対象エンティティが用語の表にも状態の表にもない。関係する状態が、その対象エンティティの状態の表にない。本文・受入基準の `{PARAM-xxx}` が参照パラメータの欄にない（欄にあるのに使っていない PARAM は warn） | error / warn | 用語・状態の表に定義するか、欄を直す |
| CHK-26 | 孤立した定義: どこからも参照されない PARAM・出典（SRC）、どの要求の対象エンティティでもない状態の表のエンティティ | warn | 参照を足すか、不要なら廃止する |
| CHK-27 | カタログの表どうしの不整合: 機能の表の「使っている共通部品」が共通部品の表にない。共通部品の表の「使っている要求 ID」が機能の表と一致しない。部品名・API 名・テーブル名の重複。要求の「関連する既存資産」に書いた 共通部品「…」・API「…」・テーブル「…」がカタログにない | error | 共通部品の表の要求 ID は `rdfix.py --only catalog --apply` で機能の表に合わせる。それ以外は表に行を足す |

CHK-24〜27 は、要求定義書とカタログを「体系として」保つための検査です。目的（G）→ 要求 → 受入基準 → System Test の台帳 → 実装・テストという縦のつながり（CHK-03・04・09・10）に加えて、要求と用語・状態・PARAM・出典・カタログの資産という横のつながりも、参照先が実在し、双方向で一致していることを保証します。つながりは `python scripts/rdcheck.py trace <ID または名前>` で上流・下流ともにたどれます（[5. スクリプト](05-scripts-reference.md)）。
出力は 1 行に 1 指摘（`ERROR CHK-07 docs/catalog.md:12 …`）で、最後に `rdcheck: errors=N warnings=M` の 1 行が出力されます。

## 6.3 データ層の不整合の自動修正（rdfix）

データ層のファイル（要求定義書・カタログ・ID 台帳・System Test の台帳・実行履歴・`.gitignore`）の間の食い違いのうち、要求定義書から機械的に決まるものは `python scripts/rdfix.py --apply` で直せます。verify が失敗し、自動で直せる不整合があるときは、`HINT rdfix: …` の行が出ます。

- 正本は要求定義書です。rdfix は要求定義書を変更しません（G-1）。ID 台帳は `next-id.py`、台帳は `ledger.py` を通して直し、台帳の変更は `history` に残します（G-2・G-3）。
- 判断が要る不整合は直さず、`MANUAL … （担当: <役割>）` として示します。例: AC の本文が変わった（CHK-11。ケースの見直しが要る）、削除済み・欠番の ID の再利用（CHK-02）、ID 台帳にない ID（CHK-01。手で振った ID かもしれない）、System Test の対象外になった AC のケース（CHK-10）。

| 対象（`--only`） | 自動で直すもの | 対応する検査 |
|---|---|---|
| registry | ID 台帳の状態（使用中・廃止・削除済み）、merge=union で重複した行、ID 台帳がないときの作成。`--adopt` を付けたときだけ、台帳にない ID を取り込む | CHK-01 |
| catalog | 機能の表の決定状態・題名を要求定義書に合わせる。要求の行の追加（実装ファイル・テストは、その ID を書いたコード・テストから埋める）。要求定義書にない要求の行（ファイルの記載がないもの）と重複した行の削除。名前が変わったファイルの参照の付け替えと、存在しないファイルの参照の削除。コードがなくなった廃止の要求の実装ファイルを「なし」にする。共通部品の表の「使っている要求 ID」を機能の表に合わせる | CHK-07・CHK-08・CHK-17・CHK-27 |
| ledger | ケースの欠けた項目、`requirement_ids` を AC の「対応する要求」に合わせる、`ac_digests` の不足の補充と、どのケースも参照しない `ac_digests` の削除 | CHK-10・CHK-11 |
| gitignore | `/work/` の追加 | CHK-23 |
| history | merge=union で重複した実行履歴の行の削除 | CHK-23 |

`--apply` は conductor が統合ブランチで実行します（「始めに」と工程 6）。作業役のブランチ（`work/<run-id>/<item>`）では実行を拒否し、hook も implementer・reviewer・rd-auditor による `--apply` を拒否します（G-2）。rd-author は `--only catalog,registry`、test-designer は `--only ledger` に限って使えます。
