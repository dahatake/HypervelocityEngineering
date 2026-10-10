# カタログ

既存の機能・API・テーブル・共通部品の対応表です。1 行 1 項目の短い表にし、詳細はリンク先のファイルに任せます。
機能の表は rd-author（要求 ID・題名・決定状態）と implementer（実装ファイル・テスト・共通部品）が更新します。
未実装の要求は、実装ファイルとテストの欄を「未実装」とします。

run 清掃は結果が全件完了で main へ統合後、その main 上の verify と清掃前 run-report の確定に成功した後だけ実行します。それ以外の run は自動期限なく保持します。

## 機能

| 要求 ID | 題名 | 決定状態 | 実装ファイル | テスト | 使っている共通部品 |
|---|---|---|---|---|---|
| FR-1009 | 正常完了 run の統合後清掃 | 承認済み（依頼 2026-10-10） | `scripts/clean-work.py`、[`.github/agents/conductor.agent.md`](docs/../.github/agents/conductor.agent.md) | `tests/toolkit/test_clean_work.py`、`tests/toolkit/test_run_state.py`、`tests/system/e2e/test_run_owned_cleanup.py`、`tests/system/test_run_cleanup_system.py` | run 作業資産清掃、worktree pool 管理、conductor 終了契約 |
| FR-1010 | 清掃の診断と再開 | 承認済み（依頼 2026-10-10） | `scripts/clean-work.py`、[`.github/agents/conductor.agent.md`](docs/../.github/agents/conductor.agent.md)、`users-guide/02-during-and-after-run.md`、`users-guide/05-scripts-reference.md`、`users-guide/07-troubleshooting.md` | `tests/toolkit/test_clean_work.py`、`tests/system/e2e/test_run_owned_cleanup.py`、`tests/system/test_run_cleanup_system.py` | run 状態・完了記録、run 作業資産清掃、conductor 終了契約、run 運用ガイド |
| NFR-OPS-005 | 所有権と保護状態にもとづく安全な削除 | 承認済み（依頼 2026-10-10） | `scripts/clean-work.py` | `tests/toolkit/test_clean_work.py`、`tests/toolkit/test_run_state.py`、`tests/system/e2e/test_run_owned_cleanup.py`、`tests/system/test_run_cleanup_system.py` | run 作業資産清掃、run 状態・完了記録、worktree pool 管理 |
| NFR-COMPAT-001 | Windows・報告・配布文書の一貫性 | 承認済み（依頼 2026-10-10） | `scripts/clean-work.py`、`tools/install.py`、[`.github/agents/conductor.agent.md`](docs/../.github/agents/conductor.agent.md)、`users-guide/02-during-and-after-run.md`、`users-guide/05-scripts-reference.md`、`users-guide/07-troubleshooting.md` | `tests/toolkit/test_clean_work.py`、`tests/system/e2e/test_run_owned_cleanup.py`、`tests/system/test_run_cleanup_system.py` | run 作業資産清掃、run 状態・完了記録、worktree pool 管理、conductor 終了契約、run 運用ガイド、配布同期対象 |

## API・イベント

| 名前 | 定義ファイル | 関連する要求 ID |
|---|---|---|

## テーブル

| テーブル名 | 定義ファイル | 正本のシステム | 関連する要求 ID |
|---|---|---|---|

## 共通部品

| 部品名 | ファイル | 用途 | 使っている要求 ID |
|---|---|---|---|
| run 作業資産清掃 | `scripts/clean-work.py` | 正常完了・main 統合後ゲート、所有権、保護状態にもとづく計画・清掃・診断・冪等再試行 | FR-1009、FR-1010、NFR-OPS-005、NFR-COMPAT-001 |
| run 状態・完了記録 | `scripts/run-state.py` | run の完了条件、finish、run-history と current-run の状態管理 | FR-1010、NFR-OPS-005、NFR-COMPAT-001 |
| worktree pool 管理 | `scripts/integrate.py` | pool worktree の列挙、強制削除、Git worktree 登録の prune | FR-1009、NFR-OPS-005、NFR-COMPAT-001 |
| conductor 終了契約 | [`.github/agents/conductor.agent.md`](docs/../.github/agents/conductor.agent.md) | run 開始時・工程 6・main 統合・run-report・清掃の実行順序 | FR-1009、FR-1010、NFR-COMPAT-001 |
| run 運用ガイド | `users-guide/02-during-and-after-run.md`、`users-guide/05-scripts-reference.md`、`users-guide/07-troubleshooting.md` | 利用者向けの統合、清掃、診断、再開、トラブルシューティング契約 | FR-1010、NFR-COMPAT-001 |
| 配布同期対象 | `tools/install.py` | conductor、清掃・状態・統合スクリプトをインストール対象へ同期する管理対象 | NFR-COMPAT-001 |
