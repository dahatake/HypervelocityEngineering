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

| ファイル | 検証対象 | Azure 書き込み |
|---|---|---|
| [01-request-contract.md](01-request-contract.md) | request v1 の受理 / 拒否（FR-PROMPT-02） | 禁止 |
| [02-plan-and-approval-gate.md](02-plan-and-approval-gate.md) | `plan` の提示内容と `run` の SHA-256 ゲート（FR-PROMPT-03 / 04 / 05） | 禁止 |
| [03-multi-workflow-order.md](03-multi-workflow-order.md) | 複数 Workflow の依存順・暗黙追加なし・fail-fast（FR-PROMPT-06） | 禁止 |
| [04-input-alias.md](04-input-alias.md) | 入力別名の安全契約と単一解決器（FR-PROMPT-08 / 09） | 禁止 |
| [05-gui-settings-reuse.md](05-gui-settings-reuse.md) | 保存済み GUI 設定の再利用と override allowlist（FR-PROMPT-07） | 禁止 |
| [06-agent-skill-behavior.md](06-agent-skill-behavior.md) | Skill の質問・推測禁止・禁止操作と自然言語だけでの完結（FR-PROMPT-10） | 禁止 |
| [07-docs-coverage.md](07-docs-coverage.md) | 全 Workflow の貼り付け用 Prompt が実際に計画できるか（FR-PROMPT-10） | 禁止 |
| [08-e2e-smoke.md](08-e2e-smoke.md) | 自然言語 → request → plan → 承認 → run の一気通貫 | 禁止 |
| [09-full-system-test.md](09-full-system-test.md) | CASE-ID ごと原則60分以内・case 専用隔離 lane・ready case の必須並列 wave・中断後の case 単位 checkpoint/restart を含む、要件全件・設定組合せ・対象4 Workflow の実run・性能/Token/Azure計測 | 条件付き（Phase 0 全体承認＋Azure 書き込み case ごとの追加承認後のみ） |

**01〜08 は Azure への書き込みおよびデプロイ対象外**です。**09 のみ**、Phase 0 の実行計画全体を
承認した後、Azure 書き込みを含む各 case について本文のリソース具体値を追加承認した場合に限り、
case 専用 Azure scope への書き込みを許可します。この二段階の承認は既存の認証・権限・Azure・
デプロイ gateを代替しません。既存/共有リソースの変更・削除および自動 cleanup は許可しません。
この例外を超えるデプロイを含む全範囲の
システムテストは、リポジトリ直下の `tests/[gui]SystemTest - Full.txt` を使ってください。

---

## 実行順

`01` → `08` の順に単独で実行できます。依存はありません。
時間が限られる場合は **`02`（承認ゲート）→ `04`（入力別名）→ `08`（E2E）** を優先してください。
この 3 つが Prompt 版の安全性の中核です。

`09` は長時間・高コストのフルシステムテストです。`01`〜`08` とは独立して実行できますが、
安全境界を先に確認するため `02` と `08` の完了後を推奨します。Phase 0 で `CASE-ID`、DAG / wave、
controller 最大並列数、各 case の原則60分以内の見積、case 専用隔離 lane、停止条件と checkpoint からの
case 単位再開手順を提示し、利用者が計画全体を明示承認した後にだけ run を開始します。この checkpoint は
`09` のテスト用作業記録であり、廃止済みの HVE Resume 機能ではありません。安全に並列可能な ready case は
承認済み上限まで必ず並列 wave で実行し、競合する case は直列にします。Azure 書き込みは、さらに
Azure 書き込みを含む各 case の個別明示承認と本文の追加 gate を満たした後にだけ、case 専用 Azure scope で開始します。

---

## 全 Prompt 共通の前提

1. リポジトリ直下で作業する（canonical パスがリポジトリ相対のため）
2. `.venv` を作成済み（[users-guide/hve-cli-getting-started.md](../../users-guide/hve-cli-getting-started.md)）。
   各 Prompt 内の `python` は **`.venv` の Python** を指す（Windows: `.\.venv\Scripts\python.exe`、
   macOS / Linux: `./.venv/bin/python`）。システム Python では依存が揃わず失敗する。
3. GUI（`python -m hve`）を 1 回起動し、設定を `hve/.settings.txt` へ保存済み
4. `prompt plan` だけのケースは現在の作業ツリーで実施してよい。`prompt run` により成果物の書き込みを伴うケースは、**対象 revision から作った専用の隔離 worktree** でだけ実施する。共有中または未コミット差分のある作業ツリーでは実行しない。`09` で mutating case を並列実行する場合は、case ごとに別の専用 worktree と分離した run-scoped 出力パスを使う。
5. 隔離 worktree は clean であることを確認する。未コミットの実装を検証したい場合は、共有作業ツリーへ一時 commit を作らず、その revision を安全に再現できる専用 checkout を準備できるまで書き込みケースを未実施とする。
6. 結果レポートは隔離 worktree の外にある run-scoped パスへ保存する。終了時は隔離 worktree の外へ移動し、`git -C <元リポジトリ> worktree remove --force <隔離パス>` で隔離 worktree 全体を破棄する。共有作業ツリーの成果物を個別削除・checkout・reset・stash しない。

### 隔離 lane の再現性

- **1 計測 1 fresh lane** とする。予備実行、失敗、途中停止の後に同じ lane を正式結果へ再利用せず、対象 revision から作り直して開始前の `git status --short` が空であることを確認する。
- 保存済み `hve/.settings.txt` を隔離 lane へコピーする場合、`path-valued` 設定が元リポジトリや共有 `qa/` を指していないか確認する。書き込み先は lane 内へ正規化し、Work IQ、branch、merge など本ケースに不要な副作用設定を無効化した値と変更理由を証跡へ記録する。Prompt 版の設定解決規則自体は変更しない。
- Windows で `.venv` を隔離 lane への `junction` として作った場合、cleanup は junction 自体を先に削除してから `git worktree remove --force` を行う。junction の target である元リポジトリの `.venv` は削除しない。
- run-scoped PowerShell driver は Copilot session 起動前に `[scriptblock]::Create()` などで `parser check` を行う。`pwsh -Command` の展開可能文字列へ `python -c` を二重引用で埋め込まず、可能なら lane の `.venv` executable を直接起動する。
- 上記 driver は当該統合テストの run-scoped 証跡に留め、単発用途のために HVE runtime、CLI option、依存パッケージへ昇格させない。

## no-write case の Copilot CLI capability gate

`06-agent-skill-behavior.md` の **B / C / D** を自動計測するときは、routing の成否にかかわらず
child model へ `shell` と `write` capability を公開しない。permission deny だけでなく、Copilot CLI の
tool availability filter を安全性の主ゲートにする。

- `--available-tools` の allowlist を使う。Skill 選択だけを観測する現在の最小形は
  **`--available-tools=skill`** とし、起動時の disabled-tools 表示で PowerShell・file edit・write系toolが
  modelから非公開であることを確認する。
- `--excluded-tools` は実在する tool 名を指定するときの補助手段である。`shell` と `write` は
  `--allow-tool` / `--deny-tool` が扱う permission kind であり、availability filter の tool 名ではない。
  抽象permission名を除外指定しただけで安全になったと判定してはならない。
- `--deny-tool` は公開済みtoolのapprovalを制御するだけで、toolをmodelから隠さない。たとえば
  direct `az` のdenyは、公開された `pwsh.exe` の command文字列内にあるnested `az` を遮断しない。
- no-write caseで **`--allow-all-tools` は使用しない**。`--allow-all-paths` も使用せず、対象lane外への
  path許可を広げない。これらをdeny patternと併用してもcapability isolationの代替にはならない。
- session開始時にallowlistが拒否された、未知tool警告が出た、またはshell/write可能なtoolが1つでも
  modelへ残った場合は、その計測をbehavior結果に数えず停止する。

## 全 Prompt 共通の禁止事項

- **捏造の禁止**: 実行していないコマンドの結果を書かない。エラーメッセージは実出力を引用する。
- **テストを通すためのプロダクトコード改変の禁止**: 期待と実装が食い違った場合は、どちらが正しいかを
  `hve-dev/requirement-definition.md` §5.20 で判定してから直す。
- **Azure への書き込み境界**: `01`〜`08` では Azure への書き込みとデプロイを禁止し、`az` / Azure REST を実行しない。`09` のみ、本文の追加 gate と各 case の個別明示承認後に限り、case 専用 Azure scope への書き込みを例外として許可する。既存/共有リソースの変更・削除と自動 cleanup は禁止する。
- **`docs-original/` は読み取り専用**。

## 既知の未修正事項（テスト前に確認すること）

以下は Prompt 版とは無関係の既存事象です。**これを Prompt 版の不具合として報告しないでください。**

- 2026-08-28 時点、`hve/tests/test_orchestrator_git_encoding.py::TestHveSubprocessDecodeContract` および
  `hve/tests/test_dev_task_environment_contract.py::test_copilot_sdk_lock_pins_an_exact_version` は
  現在の `main`（`hve/branch_cleanup.py` の `encoding` 明示、`hve/copilot-sdk.lock` の LF 契約を含む）で
  いずれも `PASSED` を実測済みであり、既知の未修正事項は現時点でありません。
- ただし `hve/copilot-sdk.lock` の LF/BOM なし契約は Git blob（index / HEAD）ではなく実 worktree の
  生バイトを検査する。長期利用の Windows worktree で `core.autocrlf=true` 等により当該ファイルが
  CRLF へ再 materialize された場合、`test_copilot_sdk_lock_pins_an_exact_version` だけがローカルで
  再度失敗しうる。その場合は内容を変えずに当該ファイルを LF へ書き戻せば解消する（具体的な
  materialize 経路は未確認のため断定しない）。

各テスト開始時に `git status --short` を取得し、上記が現在も該当するかを実測して報告に記録してください。
