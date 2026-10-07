# 5. 実行中と終了後

## 5.1 実行中の様子を見る

conductor の作業ツリー（VS Code の New Worktree なら、そのセッションの worktree）で次を実行します。どれも読み取りだけで、実行中の作業に影響しません。

```bash
python scripts/run-state.py status          # run-id、経過時間と時間予算、工程、queue の件数、progress の末尾
python scripts/run-state.py queue show      # 項目ごとの状態・試行回数・ブランチ
python scripts/ledger.py summary -v         # System Test の pass / fail / blocked / not_run
git log --oneline --graph -20               # [RD] [ST] [FR-xxx] の commit と統合
```

`work/.hve/gate.log` には、hook が拒否・差し戻した操作が記録されます。

## 5.2 止まったとき・再開（§7.5、§8.3）

| 状況 | すること |
|---|---|
| Autopilot がターンを終えたが、完了条件を満たしていない | 同じセッションで「続けて」と送ります。agentStop の hook が、完了条件を満たすまで自動で続けさせます（上限 40 回） |
| PC の再起動・Agent Host の停止 | 新しいセッションで、同じ Prompt をもう一度送ります。conductor は `RESUME <run-id>` として、`/work` の状態ファイルと git から続きを再開します |
| 途中でやめたい | セッションを止めます。統合ブランチには、そこまでに統合した項目が commit 済みです。`work/current-run.txt` を削除すると、次の依頼は新しい run として始まります |

conductor が自分で止まる条件（§8.3）:

| 条件 | 動作 |
|---|---|
| queue のすべての項目が done または blocked | 工程 6 に進み、終了する |
| `max_hours` の 85% を過ぎた | 新しい項目を始めず、工程 6 に進む |
| 同じ項目が 3 回続けてゲートで失敗 | 強いモデルで 1 回だけ再挑戦し、失敗したら blocked にして原因を記録 |
| canary が失敗し、3 回の修正でも直らない | 実装ループを止め、工程 6 に進む |
| 統合ブランチの verify が直前の統合で失敗に転じた | その統合を取り消し、項目を todo に戻す |

終了の判定は、モデルの「完了した」という判断ではなく、`python scripts/run-state.py complete-check` が exit 0（queue に todo・doing がない、工程 6 が終わっている、run-report.md がある）であることです。

## 5.3 終了後に読むもの（§8.4）

`work/runs/<run-id>/run-report.md`:

- 1 行目: 結果（全件完了／blocked あり／時間予算で中止／canary 失敗で中止）、経過時間、AI クレジット
- 実装した要求 ID、BLOCKED の要求 ID と理由
- **包括承認した項目**（影響の大きい順）… 意図と違えば次の `<answers>` で取り消します
- **未回答の質問票**（重要度の高い順）… 次の `<answers>` にそのまま書ける形
- 品質の指標: verify、AC の pass 率、監査の指摘（CRITICAL・HIGH の件数）
- 取り込み方法: 統合ブランチ名と、取り込みのコマンド

`/work` は 14 日で消えますが、要点は次の永続の場所に転記されています。

| 情報 | 場所 |
|---|---|
| 実行の要約と KPI（1 実行 1 行） | `docs/run-history.md` |
| 包括承認・回答を反映した決定 | 要求定義書の「決定記録」 |
| 未回答の質問票・承認依頼 | 要求定義書の「仮定・未解決事項」 |
| 残っている監査の指摘 | 要求定義書の「監査指摘」 |
| System Test の最新の状態 | `tests/system/ledger.json` |

## 5.4 取り込む

統合ブランチ（main 上で始めた場合は `run/<run-id>`。VS Code の New Worktree ならそのセッションのブランチ）を確認して取り込みます。

```bash
git switch main
git merge --no-ff run/202610080900          # ローカルで取り込む
# または
git push origin run/202610080900 && gh pr create --base main --head run/202610080900   # PR で取り込む（CI の hve-verify が再確認）
```

`git_push: 作業ブランチへ push する` を指定していれば、conductor が push と PR の作成まで行います（マージは利用者が行います。Q-5）。

取り込む前に、少なくとも次を見ます。

1. `run-report.md` の結果と「包括承認した項目」
2. `git diff main...<統合ブランチ> -- docs/requirements-definition.md`（要求の変化）
3. `python scripts/verify.py --strict` が PASS であること

## 5.5 次の依頼

回答と新しい要望を 1 つの Prompt にまとめて送れます。

```text
<request>
（新しい要望。なければ空）
</request>
<answers>
Q-003: B
残りはすべて推奨どおり
</answers>
```

## 5.6 /work の片付け

`/work/runs/` のうち 14 日を過ぎたものは、conductor が実行の最初と最後に `scripts/clean-work.py` で削除します（実行中の run と、まだ main に取り込まれていないブランチの run は残します）。手動でも実行できます。

```bash
python scripts/clean-work.py --dry-run   # 何が消えるかを確認
python scripts/clean-work.py
```
