# 2. 実行中と終了後

## 2.1 進捗を確認する

conductor の作業ツリー（VS Code の New Worktree や GitHub Copilot app の新しい作業ツリーなら、そのセッションの worktree）で次のコマンドを実行します。どれも読み取り専用で、実行中の run には影響しません。GitHub Copilot app の worktree は、既定では `<リポジトリの親>/copilot-worktrees/<リポジトリ名>/<ブランチ名>` にあります（`git worktree list` で確認できます）。

```bash
python scripts/run-state.py status          # run-id、経過時間と時間予算、統合ブランチ、工程、queue の件数、progress の末尾
python scripts/run-state.py queue show      # 項目ごとの状態・試行回数・ブランチ
python scripts/ledger.py summary -v         # System Test の pass / fail / blocked / not_run
git log --oneline --graph -20               # [RD] [ST] [FR-xxx] の commit と統合
```

hook が拒否・差し戻した操作は `work/.ebak/gate.log` に記録されます。

## 2.2 停止したときの再開

状態は `/work` のファイルと git に永続化されているので、どの時点で止まっても続きから再開できます。

| 状況 | 対処 |
|---|---|
| Autopilot がターンを終えたが、完了条件を満たしていない | 同じセッションで「続けて」と送信します。agentStop の hook が、完了条件を満たすまで自動で継続させます（上限 40 回） |
| PC の再起動・Agent Host の停止 | 新しいセッションで、同じ Prompt をもう一度送信します。conductor は `RESUME <run-id>` として、`/work` の状態ファイルと git から続きを再開します |
| GitHub Copilot app の再起動・セッションの中断 | サイドバーから**同じセッション**を開き、「続けて」と送信します。新しい作業ツリーのセッションを新しく作ると別の worktree になり、`/work` の状態がないため新しい run として始まってしまいます。ローカル リポジトリで実行していた場合は、新しいセッションでも再開できます |
| 途中でやめたい | セッションを停止します。そこまでに統合した項目は、統合ブランチに commit 済みです。`work/current-run.txt` を削除すると、次の依頼は新しい run として始まります |

conductor が自分で停止する条件:

| 条件 | 動作 |
|---|---|
| queue のすべての項目が done または blocked | 工程 6 に進んで終了する |
| `max_hours` の 85% を超えた | 新しい項目には着手せず、工程 6 に進む |
| 同じ項目がゲートで 3 回続けて失敗した | 上位モデルで 1 回だけ再挑戦し、それでも失敗したら blocked にして原因を記録する |
| canary が失敗し、3 回修正しても直らない | 実装ループを止めて、工程 6 に進む |
| 直前の統合で、統合ブランチの verify が失敗に変わった | その統合を取り消し、項目を todo に戻す |

終了の判定は、モデルの「完了した」という自己申告ではなく、`python scripts/run-state.py complete-check` が exit 0 を返すことで行います。exit 0 の条件は、queue に todo・doing がない、工程 6 が終わっている、run-report.md がある、の 3 つです。

## 2.3 終了後に読むもの

`work/runs/<run-id>/run-report.md` には次の内容があります。

- 1 行目: 結果（全件完了／blocked あり／時間予算で中止／canary 失敗で中止）、経過時間、AI クレジット
- 実装した要求 ID、BLOCKED の要求 ID とその理由
- **包括承認した項目**（影響の大きい順）… 意図と違えば、次の `<answers>` で取り消します
- **未回答の質問票**（重要度の高い順）… 次の `<answers>` にそのまま書ける形式です
- 品質メトリクス: verify、AC の pass 率、監査の指摘（CRITICAL・HIGH の件数）
- **KPI**: North Star「人の介入 1 回あたりの検証済み要求」、1 回目のゲート通過率、トレーサビリティ網羅率など。HTML 版は `work/runs/<run-id>/kpi.html` です。過去の run を通した集計は `python scripts/kpi.py history` で表示できます
- マージ方法: 統合ブランチ名と、マージのコマンド

`/work` は 14 日で削除されますが、要点は次の永続的な場所に転記されています。要求・カタログ・試験の状態は、[EABK Studio](../EABK-Studio/users-guide/README.md)（`python EABK-Studio/studio.py`）で図と表として確認できます。

| 情報 | 場所 |
|---|---|
| run の要約と KPI（1 run 1 行） | `docs/run-history.md` |
| 包括承認・回答を反映した決定 | 要求定義書の「決定記録」 |
| 未回答の質問票・承認依頼 | 要求定義書の「仮定・未解決事項」 |
| 未解決の監査指摘 | 要求定義書の「監査指摘」 |
| System Test の最新の状態 | `tests/system/ledger.json` |

## 2.4 マージする

結果が「全件完了」で最終の verify が通った run は、conductor が統合ブランチ `run/<run-id>` をローカルの main へ `--no-ff` でマージし、統合ブランチを削除します（main への push はしません）。マージが競合したり verify が失敗したりした場合、および「blocked あり」「時間予算で中止」「canary 失敗で中止」の run は、取り込まずにブランチを残します。その場合や VS Code の New Worktree・GitHub Copilot app の新しい作業ツリー（そのセッションのブランチ）では、次のように手動で取り込みます。

```bash
git switch main
git merge --no-ff run/202610080900          # ローカルでマージする
# または
git push origin run/202610080900 && gh pr create --base main --head run/202610080900   # PR でマージする（CI の ebak-verify が再検証）
```

`git_push: 作業ブランチへ push する` を指定していれば、conductor は取り込みの前に統合ブランチを push します（バックアップ。PR は作りません）。

GitHub Copilot app の新しい作業ツリーで実行した run は、セッションのブランチが統合ブランチです（`run-state.py status` の `integration:`）。conductor は main へマージしないので、アプリのプル要求の作成機能で PR を作るか、上のコマンドの `run/<run-id>` をセッションのブランチ名に置き換えて取り込みます。取り込みが終わるまで、セッションをアーカイブ・削除しないでください（worktree と `/work` の報告が消えることがあります）。

自動マージの前に確認したい場合は、`git diff main...<統合ブランチ>` を取り込み前に見ることはできないため、事後に `git revert -m 1 <マージ commit>` で戻します。

手動でマージする場合は、その前に少なくとも次の 3 点を確認します。

1. `run-report.md` の結果と「包括承認した項目」
2. `git diff main...<統合ブランチ> -- docs/requirements-definition.md`（要求の変更点）
3. `python scripts/verify.py --strict` が PASS になること

## 2.5 次の依頼

回答と新しい要望を 1 つの Prompt にまとめて送信できます。

```text
<request>
（新しい要望。なければ空）
</request>
<answers>
Q-003: B
残りはすべて推奨どおり
</answers>
```

## 2.6 /work のクリーンアップ

清掃は保持期間ではなく、正常完了の証拠で許可されます。結果が「全件完了」で、完了条件、最終 verify、対象テスト、main への統合、main 上の統合後 verify が順に成功し、清掃前版 `run-report.md` が確定した run だけを清掃します。それ以外（blocked、中止、失敗、未達、report 不足）は再開できるよう自動期限なく保持します。

清掃前版 report には main の統合 commit、各ゲートの構造化結果、清掃候補、保護・保持する資産と理由が含まれます。清掃後は候補別の削除・保持・失敗と run 最終状態だけを追記します。途中で失敗すると以後の削除を止めて非 0 で終了し、残存候補だけを再検査して安全に再試行できます。

```bash
python scripts/clean-work.py --dry-run   # 候補・保護理由・実行予定を確認（変更なし）
python scripts/clean-work.py             # 削除直前に所有権と状態を再検査
```
