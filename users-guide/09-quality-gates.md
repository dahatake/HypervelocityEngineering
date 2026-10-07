# 9. 品質ゲートと検査項目

## 9.1 hook のゲート（§7.4）

`.github/hooks/quality-gates.json`（Copilot CLI と VS Code の Copilot harness が読む形式）が `scripts/hooks/gate.py` を呼びます。

| ゲート | 対象 | 動作 |
|---|---|---|
| **G-1** 要求の書き手を 1 つにする | rd-author 以外 | 実行中、`docs/requirements*` の編集を拒否します。作業役の worktree からの編集は常に拒否します |
| **G-2** System Test を不変にする | implementer、reviewer、作業役の worktree | `tests/system/**` の編集・削除と、台帳を更新する `ledger.py` の操作を拒否します。台帳 `ledger.json` の直接の編集は誰でも拒否します（`ledger.py` を使う） |
| **G-3** ID の採番 | 全員 | `docs/id-registry.md` の直接の編集を拒否します（`next-id.py` を使う）。手で振った ID は CHK-01 が検出します |
| **G-4** 終了前の検証 | implementer、test-designer、rd-author | 作業役が終わる前に verify を実行し、失敗していれば差し戻します（最大 3 回）。implementer は結果の `WORKTREE:` の worktree で検査します |
| **G-5** 危険な操作の拒否 | 全員 | main への push、force push、履歴の書き換え、実行中の main への直接 commit、`deploy: しない` の間のデプロイ、`git_push: しない` の間の push、作業ディレクトリ外への書き込み、実行中の hook の変更。あわせて役割ごとの書き込み範囲（conductor は `work/` と run-history、rd-author は `docs/`、test-designer は `tests/system/`、rd-auditor・reviewer は読み取り専用） |
| **G-6** 一時ファイルの置き場 | 全員 | ログ・証跡・実行結果（`*.log`、`*.har`、`*.trace`、`trace*.zip`、`results*.json`、`evidence/`、`screenshots/`、`test-results/`、`playwright-report/`）を `/work` 以外に書くことを拒否します。`/work` の削除は `clean-work.py` と `git worktree remove` だけに許します |
| 完了の判定 | conductor | 完了条件（queue に todo・doing なし、工程 6 完了、run-report.md あり）を満たすまで、ターンの終了を差し戻します（最大 40 回。時間予算の 125% を過ぎたら止めません） |
| 再開の案内 | 全員 | セッションの開始時に、実行中の run があれば run-id と再開の手順を伝えます |

**エージェントの見分け方**: Copilot の hook の `preToolUse` には呼び出したエージェントの名前がありません。そこで `subagentStart` / `subagentStop` で実行中の custom agent を `work/.hve/active-agents.json` に記録し、書き込み先のパスと、作業役の worktree（`work/worktrees/…`）・ブランチ（`work/<run-id>/<item>`）で判定します（計画書 §7.4 の代替案）。

**安全側の設計**: gate.py の内部エラーや壊れた入力は「許可」として扱い、ログに残します（ゲートの不具合でセッションが動かなくなるのを防ぐため）。同じ規則を verify でも検査するので、統合の時点で必ず止まります。

## 9.2 verify の検査（§10）

| ID | 検査 | 重大度 | 直し方 |
|---|---|---|---|
| CHK-00 | 要求定義書がない | warn（`--strict` で error） | 最初の実行で rd-author が作ります |
| CHK-01 | ID の重複。ID 台帳にない ID（手で振った） | error | `next-id.py` で振り直す。既存の文書は `next-id.py --sync --adopt` |
| CHK-02 | 削除済み・欠番の ID の再利用 | error | 新しい ID を採番する |
| CHK-03 | AC が実在する要求を参照していない | error | 要求の見出しの下に書くか、`対応する要求:` を付ける |
| CHK-04 | 要求に上位の G-ID（または既定制約）がない。存在しない G-ID。承認済みの要求がない G-ID | error / warn | 上位の欄を直す |
| CHK-05 | MUST 要求に AC も未回答の Q もない | error | AC を足すか、Q を挙げる |
| CHK-06 | 承認済みの要求に決定記録（根拠と日付）がない | error | `承認済み（依頼 YYYY-MM-DD）` の形にする |
| CHK-07 | カタログの要求 ID が要求定義書にない／決定状態が違う | error | カタログを直す |
| CHK-08 | カタログのファイルが存在しない | error | パスを直すか「未実装」にする |
| CHK-09 | 実装済みの MUST 要求の ID がテストコードにも manual-tests にもない（未実装は warn） | error / warn | テスト名かコメントに `FR-012 AC-031` を書く |
| CHK-10 | system の AC と台帳のケースが双方向に対応していない | warn（工程 4 以降・`--strict-ledger` で error） | test-designer がケースを足す。対象外になった AC のケースは block |
| CHK-11 | `ac_digests` が AC の本文と一致しない | 同上 | test-designer がケースを見直し `ledger.py digests --update` |
| CHK-12 | 台帳のケースの削除、理由なしの command・ac_ids の変更、tests/system の assert の減少、作業役のブランチによる tests/system の変更 | error | 元に戻す。変更は `ledger.py update --reason` で |
| CHK-13 | 新規・変更した要求・AC の曖昧な語 | warn（`--strict` で MUST は error） | 観察できる言葉に言い換える |
| CHK-14 | 数値と単位の直書き | warn | PARAM にして `{PARAM-xxx}` で参照する |
| CHK-15 | 用語集の禁止同義語 | warn | 正しい用語に直す |
| CHK-16 | 未定義の PARAM の参照、PARAM の表にない PARAM | error | PARAM の表に足す |
| CHK-17 | 廃止の要求とコード・テスト・カタログの残存の不整合 | error / warn | 取り除き終えたら本文から外す |
| CHK-18 | BLOCKED の AC が未回答の Q・TBD・競合を参照していない／回答済みの Q を参照している | error | 依存先を書く／回答を反映して BLOCKED を外す |
| CHK-19 | コード・テストにある要求 ID・AC ID が要求定義書にない | error | ID を直す（廃止した ID の残りは取り除く） |
| CHK-20 | 既定制約の節・ペルソナ表の必須列・要求の構造化欄・承認済み AC の検証レベルがない。決定状態が規定の値でない | error | [06-requirements-format.md](06-requirements-format.md) の形にする |
| CHK-21 | （`--run` のとき）done の項目の要求がカタログに実装済みとして載り、その system AC のケースが pass になっている | error | 統合をやり直す |
| CHK-22 | 承認済みの決定記録が 依頼・Q・承認依頼・包括承認 のどれも指していない（Q が存在しない） | error | 根拠を直す |
| CHK-23 | `/work` が .gitignore にない。docs・tests に一時ファイルが commit されている。run-history の run-id の重複 | error | .gitignore に `/work/`。一時ファイルを /work に移す |

出力は 1 行 1 指摘（`ERROR CHK-07 docs/catalog.md:12 …`）で、最後に `rdcheck: errors=N warnings=M` の 1 行です。
