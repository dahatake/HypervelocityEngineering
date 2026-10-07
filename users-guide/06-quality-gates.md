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
| **G-6** 一時ファイルの置き場所 | 全エージェント | ログ・証跡・実行結果（`*.log`、`*.har`、`*.trace`、`trace*.zip`、`results*.json`、`evidence/`、`screenshots/`、`test-results/`、`playwright-report/`）を `/work` 以外に書くことを拒否します。`/work` の削除は、`clean-work.py` と `git worktree remove` にだけ許可します |
| 完了判定 | conductor | 完了条件（queue に todo・doing がない、工程 6 が完了、run-report.md がある）を満たすまで、ターンの終了を差し戻します（最大 40 回。時間予算の 125% を超えたら差し戻しません） |
| 再開の案内 | 全エージェント | セッション開始時に、実行中の run があれば run-id と再開手順を表示します |

**エージェントの識別方法**: Copilot の hook の `preToolUse` イベントには、呼び出し元のエージェント名が含まれません。そこで、`subagentStart` / `subagentStop` イベントで実行中の custom agent を `work/.hve/active-agents.json` に記録し、書き込み先のパス、作業役の worktree（`work/worktrees/…`）、ブランチ（`work/<run-id>/<item>`）と合わせて判定します。

**フェイルオープンの設計**: gate.py の内部エラーや不正な入力は「許可」として扱い、ログに記録します（ゲートの不具合でセッション全体が止まるのを防ぐためです）。同じ規則を verify でも検査するので、統合の時点では必ず止まります。

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
| CHK-07 | カタログの要求 ID が要求定義書にない／決定状態が一致しない | error | カタログを直す |
| CHK-08 | カタログに書かれたファイルが存在しない | error | パスを直すか「未実装」にする |
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
| CHK-19 | コード・テストにある要求 ID・AC ID が要求定義書にない | error | ID を直す（廃止した ID の残骸は削除する） |
| CHK-20 | 既定制約の節、ペルソナ表の必須列、要求の構造化欄、承認済み AC の検証レベルがない。決定状態が規定の値でない | error | [03-requirements-format.md](03-requirements-format.md) の形式にする |
| CHK-21 | （`--run` 指定時）done の項目の要求がカタログに実装済みとして載り、その system AC のケースが pass になっているか | error | 統合をやり直す |
| CHK-22 | 承認済みの決定記録が、依頼・Q・承認依頼・包括承認のどれも根拠として指していない（または、存在しない Q を指している） | error | 根拠を直す |
| CHK-23 | `/work` が .gitignore にない。docs・tests に一時ファイルが commit されている。run-history の run-id が重複している | error | .gitignore に `/work/` を追加する。一時ファイルを /work に移す |

出力は 1 行に 1 指摘（`ERROR CHK-07 docs/catalog.md:12 …`）で、最後に `rdcheck: errors=N warnings=M` の 1 行が出力されます。
