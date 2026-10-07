# 10. トラブルシューティング

## 拒否・差し戻し

| 症状（メッセージ） | 原因 | 対処 |
|---|---|---|
| `[G-1] 要求定義書を編集できるのは rd-author だけです` | 実行中に rd-author 以外が要求定義書を編集しようとした | 正常な動作です。conductor が rd-author に依頼します。利用者が手で直したいときは、実行が終わってから（`work/current-run.txt` がない状態で）編集します |
| `[G-5] conductor が編集できるのは /work/ と docs/run-history.md だけです` が、作業役の作業中に出る | harness が `subagentStart` を通知しておらず、作業役を見分けられない（Phase 1 の確認項目 3） | `work/.hve/gate.log` に `START <作業役>` があるかを確認します。ない場合は `scripts/hve.config.json` の `gates.enforce_conductor_edit_scope` を `false` にします（G-1・G-2 は worktree とブランチでも判定するので、主要な保護は残ります） |
| `[G-2] 作業役は台帳を更新しません` | implementer が `ledger.py run` を `--no-record` なしで実行した | `ledger.py run --cases <ID> --no-record` を使います。台帳は conductor が統合後に更新します |
| `[G-5] run_options の git_push が「しない」なので push しません` | push を許可していない | 必要なら次の依頼で `git_push: 作業ブランチへ push する` |
| `[G-6] ログ・証跡・実行結果などの一時ファイルは /work/runs/<run-id>/ に書きます` | テストのレポートなどをリポジトリ直下に出力しようとした | テストツールの出力先を `work/` の下に設定します（例: Playwright の `outputDir`） |
| `[G-4] 終了前の検証が失敗しています` | 作業役の verify が失敗 | 作業役が自動で直します。3 回で直らなければ `GATE G-4` 付きで conductor に返り、その項目は統合されません |
| hook がまったく動かない | Session Target が Copilot 以外、hook が無効、Python がない | Copilot harness を選ぶ。`/hooks`（VS Code）や `copilot` の設定で hook が有効か確認。`python --version` を確認。`work/.hve/gate.log` が作られるかで判定します |

hook を一時的に止めて原因を切り分けたいときは、`scripts/hve.config.json` の `gates.enabled` を `false` にします（verify の検査は残ります）。終わったら必ず戻します。

## 実行が止まる・終わらない

| 症状 | 対処 |
|---|---|
| Autopilot が途中でターンを終えた | 同じセッションで「続けて」。新しいセッションなら同じ Prompt を送ると `RESUME` で再開します |
| 終わらない（同じ失敗を繰り返す） | `python scripts/run-state.py status` と `progress.md` で、どの項目が何回失敗しているかを見ます。`max_hours` の 85% で自動的に最終工程に進みます。急ぐときは、その項目を `python scripts/run-state.py queue set <ID> --status blocked` にします |
| 「完了条件を満たしていません」で差し戻され続ける | `python scripts/run-state.py complete-check` の理由を確認します。工程 6 を終えて `run-state.py stage 6 --done` と `run-report.md` が必要です。差し戻しは 40 回、または時間予算の 125% で止まります |
| 前の run が残っていて新しい依頼が RESUME になる | 前の run を終えるか、`work/current-run.txt` を削除してから依頼します |

## verify が失敗する

| 症状 | 対処 |
|---|---|
| 導入直後に CHK-20・CHK-01 が多数出る | 既存の要求定義書が toolkit の書式でないためです。`python scripts/next-id.py --sync --adopt` のあと、「既存の要求定義書を toolkit の書式に合わせる。意味は変えない」と依頼します |
| CHK-10/11 が工程 4 のあとに出る | AC が追加・変更されたのに System Test が追いついていません。conductor が test-designer に回します |
| CHK-19 でテストデータや資料の中の ID が拾われる | `checks.id_scan_exclude` にそのパスを足します |
| CHK-08 でカタログのパスが見つからない | パスはリポジトリのルートからの相対パスで、`src/a.ts, src/b.ts` のようにカンマ区切りで書きます |
| CI だけで失敗する | CI にアプリのツールチェーンがない可能性があります。`.github/workflows/hve-verify.yml` にセットアップの手順を足します |

## Windows 固有

| 症状 | 対処 |
|---|---|
| `python` が Microsoft Store を開く | 実体の Python を入れ、「アプリ実行エイリアス」の python を無効にします |
| 日本語が文字化けする | スクリプトは UTF-8 で出力します。PowerShell で `$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8` を設定します |
| `verify.ps1` が実行できない | `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`、または `python scripts/verify.py` を直接使います |

## 記録を見る場所

| 見たいもの | 場所 |
|---|---|
| hook が何を拒否・差し戻したか | `work/.hve/gate.log` |
| 実行の進み具合と判断 | `work/runs/<run-id>/progress.md` |
| verify・テストのログの全文 | `work/runs/<run-id>/logs/` |
| 監査の生データ | `work/runs/<run-id>/audit/` |
| 過去の実行の結果と KPI | `docs/run-history.md` |
