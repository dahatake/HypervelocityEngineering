# 3. はじめての実行

## 3.1 VS Code で実行する（推奨。計画書 §8.1）

1. 導入したリポジトリを VS Code で開き、**Agents ウィンドウ**で **New** を選びます。
2. 次のように設定します。

   | 設定 | 値 | 理由 |
   |---|---|---|
   | Session Target | **Copilot** | Copilot harness（Agent Host）は、ウィンドウを閉じてもセッションが続き、`.github/hooks` の hook が Copilot CLI と同じ仕様で動きます |
   | Agent | **conductor** | 利用者が呼ぶ唯一のエージェント |
   | モード | **Autopilot** | ツールを承認なしで実行し、エラーでは再試行し、作業の完了まで続けます |
   | Code isolation | **New Worktree**（ベースは main） | 元の作業ツリーと分けて作業します。アプリの依存関係をコンテナーで揃えたいときは Dev Container |

3. エージェントの**サンドボックス**を有効にします。ネットワークは、パッケージのレジストリなど必要な宛先だけを許可します（worktree はセキュリティの境界ではないため。R-24）。
4. チャット欄で `/build` を選び、表示される入力欄に「やりたいこと」を書いて送信します（雛形は `.github/prompts/build.prompt.md`。書き方は [04-writing-requests.md](04-writing-requests.md)）。
5. 送信したら、ウィンドウを閉じてもかまいません。ただし **PC はスリープさせないでください**（Agent Host は PC 上で動きます）。途中の様子は、Agents ウィンドウのセッション一覧から開いて見られます。

> New Worktree では、git の管理対象外のファイル（`/work` など）は新しい worktree に入りません。conductor の `/work` は、そのセッションの worktree の中に作られます。

## 3.2 Copilot CLI で実行する

同じ customizations（`.github/agents`・`.github/skills`・`.github/hooks`）を Copilot CLI でも使えます。

```bash
# 依頼を書いたファイル（雛形は .github/prompts/build.prompt.md の本文）を用意して
copilot --agent conductor --autopilot --allow-all --max-autopilot-continues 500 -i "$(cat request.md)"
```

```powershell
copilot --agent conductor --autopilot --allow-all --max-autopilot-continues 500 -i (Get-Content request.md -Raw)
```

- `--max-autopilot-continues` の既定は 5 です。24〜48 時間の実行では大きくします。
- サンドボックスは対話中の `/sandbox` で設定します（`copilot help sandbox`）。全権限（`--allow-all`）とサンドボックスを組み合わせて使うことが推奨されています（R-24）。
- 別のブランチで実行したいときは、先に `git switch -c run/<名前>` してから起動します。main 上で起動した場合も、conductor が最初に統合ブランチ `run/<run-id>` を作ります。

## 3.3 最初の依頼の例

```text
<request>
社内の備品貸出アプリを新規に作りたい。社員は備品を検索して予約し、総務は貸出と返却を記録する。
延滞が 3 日を超えたら本人と上長に通知する。Web アプリで、まずはローカルで動けばよい。
</request>
<answers>
</answers>
<references>
docs/source/備品管理の現状.md
</references>
<run_options>
max_hours: 8
approval_policy: 安全範囲は推奨どおり
parallel_workers: 3
scope: 承認済みすべて
git_push: しない
deploy: しない
paid_services: 使わない
external_exposure: 公開しない
</run_options>
```

最初は `max_hours` を短め（4〜8 時間）にして、報告の形と品質を確かめることを勧めます。

## 3.4 何が起きるか

1. conductor が `run-state.py start` で run を始め、統合ブランチを作り、verify の基準を記録します。
2. rd-author が要求定義書とカタログを作り、質問票を挙げます（`[RD]` の commit）。
3. rd-auditor が独立に監査し、直接矛盾があれば rd-author に戻します。
4. conductor が作業キューを作ります。
5. test-designer が System Test と台帳のケースを作ります（`[ST]` の commit。すべて `not_run`）。
6. implementer が項目ごとに worktree で実装し（`[FR-xxx]` の commit）、conductor が 1 本ずつ統合します。
7. 最後に System Test の全量と全量監査を行い、`work/runs/<run-id>/run-report.md` を書きます。

## 3.5 初回に確かめること（Phase 1 のチェックリスト。§12）

hook や subagent の動きは、harness と VS Code の版によって違うことがあります。最初の実行（または短い試行）で次を確かめ、結果を `docs/run-history.md` の備考か、チームの記録に残します。

| # | 確かめること | 確かめ方 |
|---|---|---|
| 1 | custom agent を subagent として呼べるか | progress.md に rd-author・test-designer・implementer の結果が記録されている |
| 2 | custom agent ごとのモデル指定が効くか | Agent Debug Logs / 使用量の表示で、作業役ごとのモデルを確認 |
| 3 | hook のイベントと、呼び出したエージェントを見分けられるか | `work/.hve/gate.log` に `START rd-author` などと `DENY`/`BLOCK` が記録されている |
| 4 | ウィンドウを閉じても処理が続くか | ウィンドウを閉じて 30 分後に開き直し、progress.md が進んでいる |
| 5 | サンドボックスの下でテストとブラウザーの自動操作（Playwright）が動くか | `ledger.py run` の結果が pass/fail で記録される（`TIMEOUT` や権限エラーでない） |
| 6 | Advanced Autopilot の有無で完了判定がどう違うか | 早すぎる完了宣言が起きないか（agentStop の hook が `完了条件を満たしていません` で差し戻しているか） |

3 で subagent の検出がうまくいかない場合は、[10-troubleshooting.md](10-troubleshooting.md) の「conductor が編集を拒否される」を参照します。
