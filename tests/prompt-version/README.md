# HVE Prompt 版 統合テスト Prompt 集

`hve` の **Prompt 版**（Cloud / GUI / CLI に続く第 4 の利用面）を統合テストするための、
そのまま貼り付けて使える依頼文です。

- 実装の入口: `python -m hve prompt plan|run`（利用者は直接実行せず、Copilot が代行する）
- 利用者ガイド: [users-guide/hve-prompt-getting-started.md](../../users-guide/hve-prompt-getting-started.md)
- Agent Skill: [.github/skills/hve-prompt-edition/SKILL.md](../../.github/skills/hve-prompt-edition/SKILL.md)
- 規範要件: `hve-dev/requirement-definition.md` §5.20（FR-PROMPT-01〜10）

---

## 使い方

1. 下表から検証したいファイルを開く。
2. `GitHub Copilot に貼り付ける Prompt` の `markdown` コードブロック全体をコピーする。
3. このリポジトリを開いた HVE GUI 内の Copilot CLI タブ、standalone GitHub Copilot CLI、または
   VS Code Copilot Chat へ貼り付ける。
4. コードブロック内の指示に従い、Copilot が提示する計画・実測結果を確認する。

コードブロック内のコマンドは **Copilot が実行する統合テスト手順**です。利用者がコマンド、
request の保存先、plan SHA-256 を手入力する必要はありません。本 Prompt 集は GitHub.com の
Cloud Agent Orchestrator を対象にしません。

---

## ファイル一覧

| ファイル | 検証対象 | Azure |
|---|---|---|
| [01-request-contract.md](01-request-contract.md) | request v1 の受理 / 拒否（FR-PROMPT-02） | 不要 |
| [02-plan-and-approval-gate.md](02-plan-and-approval-gate.md) | `plan` の提示内容と `run` の SHA-256 ゲート（FR-PROMPT-03 / 04 / 05） | 不要 |
| [03-multi-workflow-order.md](03-multi-workflow-order.md) | 複数 Workflow の依存順・暗黙追加なし・fail-fast（FR-PROMPT-06） | 不要 |
| [04-input-alias.md](04-input-alias.md) | 入力別名の安全契約と単一解決器（FR-PROMPT-08 / 09） | 不要 |
| [05-gui-settings-reuse.md](05-gui-settings-reuse.md) | 保存済み GUI 設定の再利用と override allowlist（FR-PROMPT-07） | 不要 |
| [06-agent-skill-behavior.md](06-agent-skill-behavior.md) | Skill の質問・推測禁止・禁止操作と自然言語だけでの完結（FR-PROMPT-10） | 不要 |
| [07-docs-coverage.md](07-docs-coverage.md) | 全 Workflow の貼り付け用 Prompt が実際に計画できるか（FR-PROMPT-10） | 不要 |
| [08-e2e-smoke.md](08-e2e-smoke.md) | 自然言語 → request → plan → 承認 → run の一気通貫 | 不要 |
| [09-full-system-test.md](09-full-system-test.md) | 要件全件・設定組合せ・対象4 Workflow の実run・性能/Token/Azure計測 | 許可（既存承認ゲート必須） |

**本 Prompt 集は Azure へのデプロイを対象外**とします。デプロイを含む全範囲のシステムテストは
リポジトリ直下の `tests/[HVE]SystemTest - Full.txt` を使ってください。

---

## 実行順

`01` → `08` の順に単独で実行できます。依存はありません。
時間が限られる場合は **`02`（承認ゲート）→ `04`（入力別名）→ `08`（E2E）** を優先してください。
この 3 つが Prompt 版の安全性の中核です。

`09` は長時間・高コストのフルシステムテストです。`01`〜`08` とは独立して実行できますが、
安全境界を先に確認するため `02` と `08` の完了後を推奨します。最初は計画だけを提示し、
実run と Azure 書き込みは利用者の明示承認および既存の各承認ゲート後にだけ開始します。

---

## 全 Prompt 共通の前提

1. リポジトリ直下で作業する（canonical パスがリポジトリ相対のため）
2. `.venv` を作成済み（[users-guide/hve-cli-getting-started.md](../../users-guide/hve-cli-getting-started.md)）。
   各 Prompt 内の `python` は **`.venv` の Python** を指す（Windows: `.\.venv\Scripts\python.exe`、
   macOS / Linux: `./.venv/bin/python`）。システム Python では依存が揃わず失敗する。
3. GUI（`python -m hve`）を 1 回起動し、設定を `hve/.settings.txt` へ保存済み
4. `prompt plan` だけのケースは現在の作業ツリーで実施してよい。`prompt run` により成果物の書き込みを伴うケースは、**対象 revision から作った専用の隔離 worktree** でだけ実施する。共有中または未コミット差分のある作業ツリーでは実行しない。
5. 隔離 worktree は clean であることを確認する。未コミットの実装を検証したい場合は、共有作業ツリーへ一時 commit を作らず、その revision を安全に再現できる専用 checkout を準備できるまで書き込みケースを未実施とする。
6. 結果レポートは隔離 worktree の外にある run-scoped パスへ保存する。終了時は隔離 worktree の外へ移動し、`git -C <元リポジトリ> worktree remove --force <隔離パス>` で隔離 worktree 全体を破棄する。共有作業ツリーの成果物を個別削除・checkout・reset・stash しない。

## 全 Prompt 共通の禁止事項

- **捏造の禁止**: 実行していないコマンドの結果を書かない。エラーメッセージは実出力を引用する。
- **テストを通すためのプロダクトコード改変の禁止**: 期待と実装が食い違った場合は、どちらが正しいかを
  `hve-dev/requirement-definition.md` §5.20 で判定してから直す。
- **Azure への書き込み禁止**: 本 Prompt 集の範囲では `az` / Azure REST を実行しない。
- **`docs-original/` は読み取り専用**。

## 既知の未修正事項（テスト前に確認すること）

以下は Prompt 版とは無関係の既存事象です。**これを Prompt 版の不具合として報告しないでください。**

- `hve/tests/test_orchestrator_git_encoding.py::TestHveSubprocessDecodeContract` は
  `hve/branch_cleanup.py` の `encoding` 未指定により失敗する
- `hve/tests/test_dev_task_environment_contract.py::test_copilot_sdk_lock_pins_an_exact_version` は
  `hve/copilot-sdk.lock` の改行コードにより失敗する場合がある

各テスト開始時に `git status --short` を取得し、上記が現在も該当するかを実測して報告に記録してください。
