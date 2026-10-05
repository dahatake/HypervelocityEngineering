# HVE CLI Orchestrator ユーザーガイド

← [README](../README.md)

> **対象読者**: ローカル環境で `python -m hve cli` を使ってワークフローを実行するユーザー  
> **前提**: Python 3.11+、GitHub CLI（`gh`）、対象リポジトリのローカルクローンがあること  
> **次のステップ**: まず「クイックスタート」を実行し、必要に応じて「環境設定（ゼロからのセットアップ）」と「インタラクティブモード（推奨）」を確認してください。Cloud / Local の初期セットアップ切り分けが必要な場合は [troubleshooting.md](./troubleshooting.md#初期セットアップで詰まったとき) も参照してください

---

## 目次

- [はじめに](#はじめに)
- [クイックスタート](#クイックスタート)
- [中断と再開（Resume）](#中断と再開resume)
- [必須 / 任意ツール早見表](#必須--任意ツール早見表)
- [セットアップスクリプトを使った環境構築](#セットアップスクリプトを使った環境構築windows--macos--linux)
- [環境設定（ゼロからのセットアップ）](#環境設定ゼロからのセットアップ)
- [インタラクティブモード（推奨）](#インタラクティブモード推奨)
- [HVE GUI Orchestrator モード（PySide6）](#hve-gui-orchestrator-モードpyside6)（→ 詳細は [hve-gui-orchestrator-guide.md](./hve-gui-orchestrator-guide.md)）
- [コマンドリファレンス（CLI モード）](#コマンドリファレンスcli-モード)
- [ワークフロー一覧](#ワークフロー一覧)
- [付録A: MCP Server 設定ガイド](#付録a-mcp-server-設定ガイド)
- [付録B: Prompt 設定ガイド](#付録b-prompt-設定ガイド)
- [付録C: DAG 並列実行と Post-step 自動プロンプト](#付録c-dag-並列実行と-post-step-自動プロンプト)
- [フォーク機能 Fork-on-Retry](#フォーク機能-fork-on-retry)
- [付録D: トラブルシューティング](#付録d-トラブルシューティング)
- [付録E: セキュリティ・SSO・関連リンク](#付録e-セキュリティsso関連リンク)
- [付録G: HVE を拡張する（開発者向け）](#付録g-hve-を拡張する開発者向け)

---

## はじめに

### このガイドの目的

このガイドは、このリポジトリの `hve/` パッケージを使って、**ローカル PC 上で完結して**ワークフローを実行するための手順を解説します。実行には PyPI パッケージ `github-copilot-sdk`（`pip install github-copilot-sdk`）が依存ライブラリとして必要です。

> **注意**: `hve/` はこのリポジトリに含まれるローカルパッケージです。`python -m hve cli` はリポジトリルートをカレントディレクトリとして実行してください。引数なしの `python -m hve` は GUI を起動します（PySide6 未導入時は CLI に自動フォールバック）。

セットアップ後の通常起動は、Windows では `hve.cmd`、macOS / Linux では `./hve.sh` を使うと、常にリポジトリの `.venv` が選ばれます。`python -m hve` と `hve` console script も利用できますが、古い global install の影響を避けるには同梱ランチャーが確実です。

本ガイドは **HVE CLI Orchestrator（ローカル実行方式）** に特化しています。Web UI 方式との比較や全体の利用ガイドについては [README.md](../README.md#方式比較表4-つの使い方) を参照してください。

### ポイント

- **GitHub Actions 不要** — `python -m hve cli` で対話型 wizard が起動し、ガイド付きで実行可能
- **2つの実行モード** — インタラクティブモード（初回推奨）と CLI モード（`orchestrate` サブコマンド、スクリプト/CI 向け）を用意
- **COPILOT_PAT 不要** — ローカルで直接 Agent を実行するため、Copilot アサイン用 PAT は不要
- **通常 run に GitHub 書込み token・remote 検査は不要** — GitHub 書込みを要求する実行だけが startup preflight の対象（[詳細](#github-書込み-startup-preflightfr-cli-3182)）
- **Copilot ライセンスは必要** — Copilot SDK を利用するため、GitHub Copilot ライセンスが前提
- MCP Server・Prompt・asyncio による並列実行など、高度な機能を利用可能

### 必須 / 任意ツール早見表

初回セットアップ時に「何を入れるか」を最初に判断できるよう、`hve` ローカル実行向けに整理すると次のとおりです。

| ツール | 必須 / 任意 | 用途 |
|---|---|---|
| Python 3.11+ | 必須 | `hve` 実行 |
| Git | 必須 | リポジトリ取得 |
| GitHub CLI（`gh`） | 必須 | `gh auth login` / `gh auth status` による GitHub 認証 |
| GitHub Copilot ライセンス | 必須 | Copilot SDK / Copilot 利用 |
| GitHub Copilot SDK（`github-copilot-sdk`） | 必須 | `hve` の中核ライブラリ |
| Node.js / npm / npx | 任意 | npx ベースの MCP Server / 外部 Skills を利用する場合 |
| Work IQ Plugin または MCP Server | 任意 | M365 補助情報を参照する場合。利用者が Copilot CLI 側へ事前設定 |
| Azure CLI | 任意 | Azure リソース確認や Azure 関連作業をローカルで行う場合 |
| 外部 `copilot` CLI | 任意 | SDK 同梱ではなく外部 CLI を明示利用する場合 |

### 対象読者

- **初めてのユーザー**: まず `python -m hve cli` でインタラクティブモードを試すことを推奨します。オプションの知識がなくても wizard が順番にガイドします
- **開発者**: ローカル PC 上でワークフローを完結させたい方
- **アーキテクト**: MCP Server や Prompt を活用した高度なオーケストレーションを構築したい方
- **前提知識**: Python の基本的なスクリプト実行ができる方、`gh auth login` などの GitHub CLI 操作ができる方

---

## クイックスタート

3 ステップで実行を開始できます。

```bash
# 1. 依存パッケージをインストール
pip install github-copilot-sdk

# 2. GitHub CLI で認証（初回のみ）
gh auth login

# 3. GitHub Copilot SDK で認証（初回のみ）
python -m hve login

# 4. インタラクティブモードで実行
python -m hve cli
```

wizard が起動し、ワークフロー選択・オプション設定・実行確認を対話的にガイドします。
詳しい環境構築手順は以下の「環境設定（ゼロからのセットアップ）」セクション、wizard の詳細は「インタラクティブモード（推奨）」セクションを参照してください。

### リポジトリをローカルパッケージとしてインストールして使う

リポジトリルートで次を実行すると、`hve/` を editable install として利用できます。

```bash
python3 -m pip install -e .
```

インストール後は、以下のどちらでも起動できます。

```bash
python3 -m hve <subcommand>
hve <subcommand>
```

editable install でも distribution metadata の version は install 時点の値です。`git pull`、branch 切り替え、別 checkout への移動で `pyproject.toml` の version だけが進んだ場合、metadata は自動更新されません。HVE の起動時チェックは remote を参照せず、現在の checkout の `[project].version` とインストール済み metadata の差だけを判定します。

workflow で利用している実行例:

```bash
python3 -m hve emit-prompt pre-qa --comment-body
```

> 上記コマンドが動かない場合は、以下の「[環境設定（ゼロからのセットアップ）](#環境設定ゼロからのセットアップ)」を参照してください。

### Workbench 画面操作（主要キー）

`hve` 実行中の Workbench では、以下のキーで各ペインを操作できます。

| 対象 | 操作 |
|---|---|
| ログ | `↑` / `↓`、`PageUp` / `PageDown`、`g`（先頭）/ `G`（末尾） |
| 実行中の課題 | `[`（過去）/ `]`（最新） |
| セッションツリー | `{`（過去）/ `}`（最新）、`<`（先頭）/ `>`（末尾）、**マウスホイール** |
| 入力エリア | `:` でコマンド入力開始、`Esc` でキャンセル、`Enter` で送信 |

画面ラベルは次の名称です。

- `ログ`
- `セッションツリー`
- `実行中の課題`
- `入力エリア`
- `[統計情報]`（フッター）

---

## HVE GUI Orchestrator モード（PySide6）

ターミナル UI の代わりに、スクロール・コピーが快適な **GUI ウィンドウ** で Orchestrator を操作したい場合は、専用ガイド [hve-gui-orchestrator-guide.md](./hve-gui-orchestrator-guide.md) を参照してください。GUI Orchestrator は本ガイドと同じ `hve orchestrate` エンジン・同じ DAG 定義を共有しており、Workflow ID／オプション仕様／Work IQ／MCP Server 認証等の **詳細仕様は本 CLI ガイドが正典** です。

---

## 中断と再開（Resume）

`python -m hve resume` は、SQLite に確定済みの制御状態を使って、現在のリポジトリで中断した **標準ローカル実行**を再開するサブコマンドです。対象は durable state に登録された `run` / `cli` / `orchestrate` 実行です。`dry-run`、Fleet、Cloud Session、Autopilot、GitHub Cloud Agent の実行は対象外です。

### 基本構文と候補選択

```bash
# TTY で候補を選択
python -m hve resume

# execution ID を完全一致で指定
python -m hve resume <EXECUTION_ID> --action restart-step

# 現在のリポジトリで最後に更新された候補を指定
python -m hve resume --latest --action reuse-session
```

`<EXECUTION_ID>` と `--latest` は同時に指定できません。候補は現在のリポジトリに属し、未完了の workflow instance を持つ実行だけに限定されます。

| 状況 | 動作 |
|---|---|
| 候補なし | 非ゼロ終了し、子 workflow を開始しない |
| 候補が 1 件 | その候補を選択し、resume plan に execution ID を表示する |
| 候補が複数・TTY | 番号付きメニューから選択する |
| 候補が複数・非 TTY | 暗黙選択せず停止する。`<EXECUTION_ID>` または `--latest` が必要 |

TTY では、必要に応じて候補・復旧方法・再入力値を対話選択し、最後に resume plan の実行確認を行います。非 TTY では入力を求めず、候補が曖昧、再入力が必要、または risk があるのに `--action` が未指定の場合は fail-closed で停止します。

### Risk と復旧方法

resume plan には `risk` が表示されます。代表例は、前回状態が `failed` / `running` / `suspended` / `blocked`、リポジトリの HEAD 変更、成功済み Step の宣言出力欠落、有効な lease owner、または再利用可能な SDK session の欠落です。risk がない場合の既定 action は `restart-step` です。risk がある非 TTY 実行では、次のいずれかを明示してください。

| Action | 動作 |
|---|---|
| `--action reuse-session` | 対象 Step に保存された Main SDK session を再利用し、復旧用 prompt から継続する。session ID がない、または session が使用中の場合は停止し、`restart-step` へ暗黙 fallback しない |
| `--action restart-step` | 保存済み SDK session を使わず、対象 Step を新しい session で先頭から再実行する |

`--action` は安全性検査の回避フラグではありません。対象外 mode、有効な別 owner、破損した状態、または stale な状態は、どちらの action でも開始できません。

### 再入力、成果物再照合、承認

- 自由記述値、任意 path、endpoint、credential、tool / MCP payload などは durable state に値を保存しません。再開に必要な場合は key 名だけを表示し、TTY で値を再入力します。非 TTY の public CLI では停止するため、対話可能な端末から再開してください。
- 再入力した平文は durable state と resume plan 表示へ保存・出力されません。plan の SHA-256 には平文ではなく値の digest が反映されます。
- 成功済み Step も、宣言された必須出力の**存在**を再照合します。出力が欠けている Step と、それに依存する後続 Step は再実行対象へ戻ります。内容の意味的な正しさまでは検証しません。
- CLI は execution / workflow / instance、state version、action、risk、未入力 key、resume SHA-256 を plan として表示します。TTY で承認した後に同じ入力から plan を再計算し、SHA-256 が変化していれば開始せず、再提示を要求します。
- workflow 開始時は plan の state version を使った CAS と fenced lease を取得します。別プロセスによる状態更新、同時 resume、または有効な owner を検出した場合は stale として停止します。

### 複数 workflow の順序と保証範囲

1 つの execution に複数 workflow が登録されている場合、登録時の順序で最初の未完了 instance から直列再開します。各 child が終了コード `0` を返しただけでなく、durable state が `succeeded` へ遷移したことを確認してから次へ進みます。

次の instance では現在の HEAD と状態から新しい plan を作り直します。このplanは別の承認対象です。TTYでは再提示後にもう一度確認し、承認直後にhashを再計算してから個別にCAS/leaseを取得します。GUI/Promptなどが`--expected-resume-hash`を渡した場合、そのhashで実行できるのは最初の承認済みplanだけです。HVEは次のplanとhashを表示して停止するため、controllerは利用者へ再提示して別の明示承認を得る必要があります。先行planのhashを後続planへ流用しません。先行planへ再入力した平文値もinstance完了時に破棄し、後続で同じkeyが必要なら改めて入力・承認します。最初の失敗で停止し、未承認の後続workflowは開始しません。

output再照合の結果、選択済みStepがすべて成功済みで必須outputも存在する場合、実行対象は0件です。この場合はsubcommandなしchildを起動せず、取得済みfenced leaseの下でoutputを再確認してinstanceを`succeeded`へ確定し、同じordered規則で次へ進みます。

Resume が保証するのは、HVE が SQLite へ commit 済みの **workflow / Step 制御状態、順序、state version、lease/fencing** に基づく再開です。次は保証しません。

- 停止した Python process、生成途中のモデル応答、実行途中の tool / shell command をその位置から復元すること
- Azure、GitHub、M365、ファイル書き込み等の外部副作用を rollback または exactly-once にすること
- 存在する成果物の内容が完全・最新・意味的に正しいこと

状態 DB の破損・未対応 schema、未知または別リポジトリの execution ID、不正な保存 plan / workflow 順序、対象外 mode、未解決の再入力、stale plan/hash/CAS、lease 競合を検出した場合は、推測や暗黙 fallback を行わず fail-closed で停止します。

cold resume では caller と route の除外を `disabled_mcp_servers` で起動前に渡すため、除外サーバーを起動しません。ただし resident session の既に起動済みのプロセスを取り消すことはできません。再開後も新規 session と同じ送信前の runtime gate を通します。

SDK 1.0.11 の `disabled_skills=[]` は `disabledSkills` の wire payload では省略されます。空リスト指定だけでは保存済み Skill 除外の解除を保証できません。required Skill は runtime で確認し、不成立なら最初の送信前に fail-closed で停止します。

### Legacy `orchestrate --resume-run` との違い

`python -m hve orchestrate --workflow <WORKFLOW_ID> --resume-run <RUN_ID>` は後方互換用の legacy 機能です。同じ run ID と workflow ID の進捗記録から成功済み Step を除外し、残りを新しい session で実行します。記録がない run ID は停止します。

これは `hve resume` の alias ではなく、durable candidate 選択、output 再照合、plan SHA-256、state-version CAS、fenced lease、SDK session 再利用、再入力処理を提供しません。legacy の `<RUN_ID>` と durable resume の `<EXECUTION_ID>` は別の識別子であり、自動変換・自動 import も行いません。相互に取り違えないでください。

---

## セットアップスクリプトを使った環境構築（Windows / macOS / Linux）

HVE の基本実行環境は、`hve/` 直下のセットアップスクリプトで構築できます。どちらのスクリプトも、OS しか入っていない PC から CLI / GUI を動かせる状態までを一括で整えます。

- **OS ツールの自動導入**（未導入時のみ、`-NoInstallTools` / `--no-install-tools` で抑止）: Python 3.11+、Python の `venv` / `ensurepip` モジュール、Git、GitHub CLI（`gh`）、Node.js（`npm` / `npx`）、Azure CLI（`az`）、ShellCheck、外部 GitHub Copilot CLI（`npm install -g @github/copilot@latest`。GUI の Copilot チャットパネルで使用し、導入済みの場合も毎回最新版へ更新します。npm グローバル管理下でない `copilot` を検出した場合は二重導入を避けるため更新せずに警告します）。Windows は winget、macOS は Homebrew、Linux は apt / dnf / pacman を使います。Linux では GUI に必須の Qt / QtWebEngine system lib も検出して導入を試みます（apt のみ）。
- **Python 依存の導入**: `.venv` 作成、`github-copilot-sdk`（既定で最新版へ更新。`-PinSdk` / `--pin-sdk` を付けると `hve/copilot-sdk.lock` の固定版を導入）、repository 検証用 `[test]`（pytest）、`markdown-query` 用任意依存（`[mdq-watch,mdq-ja,semantic]` = `rank_bm25` + `tiktoken` + `watchdog` + `fastembed` + `nltk` + `numpy`）、GUI 用任意依存（`[gui,gui-pty,gui-docconvert]` = `PySide6` + `pywinpty`/`ptyprocess` + `markitdown`）、`code-query` 用任意依存（`[code]` = tree-sitter 文法 + `sqlglot`。失敗しても警告のみで継続し、regex 解析へ降格）。
- **動作確認**: `python -m hve --help` / `python -m mdq --help` / `python -m cq --help` の実行確認。

`--no-gui` 指定で GUI 系を、`--minimal` 指定で全 extras（pytestを含む）をスキップできます。各ツールの導入前に確認プロンプトが出ます。無人実行したい場合は `-Yes` / `-y` を付けてください。

### Windows 初心者向け（`.cmd` ダブルクリック）

`hve` を初めて使う Windows ユーザーは、エクスプローラーから **`hve\setup-hve.cmd`** をダブルクリックするだけでセットアップを完了できます。PowerShell の実行ポリシー設定は不要です。

`.cmd` は **`.ps1` を呼んでフラグを verbatim 転送する薄ラッパ**で、`.ps1` と同じオプションを全てサポートします（v0.1.x 以降）。

| 引数 | 動作 |
|---|---|
| なし（既定） | 不足している OS ツール（Python / venv / Git / gh / Node.js / Azure CLI / ShellCheck / Copilot CLI）を winget ・npm で導入 + venv 作成 + `github-copilot-sdk` + 全 extras（`test` / `mdq-watch` / `mdq-ja` / `semantic` / `gui` / `gui-pty` / `gui-docconvert` / `code`）を導入 |
| `-CheckOnly` | 環境状態のみ表示（変更なし。通常 GUI 構成では `gh` / PTY backend の不足も警告として報告） |
| `-NoGui` | GUI 関連 extras（gui / gui-pty / gui-docconvert）をスキップ（CLI 専用） |
| `-Minimal` | runtime base のみインストール（extras / pytest なし） |
| `-Force` | 既存 `.venv` を削除して再作成 |
| `-SkipNltkDownload` | `nltk punkt_tab` の事前 DL をスキップ |
| `-WithSkills` | `microsoft/skills` を npx で `.github/skills/azure-skills/` に導入（Node.js 20+ 必須） |
| `-Yes` | 確認プロンプトをすべてスキップ（無人実行向け） |
| `-NoInstallPython` | Python の自動導入を行わない |
| `-NoInstallTools` | Git / gh / Node.js / Azure CLI / ShellCheck / Copilot CLI の自動導入を行わない（検出と手動導入手順の案内のみ） |
| `-Help` | 使い方表示 |

### PowerShell 7+

リポジトリルートで実行します。

```powershell
pwsh -NoProfile -File hve/setup-hve.ps1
```

状態確認だけを行う場合:

```powershell
pwsh -NoProfile -File hve/setup-hve.ps1 -CheckOnly
```

### macOS

リポジトリルートで実行します。

```bash
chmod +x hve/setup-hve.sh
./hve/setup-hve.sh
```

状態確認だけを行う場合:

```bash
./hve/setup-hve.sh --check-only
```

### Linux

`hve/setup-hve.sh` は Bash が使える Linux 環境でも利用できます（Ubuntu/Debian など）。

```bash
chmod +x hve/setup-hve.sh
./hve/setup-hve.sh
```

状態確認だけを行う場合:

```bash
./hve/setup-hve.sh --check-only
```

### オプション

| 機能 | Windows | macOS / Linux | 既定 | 説明 |
|---|---|---|---|---|
| 検出のみ | `-CheckOnly` | `--check-only` | false | インストールや `.venv` 変更を行わず状態だけ確認 |
| GUI スキップ | `-NoGui` | `--no-gui` | false | GUI 関連 extras（gui / gui-pty / gui-docconvert）を除外し CLI 専用とする |
| 最小構成 | `-Minimal` | `--minimal` | false | base のみインストール（extras 全スキップ）。検証・開発用 |
| venv 再作成 | `-Force` | `--force` | false | 既存 `.venv` を削除して作り直す |
| nltk DL スキップ | `-SkipNltkDownload` | `--skip-nltk-download` | false | `nltk punkt_tab` の事前 DL をスキップ（オフライン環境向け） |
| 外部 Skills | `-WithSkills` | `--with-skills` | false | `microsoft/skills` を npx で `.github/skills/azure-skills/` に導入（Node.js 20+ 必須） |
| SDK 版の固定 | `-PinSdk` | `--pin-sdk` | false | `github-copilot-sdk` を `hve/copilot-sdk.lock` の固定版で導入する（既定は最新版へ追従） |
| SDK 版の引き上げ | `-UpgradeSdk` | `--upgrade-sdk` | false | 最新化に加えて `hve/copilot-sdk.lock` を書き換える（差分をレビューしてコミットする） |
| 確認省略 | `-Yes` | `-y` / `--yes` | false | 全確認プロンプトをスキップする（無人実行向け） |
| Python 自動導入を抑止 | `-NoInstallPython` | `--no-install-python` | false | Python 3.11+ が無い場合も自動導入しない |
| OS ツール自動導入を抑止 | `-NoInstallTools` | `--no-install-tools` | false | Git / gh / Node.js / Azure CLI / ShellCheck / Copilot CLI / Qt system lib の自動導入を行わない（検出と手動導入手順の案内のみ） |

> **旧フラグは廃止されました** (v0.1.x): `--with-gui` / `-WithGui` (既定 ON のため不要) / `--with-workiq` / `-WithWorkIQ` / `--install-external-copilot-cli` / `-InstallExternalCopilotCli` / `--force-recreate-venv` / `-ForceRecreateVenv` / `--skip-mdq` / `-SkipMdq` / `--skip-mdq-watch` / `-SkipMdqWatch`。外部 Copilot CLI は既定で自動導入されます（`-NoInstallTools` で抑止）。Work IQ は利用者が Copilot CLI 側へ Plugin または MCP Server として事前設定してください。

### 再実行時の挙動

- setup は初回専用ではなく、checkout 更新後の構成整合にも使用します。
- `.venv` が存在し、Python 3.11+ で作成されている場合は再利用します。
- `.venv` が Python 3.11 未満で作成されている場合、通常モードでは自動再作成します。`-CheckOnly` / `--check-only` 下では警告のみにダウングレードし、`-Force` / `--force` を明示すると無条件で削除して作り直します。
- `github-copilot-sdk` は再実行時も `python -m pip install --upgrade --no-deps github-copilot-sdk` で更新確認します。
- `-CheckOnly` / `--check-only` は環境を変更せず、不足している項目を警告として表示します。通常 GUI 構成（`-NoGui` / `--no-gui` / `-Minimal` / `--minimal` なし）では、`gh` を解決できない場合と、既存 `.venv` で PTY backend を利用できない場合も警告に含みます（非ゼロ終了はしません）。通常実行ではこれらは非ゼロ終了になる点が異なります。

HVE 起動時にインストール済み版が checkout 版より古い、または metadata を確認できず、標準入力が TTY の場合は `[y/N]` で setup 実行を確認します。`y` / `yes` の場合だけ既存 setup を通常モードで起動し、`n` / `no` / Enter では更新せず元の起動を継続します。setup 固有の確認を一括承認する `-Yes` / `--yes` は自動付与しません。非 TTY では自動 setup を行わず、版情報を警告して継続します。setup 成功後は metadata と checkout 版の完全一致を再確認し、一致した場合だけリポジトリの `.venv` Python で元の引数を 1 回再起動します。

インストール済み版の方が checkout 版より新しい場合、HVE は自動 downgrade せず、両方の版を警告して現在の起動を継続します。古い branch / tag へ意図的に切り替えた場合も同じです。

### 認証と任意機能

- スクリプトは Python 3.11+ の確認、`python3` / `python` / `py -3.x` の判定、Git / GitHub CLI の確認、`.venv` 作成、`pip` / `setuptools` / `wheel` 更新、`github-copilot-sdk` 導入、`nltk punkt_tab` 事前 DL、Mermaid/KaTeX アセット DL、GUI 翻訳 `.qm` コンパイル、17 項目の verify、`gh auth status` 確認までを自動化します。
- スクリプトはトークンやシークレットを作成・保存しません。GitHub 認証は `gh auth login` を実行してください。
- 基本実行では外部 `copilot` コマンドは不要です。`COPILOT_CLI_PATH` や `--cli-path` で外部 CLI を明示指定したい場合だけ、OS 標準のパッケージマネージャ（winget / brew / apt-get / dnf）から個別に導入してください。
- Node.js / npm / npx は任意です。npx ベース MCP または `-WithSkills` / `--with-skills` を使う場合のみ必要です。Work IQ のために HVE が Node.js を要求することはありません。
- HVE は Work IQ の設定・認証を実行しません。利用する Plugin または MCP Server の導入・有効化・認証・管理者同意は、利用者が同じ Copilot CLI 側で完了してください。
- `--resource-group` を指定する実行では、本処理前に `az account show` 相当の確認を行います。未ログイン時、対話可能な端末では `az login` 実行確認を表示し、非対話環境では停止します。
- `markdown-query` Skill 用の任意依存（`mdq-watch` extras = `rank_bm25` + `tiktoken` + `watchdog`、および `semantic` extras = `fastembed` + `nltk` + `numpy`）は既定で導入されます。インストールに失敗した場合でもスクリプトは警告のみで継続し、Skill は内蔵 MiniBM25 / `heading_recursive` フォールバックで動作します。`-Minimal` / `--minimal` を指定すると base のみとなり、これら extras は導入されません。詳細は [付録F. Markdown 横断クエリ（markdown-query Skill）](#付録f-markdown-横断クエリmarkdown-query-skill) を参照。

---

## 環境設定（ゼロからのセットアップ）

> **重要**: 以下の手順は、各ツールが一切インストールされていない PC を前提としています。
> 各ツールのバージョンやインストール手順は変更される可能性があります。**必ず各公式ドキュメントを最初に確認してください。**
> 以下のコマンド例は 2026年4月時点のものです。

### 前提条件

| ソフトウェア | 必須 / オプション | 説明 |
|-------------|-----------------|------|
| GitHub アカウント | **必須** | Copilot ライセンス付き |
| GitHub CLI（`gh`） | **必須** | 認証管理に使用 |
| Git | **必須** | リポジトリのクローンに使用 |
| Python 3.11+ | **必須** | `github-copilot-sdk` と hve の実行環境 |
| Copilot CLI（外部 `copilot` コマンド） | オプション | SDK 同梱ではなく `COPILOT_CLI_PATH` 等で外部 CLI を明示利用する場合 |
| Node.js（npm/npx） | オプション | npx ベースの MCP Server / npm 方式の外部 Copilot CLI を使用する場合 |

> **Windows ユーザーへ**: 以下の手順では **PowerShell** の使用を推奨します。コマンドプロンプトでの代替コマンドは各ステップの注記を参照してください。

---

### Step 0: GitHub アカウントと Copilot ライセンスの確認

GitHub アカウントをお持ちでない場合:

```
https://github.com/signup
```

Copilot ライセンスの確認（ブラウザでアクセス）:

```
https://github.com/settings/copilot
```

> Copilot Business / Enterprise / Individual のいずれかのサブスクリプションが有効である必要があります。

---

### Step 1: Git のインストール

📖 **公式ドキュメント**: https://git-scm.com/book/ja/v2/使い始める-Gitのインストール

> 最新のインストール手順は上記公式サイトを参照してください。

#### Windows の場合

公式サイトからインストーラーをダウンロードして実行してください:

```
https://git-scm.com/download/win
```

> インストーラーの設定画面では、特に **「Adjusting your PATH environment」** で「**Git from the command line and also from 3rd-party software**」（デフォルト）が選択されていることを確認してください。

インストール確認（**ターミナルを再起動してから実行**）:

```
git --version
```

#### macOS の場合

Xcode Command Line Tools 経由でインストールします:

```
xcode-select --install
```

> ポップアップダイアログが表示されたら「インストール」をクリックし、完了を待ちます。

インストール確認:

```
git --version
```

#### Linux (Ubuntu/Debian) の場合

パッケージ一覧を更新:

```
sudo apt update
```

Git をインストール:

```
sudo apt install git -y
```

インストール確認:

```
git --version
```

---

### Step 2: Python のインストール

📖 **公式ドキュメント**: https://www.python.org/downloads/

> 最新のインストール手順は上記公式サイトを参照してください。

#### Windows の場合

公式サイトからインストーラーをダウンロードして実行してください:

```
https://www.python.org/downloads/
```

> ⚠️ **重要**: インストーラーの**最初の画面**で **「Add python.exe to PATH」にチェックを入れてください**。チェックを忘れると、以降の全コマンドが動作しません。

インストール確認（**ターミナルを再起動してから実行**）:

```
python --version
```

#### macOS の場合

Homebrew が未導入の場合は、先に Step 2a を実施してください。

Homebrew でインストール:

```
brew install python
```

インストール確認:

```
python3 --version
```

> macOS では `python3` コマンドを使用してください。以降の手順で `python` と記載されている箇所は `python3` に読み替えてください。

#### Step 2a: Homebrew のインストール（macOS で未導入の場合）

📖 **公式ドキュメント**: https://brew.sh/ja/

> ⚠️ 以下のコマンドは 2026年4月時点のものです。最新のインストール手順は上記公式サイトを参照してください。

Homebrew をインストール:

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

> ターミナルに表示される指示に従い、PATH を設定してください（表示されるコマンドをコピー＆実行します）。

インストール確認:

```
brew --version
```

#### Linux (Ubuntu/Debian) の場合

パッケージ一覧を更新:

```
sudo apt update
```

Python をインストール:

```
sudo apt install python3 python3-pip python3-venv -y
```

インストール確認:

```
python3 --version
```

> Linux では `python3` コマンドを使用してください。以降の手順で `python` と記載されている箇所は `python3` に読み替えてください。

---

### Step 3: GitHub CLI（gh）のインストール

📖 **公式ドキュメント**: https://cli.github.com/

> 最新のインストール手順は上記公式サイトを参照してください。

#### Windows の場合

winget でインストール:

```
winget install --id GitHub.cli
```

> `winget` が使えない場合は、公式サイト（ https://cli.github.com/ ）からインストーラーを直接ダウンロードしてください。

**ターミナルを再起動してから**、インストール確認:

```
gh --version
```

#### macOS の場合

Homebrew でインストール:

```
brew install gh
```

インストール確認:

```
gh --version
```

#### Linux (Ubuntu/Debian) の場合

📖 **Linux 向け詳細手順**: https://github.com/cli/cli/blob/trunk/docs/install_linux.md

> ⚠️ 以下のコマンドは 2026年4月時点のものです。最新手順は上記リンクを参照してください。

GitHub CLI のリポジトリキーを登録:

```
(type -p wget >/dev/null || (sudo apt update && sudo apt-get install wget -y))   && sudo mkdir -p -m 755 /etc/apt/keyrings   && out=$(mktemp)   && wget -nv -O$out https://cli.github.com/packages/githubcli-archive-keyring.gpg   && cat $out | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null   && sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg   && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main"   | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
```

> ⚠️ 上記は公式の登録手順をそのまま転記しています。セキュリティ上の懸念がある場合は公式ドキュメントで最新手順を確認してください。

パッケージ一覧を更新:

```
sudo apt update
```

GitHub CLI をインストール:

```
sudo apt install gh -y
```

インストール確認:

```
gh --version
```

---

### Step 4: 外部 Copilot CLI のインストール（オプション）

📖 **公式ドキュメント**: https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli

> 最新のインストール手順は上記公式サイトを参照してください。
> 上記の URL が無効な場合は、GitHub Docs（ https://docs.github.com ）で「Copilot CLI install」を検索してください。

> **前提条件**: GitHub Copilot のサブスクリプションが有効なアカウントが必要です（Step 0 参照）。

通常の hve 実行では、`github-copilot-sdk` と一緒に利用される SDK 側の CLI 実行経路を使います。外部の `copilot` コマンドを別途インストールする必要があるのは、`COPILOT_CLI_PATH` や `--cli-path` で外部 CLI を明示指定したい場合のみです。

外部 CLI を利用する場合は、公式ドキュメントの手順に従って Copilot CLI をインストールしてください。

インストール確認:

```
copilot --version
```

---

### Step 5: Node.js のインストール（オプション — npx ベース MCP Server 使用時）

📖 **公式ドキュメント**: https://nodejs.org/ja

> 最新のインストール手順は上記公式サイトを参照してください。npx ベースの MCP Server、npm 方式の外部 Copilot CLI、外部 Skills を使用しない場合はこの Step をスキップできます。

#### Windows の場合

公式サイトの **LTS 版** をダウンロードして実行してください:

```
https://nodejs.org/ja
```

インストール確認:

```
node --version
```

npm の確認:

```
npm --version
```

#### macOS の場合

Homebrew でインストール:

```
brew install node
```

インストール確認:

```
node --version
```

#### Linux (Ubuntu/Debian) の場合

📖 **NodeSource 公式**: https://github.com/nodesource/distributions

> ⚠️ 以下のコマンドは 2026年4月時点のものです。最新手順は上記リンクを参照してください。

NodeSource リポジトリを追加:

```
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
```

> ⚠️ このコマンドはリモートスクリプトを root 権限で実行します。セキュリティに懸念がある場合は、公式リポジトリの手順を直接確認するか、`nvm`（ https://github.com/nvm-sh/nvm ）の利用を検討してください。

Node.js をインストール:

```
sudo apt install nodejs -y
```

インストール確認:

```
node --version
```

---

### Step 6: リポジトリのクローンと Python 環境セットアップ

📖 **github-copilot-sdk（PyPI）**: https://pypi.org/project/github-copilot-sdk/

> パッケージの最新バージョンや詳細は上記 PyPI ページを参照してください。現行の `github-copilot-sdk` は Python 3.11+ を要求します。

> **プレースホルダー**: 以下の `OWNER/REPOSITORY` は、そのまま実行せず、このガイドを含む配布元または利用する GitHub リポジトリの `owner/repository` に置き換えてください。`REPOSITORY` はリポジトリ名に置き換えます。

リポジトリをクローン:

```
git clone https://github.com/OWNER/REPOSITORY.git
```

ディレクトリに移動:

```
cd REPOSITORY
```

Python 仮想環境を作成:

```
python -m venv .venv
```

> macOS / Linux では `python3 -m venv .venv` を使用してください。

仮想環境を有効化:

**macOS / Linux:**

```
source .venv/bin/activate
```

**Windows PowerShell:**

```
.venv\Scripts\Activate.ps1
```

> **Windows コマンドプロンプト**: `.venv\Scripts\activate.bat` を使用してください。

pip をアップグレード:

```
pip install --upgrade pip
```

依存パッケージをインストール:

```
pip install github-copilot-sdk
```

インストール確認:

```
python -m hve --help
```

> **ヒント**: `python -m hve`（引数なし）を実行するとインタラクティブモードが起動します。`--help` で全オプションを確認できます。

> 作業終了時は `deactivate` で仮想環境を終了してください。

### Step 7: 認証設定

📖 **公式ドキュメント**: https://cli.github.com/manual/gh_auth_login

> 最新の認証手順は上記公式サイトを参照してください。

#### HVE CLI Orchestrator の認証ポリシー（先に確認）

- GitHub へ書き込まない通常 run では、startup preflight による `GH_TOKEN` / `GITHUB_TOKEN`、`origin`、remote branch の検査を行いません。`gh auth login`、GitHub Copilot 認証、利用する MCP / Azure 等の認証はそれぞれ別に扱います。
- Copilot SDK 実行前に `hve orchestrate` / `hve cli` が GitHub Copilot 認証状態を確認します。未ログインの場合、対話可能な端末では `copilot login` 実行確認を表示し、非対話環境では停止します。事前に `python -m hve login` を実行しておくと操作回数を減らせます。
- GitHub 書込み startup preflight の対象では、`GH_TOKEN`（未設定時は `GITHUB_TOKEN`）と `REPO`（または `--repo`）が必要です。
- `GH_TOKEN` / `GITHUB_TOKEN` は HVE CLI Orchestrator が GitHub へ書き込むためのトークンです。
- `COPILOT_PAT` は HVE Cloud Agent Orchestrator で Copilot 自動アサインに使うシークレットであり、HVE CLI Orchestrator の Issue / PR 作成用途ではありません
- `python -m hve` 実行には GitHub Copilot SDK と Copilot ライセンスが必要です

#### GitHub 書込み startup preflight（FR-CLI-31/82）

startup preflight は、次の GitHub 書込み対象だけに適用されます。

| 対象 | 適用範囲 |
|---|---|
| `--create-issues` または `--create-pr` | 全 Workflow |
| ADFDV で `--enable-auto-merge` | Workflow 全体 |
| ASDW-WEB で `--enable-auto-merge` | active step に `requires_remote_cicd=True` の Step が含まれる場合 |

対象 run では、`repo` が非空の `owner/repo` 形式であること、`GH_TOKEN` または `GITHUB_TOKEN` が存在すること、`--branch` が有効な Git branch 名であること、Git remote `origin` が設定されていること、`origin` に完全一致する `refs/heads/<branch>` が実在することを検査します。remote branch は非対話の `git ls-remote --exit-code --heads origin refs/heads/<branch>` で読み取り専用確認し、status `2` は「一致する ref が存在しない」、その他の非 0 は認証・通信等により「検証不能」として区別します。

- 不整合は判定可能な全件を一括表示して fail-closed で停止します。`main`、同名のローカル branch、GitHub の既定 branch へ暗黙に補正しません。
- `--dry-run` でも対象条件なら同じ検査を行い、失敗時は計画表示より前に停止します。通常 run で上表の条件に該当しなければ、GitHub token・`origin`・remote branch は検査しません。
- CLI wizard は選択 Step の確定後、GitHub Copilot 認証より前に remote まで検査します。非対話 CLI は先にローカル設定を検査し、`run_workflow` が active step を解決した直後に remote を検査します。いずれも最初の Agent session、モデル呼び出し、branch 作成、DAG 実行より前です。
- 追加 Prompt などの自由記述欄は内容検査の対象外です。token の値はエラーやログへ出力しません。

#### 認証手段0: `python -m hve login`（Copilot SDK）

HVE の各 Step は GitHub Copilot SDK 経由で Copilot セッションを作成します。初回または認証切れ時は次を実行してください。

```bash
python -m hve login
```

現在の状態だけ確認する場合:

```bash
python -m hve login --status
```

`--dry-run` は SDK セッションを作らないため、この Copilot 認証確認をスキップします。

#### 認証手段A: `gh auth login`（推奨）

認証を開始:

```bash
gh auth login
```

> 以下の選択肢が表示されます:
> 1. **Where do you use GitHub?** → `GitHub.com` を選択
> 2. **What is your preferred protocol?** → `HTTPS` を選択（推奨）
> 3. **Authenticate Git with your GitHub credentials?** → `Yes`
> 4. **How would you like to authenticate?** → `Login with a web browser` を選択
> 5. ブラウザが開き、表示されるワンタイムコードを入力して認証を完了します

認証確認:

```bash
gh auth status
```

> 「Logged in to github.com」と表示されれば成功です。基本実行ではこれだけで十分です。追加の環境変数設定は不要です。


#### 認証手段B: 環境変数 `GH_TOKEN`（GitHub 書込み時）

GitHub 書込み startup preflight 対象では `GH_TOKEN`、未設定時は `GITHUB_TOKEN` が必要です。

> **以下の GitHub 書込み機能はいずれも任意です。対象条件に該当しない通常 run では token は不要です。**

| オプション | GH_TOKEN |
|-----------|----------|
| `--create-issues` | 必要（未設定ならエラー終了） |
| `--create-issues --assign-copilot-agent` | 必要（新規 Root Issue の Copilot cloud agent 割当） |
| `--create-pr` | 必要（未設定ならエラー終了） |
| 対象 Workflow / Step での `--enable-auto-merge` | 必要（未設定ならエラー終了） |
| `--auto-coding-agent-review` | 不要（ローカル SDK で実行） |
| MCP Server（GitHub HTTP） | **必須** |
| 上記以外（基本実行） | **不要** |

> startup preflight 対象では、token に加えて `REPO`（`owner/repo` 形式）または `--repo` 指定も必要です。`gh auth login` のみでは不足するため注意してください。

#### Fine-grained PAT の作成手順

GitHub 書込み startup preflight の対象機能を**使用しない場合、このセクションは読み飛ばせます**。

1. GitHub.com > **プロフィールアイコン** > **Settings** > **Developer settings**
2. **Personal access tokens** > **Fine-grained tokens** > **Generate new token**
3. 基本情報を入力:
   - **Token name**: 任意（例: `copilot-sdk-tools`）
   - **Expiration**: 90日以内を推奨
4. **Repository access**: **Only select repositories** → `OWNER/REPOSITORY` を選択
5. **Permissions**（Repository permissions）:

| 権限 | 設定値 | 用途 |
|------|--------|------|
| **Issues** | Read and write | `--create-issues` / `--assign-copilot-agent` |
| **Actions** | Read and write | `--assign-copilot-agent` |
| **Pull requests** | Read and write | `--create-pr` / `--assign-copilot-agent` / 対象 Workflow の auto-merge |
| **Metadata** | Read-only（自動付与） | — |
| **Contents** | Read and write | `--create-issues` / `--create-pr` / `--assign-copilot-agent` / 対象 Workflow の auto-merge 使用時 |

> **最小権限の原則**: GitHub 書込み機能はブランチ作成・commit・push を伴うため、Contents も Read and write が必要です。
> Copilot cloud agent への割当で classic PAT を使う場合は `repo` scope が必要です。GitHub App installation token はこの割当経路の代替にしません。

6. **Generate token** をクリックし、表示されたトークン（`github_pat_` で始まる文字列）を**必ずこの時点でコピー**

> ⚠️ トークンはこの画面を離れると二度と表示されません。

7. OS の資格情報ストアまたは安全なシークレット注入手段から `GH_TOKEN` へ設定します。token の具体値をコマンド履歴、ログ、Issue、PR、文書へ記録しないでください。

#### 既存の Fine-grained PAT を使う場合

Settings > Developer settings > Fine-grained tokens で対象トークンを開き、以下を確認してください:

- 有効期限が切れていないこと
- リポジトリ範囲に `OWNER/REPOSITORY` が含まれていること
- 上記の権限が付与されていること

不足がある場合は **Regenerate token** で再生成してください（トークン文字列が変わります）。

#### トークンの動作確認

```bash
gh api user --jq '.login'                                              # トークン有効性
gh api repos/OWNER/REPOSITORY --jq '.full_name'                        # リポジトリアクセス
python -m hve orchestrate --workflow aas --branch main --dry-run       # hve dry-run
```

### SDK ResourceSnapshot routing（現行 runtime）

現在の local runtime で Plugin / MCP / Skill の **install / config / auth は Copilot CLI 側で事前設定**します。
HVE CLI の責務は、その結果を **SDK ResourceSnapshot** と policy route で読み取り、実働 local session の初期化・readiness・公開範囲制限を適用することです。永続設定の変更や認証開始は行いません。

| 項目 | 現行契約 |
|---|---|
| 設定主体 | Copilot CLI 側で登録・有効化・認証する |
| HVE CLI の責務 | local session ごとに ResourceSnapshot を読み、workflow 固有の policy route を適用する |
| required Skill の MCP 依存 | `policy.json` の `required_mcp_servers_by_skill` から exact server 名を解決する。runner には固定名を持たない |
| 公開情報 | safe field のみ。raw config / path / credential は表示・保存しない |
| Work IQ | `snapshot projection` で ready/not-configured/unverified を判定し、runtime では exact `workiq` と exact `ask` を再確認する |
| Cloud Session | この routing は **Cloud Session は未対応**。変更は次に開始する local session から反映される |

CLI から現行 surface を確認したい場合は、`python -m hve toolsearch context --workflow <id>` と
`python -m hve toolsearch context --workflow <id> --compare` を使います。Step固有のrequired / optional Skillとrequired MCPを反映する場合は `--step <Step-ID>` を加えます。fan-out子IDはbase Stepで解決されます。いずれも `no-prompt` 実測であり、model推論は発生しません。

required MCPはclassificationを理由に黙って消しませんが、対象Workflowのcategory、非空のexact allowlist、runtimeにおけるallowlist toolの実在を全て要求します。1件でも欠ければ最初のprompt前にfail-closedします。optional MCPの照合失敗は当該session内でserverを無効化します。runtime discoveryのtool名をHVEがpolicyへ自動保存することはありません。

最初のモデル送信前に required Skill を runtime で確認し、実効選択 MCP があれば **初期化 → readiness → `list_tools` → 必要な options 更新の ACK** の順で検証します。`session.rpc.tools.initialize_and_validate()` の後に各 exact server の `connected` と許可 tool の実在を確認し、初期化の正常復帰だけでは接続済みと判定しません。実効選択 MCP が 0 件なら MCP 初期化・接続待ち・tool 列挙は行いませんが、required Skill の runtime 検証と caller filter の適用確認は省略しません。

必要な options 更新は全 server 分を集約して 1 回だけ行い、`success is True` だけを ACK 成功とします。caller filter は `available_tools` / `excluded_tools` の非 `None` 指定（空リストも含む）で、route によって許可を広げません。ACK 非成功時に required MCP または caller filter がある場合は fail-closed です。選択 MCP がすべて optional かつ caller filter がない場合は、共有 deadline の残時間内に全選択 MCP の disable が成功した場合だけ継続できます。接続・tool 照合に失敗した optional server も期限内に disable できた場合だけ除外して続行します。disable 失敗・期限切れ・cancel は停止し、2 回目の options 更新や追加予算で救済しません。gate の成功またはこの optional disable が確定する前には送信しません。

初期化 API が検証不能なら fail-closed です。routing の共有 60 秒は session 取得後の `apply_resource_route` の入口から出口までで、Skill 検証・初期化・接続待ち・tool 列挙・ACK・disable を含みます。API / server ごとに予算を再付与せず、run 全体の timeout とも別です。認証と状態の切り分けは [Plugin / MCP 認証ガイド](./plugin-mcp-auth.md) を参照してください。

### MCP 通信ログ

Copilot SDK セッションで観測した MCP の入出力は、実行ごとの作業フォルダーへ MCP サーバー単位で保存されます。ターミナル表示は verbosity に応じて切り詰められますが、**このログには切り詰めなしの全文が残ります**。

| 項目 | 内容 |
|---|---|
| 出力先 | `work/run/<run-id>/mcp-<サーバー名>.log`（サーバー 1 件につき 1 ファイル） |
| 例 | `mcp-workiq.log` / `mcp-azure.log` / `mcp-microsoft-learn.log` |
| 有効化条件 | `HVE_WORK_ROOT` が設定されている実行（CLI / GUI は自動設定）。`--dry-run` では出力しません |
| 設定 | 専用の CLI オプション・設定項目はありません（常時有効） |
| 上限 | 1 ファイル 32 MiB。到達時は追記を停止し、警告を 1 回出します（ローテーションなし） |

記録されるレコード種別は次の 5 つで、各レコードは `=== ` で始まる 1 行のヘッダと本文からなります。

| 種別 | 内容 |
|---|---|
| `mcp_request` | MCP ツール呼び出しの引数（JSON） |
| `mcp_response` | 対応する結果本文またはエラー |
| `mcp_server_status` | 接続状態・プラグイン名・トランスポート |
| `session_prompt` | HVE が知識探索エージェントへ送った目的指示 |
| `session_response` | その応答本文 |

#### 知識探索セッションのログの扱い

`mcp-workiq.log` には、知識探索エージェントが同じ SDK session 内で実行した MCP call と応答が記録されます。HVE は Work IQ 用の固定 Prompt や固定 query を生成しないため、`session_prompt` はコピーして再利用するための Work IQ 専用プロンプトではありません。旧 run では旧ラベルのログが残る場合があります。

```text
=== 2026-10-01T09:12:33.421037+00:00 | session_prompt | server=workiq | label=知識探索 [pre-execution-qa]
```

`label` には探索モード（事前 QA / AKM / ARD など）が入ります。

#### 取り扱い上の注意

- このログは **M365 の業務データを平文で含みます**。共有・転送の前に内容を確認してください。
- 代表的な認証情報（`Authorization: Bearer ...` / `token=...` / JWT）は記録前に `[REDACTED]` へマスクされますが、**完全なサニタイズは保証されません**。
- `.gitignore` の `*.log` により、このログはリポジトリへコミットされません。
- GUI / CLI Autopilot のように APP ごとの子プロセスが並列実行される場合は、レコードの交錯を避けるため `mcp-<サーバー名>-<pid>.log` とファイルが分かれます。
- MCP サーバーのプロセスは Copilot CLI ランタイムが起動するため、HVE は生の JSON-RPC フレームを取得できません。記録されるのは SDK イベントが公開する範囲（上記 5 種別）です。

### Work IQ Plugin / MCP Server 連携（オプション）

Work IQ は、利用者が GitHub Copilot CLI に設定した **Plugin または MCP Server** を GitHub Copilot SDK 経由の「知識源」として利用します。HVE は配布元や構成方式を推測せず、SDK discovery で **exact `workiq`** が enabled である場合だけ候補として扱います。別名・大文字小文字違い・tool 名だけの一致を代替にしません。

`--workiq` は実効知識源へ `workiq` を追加します。**v0.8.196 以降、ローカル CLI では Work IQ が既定で有効**です（FR-KD-11）。無効にするには `--no-workiq` を指定するか、環境変数 `WORKIQ_ENABLED` を `false` / `0` / `no` にします（`--workiq` / `--no-workiq` が環境変数より優先）。Work IQ 以外の MCP server を知識源にする場合は、`--knowledge-source NAME` を複数回またはカンマ区切りで指定できます。環境変数は `HVE_KNOWLEDGE_SOURCES`（カンマ区切り）です。名前は `^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$` に一致する必要があり、CLI で不正な名前を渡すと argparse エラー（exit code 2）になります。環境変数内の不正トークンと空トークンは無視されます。実効順序は `workiq`（Work IQ 有効時）→ `--knowledge-source` / `HVE_KNOWLEDGE_SOURCES` の指定順で、重複は最初の 1 件だけ残します。

既定の読み取り専用 tool 許可リスト（`hve/toolsearch/policy.json` の `knowledge_tool_allowlists`）は `workiq` と `microsoft-learn` に定義されています。たとえば Microsoft Learn を知識源に加えるには `--knowledge-source microsoft-learn` を指定します。

Work IQ が未認証（`needs-auth`）の場合は `知識源 workiq を除外します（server-needs-auth）。GitHub Copilot CLI で /mcp auth workiq を実行して認証し、HVE を再起動してください。` と警告され、その実行だけ除外されます。除外の理由は QA ファイルの `## 知識探索の状況` 節（`| 知識源 | 状態 | 理由コード |`）にも記録されます（FR-KD-12）。

AKM の `--sources` に `workiq` を含めた場合、および ARD の Work IQ 補助を有効にした場合も、その run に限って `workiq` を実効知識源へ追加します。保存設定は変更しません。

#### Copilot CLI 側の設定・認証確認

HVE は Work IQ の設定・認証を実行しません。利用者が選んだ Plugin または MCP Server の手順に従って、HVE と同じユーザー・同じ Copilot CLI 環境で導入、有効化、認証を完了してください。確認時は Copilot CLI の対話セッションで `/mcp` を開き、server 名が exact `workiq` で `connected` であることと、必要な読み取り tool が公開されていることを確認します。

HVE は設定ファイル、raw transport、URL、header、credential を読み取ったり複製したりせず、OAuthを開始せず、ブラウザも開きません。また、capability や接続確認のためにモデル問い合わせまたは M365 の診断クエリを自動実行しません。

#### SDK discovery capability

HVE は `client.rpc.mcp.discover(MCPDiscoverRequest(working_directory=...))` で、対象リポジトリの working directory に対する enabled MCP 名だけを確認します。外部へ通知する状態は **`ready` / `not-configured` / `unverified`** の3種類です。

| 状態 | 意味 |
|---|---|
| `ready` | enabled server の中に exact `workiq` がある |
| `not-configured` | exact `workiq` がない、または disabled。別名だけが存在しても同じ扱い |
| `unverified` | SDK import、client start、discovery、response schema、working directory 解決のいずれかを検証できない |

discovery の `ready` は runtime の `connected` を意味しません。設定上の有効状態だけで、初期化・認証・MCP tool call の成功を保証しません。Prompt plan でも実働 session の初期化・query は行いません。

#### 実行時確認と利用不可時の動作

知識探索を開始する前に、HVE は ResourceSnapshot と `hve/toolsearch/policy.json` の `knowledge_tool_allowlists` を使って実効知識源を判定します。利用できない知識源は `知識源 <名前> を除外します（<理由>）` と警告し、その run だけから外します。保存設定は変更しません。既定の `workiq` allowlist は `retrieve` / `ask` / `fetch` / `search_paths` / `get_schema` / `list_agents` で、`create_entity` / `update_entity` / `delete_entity` / `do_action` / `call_function` / `fetch_blob` は公開しません。

探索用 SDK session では `session.rpc.tools.initialize_and_validate()` の後に `session.rpc.mcp.list()` で `connected` を確認し、`session.rpc.mcp.list_tools(server_name=<名前>)` で allowlist tool の公開を確認します。初期化の正常復帰だけでは接続済みと判定しません。確認できない知識源は除外し、usable が 0 件なら知識探索を実行しません。

#### 知識探索エージェント

知識源を使う処理は、1 回の探索につき **1 つの Copilot SDK session** で実行します。HVE は Work IQ query や固定応答 schema を組み立てません。モデルが目的に応じて自分で検索計画を立て、HVE は読み取り専用 MCP tool と `hve_read_file` / `hve_qa_create` / `hve_qa_answer` / `hve_knowledge_write` の custom tool だけを公開します。`ask_user` と `infinite_sessions` は公開しません。

MCP 出典は同じ session 内の成功した MCP call 応答に locator が含まれる場合だけ検証済みになります。`Confirmed` は 1 件以上の検証済み出典を必要とし、違反した書込み tool call は失敗してファイルを変更しません。修復指示は最大 2 回で、残った未調査項目は `Unknown` として記録されます。完了時は `知識探索 [<label>]: Confirmed=<n> Tentative=<n> Unknown=<n> 修復=<n> tool失敗=<n>` を出力します。

#### 事前 QA / AKM / ARD での使われ方

| 経路 | 動作 |
|---|---|
| 事前 QA | usable な知識源が 1 件以上ある場合、未回答質問票を `qa/<run_id>-<step_id>-pre-execution-qa.md` へ書き、`調査回答` / `調査状態` / `調査出典` と `## 調査出典` を知識探索エージェントが埋めます。`Confirmed` / `Tentative` で回答が空でないものを採用し、その他は既定値候補へ戻します。CLI / GUI / IPC の人への回答待ちは行いません。 |
| AKM | `--sources` に `workiq` を含むなど知識源が usable な場合、DAG 前に「AKM 知識探索」を 1 回だけ実行します。`knowledge/Dxx-*.md` と status 文書は `hve_knowledge_write` 経由で、`.hve/locks/` の OS ロック、SHA-256 楽観ロック、atomic replace により並行実行に安全に更新されます。 |
| ARD | Step 2 が実行対象で usable な知識源がある場合、DAG 前に「ARD 知識探索」を実行します。`Confirmed` / `Tentative` の回答が 1 件以上ある場合だけ、Step 2 Issue に `## ARD 知識探索: ユースケース参照情報` コメントを 1 件投稿します。 |

既存 QA ファイルの `Work IQ 回答案` / `Work IQ 理由` 列は、それぞれ `調査回答` / `調査出典` として読みます。書き出しは新しい列名だけです。

#### CLI / 環境変数 / wizard

| 用途 | CLI 引数 | 環境変数 | wizard メニュー |
|---|---|---|---|
| Work IQ を知識源へ追加 | `--workiq` | `WORKIQ_ENABLED=true` | `知識探索で Work IQ を使う？`（ARD では `ARD の知識探索で Work IQ を使う？`） |
| 任意の知識源を追加 | `--knowledge-source NAME`（複数回 / カンマ区切り） | `HVE_KNOWLEDGE_SOURCES` | GUI の「知識源 MCP サーバー」欄を使用 |
| AKM 入力 source | `--sources qa,docs-original,workiq` | なし | AKM source 選択で `workiq` を含める |

旧 Work IQ 専用の詳細オプションを指定すると argparse エラー（exit code 2）になります。旧 `WORKIQ_*` 環境変数は読まれません。

```bash
# Work IQ と Confluence を知識源として使う
python -m hve orchestrate --workflow ard --workiq --knowledge-source confluence

# AKM で qa/docs-original に加えて Work IQ を知識源にする
python -m hve orchestrate --workflow akm --sources qa,docs-original,workiq --workiq
```

> **HVE Cloud Agent 非対応**: Issue Template 経由の Cloud 実行（`auto-knowledge-management-reusable.yml`）では OAuth remote MCP を扱えないため、Work IQ 入力は使用できません。Work IQ 連携が必要な場合はローカル CLI / GUI / Prompt 版を使用してください。

---

## 自動コンテキスト圧縮（Auto Compaction）

サブステップ実行時に Copilot SDK の `infinite_sessions`（バックグラウンド compaction）を有効化し、
Context Window 使用量を SDK 側で自動的に圧縮させるオプションです。長時間/長文の workflow で
Context 上限に達して打ち切られるのを防ぎたい場合に ON にします。

| 項目 | 値 |
|---|---|
| CLI フラグ | `--auto-compaction` / `--no-auto-compaction` |
| GUI 設定 | 設定画面 → Autopilot → 「自動コンテキスト圧縮 (auto_compaction)」 |
| 既定 | OFF（SDK 既定挙動） |

```bash
# 自動コンテキスト圧縮を有効化して実行
python -m hve orchestrate --workflow aas --auto-compaction
```

> 実際の圧縮しきい値（既定 background=0.80 / buffer=0.95）は SDK 側で管理され、HVE からは変更しません。
> 圧縮は SDK の責務であり、HVE は `infinite_sessions={"enabled": True}` を `create_session` に渡すのみです。

---

## インタラクティブモード（推奨）

`python -m hve` を引数なしで実行すると、GitHub Copilot CLI スタイルの対話型 wizard が起動します。オプションの知識がなくても、画面のガイドに従うだけでワークフローを実行できます。

### 起動方法

```bash
python -m hve          # 引数なしで wizard 起動
python -m hve run      # 明示的に run サブコマンドを指定（同等）
```

### wizard フロー

wizard は以下の段階で進行します。ステップ 4（モデル選択）の直後に **実行モード選択** が表示されます。

```
┌──────────────────────────────────────────────────────────┐
│  1. ウェルカムバナー表示                                      │
│  2. ワークフロー選択（番号入力）               ← 手動          │
│  3. ステップ選択（カンマ区切り / Enter = 全選択） ← 手動         │
│  4. モデル選択（番号入力）                     ← 手動          │
│                                                            │
│  ★ 実行モード選択（番号入力）                 ← 新規追加      │
│     1) クイック全自動  — デフォルト値で即実行（確認あり）          │
│     2) カスタム全自動  — 全設定を手動入力後に自動実行              │
│     3) 手動           — 従来どおり（実行中も対話あり）            │
│                                                            │
│  5. オプション設定       ← 1)スキップ / 2)手動 / 3)手動         │
│  5a. 知識探索の利用設定 ← Work IQ / 知識源を使う場合のみ表示        │
│  6. ワークフロー固有パラメータ ← 1)必須のみ / 2)手動 / 3)手動   │
│  7. 追加プロンプト（全Step） ← 1)スキップ / 2)手動 / 3)手動      │
│  7b. 実行計画のプレビュー（dry-run）Y/N                          │
│  7c. ワークベンチ（4 ペイン UI）を起動しますか？ Y/n ← 新規追加  │
│  8. 設定サマリー表示 + 実行確認 ← 全モード共通                   │
│  9. ワークフロー実行                                          │
└──────────────────────────────────────────────────────────┘
```

各段階の詳細を以下に説明します。

#### ステップ 1: ウェルカムバナー

起動すると、ボックス装飾付きのウェルカムバナーが表示されます。

```text
╭──────────────────────────────────────────────────────────╮
│  HVE CLI Orchestrator                                    │
│  ワークフローをインタラクティブに実行します              │
╰──────────────────────────────────────────────────────────╯
```

#### ステップ 2: ワークフロー選択

登録されている全ワークフローが番号付きリストで表示されます。番号を入力して選択します。

```text
? ワークフローを選択してください
    1)  Business Engineering (要求定義) > Auto Requirement Definition  (ard — 10 実行ステップ)
    2)  Architecture Design > Architecture Design  (aas — 10 実行ステップ)
    3)  Software Engineering > Web App Design  (aad-web — 8 実行ステップ)
    4)  Software Engineering > Web App Dev & Deploy  (asdw-web — 21 実行ステップ)
    5)  Software Engineering > Dataflow Design  (adfd — 7 実行ステップ)
    6)  Software Engineering > Dataflow Dev & Deploy  (adfdv — 8 実行ステップ)
    7)  既存ドキュメントのインポート > Auto Design-doc Ingestion  (adi — 9 実行ステップ)
    8)  Knowledge Management > Knowledge Management  (akm — 2 実行ステップ)
    9)  Knowledge Management > Source Codeからのドキュメント作成  (adoc — 19 実行ステップ)
   10)  AI Agent > Agent Data Architecture  (ada — 9 実行ステップ)
   11)  AI Agent > AI Agent Design  (aag — 3 実行ステップ)
   12)  AI Agent > AI Agent Dev & Deploy  (aagd — 9 実行ステップ)
   13)  AI Agent > Agentic Retrieval Add-on  (aar — 7 実行ステップ)
> 3
```

> 選択肢は `hve/workflow_registry.py` の `WORKFLOW_CATEGORIES` に従ってグループ順に並び、先頭にグループ名が付きます。この分類は HVE GUI Orchestrator の Step 1 と共通です。

#### ステップ 3: ステップ選択

選択したワークフローのステップ一覧が表示されます。実行したいステップの番号をカンマ区切りで入力します。**Enter キーだけ押すと workflow registry の既定の選択が使われます。**

```text
? 実行するステップを選択（Enter = 全4ステップ）
  1) [Step.1] 画面一覧と遷移図
  2) [Step.2.1] 画面定義書
  3) [Step.2.2] マイクロサービス定義書
  4) [Step.2.3] TDDテスト仕様書
  ...
> 1,2,3      ← カンマ区切りで指定
>            ← Enter のみ = 既定の選択
```

> 通常は「既定の選択 = 全ステップ」です。例外として `adi` は、Step `1.1` / `1.2`（原本質問票）が `selected_by_default=False` のため、`--steps` 省略時・wizard で Enter のみ・Prompt 版で `steps` 省略のいずれでも既定では選ばれません。必要なときだけ明示指定します。

#### ステップ 4: モデル選択

使用する AI モデルを番号で選択します。表示順は一例で、実際の候補は `python -m hve login` がキャッシュした SDK の model catalog（`list_models()`）に従います。キャッシュが無い場合は `Auto` + 組み込み fallback 一覧を表示します。

```text
? 使用するモデルを選択
  1) Auto
  2) claude-opus-5.5
  3) claude-opus-4.7
  4) claude-opus-4.6
  5) gpt-5.5
  6) gpt-5.4
> 2
```

> 初期選択は `claude-opus-5.5`（`DEFAULT_MODEL`）です。Enter だけで確定するとこのモデルで実行します。

> **Auto を選択した場合**: GitHub が最適モデルを動的に選択します。可用性・レイテンシ・レート制限・プラン/ポリシーを考慮し、プレミアムリクエスト枠は 0.9x（10% ディスカウント）で計上されます。プレミアム乗数 1x 超のモデルは Auto 対象外です。公式: https://docs.github.com/en/copilot/concepts/auto-model-selection

#### ステップ 4.5: 実行モード選択（新規追加）

モデル選択の直後に、ワークフロー実行の自動化レベルを選択します。

```text
? 実行モードを選択
  1) クイック全自動  — デフォルト値で即実行（確認あり）
  2) カスタム全自動  — 全設定を手動入力後に自動実行
  3) 手動           — 従来どおり（実行中も対話あり）
> 1
```

##### 3つのモードの比較

| 項目 | クイック全自動 | カスタム全自動 | 手動 |
|------|------------|------------|------|
| ステップ5〜7a の設定 | デフォルト値で自動設定 | 手動入力 | 手動入力 |
| タイムアウトデフォルト | 86400 秒（24時間） | 86400 秒（24時間） | 21600 秒（6時間） |
| 出力レベルデフォルト | `normal` (2) | `compact` (1) | `compact` (1) |
| 実行確認プロンプト | あり（Y/N） | あり（Y/N） | あり（Y/N） |
| 実行中の対話 | なし（全自動） | なし（全自動） | あり |
| 推奨場面 | 素早く実行したい場合 | 設定を細かく制御しつつ長時間放置 | 通常利用 |

##### クイック全自動のデフォルト値

| 設定項目 | 自動設定される値 |
|---------|----------------|
| ベースブランチ | `main` |
| 並列実行数 | `15`（AKM は `1`） |
| 出力レベル | `normal` (2) |
| タイムアウト | `86400` 秒（24時間） |
| ログレベル | `error` |
| QA 自動投入 | OFF |
| Review 自動投入 | OFF |
| Issue 作成 | OFF |
| PR 作成 | OFF |
| Code Review Agent | OFF |
| ドライラン | OFF |
| ワークベンチ起動 | ON（既定 Yes、ユーザー回答で変更可） |
| リポジトリ | `$REPO` 環境変数 または 空 |
| 知識探索の追加知識源 | なし |
| 追加プロンプト | なし |

> **注意**: クイック全自動でも、AKM 以外のワークフローで**必須パラメータ**（`app_id`、`usecase_id` 等）がある場合は、それらの入力のみ求められます。

##### 全自動モード実行時のメッセージ

実行確認後、全自動モードでは以下のメッセージが表示されて自動実行が開始されます：

```text
✓ 全自動モードで実行を開始します。実行中の入力は不要です。
```

**クイック全自動モード**では、これらのオプション設定をスキップして実行されます。カスタム全自動モードおよび手動モードでは、各種オプションを順番に設定します。Y/N のプロンプトでは Enter キーでデフォルト値が適用されます。

```text
? ベースブランチ [main]: main
? 並列実行数 [15]: 15
? Copilot CLI ログレベルを選択
  1) none
  2) error
  3) warning
  4) info
  5) debug
  6) all
> 2
? セッション idle タイムアウト（秒。デフォルト: 21600 = 6時間） [21600]: 21600
? QA 自動投入を有効にする？ [y/N]: N
? Review 自動投入を有効にする？ [y/N]: N
? GitHub Issue を作成する？ [y/N]: y
? GitHub PR を作成する？ [y/N]: ← Issue 作成が Y の場合は自動で ON
? リポジトリ (owner/repo) []: dahatake/MembershipServiceForHVE
? ドライラン（実際の SDK 呼び出しをしない）？ [y/N]: N
? ワークベンチ（4 ペイン UI）を起動しますか？ [Y/n]: Y
```

> **デフォルトは N（作成しない）です。ローカル実行のみの場合は N のままで問題ありません。**

> **QA/Review 用サブモデルの選択**:
> - `QA 自動投入を有効にする？` が `n` の場合は QA 側の追加確認は表示されません。
> - `QA 自動投入を有効にする？` が `y` の場合のみ「QA にメインモデルとは別のモデルを使う？」が表示されます。ここが `n` の場合は `QA_MODEL` 環境変数が設定されていればその値が使われ、未設定ならメインモデルを使用します。`y` の場合のみ「QA 用モデルを選択」が表示されます。
> - `Review 自動投入を有効にする？` が `n` の場合は Review 側の追加確認は表示されません。
> - `Review 自動投入を有効にする？` が `y` の場合のみ「Review にメインモデルとは別のモデルを使う？」が表示されます。ここが `n` の場合は `REVIEW_MODEL` 環境変数が設定されていればその値が使われ、未設定ならメインモデルを使用します。`y` の場合のみ「レビュー用モデルを選択」が表示されます。

> **リポジトリ入力について**: 「GitHub Issue を作成する？」または「GitHub PR を作成する？」に `y` と回答した場合のみ、`owner/repo` 形式でリポジトリの入力を求められます。環境変数 `REPO` が設定されている場合はその値がデフォルトとして表示されます。Issue/PR 作成が両方とも OFF の場合、このプロンプトは表示されません。

| 設定項目 | デフォルト | CLI モードでの対応オプション |
|---------|-----------|--------------------------|
| ベースブランチ | `main` | `--branch` |
| 並列実行数 | `15` | `--max-parallel` |
| ログレベル | `error` | `--log-level` |
| タイムアウト | `21600`（6時間） | `--timeout` |
| QA 自動投入（事前 QA と実行後の不明点調査） | **ON**（`--no-auto-qa` で OFF） | `--auto-qa` / `--no-auto-qa` |
| Work IQ を知識源に加える | **ON**（`--no-workiq` または `WORKIQ_ENABLED=false` で OFF） | `--workiq` / `--no-workiq` |
| QA 回答の Knowledge Management へのバックグラウンドマージ | OFF | `--qa-akm-background-merge` |
| Review 自動投入 | OFF | `--auto-contents-review` |
| GitHub Issue 作成 | OFF | `--create-issues` |
| GitHub PR 作成 | OFF | `--create-pr` |
| リポジトリ (owner/repo) | `$REPO` または空 | `--repo` |
| ドライラン | OFF | `--dry-run` |
| ワークベンチ | ON（ウィザード末尾で Y/n） | `--workbench {auto,on,off}` |

> **AKM ワークフローの場合**: 並列実行数（15 固定）、QA 自動投入（OFF 固定）、Review 自動投入（OFF 固定）のプロンプトはスキップされます。タイムアウト設定は AKM でもスキップされず、全ワークフロー共通で個別設定可能です。

> **各出力レベルで何が表示されるか**: 「コマンドリファレンス」の「コンソール出力レベル詳細」セクションに、各レベルの出力比較テーブルとサンプル出力例を掲載しています。

#### ステップ 6: ワークフロー固有パラメータ

選択したワークフローに固有のパラメータがある場合、自動的にプロンプトが表示されます（全て必須入力）。

```text
# asdw-web ワークフローの場合（複数 APP-ID 指定可 + 主対象 APP-ID を1つ指定）
? 対象アプリケーション (app_ids) — カンマ区切りで複数指定可: APP-04, APP-05
? 主対象アプリケーション (app_id) — 上記の中から1つを選択: APP-04
? resource_group: rg-dev
```

固有パラメータを持つワークフロー:
- `aad-web`: `app_ids`（対象 APP-ID 一覧、カンマ区切り）, `app_id`（主対象 APP-ID を1つ指定）
- `asdw-web`: `app_ids`（対象 APP-ID 一覧、カンマ区切り）, `app_id`（主対象 APP-ID を1つ指定）, `resource_group`, `usecase_id`
- `adfd`: `app_ids`（対象 APP-ID 一覧、カンマ区切り）, `app_id`（主対象 APP-ID を1つ指定）
- `adfdv`: `app_ids`（対象 APP-ID 一覧、カンマ区切り）, `app_id`（主対象 APP-ID を1つ指定）, `resource_group`, `app_id`
- `aag`: `app_ids`, `app_id`, `usecase_id`
- `aagd`: `app_ids`, `app_id`（主対象 APP-ID）, `resource_group`, `usecase_id`
- `adi`: `purpose`, `target_scope`, `depth`, `focus_areas`
- `akm`: `sources`, `target_files`, `force_refresh`, `custom_source_dir`

> **推薦アーキテクチャによる自動 APP-ID フィルタリング**:
> `aad-web` / `asdw-web` / `adfd` / `adfdv` では、APP-ID 未指定時に「全 APP 対象」とはなりません。
> `docs/catalog/app-arch-catalog.md` の `A) サマリ表（全APP横断）` を参照し、
> workflow に対応する推薦アーキテクチャの APP-ID のみが自動的に対象になります。
> - `aad-web` / `asdw-web`: `Webフロントエンド + クラウド` の APP-ID のみ対象
> - `adfd` / `adfdv`: `データデータフロー処理` / `バッチ` の APP-ID のみ対象
> APP-ID を明示指定した場合も、推薦アーキテクチャが一致するもののみ採用されます。

> **AKM ワークフローの場合**: 固有パラメータ（sources=qa, target_files=sourcesに応じた全件, force_refresh=true, custom_source_dir=空）はデフォルト値で自動設定され、プロンプトはスキップされます。

> 固有パラメータのないワークフローは `aas` のみです。`aad-web` / `adfd` / `adfdv` / `aag` / `aagd` は `app_ids` / `app_id` を、`adi` は `purpose` / `target_scope` / `depth` / `focus_areas` を受け付けます。

#### 知識探索の利用設定

知識探索で Work IQ を使う場合、ワークフロー固有パラメータ入力の前に確認が表示されます。ARD では文言が「ARD の知識探索で Work IQ を使う？」になります。Work IQ 以外の MCP server を知識源にする場合は CLI で `--knowledge-source NAME` を指定するか、GUI の「知識源 MCP サーバー」欄を使用します。HVE はここで認証を開始しません。

```text
? 知識探索で Work IQ を使う？ [y/N]: y
```

ワークフロー固有パラメータ入力後、全ステップ向けの追加プロンプト入力が表示されます。

```text
? 全てのステップでの Prompt の末尾に追加するプロンプト（省略可）: 日本語で出力してください
```

#### ステップ 7c: ワークベンチ起動の有無（新規）

ウィザード末尾（確認パネル直前）で、4 ペイン固定レイアウト UI（ワークベンチ）を起動するか確認します。**全モード（クイック全自動 / カスタム全自動 / 手動）共通**で表示されます。

```text
? ワークベンチ（4 ペイン UI）を起動しますか？ [Y/n]: Y
```

- **Yes（既定）**: ワークベンチ UI を起動。TTY / quiet / `final_only` / 環境変数 `HVE_NO_WORKBENCH=1` 等の自動降格条件は orchestrator / Console 側に従う（既存仕様）。
- **No**: 起動せず、従来の plain 出力でターミナル実行（CLI フラグ `--workbench off` 相当）。

> **環境変数 `HVE_NO_WORKBENCH=1` が設定済みの環境では、Yes を選んでも自動降格により起動しません**（既存仕様）。

#### ステップ 8: 設定サマリーと実行確認

入力した全設定が一覧パネルとして表示されます。内容を確認し、実行するかどうかを選択します。

```text
┌─ 実行設定 ────────────────────────────────────────┐
│  ワークフロー : Web App Design (aad-web)        │
│  ステップ     : 全ステップ                          │
│  モデル       : claude-opus-4.7                    │
│  ブランチ     : main                               │
│  並列数       : 15                                 │
│  ログレベル   : error                              │
│  タイムアウト  : 21600 秒                          │
│  QA 自動      : ON                                │
│  Review 自動  : OFF                               │
│  知識探索    : Work IQ 有効                         │
│  Issue 作成   : ON                                │
│  PR  作成     : ON                                │
│  リポジトリ   : dahatake/MembershipServiceForHVE   │
│  ドライラン   : OFF                                │
└───────────────────────────────────────────────────┘

? この設定で実行しますか？ [Y/n]: Y
```

`N` を選択するとキャンセルされ、プログラムが終了します。

#### ステップ 9: ワークフロー実行

確認後、スピナーアニメーション付きでワークフローが実行されます。実行中は `Ctrl+C` でいつでも中断できます。

### ターミナル要件

| 環境 | 表示 |
|------|------|
| **TTY 接続時**（通常のターミナル） | ANSI カラー + ボックス装飾 + スピナーアニメーション |
| **非 TTY 時**（パイプ / リダイレクト / CI） | プレーンテキスト（ANSI エスケープなし、装飾なし） |

カラー表示の有無はターミナルの TTY 接続状態を自動判定するため、特別な設定は不要です。

### インタラクティブモードと CLI モードの比較

| 項目 | 手動モード | クイック全自動 | カスタム全自動 | CLI モード (`orchestrate`) |
|------|----------|------------|------------|--------------------------|
| 起動方法 | `python -m hve` | `python -m hve` | `python -m hve` | `python -m hve orchestrate --workflow aad-web ...` |
| 設定方法 | wizard が順番にガイド | デフォルト値を自動適用 | wizard がガイド + 自動実行 | コマンドライン引数で全て指定 |
| 推奨場面 | 初回利用・探索的実行 | 素早く実行したい場合 | 設定を細かく制御しつつ長時間放置 | スクリプト・CI/CD・繰り返し実行 |
| タイムアウトデフォルト | `21600`（6時間） | `86400`（24時間） | `86400`（24時間） | `21600`（6時間） |
| 実行中の対話 | あり | なし | なし | なし |
| ステップ選択 | 画面上で番号選択 | 画面上で番号選択 | 画面上で番号選択 | `--steps Step.1,Step.2` |
| 固有パラメータ | 自動プロンプト表示 | 必須のみプロンプト表示 | 自動プロンプト表示 | `--app-id APP-04` 等を明示指定 |
| GH_TOKEN | GitHub 書込み startup preflight 対象時のみ必要 | 同左 | 同左 | 同左 |
| SDK Resources | Copilot CLI 側で事前設定した Plugin / MCP / Skill を local session から読む | 同左 | 同左 | `python -m hve toolsearch context --workflow <id>` で no-prompt 実測 |
| 出力制御 | カラー + 装飾（TTY 自動判定） | カラー + 装飾 | カラー + 装飾 | `--verbose` / `--quiet` で制御 |

> **推奨**: 初めて使用する場合や設定を確認したい場合はインタラクティブモードを使用してください。長時間の実行で放置したい場合は「クイック全自動」または「カスタム全自動」が最適です。繰り返し実行やスクリプト化が必要な場合は CLI モードが適しています。

---

## コマンドリファレンス（CLI モード）

CLI モード（`orchestrate` サブコマンド）は、全てのオプションをコマンドライン引数で指定して実行するモードです。スクリプトや CI/CD パイプラインからの呼び出しに適しています。

### サブコマンド

| サブコマンド | 説明 |
|------------|------|
| （なし） | GUI Orchestrator を起動（PySide6 未導入時は CLI 対話ウィザードへ自動フォールバック） |
| `run` | インタラクティブモードを明示的に起動 |
| `orchestrate` | CLI モードでワークフローを実行（全オプションを引数で指定） |
| `resume` | durable state に登録された標準ローカル実行を候補選択・検証して再開する |
| `qa-merge` | `qa/` 配下の質問票と回答ファイルを統合する |
| `ingest-docs` | `docs-original/` を走査して `docs/original-design-doc-ingest/` へ目録と正規化済み Markdown を出力する |
| `emit-prompt` | `hve/prompts.py` 経由で `.github/prompts/runtime/**` のプロンプト本文を出力する（デバッグ用） |
| `gui` | PySide6 ベースの GUI Orchestrator を起動する（→ [hve-gui-orchestrator-guide.md](./hve-gui-orchestrator-guide.md)） |
| `cli` | 対話型 CLI ウィザードでワークフローを実行する（`run` と同じ経路） |
| `login` | GitHub Copilot へログインし、利用可能モデル一覧をキャッシュする |
| `pricing` | AI Credit 料金表を取得・表示する（`show` / `refresh`。→ [pricing-guide.md](./pricing-guide.md)） |
| `toolsearch` | Tool Search ランキングの統計を表示する（`dashboard` / `context`。→ [tool-search-dashboard.md](./tool-search-dashboard.md)） |

### 基本構文

```bash
python -m hve orchestrate --workflow <WORKFLOW_ID> [OPTIONS]
```

> **正規の workflow ID**: `ard` / `aas` / `aad-web` / `asdw-web` / `adfd` / `adfdv` / `aag` / `aagd` / `aar` / `akm` / `adi` / `adoc` です。`aad` / `asdw` は後方互換エイリアスとして引き続き利用できますが、本ガイドでは正規 ID を優先します。

### 最もシンプルな実行

```bash
# インタラクティブモード（wizard が起動）
python -m hve

# CLI モード（ワークフローを直接指定）
python -m hve orchestrate --workflow aad-web
```

### --dry-run（事前確認）

`--dry-run` を付けると SDK 呼び出し・Issue/PR 作成を行わず、実行計画のみ表示します。初回は必ず使用してください。

ただし、[GitHub 書込み startup preflight](#github-書込み-startup-preflightfr-cli-3182) の対象条件は `--dry-run` でも変わりません。対象 run は repo / token / branch / `origin` / exact remote ref の検査を通過してから計画を表示し、通常 run はこれらを検査しません。

```bash
python -m hve orchestrate --workflow aas --branch main --dry-run
```

出力例:
```
[DRY RUN] orchestrate: workflow=aas, branch=main
[DRY RUN] DAG Traversal:
[DRY RUN]   Wave 1: Step.1 (root)
[DRY RUN]   Wave 2: Step.2.1 (depends_on: Step.1)
[DRY RUN] Would execute: Step.1 - ソフトウェアアーキテクチャの推薦
[DRY RUN] Would execute: Step.2.1 - ドメイン分析
[DRY RUN] No SDK calls were made (dry-run mode).
```

### モデル使い分け例（メイン/レビュー/QA）

```bash
# メインタスクは GPT-5.4、レビューは Opus-4.6 で実行
python -m hve orchestrate --workflow aad-web \
  --model gpt-5.4 --review-model claude-opus-4.7 \
  --auto-contents-review
```

### 全オプション指定例

```bash
# コピーして不要なオプションを削除して使用してください
# ⚠️ --create-issues / --create-pr 使用時は GH_TOKEN または GITHUB_TOKEN が必要です
python -m hve orchestrate \
  --workflow asdw-web \
  --model claude-opus-4.7 \
  --max-parallel 15 \
  --auto-qa \
  --auto-contents-review \
  --auto-coding-agent-review \
  --auto-coding-agent-review-auto-approval \
  --create-issues \
  --create-pr \
  --repo OWNER/REPOSITORY \
  --branch main \
  --app-ids APP-01,APP-02,APP-03 \
  --resource-group rg-dev \
  --usecase-id UC-01 \
  --app-id JOB-01 \
  --steps Step.1,Step.2,Step.3 \
  --cli-path /usr/local/bin/copilot \
  --timeout 7200 \
  --review-timeout 7200 \
  --show-stream \
  --log-level info \
  --verbose \
  --dry-run
```

> **行継続文字**: `\` は macOS / Linux / Git Bash 用です。PowerShell は `` ` ``（バッククォート）、コマンドプロンプトは `^` に置き換えるか、1行にまとめてください。
>
> **排他オプション**: `--verbose` と `--quiet` は排他です。

### オプション一覧

#### 基本オプション

| オプション | 説明 | デフォルト値 |
|-----------|------|------------|
| `--workflow`, `-w` | ワークフロー ID（`ard` / `aas` / `aad-web` / `asdw-web` / `adfd` / `adfdv` / `aag` / `aagd` / `aar` / `akm` / `adi` / `adoc`。`aad` / `asdw` は後方互換エイリアス） | なし（通常は必須。`--autopilot-chain` 指定時は省略可） |
| `--branch` | ターゲットブランチ名 | `main` |
| `--steps` | 実行ステップをカンマ区切りで指定 | workflow registry の既定の選択（通常は全ステップ。`adi` は 1.1 / 1.2 を除く） |
| `--resume-run <RUN_ID>` | **Legacy**: 同じ run ID / workflow ID で成功済みの Step を除外し、残りを新しい session で実行する。durable `hve resume <EXECUTION_ID>` とは別機能で、記録がない run ID は停止 | 未指定 |
| `--approval-gates` | 承認ゲートを宣言したステップを含む wave の実行前に `[y/N]` で確認する。ターミナルが対話可能でない実行（非対話 CLI / GUI の子プロセス）では確認を出さずに停止する | 無効 |
| `--dry-run` | 事前確認モード（SDK 呼び出しなし） | `false` |
| `--verbose`, `-v` | 詳細ログ出力（`--verbosity verbose` の省略形） | `false` |
| `--quiet`, `-q` | 出力抑制（`--verbosity quiet` の省略形） | `false` |
| `--verbosity` | 出力レベルを明示指定（`quiet`/`compact`/`normal`/`verbose`）。指定した場合は `--verbose`/`--quiet` より優先 | `compact` |

> **要件適合実測が FAIL のときの差戻し案内**: `asdw-web` の `5.3`（要件適合実測）が出力するレポートの `Judgement` 列に `FAIL` があると、DAG 実行の完了後に差戻し先ステップと再実行コマンドの候補をログへ 1 回表示します。表示されるのは提案だけで、HVE が自動で再実行することはありません。`NOT_MEASURED` / `NO_TARGET` / `PASS` では表示されません。

#### Agent 実行オプション

| オプション | 説明 | デフォルト値 |
|-----------|------|------------|
| `--model`, `-m` | 使用する AI モデル（`Auto`、または `python -m hve login` がキャッシュした SDK model catalog の ID。キャッシュが無い場合は組み込み fallback 一覧を使用） | `claude-opus-5.5`（`DEFAULT_MODEL`。環境変数 `MODEL` があればその値） |
| `--review-model` | 敵対的レビュー（`--auto-contents-review`）および Code Review Agent（`--auto-coding-agent-review`）で使用するモデル（省略時は `--model` と同じ） | `None`（`--model` にフォールバック） |
| `--qa-model` | QA 質問票生成（`--auto-qa`）で使用するモデル（省略時は `--model` と同じ） | `None`（`--model` にフォールバック） |
| `--akm-model` | QA 回答から起動する AKM 差分同期（`--auto-qa` 有効時）で使用するモデル | `None`（`--model` にフォールバック） |
| `--akm-reasoning-effort` | 同 AKM 実行の reasoning effort | `None`（`--reasoning-effort` にフォールバック） |
| `--akm-context-tier` | 同 AKM 実行の context tier（`default` / `long_context`） | `None`（`--context-tier` にフォールバック） |
| `--max-parallel` | 同時実行するステップ数の上限 | `15` |
| `--auto-qa` | 各ステップ後に自動 QA を実行（対話的） | `false` |
| `--auto-contents-review` | 各ステップ後に自動レビューを実行 | `false` |
| `--auto-coding-agent-review` | 全ステップ完了後に Code Review Agent レビューを実行（`--repo` / `GH_TOKEN` 不要、ローカル SDK で実行） | `false` |
| `--auto-coding-agent-review-auto-approval` | Code Review Agent の修正プランを全て自動承認 | `false` |
| `--timeout` | idle タイムアウト秒数 | `21600`（6時間） |
| `--review-timeout` | Code Review Agent レビュー完了待ちタイムアウト秒数 | `7200`（2時間） |
| `--show-stream` | モデル応答のトークンストリーム表示 | `false` |
| `--log-level` | Copilot CLI のログレベル (`none`/`error`/`warning`/`info`/`debug`/`all`) | `error` |
| `--no-color` | ANSI カラー出力を無効化する（`NO_COLOR` 環境変数でも制御可能。[no-color.org 規格](https://no-color.org/) 準拠） | `false` |
| `--banner` / `--no-banner` | インタラクティブモード（`run` / 引数なし起動）の起動時バナー表示を制御する。`orchestrate` サブコマンドではバナーは表示されないため効果なし | 表示 |
| `--screen-reader` | スクリーンリーダー対応モード: 絵文字を日本語ラベルに置換し、スピナーを無効化する（ラベル訳語は提案値で Copilot CLI 実機との一致は未確認） | `false` |
| `--timestamp-style` | タイムスタンプ表示位置: `prefix`=行頭（デフォルト）/ `suffix`=行末（DIM）/ `off`=非表示 | `prefix` |
| `--final-only` | DAG 完了時のサマリと各ステップの最終応答のみを出力する（CI/スクリプト連携用）。timestamp/カラー/スピナーを自動無効化する | `false` |

> **⚠️ `--auto-contents-review` と `--auto-coding-agent-review` の同時有効化について**:
> 両オプションを同時に有効にすると、同一成果物に対してレビューセッションが重複し、**トークン消費・タスク回数が増える**可能性があります。
> 同時有効化時は CLI 起動時に WARNING が表示されます（強制終了はしません）。
> 通常はどちらか一方を選択してください:
> - `--auto-contents-review` … ステップごとに敵対的レビューを実行（Phase 3 組み込み）
> - `--auto-coding-agent-review` … 全ステップ完了後に Code Review Agent が差分全体をレビュー

#### Cloud Session オプション

`orchestrate` には Step セッションを Copilot SDK の Cloud Sessions で実行するための `--cloud-session` 系オプションがあります（既定は無効）。オプション一覧・自動振り分け・フォールバック・設定正本は [cloud-session.md](./cloud-session.md) を正典とします。HVE Cloud 版（Issue Template 起点）とは別機能です。

#### 環境変数

| 環境変数 | 説明 | 既定値 |
|---------|------|--------|
| `GH_TOKEN` | GitHub API 認証トークン（GitHub 書込み startup preflight 対象時に必要） | なし |
| `GITHUB_TOKEN` | `GH_TOKEN` 未設定時のフォールバックトークン | なし |
| `REPO` | 対象リポジトリ（`owner/repo`） | なし |
| `COPILOT_CLI_PATH` | Copilot CLI 実行ファイルパス | 自動検出 |
| `REVIEW_MODEL` | レビュー用モデルの環境変数既定値（CLI 未指定時に使用） | なし |
| `QA_MODEL` | QA 用モデルの環境変数既定値（CLI 未指定時に使用） | なし |
| `NO_COLOR` | 空でない値を設定すると ANSI カラー出力を無効化する（[no-color.org 規格](https://no-color.org/) 準拠）。`--no-color` フラグと同等 | なし（未設定） |

> **注意**: `--auto-contents-review` を有効にすると、Phase 3 の評価は `review_model` の値に依らずメイン Step とは別の新しいセッションで行います（FR-CLI-92）。`--auto-qa` で QA 用サブセッション（`--qa-model` で別モデルを指定した場合、または Work IQ が有効な場合）が作られる場合と合わせて、1ステップあたり最大 3 セッション（メイン + QA + レビュー）が起動する場合があります。評価者は判定と指摘だけを行い、成果物を修正しない。指摘の反映は `apply_review_improvements_to_main` が有効なときにメインセッションが行います（無効のときは再レビューせず初回の判定で確定します。FR-CLI-94）。
>
> **注意**: `--akm-*` の 3 つは QA 回答からバックグラウンド起動される Knowledge Management 子プロセスにだけ効きます。`--workflow akm` を明示指定した実行には適用されず、その場合は従来どおり `--model` / `--reasoning-effort` / `--context-tier` に従います。対話ウィザードでは `--qa-akm-background-merge` を有効にしたときだけ 3 項目を尋ねます（既定はいずれも継承）。
>
> **注意（既定値の変更）**: 以前は `--auto-qa` を指定するだけで QA 回答から Knowledge Management が常にバックグラウンド起動されていました。現在は `--qa-akm-background-merge` を明示指定したときだけ起動します（既定無効）。従来と同じ挙動にするには本フラグを追加してください。共有資産である `knowledge/` への自動書込みを利用者が選べるようにするための変更です。
>
> **注意**: `--akm-*` には環境変数経路がありません。`--akm-reasoning-effort` / `--akm-context-tier` は継承元の `--reasoning-effort` / `--context-tier` 自体に環境変数経路が無いためで、`--akm-model` も 3 項目の指定方法を揃える目的で CLI フラグ専用としています（`MODEL` / `REVIEW_MODEL` / `QA_MODEL` に相当する `AKM_MODEL` はありません）。
>
> **注意**: GitHub Actions 経路（`@copilot` メンション起動）ではモデル指定はできません。

### コンソール出力レベル詳細（--verbosity / --log-level）

`hve` には **2 つの独立したログ関連パラメータ** があります。それぞれが制御する対象と影響範囲を理解することで、用途に応じた最適な設定が可能になります。

#### --verbosity と --log-level の関係

| 項目 | `--verbosity` | `--log-level` |
|------|--------------|--------------|
| 制御対象 | HVE CLI Orchestrator の出力 | Copilot CLI プロセスの内部ログ |
| デフォルト | `compact`（1） | `error` |
| 影響範囲 | ステップ進捗・ツール実行・Agent 応答・セッション情報 | CLI プロセスの環境読み込み・ファイル操作・検索活動 |

> **注**: `--verbose` / `--quiet` フラグは `--verbosity verbose` / `--verbosity quiet` の省略形。`--verbosity` が明示指定された場合はそちらが優先される。

#### --verbosity 各レベルの出力比較

`console.py` のメソッドごとの振る舞いをソースコードから正確に反映した表です。

| 出力イベント | quiet (0) | compact (1) | normal (2) | verbose (3) |
|------------|-----------|------------|-----------|------------|
| **エラー (error)** | ✅ 常に表示 | ✅ 常に表示 | ✅ 常に表示 | ✅ 常に表示 |
| **警告 (warning)** | 非表示 | ✅ 表示 | ✅ 表示 | ✅ 表示 |
| **セッションエラー** | ✅ 常に表示 | ✅ 常に表示 | ✅ 常に表示 | ✅ 常に表示 |
| **ステップ開始/完了** | 非表示 | ✅ 確定行 | ✅ 確定行 | ✅ 確定行 |
| **実行計画・DAG 進捗** | 非表示 | ✅ 確定行 | ✅ 確定行 | ✅ 確定行 |
| **Wave 開始** | 非表示 | ✅ 確定行 | ✅ 確定行 | ✅ 確定行 |
| **最終サマリー** | 非表示 | ✅ 確定行 | ✅ 確定行 | ✅ 確定行 |
| **ツール実行 (tool)** | 非表示 | スピナー更新 | スピナー更新 | ✅ 確定行 |
| **ツール失敗 (tool_result)** | 非表示 | ✅ 確定行 | ✅ 確定行 | ✅ 確定行 |
| **エージェント意図 (intent)** | 非表示 | スピナー更新 | ✅ 確定行 | ✅ 確定行 |
| **Sub-agent 開始** | 非表示 | スピナー更新 | スピナー更新 | ✅ 確定行 |
| **Sub-agent 完了/失敗** | 非表示 | スピナー更新 | ✅ 確定行 | ✅ 確定行 |
| **Agent 選択** | 非表示 | スピナー更新 | スピナー更新 | ✅ 確定行 |
| **Skill 読み込み** | 非表示 | スピナー更新 | スピナー更新 | ✅ 確定行 |
| **ターン開始/終了** | 非表示 | スピナー更新 / 非表示 | スピナー更新 / 非表示 | ✅ 確定行 |
| **アシスタント応答概要** | 非表示 | スピナー更新 | スピナー更新 | ✅ 確定行 |
| **トークン使用量 (usage)** | 非表示 | スピナー更新 | スピナー更新 | ✅ 確定行 |
| **コンテキスト使用率** | 非表示 | ⚠️ 80%超時のみ確定行 | ⚠️ 80%超時のみ確定行 | ✅ 確定行 |
| **コンテキスト圧縮** | 非表示 | スピナー更新 | スピナー更新 | ✅ 確定行 |
| **タスク完了 (task_complete)** | 非表示 | スピナー更新 | ✅ 確定行 | ✅ 確定行 |
| **セッション終了統計** | 非表示 | ✅ 確定行 | ✅ 確定行 | ✅ 確定行 |
| **パーミッション** | 非表示 | スピナー更新 | スピナー更新 | ✅ 確定行 |
| **並列バッチ (dag_batch)** | 非表示 | 非表示 | 非表示 | ✅ 確定行 |
| **アシスタント最終発話 (final_message)** | 非表示 | ✅ 確定行 (●) | ✅ 確定行 (●) | ✅ 確定行 (●) |
| **ストリーム表示** | 非表示 | `--show-stream` 時のみ | `--show-stream` 時のみ | `--show-stream` 時のみ |

> **「確定行」と「スピナー更新」の違い**: 確定行はターミナルに行として残り、ログとしてスクロールバックで確認可能。スピナー更新は最終行を上書きし続けるため、最新の状態のみ表示される（TTY 接続時のみ）。

#### --verbosity 各レベルの出力サンプル例

以下のコマンドをベースとした想定出力例です。

```bash
python -m hve orchestrate --workflow aad-web --branch main --verbosity <LEVEL>
```

**quiet — エラーのみ**:

```text
(正常時は何も表示されません。エラー発生時のみ表示されます)
[14:30:22] ❌ ERROR: Step.1.1 実行中にエラーが発生しました: Session expired
```

**compact — 重要イベントのみ（デフォルト）**:

```text
[14:30:15] ⠋ 🔧 [1.1] bash(1) ruff check src/...     ← スピナー（最終行を上書き）
[14:30:15]   ┊ ● Environment loaded: 22 custom instructions
[14:30:15]   ▶ [Step.1.1] ドメイン分析 (Agent: Arch-Microservice-DomainAnalytics)
[14:30:15]   ── Wave 1/5 ────────────────────────────────────
[14:30:15]   ▸ Step.1.1 ‖ Step.1.2
[14:30:15]   進捗: ████░░░░░░░░░░░░ 4/16 完了 | 実行中 2 | 残り 10
[14:30:15]   ✅ [Step.1.1] success (45.2s) [tokens: in=12500 out=3200 tools=8]
[14:30:15]   📈 [1.1] Stats: +120/-15 lines, 3 files, 5 reqs, 45200ms
● ドメインモデル定義を docs/domain-model.md に出力しました。エンティティ 12 件を定義しました。
  ┌────────────────────────────────────────────────┐
  │ 実行サマリー                                     │
  ├────────────────────────────────────────────────┤
  │ 合計ステップ : 16                                │
  │ ✅ 成功      : 16                               │
  │ ❌ 失敗      : 0                                │
  │ ⏭️  スキップ  : 0                               │
  │ ⏱️  合計時間  : 320.5s                          │
  └────────────────────────────────────────────────┘
```

**normal — compact + intent/subagent**:

```text
[14:30:15]   ┊ ● Environment loaded: 22 custom instructions
[14:30:15]   ┊ ● Read-only remote session
[14:30:15]   ▶ [Step.1.1] ドメイン分析 (Agent: Arch-Microservice-DomainAnalytics)
[14:30:15]   ┊ Phase 1/2: メインタスク
[14:30:16]   💡 [1.1] docs/ 配下のドメイン分析テンプレートを参照します
[14:30:20]   ✅ [1.1] Sub-agent 完了: Arch-Microservice-DomainAnalytics
[14:30:25]   🏁 [1.1] タスク完了: ドメインモデル定義を docs/domain-model.md に出力
[14:30:25]   ┊ Phase 1/2: メインタスク ✓ (10.2s)
[14:30:25]   ✅ [Step.1.1] success (45.2s) [tokens: in=12500 out=3200 tools=8]
[14:30:25]   📈 [1.1] Stats: +120/-15 lines, 3 files, 5 reqs, 45200ms
● ドメインモデル定義を docs/domain-model.md に出力しました。エンティティ 12 件を定義しました。
```

**verbose — 全詳細**:

```text
[14:30:15]   ┊ ● Environment loaded: 22 custom instructions
[14:30:15]   ┊ ● Read-only remote session
[14:30:15]   ┊ ○ List directory docs
[14:30:15]   ┊   └ ".github/prompts/Arch-Microservice*"
[14:30:15]   ▶ [Step.1.1] ドメイン分析 (Agent: Arch-Microservice-DomainAnalytics)
[14:30:15]   ┊ Phase 1/2: メインタスク
[14:30:15]   🤖 [1.1] Agent 選択: Arch-Microservice-DomainAnalytics
[14:30:15]   📚 [1.1] Skill: domain-analysis
[14:30:15]   🔄 [1.1] ターン開始
[14:30:16]   💡 [1.1] docs/ 配下のドメイン分析テンプレートを参照します
[14:30:16]   🔧 [1.1] bash(1) ruff check src/
[14:30:16]   ✓ [1.1] ツール完了
[14:30:17]   🔧 [1.1] edit_file(2) docs/domain-model.md
[14:30:17]   ✓ [1.1] ツール完了
[14:30:18]   🔧 [1.1] grep(3) pattern:Entity
[14:30:18]   ✓ [1.1] ツール完了
[14:30:19]   💬 [1.1] 応答 (2450 chars, ツール要求: 2)
[14:30:20]   📊 [1.1] claude-opus-4.7 in=8500 out=2450 3200ms
[14:30:20]   ▶ [1.1] Sub-agent: Arch-Microservice-DomainAnalytics
[14:30:25]   ✅ [1.1] Sub-agent 完了: Arch-Microservice-DomainAnalytics
[14:30:25]   📏 [1.1] Context: 15200/200000 (8%) msgs=12
[14:30:25]   🔄 [1.1] ターン終了
[14:30:25]   🏁 [1.1] タスク完了: ドメインモデル定義を docs/domain-model.md に出力
[14:30:25]   🔐 [1.1] パーミッション要求: file_write
[14:30:25]   🔐 [1.1] パーミッション: approved
[14:30:25]   ┊ Phase 1/2: メインタスク ✓ (10.2s)
[14:30:25]   ✅ [Step.1.1] success (45.2s) [tokens: in=12500 out=3200 tools=8]
[14:30:25]   📈 [1.1] Stats: +120/-15 lines, 3 files, 5 reqs, 45200ms
● ドメインモデル定義を docs/domain-model.md に出力しました。エンティティ 12 件を定義しました。
```

#### --log-level の出力説明

`--log-level` は Copilot CLI プロセスの内部ログ制御であり、hve の `console.cli_log()` メソッド経由で表示されます。ただし表示は `--verbosity` の設定にも依存します。

| log-level | CLI が出力するログの範囲 |
|-----------|----------------------|
| `none` | ログ出力なし |
| `error` | エラーのみ（デフォルト） |
| `warning` | error + 警告 |
| `info` | warning + 情報（Agent ロード、ファイル操作等） |
| `debug` | info + デバッグ詳細（API リクエスト/レスポンス等） |
| `all` | 全ログ出力 |

> **自動昇格**: `--verbosity verbose` かつ `--log-level` が `error` の場合、CLI のログレベルは自動的に `debug` に昇格されます（`error` がデフォルト値のため、`--log-level` 未指定時もこれに含まれます）。

#### 推奨設定ガイド

| 用途 | 推奨設定 |
|------|---------|
| 通常運用 | `--verbosity compact`（デフォルト） |
| 進捗を詳しく確認したい | `--verbosity normal` |
| 問題調査・デバッグ | `--verbosity verbose --log-level debug` |
| CI/CD パイプライン | `--quiet` または `--verbosity quiet` |
| CI で最終結果のみ取得 | `--final-only` |
| ログファイルに保存 | `--verbosity verbose --log-level all 2>&1 \| tee run.log` |

#### `--final-only` モード（CI/スクリプト連携）

進捗ログを抑止し、各ステップの最終応答と DAG 全体のサマリのみを出力するモード。

```bash
# CI で結果のみを取得したい場合
python -m hve orchestrate --workflow aas --final-only > result.txt
```

このモードでは以下が自動的に強制される:
- `verbosity=0`（中間イベント抑止）
- タイムスタンプ抑止（機械可読性向上）
- カラー出力抑止（pipe 前提）
- スピナー無効化

> **注意**: `--final-only` での summary 出力フォーマット（`=== 実行サマリー ===` 等）は hve の提案値であり、Copilot CLI 実機との一致は保証しません。

#### CLI 接続オプション

| オプション | 説明 | デフォルト値 |
|-----------|------|------------|
| `--cli-path` | Copilot CLI 実行ファイルパス | 自動検出 |
| `--cli-url` | 外部 CLI サーバー URL（`--cli-path` の代わり） | なし |

#### Issue/PR 作成オプション

| オプション | 説明 | デフォルト値 |
|-----------|------|------------|
| `--create-issues` | 実行前に GitHub Issue を作成 | `false` |
| `--assign-copilot-agent` | `--create-issues` で当該 run が新規作成した Root Issue を Copilot cloud agent へ割り当てる | `false` |
| `--create-pr` | 実行後に GitHub PR を作成 | `false` |
| `--create-working-branch` / `--no-create-working-branch` | PR 用の作業ブランチを新規作成するか | `true`（新規作成する） |
| `--repo` | リポジトリ名（`owner/repo` 形式） | `$REPO` 環境変数の値、未設定時は空（`--create-issues` / `--create-pr` 使用時は必須） |

> **`--no-create-working-branch`（現在のブランチを使う）**:
> 既定では `--create-issues` / `--create-pr` を指定すると、ベースブランチから新しい作業ブランチを作成して checkout します。

`--assign-copilot-agent` は `--create-issues` と併用したときだけ有効です。Root Issue 作成直後、Sub-Issue 作成より前に割り当てます。`--issue-number` で既存 Root Issue を使う場合、または `--create-issues` を指定しない場合は警告して無視し、既存 Issue を割り当てません。

割当 API は public preview です。割当応答で Copilot assignee を確認できない場合は fail-closed で run を停止します。この時点で Root Issue は作成済みですが、同じ Root Issue を再作成せず、作成済み番号をエラーへ残します。当該 run が作成した作業ブランチだけを cleanup し、利用者所有の現在 branch は削除しません。
> `--no-create-working-branch` を指定すると、**現在 checkout 中のブランチをそのまま PR の head として使い、checkout を行いません**。
> 実行開始前に次のいずれかに該当すると、Agent セッションを開始せずに停止します（自動で stash / reset / pull / force-push は行いません）。
>
> - 現在のブランチを特定できない（detached HEAD を含む）
> - 現在のブランチ名がベースブランチと同じ
> - ブランチ名として不正
> - 未コミットの変更または未追跡ファイルがある
> - `origin/<現在のブランチ>` が存在するのにローカル HEAD と別コミットを指している（存在しない場合は初回 push として許容）
>
> この方法で使ったブランチは**利用者所有**とみなし、PR がマージされても自動削除しません。
> ADFDV / ASDW-WEB など、リモート CI/CD の実行契約が専用ブランチを必要とする経路では、本オプションに関わらず必要なブランチが作成されます。

#### エラーハンドリング オプション

| オプション | 説明 | デフォルト値 |
|-----------|------|------------|
| `--strict` | Pre-check（入力成果物・必須 Skill）失敗時に従来通り中断する。指定しない場合は **警告に降格して続行**（local 実行モード既定の continue-on-precheck）。<br>※ Cloud（GitHub Actions / `github` 実行モード）では本フラグは無視され、常に従来通り中断する。 | `false`（=continue-on-precheck 有効） |

**continue-on-precheck モードの仕様**:

- **Pre-check 失敗時**（入力成果物・必須 Skill 不足）: ⚠️ 警告を出力して続行。警告内容は LLM のプロンプトに注入され、不確定値は `TBD（推論: <根拠>）` として処理される。
- **Step 失敗時**: **ワークフロー全体を停止**（continue-on-precheck の有無に関わらず R1 に従う）。
- **致命的エラー検出時**（`KeyboardInterrupt` / `SystemExit` / `OSError(ENOSPC,EIO,EROFS,ENOMEM)` / `FileNotFoundError` / `PermissionError`）: 残ステップを `skipped (reason=fatal-abort)` でマークし、正常終了（exit 0）。journal に `fatal=true` が記録される。
- **GUI からの起動**: 設定画面「基本設定」の「Pre-check 失敗で中断する (strict)」で切り替えます。既定は無効（continue-on-precheck 有効）で、有効にすると `--strict` が渡されます。Prompt 版も同じ保存値を引き継ぎ、依頼文の中で run 単位に上書きできます。
- **Cloud (`execution_mode=github`)**: 影響なし（従来通り Pre-check で中断）。

> **これらは全てオプションです。GitHub に Issue/PR を作成せずローカル実行のみで完結できます。**

> **⚠️ `--create-pr` と Issue Template の `auto_merge` の違い**:
> `--create-pr` は PR を作成するだけで、**自動マージ（auto-merge）は行いません**。
> Issue Template 起動では `auto_merge: true` チェックを入れると QA・レビュー完了後に自動 Approve + squash merge まで実行されますが、hve の `--create-pr` にはこの機能はありません。
> PR のレビュー・承認・マージはユーザーが手動で行う必要があります。
> 完全自動マージが必要な場合は Issue Template 側の `auto_merge` オプションを使用してください。

> **`$REPO` 環境変数の設定方法**: `--create-issues` または `--create-pr` を使用する場合は `owner/repo` 形式でリポジトリを指定してください。環境変数で設定する場合は以下のコマンドを使用します。
> ```bash
> # macOS / Linux
> export REPO="owner/your-repository-name"
> # Windows PowerShell
> $env:REPO = "owner/your-repository-name"
> ```
> 未設定かつ `--repo` オプションも省略された場合、`--create-issues` / `--create-pr` 使用時はエラーになります。

#### その他のオプション

> **注**: 以下は主要な追加オプションです。完全なオプション一覧は `python -m hve orchestrate --help` で確認してください。

| オプション | 説明 | デフォルト値 |
|-----------|------|------------|
| `--ignore-paths` | `git add` 時に除外するパス（スペース区切りで複数指定可） | `docs images infra qa src test work` |
| `--additional-prompt` | 全 Prompt の末尾に追記する文字列。長文は直接貼らずファイルへ保存し、そのパスを書くこと（下記「プロンプトのサイズ上限」参照） | なし |
| `--issue-title` | Root Issue 作成時のタイトルを上書き | ワークフロー名から自動生成 |
| `--issue-number` | 既存の Issue #N へ連携する。`--create-issues` との併用では Root Issue を新規作成せず、Sub-Issue の親と PR 本文の `Closes #N` に用いる。`--create-pr` だけとの併用では Issue を作成せず、PR の closing target にだけ用いる。どちらも伴わない場合は警告して無視する。指定 Issue を取得できない場合は実行を中止する（新規作成へ戻らない） | なし（新規作成） |

#### プロンプトのサイズ上限

HVE は各 Step のメインタスクを送信する前に、プロンプトの UTF-8 バイト数を計測して内部予算と照合します。

- 予算内なら、プロンプトを改変せずにそのまま 1 回送信します。
- 予算を超える場合は、Phase 1 の主モデルを 1 回も呼び出さずに Step を失敗させ、プロンプトのバイト数・予算バイト数・成分別バイト数を表示します。
- 診断には判定状態・バイト数・予定した Phase 1 呼び出し回数だけを表示し、プロンプト本文、`--additional-prompt` の本文、事前 QA の応答本文、認証情報は表示しません。

判定は、受領した Step プロンプト、Phase 0 前に確定する Agent / policy / suffix を含むプロンプト、事前 QA 後の最終プロンプト、の 3 段階です。最終段階だけで超過した場合は事前 QA は実行済みですが、Phase 1 の主モデル呼び出しは行いません。成分別バイト数には区切り・固定見出し・各 suffix も含まれ、合計は最終プロンプトのバイト数と一致します。dry-run では従来どおり SDK を起動せず、サイズ予算を理由に失敗へ変更しません。

自動切り詰め・自動要約・複数ターンへの自動分割・自動再送は行いません。要求が欠落したまま実行が続くと、成果物の欠落を検出できなくなるためです。超過したときは、長文をファイル化してパスだけを渡す、`--steps` で実行範囲を分割する、などで入力を小さくして再実行してください。

> 予算値は HVE 内部の安全余白であり、GitHub Copilot API の公開仕様値ではありません。CLI オプション・環境変数では変更できません。`--context-max-chars` は事前 QA へ注入する補助コンテキストの文字数上限であり、本予算とは別の設定です。

> **Work IQ との関係**: このサイズ計画の対象は Phase 1 のメインタスクです。Work IQ は `--auto-qa` と `--workiq` が有効な QA フェーズでのみ使用されるため、この機能は Work IQ の `ask` クエリを分割・再送するものではありません。Work IQ 固有の動作は「[QA フェーズにおける Work IQ の扱い](#qa-フェーズにおける-work-iq-の扱い)」を参照してください。

#### ワークフロー固有オプション

| オプション | 説明 | 対応ワークフロー |
|-----------|------|--------------|
| `--company-name` | ARD の対象企業名。表示グループ `1`（実 Step `1` / `1.1` / `1.2`）を実行する場合だけ必須 | `ard` |
| `--target-business` | ARD の対象業務名。グループ `2` をグループ `1` なしで実行する場合は必須。グループ `1` を含めて省略した場合は、Step `1.2` 完了後の Strategic Recommendation から生成する。値はフォルダパス／複数ファイルパスも可能。パスを指定した場合、Prompt へはファイル本文ではなく相対パス一覧・件数・合計バイト数・有界なスキップ理由／解決エラーが渡り、Agent が各ファイルを読み取りツールで参照する。リポジトリ外のパス名は匿名化される | `ard` |
| `--target-recommendation-id` | ARD のグループ `1` + `2` bridge 経路で採用する SR の ID（例: `SR-1`）。明示値を優先し、不一致なら警告して先頭へ縮退。省略した非対話実行では先頭 SR を自動採用 | `ard` |
| `--survey-base-date` / `--survey-period-years` / `--target-region` / `--analysis-purpose` / `--attached-docs` | ARD の調査条件 | `ard` |
| `--app-ids` | APP-ID をカンマ区切りで複数指定 | `aad-web`, `asdw-web`, `adfd`, `adfdv`, `aag`, `aagd` |
| `--app-id` | 主対象 APP-ID（後方互換。新規利用は `--app-ids` 推奨） | `aad-web`, `asdw-web`, `adfd`, `adfdv`, `aag`, `aagd` || `--resource-group` | Azure リソースグループ名 | `asdw-web`, `adfdv`, `aagd` |
| `--usecase-id` | ユースケース ID | `asdw-web`, `aag`, `aagd` |
| `--app-id` | データフローアプリ ID（カンマ区切り可） | `adfdv` |
| `--tdd-max-retries` | TDD GREEN フェーズの再試行上限。未指定時は環境変数 `HVE_TDD_MAX_RETRIES`、それも無ければ既定値 | `asdw-web`, `adfdv`, `aagd` |
| `--create-remote-mcp-server` / `--no-create-remote-mcp-server` | Knowledge Base を Remote MCP Server として公開するか。未指定時は Workflow の既定値に従う | `aad-web`, `asdw-web` |
| `--sources` | AKM の取り込み元（`qa` / `docs-original` / `both`） | `akm` |
| `--target-files` | AKM の対象ファイル（省略時は選択ソース配下の全件） | `akm` |
| `--force-refresh` / `--no-force-refresh` | AKM の status 再生成制御 | `akm` |
| `--custom-source-dir` | AKM の追加ソースディレクトリ | `akm` |
| `--enable-auto-merge` | PR 自動 Approve & Auto-merge。有効時は ASDW-WEB / ADFDV で Deploy 成果物の push / PR / merge 待機にも使用 | `asdw-web`, `adfdv`, `akm` |
| `--purpose` | ADI の設計書選別目的（空の場合は `must` を付与しない） | `adi` |
| `--target-scope` | ADI の確認対象スコープ（`docs-original/` またはその配下） | `adi` |
| `--depth` | ADI の分析深さ（`standard` / `lightweight`） | `adi` |
| `--focus-areas` | ADI の重点観点 | `adi` |
| `--target-dirs` | ADOC の対象ディレクトリ | `adoc` |
| `--exclude-patterns` | ADOC の除外パターン | `adoc` |
| `--doc-purpose` | ADOC の文書目的（`all` / `onboarding` / `refactoring` / `migration`） | `adoc` |
| `--max-file-lines` | ADOC の大規模ファイル分割閾値 | `adoc` |

> **ARD の `--steps` 省略時**: `target_business` の有無では実行グループを切り替えず、常に表示グループ `2,3,4` を選択します。したがって通常は `--target-business` を併記してください。企業分析から bridge したい場合は `--steps 1,2,3,4 --company-name "..."` を明示します。
>
> **対話ウィザードとの差**: `--target-recommendation-id` 相当の事前質問は、カスタム全自動でグループ `1` + `2` の bridge 条件を満たす場合だけ表示します。クイック全自動は先頭 SR、手動は Step `1.2` 後の選択メニュー（既定: 先頭）を使います。

> **ワークフロー固有パラメータの指定面**: `--create-remote-mcp-server` / `--tdd-max-retries` は、直接 CLI・GUI・Prompt 版の 3 面すべてから指定できます。GUI では対象 Workflow を選んだときだけ Step 1 のワークフロー枠に入力欄が現れます（全体設定としては保存されません）。どちらも未指定のときは従来どおり対話ウィザードまたは既定値が使われます。

### 使い方の例

#### 基本実行

```bash
python -m hve orchestrate --workflow aad-web
```

#### QA + Review 有効

```bash
python -m hve orchestrate \
  --workflow aad-web \
  --branch main \
  --auto-qa \
  --auto-contents-review
```

> QA 有効時はステップごとにユーザーの回答入力が求められる対話的な実行になります。

#### ResourceSnapshot を前提にした実行

```bash
python -m hve orchestrate \
  --workflow aad-web \
  --branch main \
  --auto-qa
```

> Plugin / MCP / Skill の install / config / auth は Copilot CLI 側で事前設定します。HVE CLI は local session で同じ ResourceSnapshot を読むだけです。

#### Issue/PR 作成有効

```bash
python -m hve orchestrate \
  --workflow aas \
  --branch main \
  --repo OWNER/REPOSITORY \
  --create-issues \
  --create-pr
```

> `GH_TOKEN` または `GITHUB_TOKEN` が必要です。どちらも未設定の場合、startup preflight で終了します。

#### 複数 APP-ID 指定（ASDW）

```bash
# 複数の APP-ID をカンマ区切りで指定
python -m hve orchestrate \
  --workflow asdw-web \
  --app-ids APP-01,APP-02,APP-03 \
  --resource-group rg-dev \
  --usecase-id UC-01

# 単一 APP-ID（後方互換、--app-ids 推奨）
python -m hve orchestrate \
  --workflow asdw-web \
  --app-id APP-01 \
  --resource-group rg-dev
```

> **2度目実行時の既存成果物再利用**: ワークフロー実行開始時に `docs/`・`src/`・`test/`・`knowledge/` 配下の既存成果物が自動検出されます。既存成果物が見つかった場合、「既存成果物を検出しました（N 件）。再利用モードで実行します。」と表示され、各ステップのプロンプトに再利用ルールが追記されます。Catalog ファイルは既存エントリを保持したまま新規エントリが追加されます。

> **Autopilot 実行時の APP-ID 絞り込み**: Autopilot 経路（`python -m hve orchestrate --autopilot-chain <workflow_id,...>` で複数 APP を並列実行する内部モード。GUI Workbench の Autopilot ON 時にも自動で使用される）では、`--app-ids`（または後方互換の `--app-id`）を指定すると **その APP-ID のみが計画対象** となります（catalog 全件ではなく指定分のみ）。catalog に存在しない指定 ID や、`--autopilot-chain` で選んだ workflow とアーキテクチャ不一致の APP は計画サマリの `skipped` セクションに記録されます。APP-ID 指定なし（`--app-ids` / `--app-id` 共に未指定）のときは従来どおり catalog 全件が対象です。APP-ID 比較は大文字小文字を正規化して行われます。

#### Code Review Agent 有効

```bash
python -m hve orchestrate \
  --workflow aad-web \
  --branch main \
  --auto-coding-agent-review
```

自動承認を有効にする場合は `--auto-coding-agent-review-auto-approval` を追加してください。

> **前提**: Code Review Agent はローカル SDK で実行するため、単独では `GH_TOKEN` / `--repo` を要求しません。GitHub 書込み機能を併用した場合だけ、その機能の startup preflight 条件が適用されます。

---

## ワークフロー一覧

`hve/workflow_registry.py` に登録されている workflow を、正規 ID・ステップ数・主要パラメータ・最小 dry-run 例で整理します。

| Workflow ID | 名称 | Step 数 | 主な固有パラメータ | 最小 dry-run 例 |
|-------------|------|--------:|--------------------|-----------------|
| `ard` | Auto Requirement Definition | 10 | `--company-name`、`--target-business`、`--target-recommendation-id`、`--survey-base-date`、`--survey-period-years`、`--target-region`、`--analysis-purpose`、`--attached-docs`、`--include-kpi-okr`（後方互換） | `python -m hve orchestrate --workflow ard --target-business "ロイヤルティ事業" --dry-run` |
| `aas` | Architecture Design | 10 | なし | `python -m hve orchestrate --workflow aas --dry-run` |
| `aad-web` | Web App Design | 8 | `--app-ids`、`--app-id` | `python -m hve orchestrate --workflow aad-web --app-ids APP-01 --dry-run` |
| `asdw-web` | Web App Dev & Deploy | 21 | `--app-ids`、`--app-id`、`--resource-group`、`--usecase-id`、`--tdd-max-retries` | `python -m hve orchestrate --workflow asdw-web --app-ids APP-01 --resource-group rg-dev --usecase-id UC-01 --dry-run` |
| `adfd` | Dataflow Design | 7 | `--app-ids`、`--app-id` | `python -m hve orchestrate --workflow adfd --app-ids APP-02 --dry-run` |
| `adfdv` | Dataflow Dev | 8 | `--app-ids`、`--app-id`、`--resource-group`、`--app-id`、`--tdd-max-retries` | `python -m hve orchestrate --workflow adfdv --app-ids APP-02 --resource-group rg-batch --app-id JOB-01 --dry-run` |
| `aag` | AI Agent Design | 3 | `--app-ids`、`--app-id`、`--usecase-id` | `python -m hve orchestrate --workflow aag --app-ids APP-01 --usecase-id UC-01 --dry-run` |
| `aagd` | AI Agent Dev & Deploy | 7 | `--app-ids`、`--app-id`、`--resource-group`、`--usecase-id`、`--tdd-max-retries` | `python -m hve orchestrate --workflow aagd --app-ids APP-01 --resource-group rg-agent --usecase-id UC-01 --dry-run` |
| `aar` | Agentic Retrieval Add-on | 7 | `--app-ids`、`--app-id`、`--resource-group`、`--usecase-id` | `python -m hve orchestrate --workflow aar --app-ids APP-01 --resource-group rg-search --usecase-id UC-01 --dry-run` |
| `akm` | Knowledge Management | 2 | `--sources`、`--target-files`、`--force-refresh`、`--custom-source-dir`、`--enable-auto-merge` | `python -m hve orchestrate --workflow akm --sources both --dry-run` |
| `adi` | Auto Design-doc Ingestion | 9 | `--purpose`、`--target-scope`、`--depth`、`--focus-areas` | `python -m hve orchestrate --workflow adi --target-scope docs-original/ --depth lightweight --dry-run` |
| `adoc` | Source Codeからのドキュメント作成 | 19 | `--target-dirs`、`--exclude-patterns`、`--doc-purpose`、`--max-file-lines` | `python -m hve orchestrate --workflow adoc --target-dirs src/,hve/ --doc-purpose onboarding --dry-run` |

> **補足**: `aad` / `asdw` はそれぞれ `aad-web` / `asdw-web` の後方互換エイリアスです。Issue Template / Workflow 名 / `workflow_registry` の表記に合わせ、本ガイドでは正規 ID を優先します。

> **補足**: `akm` は `--sources qa` で `qa/`、`--sources docs-original` で `docs-original/` を処理します。ADIの原本質問票生成はStep 1.1 / 1.2のmain DAGであり、`--auto-qa`による事前QAとは別です。

> **補足**: `adi` は 9 実行 Step を持ちますが、`--steps` を省略した既定実行では Step `1.1` / `1.2` を自動選択しません。原本質問票が必要な場合だけ `--steps 1,1.1,1.2,...` のように明示してください。

---

## 付録A: MCP Server 設定ガイド

### Local/Stdio サーバー

ローカルのコマンドを起動して MCP Server として使用します。

```json
{
  "filesystem": {
    "type": "local",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
    "tools": ["*"]
  },
  "custom-tool": {
    "type": "local",
    "command": "python",
    "args": ["-m", "my_mcp_server"],
    "env": {
      "MY_API_KEY": "${MY_API_KEY}"
    },
    "tools": ["search", "fetch_data"]
  }
}
```

| フィールド | 説明 |
|----------|------|
| `type` | `"local"` を指定 |
| `command` | 起動コマンド（`npx`, `python`, `node` 等） |
| `args` | コマンドの引数リスト |
| `env` | 環境変数（`${VAR}` 形式で参照可能） |
| `tools` | 使用するツール名のリスト。`["*"]` で全許可 |

### Remote HTTP/SSE サーバー

外部の HTTP エンドポイントに接続します。

```json
{
  "github": {
    "type": "http",
    "url": "https://api.githubcopilot.com/mcp/",
    "headers": {
      "Authorization": "Bearer ${GH_TOKEN}"
    },
    "tools": ["*"]
  }
}
```

| フィールド | 説明 |
|----------|------|
| `type` | `"http"` を指定 |
| `url` | MCP Server の URL |
| `headers` | HTTP ヘッダー（認証トークン等） |
| `tools` | 使用するツール名のリスト |

### Agent 固有の MCP Server

ワークフロー定義（`workflow_registry`）で特定のステップにのみ MCP Server を適用できます。詳細は [付録B](#付録b-prompt-設定ガイド) を参照してください。

---

## 付録B: Prompt 設定ガイド

### workflow_registry の custom_agent フィールド

ワークフロー定義でステップごとに `custom_agent` を指定します（フィールド名は歴史的経緯で snake_case のまま残置されており、値としては `.github/prompts/*.prompt.md` の Prompt 名を指します）。

```python
WORKFLOW_REGISTRY = {
    "aad-web": {
        "steps": [
            {
                "id": "1",
                "title": "画面一覧と画面遷移図",
                "custom_agent": "Arch-UI-List",
                "depends_on": []
            },
            {
                "id": "2.1",
                "title": "画面定義書",
                "custom_agent": "Arch-UI-Detail",
                "depends_on": ["1"]
            }
        ]
    }
}
```

`custom_agent` に指定した名前が `.github/prompts/*.prompt.md` の Prompt ファイル名に対応します。Agent 本文は `load_prompt(<Agent 名>)` の呼び出し互換を保つため flat 配置のままで、サブディレクトリ化しません。Step 本文は `.github/prompts/steps/<workflow>/step-<id>.prompt.md`（StepDef の `body_template_path`）、fan-out 追加本文は `.github/prompts/fanout/<workflow>/*.prompt.md`（同 `additional_prompt_template_path`）に置きます。

### Prompt の選択優先順位

1. ステップ固有の `custom_agent`（workflow_registry で定義）
2. デフォルト Prompt（Copilot SDK のデフォルト）

---

## 付録C: DAG 並列実行と Post-step 自動プロンプト

### DAG 並列実行

> **技術アーキテクチャ詳細**（DAG パターン・`asyncio.Semaphore` 並列制御・Fork-on-Retry の内部実装）は [hve-technical-architecture.md §4.3](./hve-technical-architecture.md#43-並列実行fork-on-retry-の詳細) を参照。

運用上の主要トピックは以下のとおり。

| パターン | 説明 | 例 |
|---------|------|-----|
| sequential | 前ステップ完了後に次が開始 | Step.1 → Step.2 |
| fork | 1ステップ完了後に複数が並列開始 | Step.6 → Step.7.1 ‖ Step.7.2 |
| AND join | 複数ステップがすべて完了後に次が開始 | Step.7.1 AND Step.7.2 → Step.7.3 |
| skip fallback | 条件不一致時にスキップ | skip_if 条件に合致 → スキップ |

> メモリ不足が発生する場合は `--max-parallel` を小さくしてください（例: `--max-parallel 3`）。

### 計画の分割と Cloud Sub-Issue 経路

計画を分割するかどうかは、モデルが作業内容から判断します。`task_scope` / `context_size` などの指標から分割を機械的に強制する規則や、`plan.md` の `split_decision`（`SPLIT_REQUIRED`）による判定は撤去済みです（FR-PLAN-01）。CLI / GUI 標準経路では、Agent が `subissues.md` を作成しても、ローカルで runtime fork しません。

- `subissues.md` は、Cloud Agent Orchestrator（Issue Template + GitHub Actions + Copilot Cloud Agent）で分割を選んだときの任意の入力です。PR の差分に `work/**/subissues.md` が含まれると `plan-validation-and-labeling.yml` が `split-mode` / `plan-only` ラベルを付け、`create-subissues` ラベルの付与後に `.github/workflows/create-subissues-from-pr.yml` が GitHub Sub-Issue を作成します。
- CLI / GUI で分割・並列化したい場合は、workflow 定義の DAG / fan-out（例: `Step.1/D01` のような展開済み Step）として表現してください。
- 以前の legacy runtime split-fork（`OrchestratorContext.split_fork_enabled=True`）は `hve` 0.8.162 で撤去しました。

#### `plan.md` / `subissues.md` の完了条件（DoD）セクション

`plan.md` と `subissues.md` の各 `<!-- subissue -->` ブロックには、`## 完了条件` セクションが必須です（FR-DOD-01 / FR-DOD-02）。

- 非空の記述を **1 行以上** 書いてください。セクション見出しだけ、空白のみ（NO-BREAK SPACE や全角空白を含む）、水平線 `---` だけ、`REPLACE_ME` を含む記述だけの状態は、いずれも欠落として拒否されます。
- テンプレート正本は [plan-template.md](../.github/skills/_hve-plan-artifacts/plan-template.md) と [subissues-template.md](../.github/skills/_hve-plan-artifacts/subissues-template.md) です。
- 保存後は、お使いの環境に合わせて次のどちらかで検証してください（bash 版と PowerShell 版は同じ判定条件です）。

  ```bash
  bash .github/scripts/bash/validate-plan.sh --path <plan.md のパス>
  bash .github/scripts/bash/validate-subissues.sh --path <subissues.md のパス>
  ```

  ```powershell
  pwsh -NoLogo -NoProfile -File .github/scripts/powershell/validate-plan.ps1 -Path <plan.md のパス>
  pwsh -NoLogo -NoProfile -File .github/scripts/powershell/validate-subissues.ps1 -Path <subissues.md のパス>
  ```

- Cloud では、`plan.md` は Pull Request で変更された `work/**/plan.md` だけが検証対象になります（[plan-validation-and-labeling.yml](../.github/workflows/plan-validation-and-labeling.yml)）。`subissues.md` は Pull Request の差分に含まれるものが対象です。差分に `subissues.md` が 1 件も含まれない場合に限り、PR に `split-mode` または `create-subissues` ラベルが付いていれば `work/` 配下の `subissues.md` を全件検索して検証します（[validate-subissues.yml](../.github/workflows/validate-subissues.yml)）。fleet mode の CLI / GUI 実行では、`subissues.md` のパース時に同じ検査が働きます。
- 本検査は **構造検査** です。セクションが存在し非空であることだけを確認するもので、記述内容が十分かどうかは保証しません。内容の妥当性は敵対的レビューと、各 Step の `output_paths` 存在ゲートで別途確認してください。

Fleet mode を CLI / GUI で使う場合は、計画の分割ではなく workflow-level fan-out / DAG wave の実行 backend として扱います。CLI では `--fleet-mode`、明示的に無効化する場合は `--no-fleet-mode` を指定します。Fleet mode は opt-in で、単一 Step の wave は従来どおり通常実行されます。

> **⚠️ Fleet wave では実行されないフェーズがあります**
>
> Fleet mode へ委譲された wave（実行可能 Step が **2 件以上** の wave）は Step 単位の実行経路を通らないため、次の 2 つは **実行されません**。
>
> | 対象 | フラグ | Fleet wave での扱い |
> |---|---|---|
> | 事前 QA（Phase 0）と QA 起点 Knowledge Management | `--auto-qa` / `--qa-akm-background-merge` | 実行されない |
> | 敵対的レビュー（Phase 3） | `--auto-contents-review` | 実行されない |
>
> これらのフラグを有効にしたまま Fleet wave を開始すると、Fleet 起動成功を確認した時点で wave ごとに 1 回警告が出ます。
>
> ```text
> Fleet wave 1: 事前 QA（および QA 起点 Knowledge Management）/ 敵対的レビュー は実行されません。Fleet mode へ委譲した wave は Step 単位の実行経路を通らないためです。これらが必要な wave では --no-fleet-mode を指定してください。
> ```
>
> 当該 wave でもこれらを実行したい場合は `--no-fleet-mode` を指定してください。fan-out する Step（例: AKM の D01〜D21）は wave の Step 数が 2 件以上になるため、Fleet mode を有効にしているとこの経路に入ります。

### Post-step 自動プロンプト（QA / Review）

`--auto-qa` はローカル CLI では既定で有効です（`--no-auto-qa` で無効。FR-KD-11）。

| フラグ | 動作 |
|--------|------|
| `--no-auto-qa` | メインタスクのみ実行 |
| 指定なし / `--auto-qa` | 事前 QA → メインタスク → 実行後の不明点調査 |
| `--no-auto-qa --auto-contents-review` | メインタスク → Review |
| 指定なし / `--auto-qa` と `--auto-contents-review` | 事前 QA → メインタスク → 実行後の不明点調査 → Review |

#### 実行後の不明点調査（FR-KD-13）

`--auto-qa` が有効な Step では、メインタスクが成功した後・Review の前に、メインタスクと同じセッションへ「実行中に不明・曖昧なため仮定を置いて進めた点」を質問票にするよう依頼します。質問が 0 件（`質問なし`）なら何も保存しません。質問がある場合は `qa/<run_id>-<step_id>-post-execution-qa.md` に保存し、知識源（Work IQ など）が使えれば知識探索で調べて `調査回答` / `調査状態` / `調査出典` を記録します。回答は `Confirmed` / `Tentative` の調査回答、それ以外は既定値候補を採用し、人への回答待ちはしません。この phase の失敗は警告だけで、Step の成否は変わりません。

#### ワークフロー別 QA フェーズ動作

注: 人に回答を求める事後 QA（旧 Phase 2 / post-QA モード）は廃止されています。v0.8.196 で追加した「実行後の不明点調査」は人への回答待ちを行いません。

| ワークフロー | 事前 QA (Phase 0) | 実行後の不明点調査 | 備考 |
|---|---|---|---|
| AAD-WEB / その他通常 | `auto_qa=True` で実行 | `auto_qa=True` で実行 | — |
| **AKM** | `auto_qa=True` で実行 | `auto_qa=True` で実行 | QA 起点 AKM の子実行は `--no-auto-qa --no-workiq` で起動する |

> 上表は **Step 単位の実行経路を通る wave** を前提としています。Fleet mode へ委譲された wave（2 Step 以上）では、ワークフローによらず事前 QA は実行されません（前節の警告を参照）。

```bash
# AKM: 事前 QA を有効化してメインタスクへ注入
python -m hve orchestrate --workflow akm --auto-qa
```

> ADI Step 1.1 / 1.2の原本質問票はmain DAGの成果物です。`--auto-qa`を付けると、それとは別に各Step前のPhase 0 QAが実行されます。

#### 事前 QA 回答からの AKM 自動同期

`--auto-qa` で質問が 1 件以上あった場合、回答済み QA ファイルは保存後に再読込・内容・全回答を検証してから、AKM（`KnowledgeManager`）へファイル単位で差分同期の実行が登録されます。Knowledge Management 自身（`--workflow akm`）は再帰を避けるため対象外です。

- メインの DAG は AKM の完了を待たずに次 Step へ進みます。
- AKM は FIFO かつリポジトリ単位のロックで直列実行され、明示的な `akm` 実行とも排他されます。同時に起動する AKM 子プロセスは常に 1 つです（AKM の出力対象は `target_files` によらず `knowledge/D01`〜`D21` 全体と `business-requirement-document-status.md` を含むため）。
- 実行開始時点でキューに滞留している登録は **1 回の AKM 子実行へまとめられます**。`--target-files` に当該バッチの全ファイルが渡り、結果は登録件数分（ファイル単位）で報告されます。
- AKM 子実行は **AKM が宣言する並列上限（`21`）** で走り、D01〜D21 の fan-out 21 件が同時に実行されます。宣言値を持つワークフローは `--max-parallel` で上書きできないため（[workflow-reference.md](./workflow-reference.md) 参照）、親の並列実行数は子実行へ影響しません。
- Git commit / branch 切替 / GUI 終了などの境界では、未完了の AKM 書き込みを残さないよう待ち合わせます。
- Cloud（GitHub Issue 経路）では、回答コメントを回答済み QA として `qa/` の固定パスへ保存し、Contents API の再取得と SHA 照合が成功してから、QA 起点 AKM 調整ワークフロー（`auto-akm-after-qa.yml`）を非同期 dispatch します。dispatch 要求が受理された時点でメインタスクのアサインへ進み、AKM の完了は待ちません。

> **インタラクティブモードでの設定**: wizard 内で「QA 自動投入を有効にする？ [Y/n]」（AKM 以外。既定 `y`）「Review 自動投入を有効にする？ [y/N]」と順番に確認されます。続く「知識探索で Work IQ を使う？」も既定は `y` です（Work IQ が利用可能な場合だけ表示）。`y` を選んだ場合のみ、各項目ごとに「メインモデルとは別モデルを使うか」を確認し、必要時のみ QA/Review 用モデル選択メニューが表示されます。CLI モードの `--auto-qa` / `--auto-contents-review` フラグに相当します。

### Code Review Agent フェーズ（`--auto-coding-agent-review`）

全ステップ完了後: Root Issue 作成 → ブランチ作成 → 全ステップ実行 → PR 作成 → Code Review Agent レビュー依頼 → レビュー完了ポーリング（デフォルト 7200秒） → 修正プロンプト

---

### フォーク機能 Fork-on-Retry

> **概要・KPI スキーマ・ロールバック手順**: 本セクションは運用ガイドとして要点のみを記載します。実装詳細（fork_kpi_logger の内部構造、新 session_id 発行の挙動）は [hve-technical-architecture.md §4.3](./hve-technical-architecture.md#43-並列実行fork-on-retry-の詳細) を参照。

#### 概要

`hve` の DAG 実行中にステップが失敗した場合、**フィーチャフラグ `HVE_FORK_ON_RETRY=true`** を設定しておくと、**1 回だけ**自動的に新しい session_id（フォーク）でリトライします。

- 既定: **OFF**（旧挙動と完全一致）
- 発火対象: 非コンテナの失敗ステップ
- リトライ回数: 1 回のみ（過剰トークン消費を防止）
- リトライも失敗した場合: 従来通り `failed` 扱い、後続ステップはブロック

#### 有効化方法

```bash
# Linux / macOS
export HVE_FORK_ON_RETRY=true
python -m hve orchestrate --workflow aas

# Windows (PowerShell)
$env:HVE_FORK_ON_RETRY = "true"
python -m hve orchestrate --workflow aas
```

#### KPI レポートの読み方

フラグ ON でフォークが発火すると、`work/kpi/fork-kpi-<run_id>.jsonl` に JSON Lines 形式でログが出力されます。フィールド定義および 3 指標（トークン量・再実行率・所要時間）の派生方法は [hve-technical-architecture.md](./hve-technical-architecture.md) を参照してください。

#### ロールバック手順

`HVE_FORK_ON_RETRY` 環境変数を `false`（または未設定）に戻して `python -m hve` を再実行するだけです。既存テスト（`hve/tests/test_dag_executor.py` 等）の挙動は変わりません。`state.json` は追加のみで後方互換を維持しています。

#### 既知の制約

- Copilot SDK 側にネイティブの `fork` API があるかは公開情報からは未確認です。本実装は **フォールバック方式**（新 session_id を発行する）です。
- リトライは **1 回限り**です。`tdd_max_retries`（TDD GREEN フェーズの再試行数）とは独立です。
- 用語: 本ガイドでは「フォーク」で統一しています（GitHub Copilot CLI の `/fork` 由来）。

---

## 付録F: Markdown 横断クエリ（markdown-query Skill）

> **本付録は HVE 固有の運用細則を含みます。汎用 Skill 仕様は [.github/skills/markdown-query/SKILL.md](../.github/skills/markdown-query/SKILL.md)、HVE 独自の統合仕様は [.github/skills/markdown-query/references/repo-specific/hve-integration.md](../.github/skills/markdown-query/references/repo-specific/hve-integration.md) を参照してください。**

Copilot / Prompt が大量の Markdown を参照する際の **Context Window を最小化** する、ローカル完結（外部 API 不使用）の Skill とその CLI（`mdq`）に関する解説です。

- Skill: `.github/skills/markdown-query/SKILL.md`
- 実装: `mdq/`（SQLite + BM25、見出し境界・コードフェンス対応）
- 索引対象（既定）: `docs/`, `docs-generated/`, `users-guide/`, `template/`, `knowledge/`, `qa/`, `docs-original/`, `work/`, `sample/`, `hve-dev/`
- 索引ファイル: `.mdq/index.sqlite`（gitignore 済、リポジトリにコミットしないこと）

### F.1 環境構築

`hve/setup-hve.ps1` / `hve/setup-hve.sh` を `-Minimal` / `--minimal` 無しで実行している場合、本ステップは既に完了しています。以下はセットアップスクリプトを使わない場合や、`[mdq]` extras のインストールが失敗した後に手動再導入する場合の手順です。

```bash
pip install -e ".[mdq-watch]"   # 任意 extras: rank_bm25 + tiktoken + watchdog（推奨）
# rank_bm25 / tiktoken だけで watcher が不要なら:
pip install -e ".[mdq]"
```

未導入時は内蔵 MiniBM25（純 stdlib）と char/4 トークン推定で動作します。

動作確認:

```bash
python -m mdq index
python -m mdq stats
python -m mdq search --q "業務要件" --top-k 3 --format compact
```

### F.2 使い方（CLI Orchestrator 実行中）

- 各 step / サブセッション開始前に `python -m mdq index` を実行（増分更新で安全）。
- Agent からの典型呼び出し:

  ```bash
  python -m mdq search --q "<クエリ>" --paths "docs/*" --top-k 5 --max-tokens 800 --format compact
  python -m mdq get --chunk-id <id>   # 必要なチャンクのみ本文取得
  ```

- `search` で hit の `chunk_id` を得てから `get` で本文取得する **2 段階パターン** が Context 最小化に最も効きます。

### F.3 ファイル追加・更新・削除時のオペレーション

- 追加・更新後: `python -m mdq index`（SHA-1 一致ファイルはスキップされ高速）。
- 強制再索引: `python -m mdq index --rebuild`。
- **削除されたファイルの処理**: `index` は既定で自動 prune を行い、指定 root 配下で **ディスク上に存在しないファイル** のチャンクを削除します（`ON DELETE CASCADE`）。手増しで DB を保ちたい場合は `--no-prune` を指定してください。`index` の summary JSON に `pruned_files` / `pruned_chunks` が含まれます。
- 他 root 配下のファイルは今回の `--root` 指定に入っていない限り prune 対象外（誤削除防止）。

### F.4 期待される効果（このリポジトリでの実測例）

計測スクリプト: [tools/skills/markdown_query/benchmark.py](../tools/skills/markdown_query/benchmark.py)。トークナイザ: `tiktoken / cl100k_base`、計測日: 2026-05-13、対象: このリポジトリ作業ツリー（旧 `tools/measure_mdq_tokens.py` による計測例、現在は benchmark.py に統合済）。

- 索引対象: **122 ファイル / 1,775 チャンク**
- 全文ベースライン: **472,841 tokens**
- mdq 応答平均（5 クエリ: 業務要件 / ARD / Bounded Context / アーキテクチャ / テスト戦略、各 `--top-k 5 --max-tokens 800`）: **1,059 tokens / query**
- **平均削減率: 99.78%**（範囲 99.68%〜99.83%）

> 上記はこのリポジトリ・この時点・このクエリ集合での実測値です。他リポジトリ・他クエリでは再計測してください。実時間（latency）は benchmark.py で計測できます（下記 §F.7 参照）。

pytest 結果: `python -m pytest hve/tests/test_mdq.py -q` → 6 passed in 3.09s（同日）。

### F.5 HVE Cloud Agent Orchestrator との関係

- Cloud runner でも同じ CLI が動作します（Python が利用可能なため）。
- Cloud runner の作業ツリーは揮発し、索引ファイル `.mdq/index.sqlite` は gitignore 済でセッション間で共有されません。**Cloud Agent セッション側で毎回 `python -m mdq index` を自身で実行**してから `search` / `get` を使う運用です（増分キャッシュは効きません）。
- 現行の `auto-*-reusable.yml` 群は GitHub Actions runner 上で Issue 作成と Copilot アサインを行うだけで、Prompt 本体は Copilot Cloud の独立セッションで動作します。そのため runner 上で事前生成した索引を Cloud Agent セッションへ渡す reusable workflow は提供しません。CI の索引スモークテストは `test-hve-python.yml` の `mdq-smoke` job が直接実行します。同じ job は、[mdq/golden-queries.json](../mdq/golden-queries.json) の golden 評価も実行し、top-k の正解数が下限を下回ると失敗します（[FR-MAINT-15](../hve-dev/requirement-definition.md)）。
- Skill 発見は `.github/skills/_routing/README.md` の planning 共通テーブル経由（CLI / Cloud 共通）。Cloud Agent 側への「必ず 1 回 `mdq index` を実行」説明は `markdown-query` Skill 本体に記載済です。

### F.6 注意点

- 削除ファイル検知は既定で有効（F.3 参照）。`--no-prune` で無効化可。
- 日本語は形態素解析を行わず 1 文字単位トークナイズ。短いクエリ・固有名詞の一部マッチで再現率が下がる場合があります。
- BM25 はクエリ時に全チャンクをメモリへロードします（現状 1,775 チャンク規模で問題なし。さらに大規模化する場合は SQLite FTS5 への移行を検討、`.github/skills/markdown-query/references/indexing-internals.md` 参照）。
- DAG 並列実行（付録 C）でサブセッションが同時に `search` を呼ぶ場合: SQLite の読み取りは並行可能、**書き込みは `index` フェーズに集約** してください（並行 `index` は推奨しません）。
- `.mdq/index.sqlite` はローカルキャッシュです。共有・コミットは不可（gitignore 済）。

### F.7 パフォーマンス確認手順（撤去判断用）

`markdown-query` Skill は Context Window 最小化のためだけに存在します。別の retrieval 手段（例: ネイティブ検索、埋め込みベース RAG）が提供された時点で撤去を判断できるよう、数値計測 CLI を同梱しています。

- スクリプト: [`tools/skills/markdown_query/benchmark.py`](../tools/skills/markdown_query/benchmark.py)
- サンプルクエリ: [`tools/skills/markdown_query/queries.sample.txt`](../tools/skills/markdown_query/queries.sample.txt)
- 詳細仕様・出力フォーマット: [`tools/skills/markdown_query/README.md`](../tools/skills/markdown_query/README.md)

**計測する 3 シナリオ**: `baseline_full`（全文投入想定）/ `mdq_bm25`（BM25 検索結果のみ）/ `mdq_grep`（grep 検索結果のみ）。同一プロセス・同一クエリ集合に対して計測します。

**実行例**:

```bash
python tools/skills/markdown_query/benchmark.py \
  --queries-file tools/skills/markdown_query/queries.sample.txt \
  --top-k 5 --max-tokens 800 --repeat 3 --ensure-index
```

**出力**: `tools/skills/markdown_query/results/bench-<UTCタイムスタンプ>.{json,md}`（`results/` は gitignore 済）。

**出力される主要指標**:

- `avg_response_tokens` — シナリオごとの平均応答トークン
- `avg_vs_baseline_savings_pct` — ベースライン比削減率（%）
- `latency_ms_all` — mean / p50 / p95 / min / max（`--repeat` 回計測のうち初回は warmup として除外）
- `per_query[].coverage_proxy` — `--queries-json` で `expected_paths` を与えた場合のみ

**撤去判断**: 本ツールは数値を出力するのみで、撤去可否の閾値は提示しません。代替手段との比較数値を見て利用者が判断してください。CI の golden ゲート（[FR-MAINT-15](../hve-dev/requirement-definition.md)）の下限は回帰を検出するためのもので、撤去の判断基準ではありません。

**既知の限界**: LLM API は呼ばないため end-to-end RAG 品質の評価ではなく、Context 投入量と検索 wall-clock の代理指標に留まります。詳細は README.md の「既知の限界」節を参照。

### F.8 リアルタイム索引更新（HVE CLI Orchestrator のみ）

`hve orchestrate` 実行中は、内蔵の **MdqWatcher** がバックグラウンドで `.md` ファイルの追加 / 更新 / 削除を OS イベントで検知し、`.mdq/index.sqlite` を逐次更新します。手動の `python -m mdq index` を都度実行しなくても、サブセッションが最新の索引を参照できます。

- **適用範囲**: HVE CLI Orchestrator のみ。Cloud Agent / GitHub Actions では動作しません（F.5 のとおり Cloud では `mdq index` を都度実行する運用のまま）。
- **既定**: ON（明示的に無効化しない限り起動時に開始）。
- **依存**: `watchdog>=4.0`（任意 extras）。未導入時は警告ログのみ出して watcher は起動せず、CLI は通常通り続行します。
- **起動順序**: watcher は F.8.1 の起動時差分更新が終わってから開始します。同一の索引 DB へ 2 つの書き込み経路を同時に存在させないためです。

### F.8.1 起動時の索引差分更新（HVE CLI / GUI）

`hve run` / `hve cli` / `hve orchestrate` と HVE GUI は、起動時に **実在する** `mdq` / `cq` の索引 DB をバックグラウンドで差分更新します（`watchdog` は不要）。

- **対象**: `.mdq/index-<lang>-<strategy>.sqlite` に一致する実在ファイルと、`cq` 設定が宣言する profile のうち `.cq/index-<profile>.sqlite` が実在するもの。**未構築の strategy / profile を新規作成することはありません**（利用者が選択していない索引を起動のたびに生成しないため）。SQLite 索引を持たない `graphrag` とレガシーの `.mdq/index.sqlite` は対象外です。
- **更新方式**: 差分更新のみ（完全再ビルドはしません）。索引対象 roots は `mdq.toml` / `cq.toml` の解決結果、つまり `python -m mdq index` / `python -m cq index` と同じです。
- **無効化**: `HVE_STARTUP_INDEX_REFRESH=0`。専用の CLI フラグ・GUI 設定はありません。
- **`--dry-run`**: 索引は更新されます（索引は Workflow の成果物ではないため）。watcher が `--dry-run` で起動しないのとは扱いが異なります。
- **GUI**: 差分更新中は実行開始操作を受け付けません（子プロセスの watcher と同一 DB へ同時に書き込むのを避けるため）。理由はステータス欄に表示されます。
- **失敗時**: 警告のみを出して実行は継続します（任意依存の欠落・`cq` 設定不在・索引 DB のロック競合を含む）。
- **実測（2026-08-20、本リポジトリ / warm 状態）**: 4 対象（`mdq` heading / `mdq` fixed_window / `cq` hve / `cq` app）を逐次処理して合計 **32.7 秒**（実際の起動経路と同じプロセス内実行での計測）。索引規模は `mdq` heading が 2,008 ファイル / 37,431 チャンク、`cq` hve が 1,049 ファイル。

**有効化（依存導入）**:

推奨は `hve/setup-hve.ps1` / `hve/setup-hve.sh` の実行です。これらは既定で `[mdq-watch]` extras（`watchdog` 含む）をインストールするため、追加コマンドなしでリアルタイム索引更新が利用可能になります。`-Minimal` / `--minimal` を指定すると base のみとなり watcher 依存も導入されません。手動 `pip install` 例は §F.1 を参照してください。

```bash
pip install -e ".[mdq-watch]"   # watchdog + rank_bm25 + tiktoken
```

**無効化 / チューニング**:

| 手段 | 内容 |
|---|---|
| `--no-mdq-watch` | 当該実行のみ watcher を無効化 |
| `--mdq-watch` | 明示的に有効化（既定 ON なので通常は不要） |
| `--mdq-watch-debounce-ms <MS>` | デバウンス間隔（既定 500ms）。連続更新の集約幅 |
| `HVE_MDQ_WATCH=0` | 環境変数で恒久的に無効化 |
| `HVE_MDQ_WATCH_DEBOUNCE_MS=300` | 環境変数でデバウンス変更 |

**動作仕様**:

- 監視対象: 索引対象 11 root の `.md` ファイルのみ（スコープ外イベントは破棄）。
- 同一ファイルの連打はデバウンス（既定 500ms）で集約し、最終状態のみ反映。
- バーストイベント（1 秒以内に 100 件超）は安全網として `build_index(prune=True)` で全 root を再走査。
- 書き込みは watcher 専用 SQLite 接続 1 本に直列化（スレッド競合回避）。
- プロセス終了時は `atexit` で `stop()` が呼ばれ、保留分を最後に 1 回 flush。

**スタンドアロン版**: Orchestrator を介さず watcher のみを実行する場合:

```bash
python -m mdq watch              # 既定 root を監視
python -m mdq watch --initial-index   # 起動時に 1 回 index も走らせる
python -m mdq watch --root docs --root users-guide --debounce-ms 300
```

**既存の `index` コマンドとの関係**:

- `python -m mdq index` は **これまで通り利用可能** です（撤去・変更なし）。CI や手動の一括更新で引き続き使用してください。
- watcher と `index` は同じ `.mdq/index.sqlite` を共有しますが、書き込み経路が直列なので競合しません。watcher 起動中に手動 `index` を実行しても安全です。

---

## 付録D: トラブルシューティング

> HVE Cloud Agent Orchestrator 側を含む初期セットアップ全体の切り分けは [troubleshooting.md](./troubleshooting.md#初期セットアップで詰まったとき) を参照してください。

### Copilot CLI が見つからない

```
エラーメッセージ: command not found: copilot
```

外部 `copilot` コマンドを `COPILOT_CLI_PATH` や `--cli-path` で明示指定している場合は、[公式ドキュメント](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli)に従ってインストールし、`copilot --version` で確認してください。PATH 上の場所は `which copilot`（macOS/Linux）または `where copilot`（Windows）で確認できます。

外部 CLI を明示指定していない場合は、まず `github-copilot-sdk` が仮想環境にインストールされていることを確認してください。

### github-copilot-sdk がインストールされていない / `python -m hve` が動かない

```
エラーメッセージ: ModuleNotFoundError: No module named 'copilot'
```

仮想環境が有効化されていることを確認し、`pip install github-copilot-sdk` を実行してください。`pip show github-copilot-sdk` でインストール状態を確認できます。

### セッションタイムアウト

```
エラーメッセージ: Session expired. Please re-authenticate.
```

`gh auth logout` → `gh auth login` で再認証してください。長時間実行時は `--max-parallel` を小さくすることで実行時間を短縮できます。

### MCP Server が接続できない

```
エラーメッセージ: Failed to connect to MCP server: filesystem
```

**Local/Stdio の場合**: `npx --version` で npx が使えることを確認し、設定ファイルの JSON 構文を `python -m json.tool < mcp-servers.json` で検証してください。

**Remote HTTP の場合**: URL の正しさ、ネットワーク疎通（`curl <URL>`）、認証トークンの正しさを確認してください。

> Work IQ で `MCP error -32001: Request timed out` が出た場合は、対応不要と決めつけず、Copilot CLI の `/mcp` で exact `workiq` の接続状態と `ask` の公開を確認してください。HVE は認証や設定変更を代行しません。

`MCP host not initialized` は初期化未完了であり、登録の不存在や認証エラーを確定しません。`needs-auth` は認証が必要な状態です。HVE は認証を開始しないため、`needs-auth` を待たずに直ちに失敗として扱います（required の server は停止、optional の server は session 内で無効化して続行）。必要な認証は Copilot CLI の `/mcp` 側で行ってから再実行してください。HVE 内で認証を再試行しません。

初期化不能、required resource・caller filter の検証不能、disable 失敗・期限切れ・cancel は fail-closed です。optional を除外して継続できる条件は前述の SDK ResourceSnapshot routing に従います。Prompt 実行条件を変更する場合は、新しい計画内容と hash を再提示して明示承認を得ます。この修正の live E2E は未実施で、文書テストの成功は実接続・実 query・Prompt 実行の成功を証明しません。

### 並列実行でメモリ不足

```
エラーメッセージ: MemoryError / OSError: [Errno 12] Cannot allocate memory
```

`--max-parallel` を小さくして実行してください（例: `--max-parallel 3`）。

### PR 作成時に HTTP 422 エラー

```
PR 作成に失敗しました (HTTP 422)
原因: ブランチ間に差分が存在しない可能性があります。
```

Agent の成果物がリモートブランチに push されているか確認してください。`git log --oneline` でコミットが存在することを確認してください。

### `--auto-coding-agent-review` で前提条件エラー

```
❌ --auto-coding-agent-review の前提条件が満たされていません
```

`GH_TOKEN` 環境変数と `--repo` オプションの両方が設定されているか確認してください。

### デバッグ情報を増やしたい

Copilot CLI の内部ログを詳細に出力するには `--log-level debug` を指定します。

```bash
python -m hve orchestrate -w aad-web --log-level debug
```

有効な値は `none` / `error`（デフォルト）/ `warning` / `info` / `debug` / `all` です。問題の切り分け時に `debug` または `all` を使い、通常運用では `error` のままにしてください。

> **`--verbosity` との併用**: `--log-level debug` は Copilot CLI プロセスのログ詳細度のみを制御します。HVE CLI Orchestrator 自体の出力を増やすには `--verbosity verbose` も併用してください。最大の情報量で問題調査するコマンド例:
> ```bash
> python -m hve orchestrate -w aad-web --verbosity verbose --log-level debug
> ```

### インタラクティブモードが起動せず orchestrate のヘルプが表示される

`python -m hve` を実行した際に `orchestrate` サブコマンドのヘルプが表示される場合は、`hve/` パッケージが古い可能性があります。`hve/__main__.py` が最新版であることを確認してください。

### ターミナルでカラー表示が崩れる / 文字化けする

ANSI エスケープシーケンスに対応していないターミナルでは表示が崩れることがあります。以下を確認してください:

- **Windows**: Windows Terminal または PowerShell 7+ を推奨。古い `cmd.exe` では ANSI 非対応の場合があります
- **パイプ/リダイレクト時**: `python -m hve | tee log.txt` のように TTY 非接続環境ではカラー出力が自動的に無効化されます
- **CI/CD 環境**: 非 TTY のため自動でプレーンテキスト出力になります。CI では `orchestrate` サブコマンドの使用を推奨します

---

## 付録E: セキュリティ・SSO・関連リンク

### セキュリティ上の注意事項

| 注意事項 | 説明 |
|---------|------|
| **トークンをコードにハードコードしない** | `.env` ファイルや環境変数で管理し、Git にコミットしないでください |
| **`.gitignore` に追加** | `.env` ファイルを使う場合は `.gitignore` に含めてください |
| **有効期限を設定する** | 無期限トークンは避け、90日以内を推奨します |
| **不要になったら削除する** | Settings > Developer settings > Personal access tokens から削除できます |
| **漏洩した場合は即座に無効化** | トークンが漏洩した場合は、同画面から **Delete** で即座に無効化してください |

### SAML SSO が有効な組織の場合

組織で SAML シングルサインオンが有効になっている場合は、トークン作成後に **SSO 認証** が必要です。

1. **Settings** > **Developer settings** > **Personal access tokens** に移動
2. 対象トークンの横にある **Configure SSO** をクリック
3. 対象組織の **Authorize** をクリック

詳細: [Authorizing a personal access token for use with SAML single sign-on](https://docs.github.com/en/enterprise-cloud@latest/authentication/authenticating-with-saml-single-sign-on/authorizing-a-personal-access-token-for-use-with-saml-single-sign-on)

### 関連リンク

| リソース | URL |
|---------|-----|
| 利用ガイド（README） | [README.md](../README.md) |
| CLI はじめかた（環境構築チュートリアル） | [hve-cli-getting-started.md](./hve-cli-getting-started.md) |
| GitHub Web での実行（方式 1 / 方式 2） | [web-ui-guide.md](./web-ui-guide.md) |
| GitHub Copilot SDK（リポジトリ） | https://github.com/github/copilot-sdk |
| SDK Getting Started | https://github.com/github/copilot-sdk/blob/main/docs/getting-started.md |
| Custom Agents ドキュメント（上流 Copilot SDK 機能） | https://github.com/github/copilot-sdk/blob/main/docs/features/custom-agents.md |
| Cloud Sessions ドキュメント（上流 Copilot SDK 機能） | https://github.com/github/copilot-sdk/blob/main/docs/features/cloud-sessions.md |
| MCP Servers ドキュメント | https://github.com/github/copilot-sdk/blob/main/docs/features/mcp.md |
| Copilot CLI インストールガイド | https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli |
| Model Context Protocol（MCP）仕様 | https://modelcontextprotocol.io/ |
| Code Review Agent ドキュメント | https://docs.github.com/en/copilot/using-github-copilot/code-review/using-copilot-code-review |

### knowledge/ ディレクトリの参照

HVE CLI Orchestrator でワークフローを実行する際も、`knowledge/` フォルダーの業務要件ドキュメント（D01〜D21）が存在する場合、各 Prompt が自動参照します。HVE CLI Orchestrator での `knowledge-management` ワークフロー実行:

```bash
python -m hve orchestrate --workflow akm
```

`knowledge/` ファイルが存在すると、以降の設計・実装ワークフロー（`aas`, `aad-web`, `asdw-web` 等）での設計品質が向上します。詳細は [km-guide.md](./km-guide.md) を参照してください。

---

## 付録G: HVE を拡張する（開発者向け）

CLI Orchestrator 自体を変更する場合の正本、変更手順、回帰検証、互換性の観点をまとめます。利用手順のみが目的の場合は本節を読み飛ばしてください。

### 設定・実装の正本

| 変更したいもの | 正本 |
|---|---|
| サブコマンド・引数・既定値の宣言 | `hve/__main__.py` |
| 設定値の解決・環境変数・正規化 | `hve/config.py` |
| ワークフロー・Step・`custom_agent`・成果物パス | `hve/workflow_registry.py` |
| DAG 構築と並列実行 | `hve/dag_planner.py` / `hve/dag_executor.py` |
| Step 実行と出力ゲート | `hve/runner.py` |
| Prompt の解決 | `hve/prompt_loader.py` と `.github/prompts/`（Agent 本文は flat、Step 本文は `steps/`、fan-out 追加本文は `fanout/`、HVE 内部 Prompt は `runtime/`、Cloud 実行指示は `cloud/`） |
| Skill の解決 | `hve/skill_resolver.py` と `.github/skills/` |
| Cloud Session の振り分け | `hve/cloud_session.py`（→ [cloud-session.md](./cloud-session.md)） |
| セットアップスクリプト | `hve/setup-hve.ps1` / `hve/setup-hve.sh` / `hve/setup-hve.cmd` |
| 依存パッケージ・extras | `pyproject.toml` |

### 変更手順

1. **引数を追加・変更する**: `hve/__main__.py` に定義を追加し、対応する設定フィールドを `hve/config.py` に置く。既定値は `config.py` 側を正とし、CLI 側は「未指定＝継承」にする。
2. **Step / 成果物を変更する**: `hve/workflow_registry.py` を変更する。`output_paths` は実行時ゲートの参照元なので、成果物パスの変更は必ず registry 側と対で行う。
3. **Prompt を変更する**: Agent 本文は `.github/prompts/<Name>.prompt.md`、Step 本文は `.github/prompts/steps/<workflow>/step-<id>.prompt.md`、fan-out 追加本文は `.github/prompts/fanout/<workflow>/*.prompt.md` を変更する。Step からの参照名は registry の `custom_agent` / `body_template_path` / `additional_prompt_template_path` フィールド。Prompt 本文は `.github/prompts/**` だけを正本とし、Python 定数や Workflow 側へ本文を重複保持しない。必須 Prompt の欠損・空・不正パスは model call 前に fail-closed で停止する。編集内容は次回の process / session から反映され（hot reload なし）、`{root_ref}` や `{{key}}` などの placeholder 記法を壊さないこと。
4. **文書を更新する**: 引数・既定値・ワークフロー一覧を変更したら、本ガイドの該当表と、影響する入門ガイドを同じ変更で更新する。

### 回帰検証

HVE 自己テストとその直接依存の回帰検証は、開始前に [共通入口・品質証跡契約（FR-MAINT-12）](../tests/README.md) と [CLI Full SystemTest](../tests/%5Bcli%5DSystemTest%20-%20Full.txt) を確認してください（Prompt 版の入口も共通 README にあります）。

- 起動前に**元リポジトリの `tests/run/<run-id>/<task>/`** を確保し、全 controller 生成物（plan / request / case / status / checkpoint / review / helper / driver / stdout・stderr / 終了コード / ログ / 測定値 / 検証結果 / PNG・manifest / 安全な設定 snapshot / report）を最初からこの保存ルート配下に保持します。指定された README・plan・completion report は task 直下、その他の詳細証跡は `artifacts/` とし、いずれも lane 外へ置きます。最終 report だけの移動では不十分です。
- 子 session に元リポジトリ・保存ルート・専用 lane・書き込み範囲を絶対パスで渡し、CLI の既存 `HVE_WORK_ROOT` / `HVE_RUN_ID` は子プロセス単位で整合させます。元リポジトリの `work/` へ自己テストの新規出力をせず、通常の work / logs defaults と lane 内の canonical outputs は変更しません。
- 専用 lane / fixture の cleanup 前に、必要な安全な内部ログ・生成物の検証証拠を lane 外の兄弟 `artifacts/` へ退避し、証跡一覧との対応・存在・必要な非空条件・相対リンク・要求される hash を確認します（正常な空 stderr は許容）。欠損・検証不能なら cleanup を止め、PASS としません。
- 機微情報は保存せず、failed / blocked / interrupted を含む品質証跡・過去履歴は削除しません。再実行は新 run / attempt に分離します。保存先の契約はモデル利用・Azure 操作等の実行承認を代替しません。

```bash
# CLI パーサー・エントリポイント
python -m pytest hve/tests/test_main.py hve/tests/test_main_entrypoints.py

# Prompt / Skill の解決
python -m pytest hve/tests/test_prompt_loader.py hve/tests/test_skill_resolver.py

# GUI ヘルプ本文（CLI ガイドと共有する記述の契約）
python -m pytest hve/tests/test_gui_help_content.py
```

### 互換性・安全性

- 既存の引数名・既定値の変更は互換性を壊します。別名を追加してから移行し、廃止する場合は本ガイドに廃止版数を明記してください（例: 「中断と再開（Resume）— 廃止（v1.1）」）。
- `--create-issues` / `--create-pr` と対象 Workflow / Step の auto-merge は GitHub 書込みを行うため `GH_TOKEN` または `GITHUB_TOKEN` が必要です。Code Review Agent 単独はローカル SDK で実行します。トークンは安全な環境変数注入を使い、ドキュメントやコードへ埋め込まないでください。
- Cloud Session の `policy_blocked` はローカルへフォールバックしません。組織ポリシーの拒否を迂回する変更を入れないでください。
