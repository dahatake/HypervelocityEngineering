# HVE GUI Orchestrator ガイド

← [README](../README.md)

> **対象読者**: PySide6 GUI ウィンドウで HVE ワークフローを実行したい方。コマンドライン操作が不要です。  
> **前提**: Python 3.11+、GitHub CLI（`gh`）、対象リポジトリのローカルクローンがあること  
> **次のステップ**: まず「[クイックスタート](#クイックスタート)」を実行し、必要に応じて「[インストール](#インストール)」「[2 ステップ操作ガイド](#2-ステップ操作ガイド)」を確認してください。

---

## 目次

- [概要](#概要)
- [対象読者](#対象読者)
- [クイックスタート](#クイックスタート)
- [前提条件](#前提条件)
- [インストール](#インストール)
- [起動](#起動)
- [2 ステップ操作ガイド](#2-ステップ操作ガイド)
- [Copilot パネル（対話と実行ジョブ連携）](#copilot-パネル対話と実行ジョブ連携)
- [GitHub Issue / Pull Request](#github-issue-pull-request)
- [Plugin / MCP Server 認証](#plugin-mcp-server-認証)
- [データフロー](#データフロー)
- [複数セッションの同時起動](#複数セッションの同時起動)
- [中断と再開（Resume）— 廃止（v1.1）](#中断と再開resume-廃止v11)
- [コマンドリファレンス](#コマンドリファレンス)
- [ワークフロー一覧](#ワークフロー一覧)
- [CLI との違い・使い分け](#cli-との違い使い分け)
- [Fork-on-Retry / DAG 並列実行・Post-step 自動プロンプト](#fork-on-retry-dag-並列実行post-step-自動プロンプト)
- [セキュリティ・SSO・関連リンク](#セキュリティsso関連リンク)
- [トラブルシューティング](#トラブルシューティング)
- [多言語表示（日本語 / English）](#多言語表示日本語-english)
- [GUI を拡張する（開発者向け）](#gui-を拡張する開発者向け)
- [関連ドキュメント](#関連ドキュメント)

---

## 概要

**HVE GUI Orchestrator** は、HVE の 3 つ目の Orchestrator（HVE Cloud Agent Orchestrator / HVE CLI Orchestrator に続く位置づけ）です。`python -m hve`（引数なし、既定）または `python -m hve gui` で起動する PySide6 製 GUI アプリケーションで、単一ウィンドウの 2 ステップ ウィザード（Step 1: ワークフロー選択＋オプション設定 / Step 2: 実行）からワークフローを選択・設定・実行できます。内部で `hve orchestrate` エンジンを呼び出すため、CLI Orchestrator と同じ DAG 実行エンジンを共有しています。

![HVE 3 Orchestrators アーキテクチャ比較](./images/hve-gui-orchestrator-architecture.svg)

### 3 つの Orchestrator 比較

| 正式名称 | 入口 | 実行場所 | 追加依存 | 主な特徴 |
|---|---|---|---|---|
| **HVE Cloud Agent Orchestrator** | GitHub Issue Template | GitHub Actions | なし | リモート実行・Sub Issue 自動生成 |
| **HVE CLI Orchestrator** | `python -m hve orchestrate` / `python -m hve cli` | ローカル端末 | なし | ターミナル Rich Live Workbench |
| **HVE GUI Orchestrator** | `python -m hve`（既定）/ `python -m hve gui` | ローカル端末 | `PySide6>=6.6` | GUI ウィザード・マウス操作・複数セッション |

HVE GUI Orchestrator は CLI Orchestrator と同じ `hve orchestrate` エンジンを呼び出します。内部動作・オプション仕様・ワークフロー定義は共通です。UI の操作方法のみが異なります。

---

## 対象読者

- **初めてのユーザー**: コマンドライン操作なしで HVE を試したい方。GUI のラジオボタン・チェックボックス・ドラッグ&ドロップで全操作を完結できます。
- **複数セッション運用者**: 異なるワークフローを並行で起動・モニターしたい方（ターミナル UI は単一セッション）。
- **ARD 利用者**: 添付資料（`.docx` / `.pdf` / `.xlsx` / `.pptx` / `.html` 等）を D&D で取り込みたい方。
- **オプション理解の補助が欲しい方**: 多数の `orchestrate` オプションをカテゴリ別アコーディオンで参照したい方。

CLI 互換のスクリプト実行・CI 連携・Workbench 操作詳細が必要な場合は [hve-cli-orchestrator-guide.md](./hve-cli-orchestrator-guide.md) を参照してください。

---

## クイックスタート

3 ステップで実行を開始できます。

```bash
# 1. 依存パッケージをインストール（GUI extras 込み）
#    Windows: hve\setup-hve.cmd   /   macOS ・ Linux: ./hve/setup-hve.sh
./hve/setup-hve.sh

# 2. GitHub CLI で認証（初回のみ）
gh auth login

# 3. GUI を起動
./hve.sh gui
```

**Windows 初心者向け（ダブルクリックで完結）**:

```text
hve\setup-hve.cmd   ← 初回 1 回だけダブルクリック（.venv + GUI extras + markitdown 一括）
hve.cmd gui         ← 以降はこれで GUI 起動
```

**macOS / Linux**: `./hve/setup-hve.sh` で一括セットアップ後、`./hve.sh gui` で起動。

ウィザードが開いたら **Step 1（ワークフロー選択＋オプション設定）→ Step 2（実行）** の順に進めます（Step 1 は左ペインで選択、右ペインでオプション設定）。詳細は [2 ステップ操作ガイド](#2-ステップ操作ガイド) を参照してください。

---

## 前提条件

| 要件 | 必須 / オプション | 備考 |
|---|---|---|
| Python 3.11+ | **必須** | HVE 基本要件 |
| `hve\setup-hve.cmd`（Windows）/ `./hve/setup-hve.sh`（macOS ・ Linux） | **必須** | PySide6 を含む GUI 依存、埋め込み端末用 PTY backend（`pywinpty` / `ptyprocess`）、`gh` を一括で導入・検証する |
| 添付変換（markitdown） | オプション | ARD ワークフローで `.docx` / `.pdf` / `.xlsx` / `.xls` / `.pptx` / `.html` をドラッグ&ドロップする場合（変換エンジンは [microsoft/markitdown](https://github.com/microsoft/markitdown)。上記 setup をオプション無しで実行すれば既定で導入） |
| GitHub Copilot CLI（外部 `copilot` コマンド） | HVE CLI 共通 | Prompt 実行に必要 |

> その他の前提条件（Git / GitHub アカウント / Copilot ライセンス等）は [hve-gui-getting-started.md](./hve-gui-getting-started.md) を参照してください。

---

## インストール

**Windows 初心者向け（最短）**: エクスプローラーから **`hve\setup-hve.cmd`** をダブルクリックすると、`.venv` 作成 + `github-copilot-sdk` + 全 extras（test / mdq-watch / mdq-ja / semantic / **gui** / gui-pty / gui-docconvert）を一括インストールします。PowerShell の実行ポリシー設定は不要です。完了後は **`hve.cmd gui`** で GUI を起動できます。

```bash
# リポジトリをクローン後、セットアップスクリプトで GUI + 添付変換（markitdown）を一括インストールするのが推奨（v0.1.x 以降、GUI extras は既定 ON）:
# Windows (初心者向け、cmd ダブルクリック対応):
hve\setup-hve.cmd
# Windows (PowerShell 7+):
pwsh -NoProfile -File hve\setup-hve.ps1
# Linux / macOS:
./hve/setup-hve.sh

# CLI 専用にしたい場合は --no-gui / -NoGui を付与。
```

> **手動インストールは補助手段**: `pip install -e ".[gui,gui-pty,gui-docconvert]"` でも Python 依存は入りますが、`gh` の導入と PTY backend の利用可否検証は行われません。GUI の「GitHub CLI でログイン」を含む完全構成の復旧には、OS 別の通常 setup を使ってください。

> **`.cmd` vs `.ps1`**: `.cmd` は `.ps1` を呼ぶ薄ラッパとなり、同一のオプション（`-CheckOnly` / `-NoGui` / `-Minimal` / `-Force` / `-SkipNltkDownload` / `-WithSkills` / `-Yes` / `-NoInstallPython` / `-NoInstallTools`）をサポートします。既定では不足している OS ツール（Git / gh / Node.js / Azure CLI / ShellCheck / 外部 Copilot CLI、Linux では Qt system lib）も自動導入します。詳細は [hve-cli-orchestrator-guide.md - セットアップスクリプト](./hve-cli-orchestrator-guide.md#セットアップスクリプトを使った環境構築windows--macos--linux) を参照。

---

## 起動

起動方法は OS ごとのランチャスクリプトを使う方法（方法 A）と、ターミナルから直接実行する方法（方法 B）があります。普段使いは **方法 A** を推奨します。

### 方法 A: ランチャスクリプト起動（推奨）

#### Windows — `hve.cmd`

リポジトリ直下の **`hve.cmd`** を使います。エクスプローラからダブルクリックすると引数なしで実行され、GUI が起動します（コマンドプロンプトから明示する場合は `hve.cmd gui`）。

> **役割の違い**: `hve\setup-hve.cmd` は **初回セットアップ専用**（venv + 依存関係の導入、通常 1 度だけ実行）。`hve.cmd` は **起動専用**（セットアップ完了後、毎回これを使う）。

```text
RoyalytyService2ndGen\
├── hve\setup-hve.cmd   ← 初回 1 回だけダブルクリック（セットアップ）
└── hve.cmd             ← 毎回ダブルクリック（GUI 起動）
```

内部で `.venv\Scripts\python.exe -m hve` を実行します。

| 状況 | 動作 |
|---|---|
| `.venv` が未作成 | エラー表示 → `hve\setup-hve.cmd` または `hve\setup-hve.ps1` の実行を案内 → 停止 |
| GUI 依存が未導入（exit code 2） | エラー表示 → `hve\setup-hve.cmd` の実行と `hve.cmd gui` での再起動を案内 → 停止 |
| 正常起動 | GUI ウィンドウが開く（裏でコマンドプロンプトが残ります） |

> **デスクトップから起動したい場合**: `hve.cmd` を右クリック → 「ショートカットの作成」 → `.lnk` をデスクトップに移動。

#### macOS / Linux — `hve.sh`

リポジトリ直下の **`hve.sh`** を使います。

```text
RoyalytyService2ndGen/
└── hve.sh   ← ターミナルから実行（引数なしで GUI 起動）
```

```bash
./hve.sh gui
```

内部で `.venv/bin/python -m hve` を実行します。

| 状況 | 動作 |
|---|---|
| `.venv` が未作成 | エラー表示 → `./hve/setup-hve.sh` の実行を案内 → 停止 |
| GUI 依存が未導入（exit code 2） | エラー表示 → `./hve/setup-hve.sh` の実行と `./hve.sh gui` での再起動を案内 → 停止 |
| 正常起動 | GUI ウィンドウが開く |

### 方法 B: コマンドライン起動（クロスプラットフォーム）

仮想環境を有効化してから実行するか、フルパスで指定します。

```bash
# Unix 系（macOS / Linux）
.venv/bin/python -m hve gui
```

```powershell
# Windows PowerShell
.\.venv\Scripts\python.exe -m hve gui
```

### 共通: 起動後の動作

いずれの方法でも **単一ウィンドウ** が開き、2 つの画面（ワークフロー選択 → 実行）を順に進めます。

起動直後、GUI は **既存の `markdown-query` / `cq` 索引 DB をバックグラウンドで差分更新** します。更新中はステータス欄に「索引 (markdown-query / code-query) の差分更新中です。完了後に実行を開始できます。」と表示され、実行開始ボタンが一時的に無効になります。GUI が起動する `hve orchestrate` 子プロセスは自身の索引 watcher を起動するため、同一の索引 DB へ同時に書き込まないようにするためです。更新が終わるとボタンは自動的に有効へ戻ります。

- 対象は **実在する索引 DB のみ**です。未構築の chunking strategy / `cq` profile を新規作成することはありません。
- `HVE_STARTUP_INDEX_REFRESH=0` を設定すると無効化できます（CLI と共通。GUI 専用の設定項目はありません）。
- 詳細は [skills-markdown-query.md §4.2](./skills-markdown-query.md#42-索引整合性の前提と運用-tips) / [skills-code-query.md §4.3](./skills-code-query.md#43-索引整合性の前提と運用-tips) を参照してください。

---

## 2 ステップ操作ガイド

![2 ステップ操作フロー](./images/hve-gui-orchestrator-2step-flow.svg)

> GUI ウィザードは **2 ステップ** です。**Step 1** の画面は左ペイン（ワークフロー選択）と右ペイン（オプション設定）で構成され、**Step 2** が Workbench（実行）です。以下では Step 1 を「ワークフロー選択（左ペイン）」「オプション選択（右ペイン）」の 2 パートに分けて説明します。

### Step 1: ワークフロー選択

`workflow_registry.list_workflows()` から取得した全ワークフローをラジオボタンで提示します。

起動直後のメインウィンドウは以下のとおりで、左に エクスプローラー、中央にウィザード本体、右に Copilot Chat / 追加プロンプト等の補助パネルが並びます。

![GUI Step 1: ワークフロー選択画面（起動直後）](./images/screenshots/gui-01-main-window.png)

複数のワークフローを同時選択することも可能です。下記は `Architecture Design (AAS)` を選択した状態の例です。

![GUI Step 1: AAS を選択した状態](./images/screenshots/gui-03-workflow-selected-aas.png)

| グループ | ワークフロー ID | 正式名称 |
|---|---|---|
| Business Engineering (要求定義) | `ard` | Auto Requirement Definition |
| Architecture Design | `aas` | Architecture Design |
| Software Engineering | `aad-web` | Web App Design |
| Software Engineering | `asdw-web` | Web App Dev & Deploy |
| Software Engineering | `adfd` | Dataflow Design |
| Software Engineering | `adfdv` | Dataflow Dev & Deploy |
| 既存ドキュメントのインポート | `adi` | Auto Design-doc Ingestion |
| Knowledge Management | `akm` | Knowledge Management |
| Knowledge Management | `adoc` | Source Codeからのドキュメント作成 |
| AI Agent | `ada` | Agent Data Architecture |
| AI Agent | `aag` | AI Agent Design |
| AI Agent | `aagd` | AI Agent Dev & Deploy |
| AI Agent | `aar` | Agentic Retrieval Add-on |

- ワークフローは上表の **グループ見出しごとにまとめて表示**されます。グループ定義は `hve/workflow_registry.py` の `WORKFLOW_CATEGORIES` が正本で、HVE CLI Orchestrator の対話メニューと共通です。

- 選択中ワークフローの ID・正式名称・短い説明を下部に表示。
- 画面左下の **「実行ステップ（チェック ON のみ実行対象）」** では、実行したいステップだけを個別に ON/OFF できます。各チェックは**単独で切り替わり、前後のステップへ自動連動しません**（依存伝播なし）。前段ステップの成果物が既に存在していれば、途中のステップ（例: `Step 2.1` の追加サービスから）だけを選んで実行できます。
- [次へ] 押下時の統合 precheck は、選択したステップの必須ファイル / 必須入力を `FILE` / `WIZARD_INPUT` として検査し、GitHub 書き込みを伴う実行では GitHub 連携のローカル不整合も `SETTING` / `AUTH` として表示します。起動引数の組み立てで `ValueError` になった場合は「入力エラー」を表示し、precheck や Step 2 へ進まず Step 1 に留まります。
- 左ペインで選択後、同じ画面右ペインの「オプション選択」（下記）でオプションを設定します。

---

### Step 1（右ペイン）: オプション選択

`orchestrate` サブコマンドの多数のオプション（正本は [hve/gui/orchestrate_args.py](../hve/gui/orchestrate_args.py) の `OrchestrateArgs`）は、**設定画面（HVE 設定）** 側でカテゴリー別に分類して保持します。設定画面のツリーは固定 13 ノードと `skills` グループの 3 ノードを合わせた計 16 ノードです。

**Step 1 の右ペインはこのカテゴリー一覧をそのまま並べません**。選択中のワークフローに応じて実効的な行だけを表示し、ワークフロー固有の入力欄は選択ワークフロー枠へ移されます（例: AAS の Step 1 では C3 内の 6 行 / 7 入力だけが実効表示されます）。

以下の表は、設定画面側のカテゴリー ID と保持するオプションの対応です。

| カテゴリ | 画面上の見出し | 主な内容 |
|---|---|---|
| C1 | 基本設定  *必須 | `--model` / `--review-model` / `--qa-model` / `--reasoning-effort` 系 / `--context-tier` / `--max-parallel` / `--timeout` / `--review-timeout` / `--verbosity` / テーマ / `--additional-prompt` / `--context-max-chars` |
| C3 | 共通設定  *必須 | `--auto-qa`（**必須選択** / 下記参照）/ **QA (質問票) 回答モード**（下記参照）/ `--auto-contents-review` / `--auto-coding-agent-review` / `--qa-akm-background-merge`（下記参照）/ `--akm-model` / `--akm-reasoning-effort` / `--akm-context-tier` / `--self-improve` 系。設定画面では `QA (質問票)` / `レビュー` / `Knowledge Management` / `自己改善 (Self Improve)` の 4 ノードへ分かれています |
| C4 | Work IQ | `--workiq` 系（M365 メール・チャット・会議・ファイル参照。`@microsoft/workiq` プラグインのインストールが必要）。`OrchestrateArgs` は Work IQ 関連 12 フィールドを保持し、`--workiq*` 引数として CLI に渡ります（`--workiq-tenant-id` の GUI 入力欄は廃止済み。CLI 引数と環境変数 `WORKIQ_TENANT_ID` は引き続き有効） |
| C5 | GitHub | `--create-issues` / `--create-pr` / `--repo` / **Root Issue の扱い**（新規作成 / 既存 Issue に連携、`--issue-number`。下記参照）/ `--issue-title` / `--branch` / **進捗を引き継いで再実行する run-id**（`--resume-run`。下記参照）/ `--enable-auto-merge` / マージ後ローカルブランチ削除 / Fleet mode / Cloud Sessions 関連 |
| C6 | 出力制御 | `--verbose` / `--quiet` / `--show-stream` / `--log-level` / `--no-color` / `--banner` / `--screen-reader` / `--timestamp-style` / `--final-only`。**この枠の値は保存されず、起動のたびに既定値へ戻ります**（コンソール表示の制御であり実行結果の意味を変えないため、面固有のままとしています。固定したい場合は CLI 実行時に同名のフラグを指定してください。なお `--banner` は `orchestrate` では効果がありません） |
| C7 | MCP / CLI 接続 | `--cli-path` / `--cli-url` |
| AZURE | Azure | `--resource-group`（`default_params` を持たない必須パラメータのみ。FR-GUI-02 / FR-WF-ASDW-02） |
| AGENTIC | Agentic Retrieval | `--enable-agentic-retrieval` / データソース方式 / Foundry MCP 連携 / データソースのヒント / 既存設計の差分更新 / Foundry SKU フォールバック方針。**この枠の 6 項目は保存され、次回起動時に復元されます**（Prompt 版も同じ保存値を引き継ぎます） |
| C10 | アプリケーションID | `--app-ids` / `--usecase-id` / github.com CI/CD トグル（下記参照） |
| C11 | Knowledge Management 固有 | `--sources` / `--target-files` / `--force-refresh` / `--custom-source-dir`。AKM 選択時だけ CLI 実行引数へ反映されます |
| C13 | ADOC 固有 | `--target-dirs` / `--exclude-patterns` / `--doc-purpose` / `--max-file-lines` |
| C14 | 要求定義書 | `--company-name` / `--target-business` / `--target-recommendation-id` / 調査基準日・調査期間・対象地域 / 添付資料 D&D（下記参照） |
| C17 | ADI 固有 | `--purpose` / `--target-scope` / `--depth` / `--focus-areas` |

選択ワークフローに応じて各カテゴリ枠の表示・有効化が自動制御されます。`C1` / `C5` / `C6` / `C7` / `AZURE` / `AGENTIC` は Step 2 セッションでは非表示です。`C3` も非表示集合に含まれますが例外として再表示され、追加プロンプトと、見出し非表示対象外の共通設定行を表示します。

> カテゴリ ID（`C1` / `C3` / …）は設定互換性のための内部識別子です。`C2` / `C8` / `C9` / `C12` / `C15` / `C16` は他カテゴリへ統合または廃止済みで、欠番のまま番号を繰り上げません。`--max-parallel` は C1、`--timeout` 系は C1、`--branch` は C5、`--additional-prompt` は C1 へ統合されています。mdq / cq / Tool Search の設定は設定画面の `skills` グループにあります。

> **追加プロンプトのサイズ**: 追加プロンプトを含む Step のプロンプト全体には HVE 内部のサイズ予算があります。予算を超えると、その Step は Phase 1 の主モデルを 1 回も呼び出さずに失敗し、バイト数と成分別内訳がログに出ます。事前 QA 後の最終判定だけで超過した場合、事前 QA は実行済みです。長文は追加プロンプト欄に直接貼らず、ファイルへ保存してそのパスを書いてください。予算値は GUI 設定・CLI オプション・環境変数では変更できません。`--context-max-chars` は事前 QA へ注入する補助コンテキストの文字数上限であり、別の設定です（[troubleshooting.md](./troubleshooting.md#プロンプトが大きすぎて-step-が停止する) 参照）。

#### C10 対象アプリケーション (APP-ID) の絞り込み

- `aad-web` / `asdw-web` / `adfd` / `adfdv` のいずれかを選択すると、C10 に **APP-ID チェックリスト** が表示されます。チェックリストは `docs/catalog/app-arch-catalog.md` から読み込まれます。
- 選択中の workflow に対応するアーキテクチャ kind（`web-cloud` / `batch`）の APP-ID のみを表示し、複数 workflow を同時選択すると両 kind の和集合を表示します。
- チェック状態は内部の `--app-ids` CSV と同期し、**Autopilot ON / OFF いずれの経路でも実行対象 APP がチェック済み APP-ID のみに絞り込まれます**。未指定（空）の場合は catalog 全件が対象です。
- catalog に存在しない APP-ID を手動入力した場合は、Autopilot 計画ログ（GUI ログペイン / CLI dry-run 出力）の `skipped` セクションに `reason=unknown app_id (not in catalog)` として記録され、実行対象からは除外されます。アーキテクチャ不一致の指定 APP も同様に skip 扱いとなります（`reason=unmapped architecture or filtered by selection`）。

- `argparse.BooleanOptionalAction`（例: `--banner` / `--no-banner`）は「継承（未指定）/ 明示 ON / 明示 OFF」の 3 状態を `QComboBox` で表現します。
- 「実行 ▶」で Step 2（Workbench 実行）に移行します。

> 通常起動の GUI は MainWindow の 2 画面構成で、実行前に生成コマンドを提示する確認ページはありません。「プレビュー更新」は legacy の `QWizard` 実装（`hve/gui/wizard.py`）にある確認ページの機能であり、通常 GUI の Step 1 には含まれません。

> **GUI 強制制約**: GUI モードでは内部で `--workbench off` が自動注入されます。GUI は自前の Workbench 画面を持つため、ターミナル UI 系オプション（`--workbench` / `--workbench-body-lines` / `--workbench-history`）を利用者が選択する必要がないからです。なおこれらのオプションを収めていた `C16` カテゴリは現行の Step 1 右ペインにも設定画面にも存在せず、互換 ID の欠番としてのみ残っています。

#### ARD のみ: Strategic Recommendation の指定

ワークフローが `ard` の場合、要求定義書の枠に **「採用 Strategic Recommendation ID」**（例: `SR-1`）が常に表示されます。グループ `1` と `2` を選択し、業務エリアを空にする bridge 経路で、Step `1.2` 完了後に採用する候補を固定したい場合に入力します。

- ID の大文字小文字は区別しません。指定 ID が候補にあれば、その候補から `target_business` を生成します。
- 指定 ID が見つからなければ警告し、先頭候補へ縮退します。
- 空欄なら、GUI の非対話実行では先頭候補を採用します。
- 入力値は他の C14 項目と同じく設定へ保存されますが、グループ `1` + `2` の bridge を使わない実行では SR 選択に使用しません。

#### ARD のみ: 添付ファイル D&D

ワークフローが `ard` の場合、C14 セクションの末尾に **添付資料ドラッグ&ドロップ領域** が表示されます。

```
── 添付資料（ドラッグ&ドロップ可） ──
┌──────────────────────────────────────┐
│ 📥 ここにファイルをドロップ           │
│   （.md / .txt / .csv / .html /      │
│    .docx / .pdf / .xlsx）            │
└──────────────────────────────────────┘
```

| 対応形式 | 必要なインストール |
|---|---|
| `.md` / `.markdown` / `.txt` / `.csv` | `pip install -e ".[gui]"` のみ |
| `.html` / `.htm` / `.docx` / `.pdf` / `.xlsx` / `.xls` / `.pptx` | `pip install -e ".[gui,gui-docconvert]"` が必要（`hve/setup-hve.ps1` / `hve/setup-hve.sh` をオプション無しで実行すれば既定で導入。変換エンジンは [microsoft/markitdown](https://github.com/microsoft/markitdown)） |

- **保存先**: `<repo>/docs/attached/` 配下に Markdown として保存されます。ファイル名は ASCII 安全化されます。
- **起点ファイル選択**: 複数ファイルを D&D した場合、`business_requirement-input.md` として採用する起点ファイルをダイアログで選択します。1 ファイルのみの場合は確認なしで自動採用。
- **生成される引数**: 変換結果を `--attached-docs` カンマ区切りで自動付与し、起点ファイルは `--target-business <起点ファイルパス>` として渡されます。

> **設計上の注意**: 起点ファイルは `docs/business-requirement.md` ではなく `docs/attached/business-requirement-input.md` という別名で保存されます。ARD ワークフロー Step 2 が `docs/business-requirement.md` を自動上書きする可能性があるためです。詳細は [hve-technical-architecture.md §5](./hve-technical-architecture.md#5-hve-gui-orchestrator) を参照してください。

#### 共通設定: QA (質問票) 自動投入（必須選択）

ワークフローを選択すると、右ペイン最上部の「共通設定  *必須」枠に「QA (質問票) 自動投入」が常時表示されます。全ワークフロー共通で、実行前に必ず選択してください。

| 選択肢 | 動作 |
|---|---|
| **未選択**（既定） | 実行できません。「実行 ▶」を押すと入力エラーとして選択を促されます |
| **有効にする** | 実行前 QA 質問票を自動投入し、回答済み QA を保存・検証してからメインタスクを開始します |
| **無効にする** | 実行前 QA を行いません |

> 既定値による暗黙の決定を避けるため、未選択は `False` として保存されません。
> 回答を `knowledge/` へ取り込むかどうかは、次の「Knowledge Management へのバックグラウンドマージ」で別途選択します。

> **⚠️ fan-out する Step では適用されません**
>
> Fleet mode（設定画面の「Fleet mode」）が有効な状態で、1 つの wave に実行対象 Step が 2 件以上ある場合、その wave は Fleet mode へ委譲され Step 単位の実行経路を通りません。このとき **実行前 QA・Knowledge Management へのバックグラウンドマージ・敵対的レビューは実行されません**。
>
> APP-ID や D01〜D21 へ fan-out する Step（例: AKM Step 1）が該当します。Fleet 起動成功を確認した時点で wave ごとに 1 回警告が出ます。これらを実行したい場合は、設定画面の「GitHub」セクションにある「Fleet mode」を OFF にしてください（CLI では `--no-fleet-mode`）。

#### 共通設定: Knowledge Management へのバックグラウンドマージ

「QA (質問票) を Knowledge Management へバックグラウンドでマージする」にチェックを入れると、回答済み QA を `knowledge/` へ取り込む Knowledge Management がバックグラウンドで起動します（メインタスクは完了を待ちません）。

| 項目 | 既定 | 内容 |
|---|---|---|
| **QA (質問票) を Knowledge Management へバックグラウンドでマージする** | 無効（チェックなし） | 有効にすると、検証済み QA ファイル 1 件ごとに Knowledge Management の差分更新を起動します |

- 「QA (質問票) 自動投入」が「有効にする」のときだけ選択できます。
- 右ペインの「共通設定」枠と、設定画面の「一般 > Knowledge Management」の双方から編集できます。
- ワークフローとして **Knowledge Management を直接選んだ実行には適用されません**。

> **以前の挙動からの変更**: 従来は「QA 自動投入」を有効にするだけで Knowledge Management が常に起動していました。共有資産である `knowledge/` への自動書込みを利用者が選べるようにするため、本チェックボックス（既定無効）で制御する方式へ変更しました。従来と同じ挙動にするには本チェックボックスを有効にしてください。

#### 共通設定: QA (質問票) 回答モード

「QA (質問票) 自動投入」を「有効にする」にしたとき、回答収集の挙動を 2 つから選択できます（既定: Autopilot）。

| モード | 動作 |
|---|---|
| **Autopilot (全自動)** | AI が質問と既定回答を作成し、既定回答を全て自動採用してメインタスクへ適用します。ユーザー操作は不要です。 |
| **ユーザー回答** | AI が質問と既定回答を作成した後、GUI に **QA 回答ダイアログ** が表示されます。全質問への回答を入力して [Submit] を押すとメインタスクへ適用されます。[全て既定値で進める] / [キャンセル] も選択可能です。 |

- 「QA (質問票) 自動投入」が「無効にする」または未選択のときは本設定は無視されます（入力欄も無効化されます）。
- ユーザー回答モードは、GUI ↔ CLI 間で `.hve/qa-ipc/<uuid>/` 配下のファイルベース IPC を用います（タイムアウト: 既定 1 時間）。タイムアウト時は既定値を全採用してメインタスクを継続します。
- [キャンセル] を押すと、subprocess を停止して orchestrate 全体を中断します（途中状態を破棄）。
- 自由記述質問（選択肢がない質問）は現行 CLI の仕様により既定値が採用されます（GUI 上では入力欄が無効化されます）。

##### QA 回答ダイアログからのクリップボードコピー

QA 回答ダイアログの左下には、質問票をクリップボードへ複製する 2 つのボタンがあります。どちらも**クリップボードへ書き込むだけ**で、Work IQ への送信・ログインは行いません。

| ボタン | コピーされる内容 |
|---|---|
| **質問票をコピー** | 表示中の質問票の Markdown 全文 |
| **Work IQ 用プロンプトをコピー** | Work IQ へ貼り付けるためのプロンプト（上記の質問票全文を埋め込んだもの） |

- コピーされるのは AI が生成した質問票そのものです。**ダイアログで入力途中の回答は含まれません。**
- 質問が 1 件もない場合、両ボタンは無効になります。
- **貼り付け先には質問票の本文がそのまま渡ります。** 質問票には対象業務やリポジトリの情報が含まれるため、貼り付け先を確認してから実行してください。
- Work IQ 用プロンプトの応答は**最大 5 件**に制限されています（プロンプト側の出力スキーマによる）。質問数がこれを超える場合、回答されない質問が残ります。
- 「QA (質問票) 自動投入」に組み込まれた Work IQ 自動連携とは送信内容が異なります。自動連携は質問を 1 件ずつ送り、重要度による絞り込みと件数上限（既定 10 件）を適用しますが、本ボタンは表示中の全質問を 1 つの表としてまとめて渡します。
- 質問票の表セル内の改行は `<br>`、記号 `|` は `&#124;` として出力されます（表形式を保つための変換）。貼り付け先でそのまま表示される点に注意してください。

#### 共通設定: Knowledge Management 用モデル / コンテキスト階層

上記のバックグラウンドマージを有効にすると、その Knowledge Management 子実行だけにメインタスクとは別の実行品質を指定できます。

| 項目 | 既定 | 内容 |
|---|---|---|
| **Knowledge Management 用モデル** | （「使用するモデル」を継承） | 子実行だけに使うモデル。同じ行の **Effort** で reasoning effort も選べます（モデルが対応する場合のみ有効） |
| **Knowledge Management 用コンテキスト階層** | （「コンテキスト階層」を継承） | `default` / `long_context` |

- 3 項目とも右ペインの「共通設定」枠と、設定画面の「一般 > Knowledge Management」の双方から編集できます。
- 未指定（継承）の項目は、設定画面の「基本設定」で選んだメインの値をそのまま使います（従来と同じ振る舞い）。
- バックグラウンドマージが無効のときは 3 項目とも無効化され、実行時にも使われません。
- ワークフローとして **Knowledge Management を直接選んだ実行には適用されません**（従来どおり「使用するモデル」に従います）。

> **使いどころ**: メインの設計タスクは高品質モデルで実行しつつ、定型作業に近い差分同期だけを安価なモデルへ逃がすことで、品質を下げずにコストを押さえられます。

---

### Step 2: Workbench（実行）

実行画面は左に「作業状況」ツリー（各 Step がノードとして表示）、右に「ログ」ペインを並べた構成です。下部には実行モデル・経過時間・コスト・Reqs・Tools・Skills の集計が表示されます。

![GUI Step 2 (実行): 作業状況ツリー + ログ + 実行統計](./images/screenshots/gui-04-step2-execution.png)

```
┌─────────────────────────────────────────────────────┐
│ Step 2: 実行 (ard — Auto Requirement Definition)    │

├─────────────────────────────────────────────────────┤
│  ログ出力                                     [📋]  │
│  （QPlainTextEdit — マウスホイールスクロール・     │
│   テキスト選択・右クリックコピーが利用可能）       │
├─────────────────────────────────────────────────────┤
│  ユーザーアクション                           [📋]  │
└─────────────────────────────────────────────────────┘
                                              [■ 停止]
```

- **📋 コピーアイコン**: ログ・ユーザーアクション各ペインのテキストをクリップボードに 1 クリックでコピー。なお通常 GUI の Workbench では実行コマンドの表示ペインは撤去済みです。
- **スクロール**: OS ネイティブのマウスホイール / スクロールバーが利用可能。
- **テキスト選択**: `Ctrl+A`（全選択）・ドラッグ選択・`Ctrl+C` で部分コピー可能。
- **停止**: 「■ 停止」ボタンで `subprocess.Popen.terminate()` を送信（Windows ではハードキル相当）。

---

<a id="copilot-パネル対話と実行ジョブ連携"></a>

## Copilot パネル（対話と実行ジョブ連携）

ヘッダー右上の **[Copilot]** ボタンで右側のドックを開閉します。ドックは 2 つのタブを持ちます。

| タブ | 用途 |
|---|---|
| **Copilot CLI** | GitHub Copilot CLI の対話セッションをそのまま埋め込んで表示・操作する |
| **実行ジョブ** | 実行中ワークフローへのメッセージ送信と、実行ログ・完了結果の参照 |

### Copilot CLI タブ

[セッション開始] を押すと、リポジトリルートを作業ディレクトリとして `copilot` の対話セッションを
1 プロセス起動します。以降のやり取りは同じセッションで継続するため、会話の文脈が失われません。

- **利用できる機能は Copilot CLI が提供するものそのものです。** `/model`・`/agent`・`/plan`・
  `/autopilot`・`/context`・`/compact`・`/fork`・`/resume`・`/diff`・`/review`・`/mcp`・`/plugin`・
  `/skills`・`/permissions` などのコマンドは、CLI と同じように入力できます。利用可能な一覧は
  `/help` で確認してください。
- **権限は CLI の確認プロンプトに従います。** HVE は `--allow-all-tools` や `--yolo` を
  自動付与しません。ツール実行の可否はセッション内で都度確認され、方針を変えたい場合は
  `/permissions` を使います。
- **セッションと履歴の保存先は Copilot CLI 側です。** HVE はチャット内容を別途保存しません。

> `copilot` コマンドまたは OS 別 PTY backend が見つからない場合は、セッションを開始せずに
> セットアップ手順を案内します（Windows は `hve\setup-hve.cmd`、macOS / Linux は `./hve/setup-hve.sh`）。

#### このタブで Prompt 版を使う

HVE の **Prompt 版**（自然言語から既存 Workflow を計画・実行する利用面）は、
この **Copilot CLI タブをそのまま使います**。専用のタブや画面は追加されていません。

1. このタブで [セッション開始] する
2. [prompts/README.md](./prompts/README.md) から選んだ依頼文を貼り付ける
3. Copilot が `.github/skills/hve-prompt-edition/SKILL.md` に従って request を作り、
   `hve prompt plan` の結果（実行計画と plan SHA-256）を提示する
4. 内容を確認して「この計画で実行してください」と日本語で伝えたときだけ
   `hve prompt run --expected-sha256 <hash>` が実行される

> **このタブであなたがコマンドを入力する必要はありません。** CLI の実行と
> plan SHA-256 の転記は Copilot が代行します。

Prompt 版は **この GUI で保存した設定**（モデル、reasoning effort、並列度、タイムアウト等）を
そのまま再利用し、新しい実行エンジンを持たずに既存の `hve orchestrate` へ委譲します。
手順の全体像は [hve-prompt-getting-started.md](./hve-prompt-getting-started.md) を参照してください。

> GitHub.com の HVE Cloud Agent Orchestrator からの Prompt 実行は現時点では対象外です。

### 実行ジョブタブ

画面の並びは Visual Studio Code の [チャット] と同じです。

| 位置 | 要素 | 役割 |
|---|---|---|
| 上段 | **[対象ジョブ]** / **[更新]** / **[⋯]** | 宛先の選択と補助操作 || 上段下 | **ターンナビゲーション** | 送信メッセージの現在位置と前後移動（送信が 1 件以上のときだけ表示） || 中央 | **会話ビュー** | 送信したメッセージ・受理結果・実行ログを時系列で表示 |
| 中央下 | **送信待ちキュー** | 未処理のメッセージがあるときだけ表示 |
| 下段 | **入力ボックス** | 添付チップ・複数行入力・送信方法・送信ボタン |
| 最下段 | **状態行** | 宛先の状態・対話チャネルの可否・送信待ち件数 |

**[対象ジョブ]** で、実行中のワークフロー／ステップを明示的に選びます。並列実行中でも
一覧にはすべての実行中ステップが並ぶため、宛先を取り違えずに送信できます。

送信方法は 3 種類です。

| 送信方法 | 動作 | 使いどころ |
|---|---|---|
| **キューに追加** | 現在の応答が終わってから順に処理される | 進行を止めずに次の指示を積む |
| **いま割り込む** | 現在の応答へ即時に割り込む | 方向がずれてきたので軌道修正する |
| **中断して送信** | 実行中のターンを中断し、送った指示を新しいターンとして実行する | 現在の作業をやめて別の指示に切り替える |

- 「中断して送信」で送った指示の応答が、そのステップの結果として扱われます。
- 送信結果は送信メッセージの右側に **受理 / 失敗** として表示されます。送信内容そのものはログや統計へ複製されません。
- 選択したジョブの実行ログは同じ会話ビューに表示され、実行の進行に合わせて追記されます。
  実行ログは **加工せずそのまま** 表示します。HVE がログ行を解析して発話者やターンの区切りを推測することはありません。

#### 入力のしかた

- `Enter` で送信し、`Shift+Enter` で改行します。入力量に応じて入力欄が広がり、一定の高さで止まってスクロールします。
- **[+]** でファイルを選ぶと、入力欄の上に添付チップが並びます。チップの `×` で個別に外せます。
- 添付されるのは **パスだけ** です。ファイルの中身は送信されないため、Copilot 側が必要な範囲を読み取ります。
- 添付を含めた本文が送信上限（8 KiB）を超える場合は送信されず、会話ビューに理由が表示されます。

#### 送信したメッセージを行き来する

送信メッセージが 1 件以上あるとき、会話ビューの上に現在位置が出ます。

- 表示は `現在番号/総数` です（例: `3/3`）。左側には現在のメッセージ本文が 1 行で出ます。長い本文や複数行の本文は末尾を省略します。
- **[▲] / [▼]** で前後のメッセージへ移動します。移動先が会話ビューの先頭へ来るようスクロールします。
- 先頭では [▲]、末尾では [▼] が選べなくなります。端から反対側へは回り込みません。
- 会話ビューを直接スクロールすると、いま見ている位置に合わせて番号が変わります。
- 新しく送信すると、そのメッセージが現在位置になります。

#### 送信待ちのメッセージを操作する

未処理の送信要求があるときだけ、会話ビューの下に送信待ちキューが現れます。

- **[↑] / [↓]**: 処理される順番を入れ替えます。
- **[×]**: まだ処理されていない要求を取り消します。
- 実行側が処理を始めた要求は一覧から消え、取り消し・並べ替えの対象になりません。

#### [⋯] メニュー

| 項目 | 動作 |
|---|---|
| **会話をクリア** | 画面の表示だけを消します。送信済みの要求・実行中のジョブには影響しません |
| **会話をコピー** | 会話ビューの全文をクリップボードへコピーします |
| **結果を Copilot で開く** | 下記「完了したジョブの結果を相談する」を実行します |

### 完了したジョブの結果を相談する

ジョブが完了したあとも、対象ジョブを選んだまま **[⋯] → [結果を Copilot で開く]** を選ぶと、
そのジョブの実行ディレクトリ・コンソールログ・完了レポート・生成ファイルの **パスだけ** を
初期メッセージに含めた新しい Copilot CLI セッションを開始します。

- ファイルの中身はプロンプトへ埋め込まれません。必要な範囲を Copilot 自身が読み取ります。
- 対話セッションが実行中の場合は、終了してよいか確認してから切り替えます。
- **セッション作業フォルダーのクリーンアップ設定が `purge` の場合、GUI 終了後は参照先が残りません。**
  実行後に相談する運用では `keep`（既定）または `archive` を選んでください。

### この機能で提供しないもの

HVE GUI は Visual Studio Code 自体の再実装ではありません。エディタのインライン補完・
インラインチャット・ソース管理／デバッガ／テスト UI・拡張機能ホスト・統合ブラウザーなど、
VS Code 固有の実行面は対象外です。Copilot CLI が提供する範囲の機能を、HVE の実行ジョブと
結び付けて使えるようにすることが本パネルの役割です。

実行ジョブタブでは、次の VS Code チャットの要素も提供しません。

| 提供しない要素 | 理由 |
|---|---|
| モデル / reasoning effort の切り替え | 実行中ジョブのモデルは `hve orchestrate` の起動時に決まり、途中で変更する経路がありません |
| 応答の停止ボタン | 「実行中の応答だけを取り消す」送信方法はありません。ジョブ全体の停止は [作業状況] 画面の停止操作です |
| 音声入力 | Copilot CLI / HVE のどちらもこの経路を持ちません |

---

<a id="github-issue-pull-request"></a>

## GitHub Issue / Pull Request

ヘッダー右上の **[GitHub]** ボタンで、GitHub 連携の全てを扱う別ウィンドウ（GitHub Hub）を開きます。設定ウィンドウと同じく非モーダルで、ワークフロー実行中でも使えます。

タブは **[連携設定]** / **[Issue]** / **[Pull Request]** の 3 つです。

タブの上には **「現在のタスク」** が表示され、GUI セッションの run ID、Workflow / instance、対象リポジトリ、関連 Issue / Pull Request、head → base branch、関連付け元を確認できます。Hub で選択・作成した対象と、Orchestrator が確定した対象は同じ表示へ反映されます。実行中の別 Workflow / APP instance の関連付けを混在させません。

- Workflow 実行前に関連付けた Issue は、GitHub 書き込みを伴う実行の `--issue-number` として使われます。
- 実行開始後に Issue を選び直しても、起動済み Orchestrator の Root Issue は変更されません。Hub の追跡先だけが変わります。
- **[Issue の関連付けを解除]** / **[Pull Request の関連付けを解除]** で現在の関連付けを解除できます。
- run-scoped な関連付けは設定ファイルへ自動保存されません。既存の「連携する Pull Request 番号」は起動時の既定値としてだけ使われます。

> **GitHub 設定の場所はここだけです**。以前は設定ウィンドウの「各サービス連携 > GitHub」にも同じ項目がありましたが、現在は本画面の **[連携設定]** タブに一本化されています。保存先は従来と同じ設定ファイルなので、既存の設定はそのまま引き継がれます。

**[連携設定]** タブの **リポジトリ (owner/repo)** 欄が、Issue / Pull Request 両タブの対象リポジトリを兼ねます。未入力の場合は `REPO` 環境変数、次いでローカルの `git remote origin` から推定します。

リポジトリが確定した時点（ウィンドウを開いたときと、リポジトリ欄の入力を確定したとき）に、Issue と Pull Request の一覧をそれぞれ **1 回だけ** 取得します。以降の更新は **[更新]** 押下時だけで、定期的な自動取得（ポーリング）は行いません。

> **一覧が空のとき**: 既定の絞り込みは `オープン` です。オープンな Issue / PR が 1 件も無いリポジトリでは 0 件になります。この場合は画面下部に「「状態」を「すべて」にして [更新] するとクローズ済みも表示されます」と案内が出ます。取得失敗ではなく対象が無い状態です。

一覧の上にある絞り込み欄は、**取得済みの一覧を番号・タイトルでクライアント側だけで絞り込みます**（GitHub API を追加で呼びません）。

> **ページ追加と順序**: Issue / Pull Request 一覧の初回取得は作成日時の降順です。GitHub が次ページを返したときだけ **[さらに読み込む]** が有効になり、押すと取得済み一覧へ追記します。失敗時は既存一覧を保持したまま同じ操作を再試行できます。リポジトリ・状態・**[更新]** を変えると古い次ページ情報は破棄されます。既存項目の更新ではページ順が移動しませんが、ページ取得中の新規作成・state 変更・削除では母集合が変わり、未取得項目が生じる可能性があります。最新状態を確定したい場合は **[更新]** で page 1 から取得し直してください。

### コメント入力欄（書式ツールバーとプレビュー）

Issue 本文・Issue コメント（新規投稿・編集）・Pull Request コメントの入力欄は、github.com のコメント欄と同じく **[編集] / [プレビュー] の 2 タブ + 書式ツールバー** を持ちます。

| ボタン | 挿入される記法 |
|---|---|
| 太字 | `**...**` |
| 斜体 | `*...*` |
| 見出し | 行頭に `### ` |
| 引用 | 行頭に `> ` |
| コード | `` `...` `` |
| リンク | `[選択文字列](url)` |
| 箇条書き | 行頭に `- ` |
| 番号付きリスト | 行頭に `1. ` |
| タスクリスト | 行頭に `- [ ] ` |

- 選択範囲があるときは選択範囲へ、無いときはキャレット位置へ挿入します。行頭付与型は選択した全行に適用されます。
- **[プレビュー]** タブは入力中の Markdown を描画します。入力欄は Markdown の原文をそのまま保持するため、保存してもコードフェンスの言語指定やタスクリストが失われません。
- プレビューは Qt のリッチテキストで描画します。Mermaid 図と数式は描画されません（これらを見るにはファイルプレビュー Dock を使います）。
- 画像・ファイルの添付、`@` メンション補完、`#` 参照補完、絵文字補完は提供しません。

### Issue タブ

| できること | 操作 |
|---|---|
| 一覧の取得・絞り込み | 「状態」で オープン / クローズ / すべて を選び **[更新]** |
| 2 ページ目以降の取得 | **[さらに読み込む]**（取得済み一覧へ追記） |
| 一覧の絞り込み（ローカル） | 一覧上の入力欄へ番号またはタイトルの一部を入力 |
| **Issue の新規作成** | タイトル、任意の本文、ラベル、担当者、マイルストーンを指定して **[Issue を作成]**（下記） |
| 詳細の閲覧 | 一覧から Issue を選択（番号・状態・作成者・ラベル・担当者・本文・URL） |
| タイトル / 本文の編集 | 入力後に **[タイトル / 本文を保存]** |
| metadata の編集 | 取得済み候補からラベル・担当者・マイルストーンを選び **[metadata を保存]** |
| Copilot cloud agent への割当 | base branch を確認して **[Copilotへ割り当て]** |
| クローズ / 再オープン | **[Issue をクローズ]** / **[Issue を再オープン]** |
| コメントの閲覧・投稿 | API の全ページから取得したコメント一覧を確認し、下部の入力欄から **[コメントを投稿]** |
| 自分のコメントの編集 | コメントを選択して編集し **[コメントを更新]**（他人のコメントは読み取り専用） |

#### Issue を新規作成する

Issue タブの作成欄に本文を入力し、**[Copilot でタイトルを生成]** を押すと、GitHub Copilot CLI が本文を要約してタイトル欄へ入力します。生成結果は作成前に自由に編集できます。

タイトルを空欄のまま **[Issue を作成]** を押した場合も、Copilot CLI でタイトルを生成してから通常の Issue を作成します。タイトルを手入力済みの場合は Copilot CLI を呼ばず、そのタイトルをそのまま使います。

- 本文欄はコメント入力欄と同じ **[編集] / [プレビュー] + 書式ツールバー** を持ち、Markdown をそのまま送信します。
- タイトル生成は GitHub Copilot の token / premium request を消費することがあります。処理中はタイトル・本文・生成・作成ボタンを一時的に無効化します。
- 本文が空の場合はタイトルを生成せず、GitHub Copilot の token も消費しません。
- Copilot CLI が見つからない、応答が空、120 秒以内に完了しないなどの失敗時は Issue を作成せず、タイトルと本文を保持してエラーを表示します。
- Copilot CLI は空の一時ディレクトリで `--no-ask-user` と `--available-tools=ask_user` を併用して実行し、入力本文は最大 12,000 文字、生成タイトルは最大 120 文字に制限します。
- 作成に成功すると一覧を更新し、作成した Issue を選択状態にします。絞り込み条件のすでに一覧に現れない場合は、作成された番号をメッセージで知らせます。
- タイトルを入力済みなら本文は空でも作成できます。タイトルと本文が両方空の場合は作成しません。
- **[作成候補を取得]** は対象リポジトリからラベル・担当者・open マイルストーンを最大 100 件ずつ取得します。候補は追加の自動ポーリングを行いません。
- **[作成後、このタスクに関連付ける]** は既定 ON です。OFF にすると Issue は作成しますが、現在のタスクは変更しません。
- GitHub が指定した metadata を反映しなかった場合は、作成済み Issue 番号を保持したまま警告します。同じ Issue を自動で再作成しません。
- API 失敗時はタイトル・本文・metadata の選択を保持します。
- Projects と GitHub Issue Form の field / upload / required validation は本画面では提供しません。

#### 既存 Issue の metadata を編集する

Issue 作成面の **[作成候補を取得]** で取得したラベル・担当者・open マイルストーンを、既存 Issue の編集面でも再利用します。編集面を開くための追加 API request や自動ポーリングは行いません。

- 候補未取得時は、先に **[作成候補を取得]** を実行するよう案内します。
- 候補一覧に無い現在値も選択状態のまま表示し、保存操作だけで意図せず削除しません。
- 空のラベル／担当者選択は全解除、マイルストーンの「未設定」は解除として送信します。
- 保存失敗時は選択を保持します。GitHub の応答が指定値と一致しない場合は、Issue を再作成せず項目名を警告します。

#### Copilot cloud agent へ割り当てる

選択中 Issue で **[Copilotへ割り当て]** を押すと、Issue 番号・repository・base branch を含む確認ダイアログが表示されます。既定の回答は「いいえ」です。base branch を空欄にすると GitHub の既定 branch に委ねます。

- この API は public preview です。応答で Copilot の assignee を確認できない場合は成功表示にしません。
- 割当中は Issue 選択、metadata の置換、コメント投稿など同じ対象への操作を無効化します。失敗時は Issue 選択と base branch 入力を保持します。
- fine-grained PAT には Metadata: read と Actions / Contents / Issues / Pull requests: read and write が必要です。classic PAT は `repo` scope が必要です。

### Pull Request タブ

| できること | 操作 |
|---|---|
| 一覧の取得・絞り込み | 「状態」を選び **[更新]**。一覧上の入力欄でローカル絞り込み |
| 2 ページ目以降の取得 | **[さらに読み込む]**（取得済み一覧へ追記） |
| **Pull Request の新規作成** | 現在のローカルブランチから **[作成前チェック]** を実行し、タイトル等を確認して **[Pull Request を作成]** |
| 詳細の閲覧 | 番号・状態（merged / draft を含む）・作成者・head → base・本文・URL |
| 変更ファイルの確認 | 「変更ファイル」一覧（パスと status） |
| review の閲覧・提出 | **[レビューを更新]**、種類と本文を確認して **[レビューを提出]** |
| 差分行への review comment | **[差分行へレビューコメント]** から patch の行を選択して投稿 |
| check-runs の確認とマージ | **[check-runs を更新]** 後、方式を選び **[Pull Request をマージ]** |
| コメントの閲覧・投稿 | API の全ページから取得した会話コメントを確認し、**[コメントを投稿]** |
| コンソール出力の投稿 | **[コンソール出力を投稿]**（下記） |
| ブランチの push | **[現在のブランチを push]**（下記） |
| head ブランチの削除 | **[head ブランチを削除]**（下記） |

#### Pull Request を直接作成する

Pull Request タブ上部の作成欄では、**現在 checkout 中のローカルブランチだけ**を head として使用します。任意の別ブランチへの checkout や自動 commit は行いません。

1. **Base branch** を確認します（連携設定のベースブランチと同期）。
2. **[作成前チェック]** を押し、head → base、commit 数、変更ファイル数、remote の ahead / behind、公開・未 push 状態を確認します。
3. タイトルと任意の Markdown 本文を入力します。本文が未編集なら `.github/pull_request_template.md` を読み込めます。
4. 必要に応じて関連 Issue、Draft、ラベル、担当者、マイルストーン番号、reviewer user、reviewer team slug を指定します。
5. **[Pull Request を作成]** を押します。

次の場合は fail-closed で作成しません。

- detached HEAD、head と base が同じ、base に対する新規 commit が 0 件
- 未コミットの変更がある
- local checkout の origin と Hub の対象 repository が異なる
- branch が origin に未公開、または未 push commit がある（先に **[現在のブランチを push]** を明示操作します）
- GitHub 上の compare で ahead が 0 件
- 同じ head / base の open Pull Request が既にある（新規作成せず既存 PR を選択します。このとき作成欄の metadata / reviewer は既存 PR へ自動適用しません）

関連 Issue を入力した場合、**「default branch への merge 時に Issue を閉じる」**は既定 OFF です。ON でも base が repository の default branch の場合だけ `Closes #<番号>` を付け、それ以外は plain `#<番号>` にします。この指定は「PR 自動 Approve & Auto-merge」とは無関係で、保存されません。

PR 本体の作成成功後、その番号と URL を直ちに表示し、現在のタスクへ関連付けます。ラベル・担当者・マイルストーン・reviewer の後処理が失敗しても、PR 本体を失敗扱いにしません。再試行に必要な情報を保持できた失敗だけ **[metadata を再試行]** できます。分類できない後処理エラーは警告のみで、安全のため再試行できません。再試行で PR 本体を再作成しません。

**[Copilot でタイトルを生成]** は既存の title generator を使用します。入力済みタイトルを自動上書きせず、ボタンを明示操作した場合だけ置換します。生成には GitHub Copilot の token / premium request を消費することがあります。

#### review と差分行コメント

Pull Request の詳細を選択すると review 一覧を 1 回取得します。1 回の取得で API の全ページを時系列順に読み、以降は **[レビューを更新]** の明示操作だけで再取得し、自動ポーリングしません。review は `APPROVE` / `REQUEST_CHANGES` / `COMMENT` の 3 種です。`REQUEST_CHANGES` と `COMMENT` は本文必須、`APPROVE` は本文を省略できます。提出失敗時は本文と種類を保持します。

**[差分行へレビューコメント]** は GitHub が返した `patch` を持つファイルだけを対象にします。ダイアログで行を選ぶと path / line / LEFT・RIGHT / head commit SHA が確定表示されます。同ダイアログは既存の review comment を全ページ取得して API 順に表示します。patch が無いファイルの行番号は推測しません。PR 詳細と変更ファイルの取得時点で head SHA が一致しない場合は起動せず、詳細の再取得を案内します。

#### check-runs を確認してマージする

**[check-runs を更新]** は選択中 Pull Request の head commit を明示取得します。未取得、応答を解釈できない、head SHA 不明、未完了、または conclusion が `success` / `neutral` / `skipped` 以外の check-run がある場合、マージボタンは無効です。

マージ方式は `merge` / `squash` / `rebase` の 3 種です。実行前の確認ダイアログには Pull Request 番号、head / base branch、方式を表示し、既定の回答は「いいえ」です。確認後に head が変わった場合は送信しません。405（保護ルール等）や 409（head 更新・競合）、または成功を確認できない応答ではマージ済みと表示せず、取得済み check-runs を破棄します。再度 **[check-runs を更新]** してから判断してください。native Auto-merge と merge queue の有効化は行いません。

#### コンソール出力を PR コメントとして残す

**[コンソール出力を投稿]** で、[作業状況] 画面に表示中のコンソール出力を、選択中の PR へコメントとして投稿できます。

- 本文は見出しとメタ情報（run-id / 総行数 / 掲載行数）の表 + 折りたたみ（`<details>`）のコードブロックという、GitHub 上で読みやすい形式に整形されます。
- 掲載されるのは **末尾 300 行** までです。超えた分は「先頭 N 行を省略」と本文に明記されます。GitHub のコメント作成 API は本文の最大長を公開していないため、全文投稿は行いません。
- カラー表示用の ANSI エスケープは除去され、出力中に \`\`\` があってもコードブロックが壊れないようフェンス長を自動調整します。
- 全文は従来どおり `work/run/<run-id>/console-log.txt` に保存されます。
- 掲載行数や書式を変える設定項目はありません。

#### push と head ブランチの削除

| ボタン | 動作 |
|---|---|
| **[現在のブランチを push]** | 現在のローカルブランチを `git push -u origin <ブランチ>` で push します。`git add` / `git commit` は行いません |
| **[head ブランチを削除]** | 選択中 PR の head ブランチを **origin から** 削除します。github.com の PR ページにある [Delete branch] と同じ位置づけです |

- 削除ボタンは **PR が merged または closed のときだけ** 有効になります。実行前に対象ブランチ名を含む確認ダイアログが出ます。
- 削除されるのは **リモート（origin）のブランチだけ** です。ローカルブランチの削除はこの画面では行わず、「マージ後にローカル作業ブランチを削除」設定が担います。
- push と削除は別操作です。連続実行するボタンはありません。

### 実行中の進捗を Issue / PR へ自動で Post する

**[連携設定]** タブの **進捗を自動 Post** で、ワークフロー実行中の進捗を関連 Issue / Pull Request へ自動投稿できます。

| 選択肢 | 動作 |
|---|---|
| **Post しない**（既定） | 自動投稿を行いません。GitHub API を呼びません |
| **Issue のみ** | 対象 Issue へだけ投稿します |
| **Pull Request のみ** | 対象 PR へだけ投稿します |
| **Issue と Pull Request** | 両方へ投稿します |

- Post 先 1 件につき **実行 1 回あたりコメントを 1 件だけ作成** し、以降は同じコメントを更新します。ログ 1 行ごとにコメントが増えることはありません。
- 更新の契機は **実行開始、各 Step の完了（完了 / 失敗 / スキップ / ブロック）、ワークフロー終了** の 3 つだけです。
- 本文に含まれるのは run ID、ワークフロー名、Step ごとの状態と経過時間だけです。**prompt ・応答本文・ツールの入出力・認証情報は含まれません。**
- 最終更新のときだけ、[作業状況] 画面のコンソール出力末尾 300 行を折りたたみで付加します（認証情報はマスク済み）。
- 新規作成される PR は実行の最後にしか番号が確定しないため、その PR への自動投稿は **最終更新の 1 回だけ** です。
- 投稿に失敗してもワークフローは失敗しません。次の更新契機で再試行します。
- 実行中でも設定を切り替えられます。**Post しない** に戻しても、すでに投稿済みのコメントは削除されません。
- 手動の **[コメントを投稿]** や **[コンソール出力を投稿]** はこの設定とは独立して従来どおり使えます。

### マージ後のローカルブランチを自動で削除する

「マージ後にローカル作業ブランチを削除」が有効な GUI 実行では、**その実行が新規作成した作業ブランチ** について、GUI が起動している間だけ対象 PR の状態を低頻度で確認し、マージを見つけたときだけローカルブランチを削除します。

- 削除されるのは **ローカルブランチだけ** です。リモートの head ブランチは削除しません（**[head ブランチを削除]** または github.com の自動削除設定を使ってください）。
- **「PR 用の新しい作業ブランチを作成」を OFF にして現在のブランチを使った場合、そのブランチは自動削除の対象外です。** 利用者が選んだブランチを勝手に消しません。
- ベースブランチと同名、PR の head が別リポジトリ（fork）、head / base / 番号が一致しない、未マージのまま close された——のいずれかに当てはまる場合は削除しません。
- 確認は対象 PR 番号を指定した問い合わせだけで行い、Issue / PR の一覧を定期取得することはありません。
- **GUI をマージ前に終了した場合、その後の自動削除は行われません。** 次回起動時に監視を再開する仕組みもありません。手動で `git branch -D <ブランチ>` してください。

### この画面で提供しないもの

| 提供しない機能 | 理由 |
|---|---|
| リアクション / Projects / タイムラインイベントの編集 | Issue metadata の編集は提供しますが、これらは対象外です |
| Projects v2 / native Auto-merge / merge queue / fork・cross-repository head | GitHub Hub の直接 PR 作成では対象外です |
| 一覧の自動更新（ポーリング） | GitHub API のレート制限を不要に消費しないため、リポジトリ確定時の 1 回の取得を除き **[更新]** 押下時のみです |
| GitHub Search API によるキーワード検索 | **[さらに読み込む]** でページを追加取得できますが、絞り込みは取得済み一覧に対するローカル処理です |
| 画像添付 / `@` / `#` / 絵文字の補完 | コメント入力欄の対象外です（手入力で代替できます） |

GUI から `--create-pr` / `--create-issues` を使う実行では、Orchestrator が PR 作成直前に PR 本文を GitHub Copilot CLI へ渡し、PR タイトルを自動生成します。この Orchestrator 経路は、GitHub Hub から現在の commit 済みブランチを直接 PR 化する経路とは別です。

- PR タイトル生成も GitHub Copilot の token / premium request を消費することがあります。
- Workflow の `[AAS]` などの prefix は保持され、local checkpoint の draft PR では `— local checkpoint (draft)` も保持されます。
- Copilot CLI の失敗時は従来の決定的タイトルへ自動的に戻し、PR 作成自体は継続します。
- CLI 単独実行および Cloud 実行ではタイトル自動生成を行わず、従来のタイトルを使います。

### Root Issue を新規作成する / 既存 Issue に連携する

GitHub Hub → **[連携設定]** → 「リポジトリ / Issue 設定」の **「Root Issue の扱い」** で選びます。

| 選択 | 振る舞い |
|---|---|
| **新規作成**（既定） | GUI workflow では Root Issue 本文から Copilot CLI がタイトルを生成します。「Issue タイトル（上書き）」を指定した場合は Copilot CLI を呼ばず、その値を使います |
| **既存 Issue に連携** | 「連携する Issue 番号」の Issue を Root Issue として使います。Sub-Issue はその Issue の子として作成され、PR 本文に `Closes #<番号>` が入ります。タイトル上書きは送られません |

- この選択は **「GitHub Issue を作成」を有効にしたときだけ** 効力を持ちます。CLI では `--issue-number <N>` に相当し、`--create-issues` を伴わないと警告のうえ無視されます。
- 番号は直接入力できるほか、**[Issue を選択...]** でリポジトリの Issue 一覧から選べます（`GH_TOKEN` が必要）。
- 「既存 Issue に連携」で番号が未入力の場合、[実行 ▶] は開始されず警告が出ます。
- 指定した番号を取得できない場合や、Pull Request の番号を指定した場合は、**実行を中止します**（Root Issue の新規作成へは戻りません）。誤った番号のまま Sub-Issue を無関係な Issue へ紐付けないためです。
- Root Issue の自動タイトル生成は GitHub Copilot の token / premium request を消費することがあります。失敗時は従来の `[AAS] ...` 形式へ fallback し、Issue 作成を継続します。
- Sub-Issue は Step ID と Step 名を識別できる必要があるため、`[AAS] Step.1 ...` 形式の決定的タイトルを維持し、Copilot CLI へ問い合わせません。

### 現在のタスクへ Pull Request を関連付ける

GitHub Hub の一覧から Pull Request を選択するか、連携設定の **「連携する Pull Request 番号」** で番号を直接入力します。Hub で作成した Pull Request は自動的に現在のタスクへ関連付けられます。

> この指定は **GUI セッション内の run / Workflow / instance 単位**で使われ、`hve` の実行引数（CLI オプション）には含まれません。設定の番号は起動時の既定値としてだけ読み込まれ、実行中の関連付け変更は設定へ自動保存されません。Orchestrator は既存 PR を入力として受け取る処理を持たないためです。

> **PR 作成時のブランチ**: 「GitHub Issue を作成」または「GitHub Pull Request を作成」を有効にすると、Orchestrator はベースブランチから `copilot-sdk/<prefix>-<8 桁>` 形式の作業ブランチを作成して checkout し、そのブランチで作業してから PR を作成します。ベースブランチへ直接コミットすることはありません。

---

<a id="plugin-mcp-server-認証"></a>

## Plugin / MCP Server 認証

GUI Orchestrator は、GitHub Copilot / GitHub CLI / Work IQ の認証導線を GUI から起動できます。一方、任意の MCP Server の登録・OAuth 再認証は GitHub Copilot CLI 側で管理します。GUI は登録済み MCP Server / Plugin の一覧表示と手順案内を行います。

> **一覧に出ていても、リポジトリが `.github/.mcp.json` で宣言していない MCP Server / Plugin は HVE のセッションからは使われません。** HVE は実行時に MCP の自動探索を停止し、宣言分だけをセッションへ渡します（詳細は CLI ガイドの「HVE のセッションが接続する MCP サーバー」）。Copilot CLI へインストール済みでも、認証不備などで利用できない Plugin が HVE の実行を妨げないようにするためです。

### 認証ボタンの場所

- CLI: `python -m hve login` — GitHub Copilot SDK へのログインを行います（GUI に専用ボタンはありません）。
- ステータスバー / 設定 → 基本設定: **「利用できるモデルの取得」** — ログイン済みの GitHub Copilot SDK からモデル一覧を取得しキャッシュを更新します（ログイン自体は行いません）。取得結果は隣接する **「使用するモデル」** 表示にも反映されます。
- **GUI 起動時の自動確認** — `GH_TOKEN` / `GITHUB_TOKEN` が未設定のときだけ `gh auth token` を試し、取得できなければログインを行うか確認するダイアログを 1 回だけ表示します（下記参照）。
- 設定 → 各サービス連携 → GitHub: **「GitHub CLI でログイン」** — `gh auth login` を埋め込み端末で実行し、この GUI セッションの `GH_TOKEN` に橋渡しします。Issue / PR 作成やブランチ取得向けです。
- Work IQ 設定: **「Work IQ 認証確認」** — `@microsoft/workiq` の EULA / Microsoft 365 認証を確認します。

### 起動時の GitHub 認証確認

GUI は起動時に次の順で GitHub 認証状態を解決します。

1. `GH_TOKEN` または `GITHUB_TOKEN` が設定済みなら何もしません（`gh` を起動しません）。
2. 未設定なら `gh auth token` を試し、取得できたトークンをこの GUI セッションの `GH_TOKEN` へ注入します。
3. 取得できなかった場合に限り、**「今すぐ `gh auth login` を実行しますか？」** の確認ダイアログを 1 回だけ表示します。

確認ダイアログで「いいえ」を選んでも GUI は通常どおり起動します。GitHub 連携を使わないワークフローはそのまま実行できます。後からログインしたい場合は設定 → GitHub → 「GitHub CLI でログイン」を使います。

> GUI が `gh auth login` を勝手に実行することはありません。対話ログインは必ず利用者の明示操作で行われます。取得したトークンはセッション限りで、ディスクへ保存されません。

### 対象とする認証先

GUI は **GitHub Copilot CLI を唯一の信頼ソース** とし、以下の方法で検出します:

| 対象 | 検出方法 | 認証方式 |
|---|---|---|
| GitHub Copilot | 常時必須 | `copilot login` (Device Flow)。CLI (`python -m hve login`) から実行（GUI に専用ボタンはなし） |
| Microsoft Work IQ | Work IQ オプションを有効にするとき | `npx @microsoft/workiq accept-eula` + `ask -q ping`。GUI の「Work IQ 認証確認」から実行可能。**実行開始時に認証確認が失敗した場合、GUI からの実行は停止せず、その実行に限って Work IQ を自動無効化して続行します**（実行ログに要求元の設定名を出力） |
| 任意の MCP Server | `copilot mcp list --json` に登録されている全サーバ | GitHub Copilot CLI 側で登録・認証。GUI は一覧表示と認証手順表示のみ |
| 外部 Copilot SDK サーバー | 「設定」→「CLI 接続」で `cli_url`（例: `localhost:4321`）を指定 | TCP 疎通テスト |

> **Breaking Change (Wave 3 以降)**: GUI 設定の `mcp_config`（MCP Server 設定 JSON
> ファイルパス）と `workiq_tenant_id` は **廃止** されました。
> 代わりに `copilot mcp add` / `copilot plugin install` で Copilot CLI 側に登録してください。
> 既存設定ファイルに残存していた場合、初回起動時に自動削除されます。

### MCP Server の扱い

GUI の MCP セクションは **登録済み一覧** です。実行時に MCP Server を Copilot SDK セッションへ渡す場合は、CLI と同じく `--mcp-config` を使います。`--mcp-config` は直接 map 形式と `.github/.mcp.json` の `mcpServers` wrapper 形式の両方を受け付けます。

一覧に登録されていることと、HVE のセッションへ渡ることは別です。HVE が接続するのは `.github/.mcp.json` の宣言分と HVE 内部の Work IQ サーバーだけです。

MCP Server の登録・OAuth 再認証は GitHub Copilot CLI の対話 UI で実施してください。GUI の「認証手順...」ボタンは、対象サーバーの再認証手順を表示する案内機能です。

### 操作フロー

1. GitHub Copilot SDK を使う前に、必要なら CLI で **`python -m hve login`** を実行
2. Issue / PR 作成やブランチ取得を使う場合は、起動時の確認ダイアログでログインするか、後から **「GitHub CLI でログイン」** を押下
3. Work IQ を使う場合は、必要なら **「Work IQ 認証確認」** を押下
4. 任意 MCP Server は、GUI の一覧で登録状況を確認し、必要なら **「認証手順...」** で Copilot CLI 側の手順を確認

### 認証が不足していた場合の振る舞い

- **起動時**: GitHub 認証のみ上記の手順で 1 回解決を試みます。拒否しても起動は継続します。
- **実行開始前**: GUI は認証状態を自動で定期確認しません。「Work IQ 認証確認」「GitHub CLI でログイン」は利用者が押したときだけ実行されます。Step 1 の統合 precheck は、GitHub 書き込みを伴う実行に限り、起動時の認証解決後に現 GUI プロセスへ設定された `GH_TOKEN` / `GITHUB_TOKEN` を確認します。ここで `gh auth token` を再実行することはなく、未設定なら `AUTH` として表示して Step 1 に留まります。
- **子プロセス起動後**: GUI が起動した `hve orchestrate` サブプロセスは、active step の解決後、最初のモデル呼び出し・ブランチ作成・DAG 構築より前に、Git remote `origin` と `refs/heads/<ベースブランチ>` の完全一致を共通 preflight で確認します。保存済みのベースブランチが remote に存在しない場合は fail-closed とし、`main`、ローカルブランチ、GitHub の既定ブランチへ自動補正しません。GitHub Copilot / Work IQ / Azure の各認証 preflight も子プロセスが担い、失敗理由を実行ログへ出力して終了します。GUI から子プロセスへ入力を送る経路は無いため、これらの preflight が対話入力を求めることはありません（FR-GUI-23）。
- **実行中の失効**: 実行中に認証が失効した場合の自動検知・自動再認証は行いません。

### 「利用できるモデルの取得」ボタンと「使用するモデル」表示

ステータスバー右端の「**利用できるモデルの取得**」ボタンは:

- 常に表示されます
- 押下時は **モデル一覧の取得とキャッシュ更新のみ** を実行します（GitHub Copilot SDK へのログイン自体は行いません。未ログインの場合は事前に CLI で `python -m hve login` を実行してください）
- 同じボタンは「HVE 設定」→「基本設定」の一番上にも配置されており、機能・挙動は全く同じです（どちらから押しても同じ処理が実行され、両方の画面の表示に反映されます）

「利用できるモデルの取得」ボタンの右側には **「使用するモデル」** / **「Effort」** の選択コンボがあり、「HVE 設定」→「基本設定」の「使用するモデル *必須」および「Effort」と**同じ選択内容**を示します。両者は別々に生成されたウィジェットであり、`settings_store` とシグナル経由で値を同期しています（同一の物理ウィジェットではありません）。ここで直接選択を変更でき、変更内容は即座に `settings_store` へ保存され、「HVE 設定」ダイアログを開いている場合はそちらの表示にも反映されます。

---

## データフロー

> **GUI → サブプロセス → DAG → 成果物** のアーキテクチャ詳細は [hve-technical-architecture.md §5 / §6](./hve-technical-architecture.md#5-hve-gui-orchestrator) を参照してください。

GUI の操作（ワークフロー選択・オプション設定）は `python -m hve orchestrate ...` コマンドに変換され、`hve orchestrate` エンジンを経て Prompt DAG が実行されます。Prompt は `work/` / `docs/` / `knowledge/` / `docs-generated/` といった成果物ファイルを生成・更新します。

---

## 複数セッションの同時起動

メニュー「セッション」→「新規セッション...」を選択すると、別の HVE GUI Orchestrator ウィンドウが追加で起動します。各ウィンドウは独立した `python -m hve orchestrate ...` サブプロセスを持つため、セッション間の干渉はありません。詳細な状態管理・終了時挙動は [hve-technical-architecture.md §5.8](./hve-technical-architecture.md#58-複数セッションの同時起動) を参照。

```bash
# ターミナルから複数起動することもできます（各プロセス独立）
python -m hve &
python -m hve &
```

ウィンドウタイトルに `HVE GUI Orchestrator - Session #N (ワークフロー ID)` の形で番号が表示されます。

---

## CLI との違い・使い分け

| 機能 | HVE CLI Orchestrator<br>（ターミナル Workbench） | HVE GUI Orchestrator |
|---|---|---|
| ログスクロール | キーバインド（`↑↓` / `PgUp/Dn`） | マウスホイール・スクロールバー |
| テキストコピー | ターミナルバッファ依存 | 📋 アイコン / `Ctrl+C` |
| 複数セッション | 非対応 | メニューから複数ウィンドウ起動 |
| 起動ウィザード | 逐次プロンプト | 単一ウィンドウ 2 ステップ |
| ARD 添付資料 | 手動でファイル配置 + `--attached-docs` | ドラッグ&ドロップ自動変換 |
| 追加依存 | なし | `PySide6>=6.6` |
| Work IQ C4 オプション | 利用可 | 利用可（GUI 固有制約なし） |

---

## 中断と再開（Resume）— 廃止（v1.1）

GitHub Copilot CLI SDK の複数デバイス間セッション管理が不十分なため、CLI / GUI の Session State（Resume）機能は **v1.1 で全廃** しました。GUI の「■ 停止」ボタンは `subprocess.terminate()`（Windows ではハードキル相当）を送信してワークフローを停止しますが、保存付き中断・再開（Resume）は提供されません。

> **Copilot CLI の `/resume` とは別概念です。** Copilot パネルの対話タブで使える `/resume` は
> **Copilot CLI 自身のチャットセッション**を選び直す機能です。HVE のワークフロー（DAG 実行）を
> 途中から再開するものではありません。ワークフローを分割実行したい場合は `--steps` で範囲を絞ってください。

### 進捗を引き継いで再実行する（Resume とは別機能）

廃止したのは **SDK セッションの復元** であり、HVE 自身が保存する **ワークフロー進捗（どのステップが成功したか）** は別機能として利用できます。

Step 1 の `C5 GitHub` セクションにある **「進捗を引き継いで再実行する run-id」** へ過去の run-id を入力すると、その run で成功済みのステップを除外して実行します（CLI の `--resume-run` と同じ機能）。

- 未完了のステップは **新しいセッション** で実行されます。会話履歴は復元されません。
- 空欄のときは通常実行となり、オプションは渡されません。
- 進捗記録が無い run-id を指定すると、実行時に停止します（全ステップの再実行へはフォールバックしません）。
- fan-out するステップは、子ステップが成功済みでも親ステップ単位で再実行されます。

---

## コマンドリファレンス

GUI Orchestrator は最終的に `python -m hve orchestrate ...` コマンドを生成・実行します。通常 GUI は Step 1（ワークフロー / オプション）と Step 2（Workbench）の 2 画面構成で、生成コマンドを画面上で確認・コピーする経路はありません。

- **全オプションの一覧・既定値・型**: [hve-cli-orchestrator-guide.md — コマンドリファレンス（CLI モード）](./hve-cli-orchestrator-guide.md#コマンドリファレンスcli-モード) を参照。
- **GUI 固有の制約**: `--workbench off` が自動注入され、ターミナル Workbench 系オプション（`--workbench` / `--workbench-body-lines` / `--workbench-history`）は GUI から指定不可です。

---

## ワークフロー一覧

選択可能な 13 ワークフロー（`ard` / `aas` / `aad-web` / `asdw-web` / `adfd` / `adfdv` / `adi` / `akm` / `adoc` / `ada` / `aag` / `aagd` / `aar`）の正式名称は [Step 1: ワークフロー選択](#step-1-ワークフロー選択) に記載しています。

- **各ワークフローの DAG・成果物・依存関係**: [workflow-reference.md](./workflow-reference.md) を参照。
- **フェーズ別ガイド**: [README — フェーズ別ガイド](../README.md#フェーズ別ガイド) を参照。

---

<a id="fork-on-retry-dag-並列実行post-step-自動プロンプト"></a>

## Fork-on-Retry / DAG 並列実行・Post-step 自動プロンプト

DAG 並列実行（`--max-parallel`）と Post-step 自動プロンプト（`--auto-qa` / `--auto-contents-review` / `--auto-coding-agent-review`）は、GUI では Step 1 右ペインの「共通設定」枠と設定画面の「基本設定」/「QA (質問票)」/「レビュー」から設定でき、Fork-on-Retry も CLI と共通の挙動です。詳細は次を参照してください。

- [hve-cli-orchestrator-guide.md — 付録C: DAG 並列実行と Post-step 自動プロンプト](./hve-cli-orchestrator-guide.md#付録c-dag-並列実行と-post-step-自動プロンプト)
- [hve-cli-orchestrator-guide.md — フォーク機能 Fork-on-Retry](./hve-cli-orchestrator-guide.md#フォーク機能-fork-on-retry)

---

## セキュリティ・SSO・関連リンク

セキュリティ・SSO・トークン管理・関連リンクは CLI Orchestrator と共通です。

- [hve-cli-orchestrator-guide.md — 付録E: セキュリティ・SSO・関連リンク](./hve-cli-orchestrator-guide.md#付録e-セキュリティsso関連リンク)

---

## トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `hve.cmd` をダブルクリックすると `.venv Python not found` と表示される | 仮想環境未作成 | ランチャが案内する通り `hve\setup-hve.cmd` または `pwsh -NoProfile -File hve\setup-hve.ps1` を実行 |
| `hve.cmd` / `hve.sh` が exit code 2 で停止する | GUI 依存（PySide6 等）未インストール | 表示される通り `hve\setup-hve.cmd` / `./hve/setup-hve.sh` を実行してから `hve.cmd gui` / `./hve.sh gui` で再起動 |
| GUI 終了後もコマンドプロンプトが残る（Windows） | エラー時のメッセージ保持のための仕様 | 正常終了時は黒画面を任意で閉じて OK |
| `./hve.sh` が `Permission denied` | 実行権限なし | `chmod +x hve.sh` を実行してから再試行 |
| `./hve.sh` で `.venv の Python が見つからない` と表示される | 仮想環境未作成 | スクリプトが案内する通り `./hve/setup-hve.sh` を実行 |
| GUI の「GitHub CLI でログイン」で案内文が出て端末が開かない | `gh` 不在、または PTY backend（`pywinpty` / `ptyprocess`）不在 | `hve\setup-hve.cmd` / `./hve/setup-hve.sh` を実行して再セットアップ。詳細は [troubleshooting.md](./troubleshooting.md) |
| `python -m hve` / `python -m hve gui` でエラー | GUI 依存未インストール | `hve\setup-hve.cmd` / `./hve/setup-hve.sh` を実行（引数なし起動は CLI に自動フォールバック） |
| D&D で `.docx` / `.pdf` / `.xlsx` / `.pptx` / `.html` が変換されない | `gui-docconvert`（markitdown）未インストール | `hve\setup-hve.cmd` / `./hve/setup-hve.sh` をオプション無しで再実行 |
| GUI が起動しない（X11 / Wayland エラー） | ディスプレイサーバー未接続 | SSH ポートフォワードや X11 転送を設定するか、CLI Orchestrator を使用 |
| ウィンドウが複数起動しない | PySide6 バージョン不足 | `PySide6>=6.6` を確認 |

その他のトラブルは [troubleshooting.md](./troubleshooting.md) を参照してください。

---

<a id="多言語表示日本語-english"></a>

## 多言語表示（日本語 / English）

GUI は日本語（既定）と英語の 2 言語に対応しています。

### 言語の切替

[設定] メニュー → **一般 → 言語 / Language** から選択できます。

| 選択肢 | 動作 |
|---|---|
| 自動 / Auto（既定） | OS のロケールから判定（`ja*` → 日本語、それ以外 → English） |
| 日本語 | 強制的に日本語表示 |
| English | 強制的に英語表示 |

**変更後はアプリの再起動が必要です。** 設定変更時に再起動を促すダイアログが表示されます。

### 環境変数による上書き

設定値より優先されます（CI / トラブルシュート用途）:

```pwsh
# Windows PowerShell
$env:HVE_GUI_LANG = "en_US"; python -m hve gui
```

```bash
# macOS / Linux
HVE_GUI_LANG=en_US python -m hve gui
```

有効値: `ja_JP` / `en_US` / `auto`。

### 翻訳ファイルの更新（開発者向け）

ソース言語は日本語（`ja_JP`）。英訳は `hve/gui/i18n/hve_gui_en_US.ts` を編集し、`pyside6-lrelease` で `.qm` をコンパイルします。詳細は [hve/gui/i18n/README.md](../hve/gui/i18n/README.md) を参照。

`setup-hve.ps1` / `setup-hve.sh` 実行時（オプション無し既定）に `.ts` が `.qm` より新しい場合は自動コンパイルされます。

---

## GUI を拡張する（開発者向け）

GUI 自体を変更する場合の正本、変更手順、回帰検証、互換性の観点をまとめます。

### 設定・実装の正本

| 変更したいもの | 正本 |
|---|---|
| ウィンドウ構成・Dock・監視ルートの適用 | `hve/gui/main_window.py` |
| Step 1 / Step 2 のページ | `hve/gui/page_workflow_select.py` / `hve/gui/page_options.py` / `hve/gui/page_workbench.py` |
| 設定項目と既定値・永続化（`hve/.settings.txt`） | `hve/gui/settings_store.py` |
| 設定値とウィジェットの対応（`_SECTION_FIELDS`。永続化・復元・autosave の配線） | `hve/gui/settings_apply.py` |
| 設定ウィンドウの UI | `hve/gui/settings_window.py` |
| ヘルプ本文 | `hve/gui/help_content.py` |
| CLI 引数への変換 | `hve/gui/orchestrate_args.py` |
| セッション作業ディレクトリと env 伝播 | `hve/gui/session_workdir.py` |
| Step 1 スナップショットとマスキング | `hve/gui/step1_args_snapshot.py` |
| エクスプローラー監視ルートの解決 | `hve/gui/explorer_roots.py` |
| 翻訳 | `hve/gui/i18n/`（[README](../hve/gui/i18n/README.md)） |
| GUI 依存パッケージ（extras） | `pyproject.toml` の `gui` / `gui-pty` / `gui-docconvert` |

### 変更手順

1. **設定項目を追加する**: `hve/gui/settings_store.py` の既定値に追加し、`hve/gui/settings_window.py` に UI を追加する。**値を保存・復元する項目は `hve/gui/settings_apply.py` の `_SECTION_FIELDS` へ「設定キー → ウィジェット属性名」を登録する**（登録しないと設定ファイルに値は残るが画面へ復元されず、画面の変更も保存されない）。CLI へ渡す必要がある項目は `hve/gui/orchestrate_args.py` の変換も更新する。
2. **ページを追加・変更する**: `hve/gui/page_*.py` を変更する。Step 構成を変える場合は Step 1 → Step 2 の受け渡し（`OrchestrateArgs`）を壊さないことを確認する。
3. **ヘルプ文言を変更する**: `hve/gui/help_content.py` を変更する。本ガイドと文言が対応するため、同じ変更でドキュメント側も更新する。
4. **翻訳を追加する**: 日本語をソースとし、`hve/gui/i18n/hve_gui_en_US.ts` を更新して `.qm` をコンパイルする。

### 回帰検証

```bash
# GUI ヘルプ本文の契約
python -m pytest hve/tests/test_gui_help_content.py

# ページ・設定・インポート
python -m pytest hve/tests/test_gui_pages.py hve/tests/test_gui_settings_store.py hve/tests/test_gui_imports.py

# 作業ディレクトリ（work/run/<run-id>）の契約
python -m pytest hve/tests/test_run_unified_workdir.py
```

GUI テストはヘッドレス環境では実行環境（Qt プラットフォームプラグイン）に依存します。実行できない場合は理由を記録し、CLI 側の契約テストで代替してください。

#### macOS GUI テスト

macOS 固有の window / menu / dialog / application lifecycle、theme / font / icon / i18n layout、QtWebEngine、`darwin` / POSIX 分岐、GUI 依存、または macOS launcher / setup に影響する変更は、手動 workflow `.github/workflows/test-hve-gui-macos.yml` で検証します。GUI に影響しない変更や docs-only 変更では実行しません。影響を判断できない場合は、費用を発生させる前に利用者へ確認します。

| Scope | 内容 | Timeout |
|---|---|---:|
| `smoke`（既定） | Qt の実 `cocoa` platform plugin で MainWindow を起動し、Python 例外、Qt Warning / Critical / Fatal、ウィンドウ生成、skip=0、スクリーンショットを検証 | 15分 |
| `full` | `hve/gui/tests` を `offscreen` で全量実行した後、別プロセスで同じ `cocoa` smoke を実行 | 120分 |

この workflow は `workflow_dispatch` 専用で、自動起動しません。実行前に GitHub の公式 Actions runner 料金を確認し、runner / architecture / scope、単価・確認日・出典 URL、予測時間・予測額、`timeout（分）×単価（USD/分）` の最大額、および free minutes 残量が不明なら実請求額が 0 から最大額までになりうることを提示します。利用者がその1回を明示承認した場合だけ、Actions 画面の **Test HVE GUI on macOS** から次を入力します。

- `test_scope`: `smoke` または `full`
- `estimated_cost_usd`: 提示・承認済みの予測課金額
- `cost_approved`: 承認済みの場合だけ有効化

既存 run の **Re-run jobs** は `github.run_attempt == 1` のゲートで実行されません。失敗または cancel 後は、料金を再確認して新しい見積りと承認を得てから、新しい workflow run を起動します。

結果は7日間の artifact（JUnit XML、Qt log、MainWindow PNG）で確認できます。MainWindow PNG は `QWidget.grab()` で取得し、macOS の Screen Recording / Accessibility 権限や TCC 変更を使用しません。

料金の正本: [GitHub Actions runner pricing](https://docs.github.com/en/billing/reference/actions-minute-multipliers)

### 互換性・安全性

- `hve/.settings.txt` は既存ユーザーの設定ファイルです。キー名の変更・削除は互換性を壊すため、既定値の追加を優先してください。
- Step 1 スナップショットはマスキング済みですが、`work/run/<session_run_id>/` は使い捨ての作業領域です。コミット対象に含めないでください。
- GUI が子プロセスへ注入する `GH_TOKEN` のコピーはセッション限りで、GUI 終了で破棄されます。一方で `gh auth login` 自体はトークンをシステム資格情報ストアへ保存し、利用できない場合は平文ファイルへフォールバックするため、保存先の取り扱いを変更する場合は影響を評価してください。

---

## 関連ドキュメント

| ドキュメント | 内容 |
|---|---|
| [hve-gui-getting-started.md](./hve-gui-getting-started.md) | 初期セットアップ全体（GUI） |
| [hve-cli-orchestrator-guide.md](./hve-cli-orchestrator-guide.md) | CLI Orchestrator ガイド・詳細オプション |
| [cloud-session.md](./cloud-session.md) | Copilot SDK Cloud Sessions（Step 実行先の振り分け） |
| [pricing-guide.md](./pricing-guide.md) | GUI Footer / 統計ポップアップに出る料金・リアルタイム統計の見方 |
| [web-ui-guide.md](./web-ui-guide.md) | Cloud Agent Orchestrator（GitHub Issue/PR） |
| [workflow-reference.md](./workflow-reference.md) | ワークフロー一覧・Prompt 一覧 |
| [hve-technical-architecture.md](./hve-technical-architecture.md) | GUI / CLI / Cloud の技術アーキテクチャ詳細（開発者向け） |
| [hve/gui/i18n/README.md](../hve/gui/i18n/README.md) | GUI 翻訳ファイル管理（開発者向け） |

---

## 公式出典

- Qt for Python（PySide6）— <https://doc.qt.io/qtforpython-6/>
- MarkItDown（microsoft/markitdown） — <https://github.com/microsoft/markitdown>
- GitHub CLI マニュアル（`gh auth login`） — <https://cli.github.com/manual/gh_auth_login>


---

## Step 1 事前チェックスナップショット（args/パラメータ保存）

Step 1「ワークフロー選択」画面で [次へ] を押し、4 カテゴリ統合 precheck とプランレビューが完了するたびに、その時点の args/パラメータ一式が JSON スナップショットとして自動保存されます。後追いデバッグ・監査・サポート問い合わせ時の再現用です。

### 保存先

```
<repo>/work/run/<session_run_id>/step1-precheck/
├── <UTC timestamp>__iter1/        # 1 回目の precheck 通過時
├── <UTC timestamp>__iter2/        # ギャップ適用→再 precheck 通過時
├── ...
└── latest-accepted/               # 「このプランで実行」承認時のコピー
```

- `session_run_id` は GUI 1 セッション = 1 ID。`hve/config.py` の `generate_run_id()` が採番し、`20260413T143022-a1b2c3` 形式（既定タイムゾーンは `Asia/Tokyo`、`HVE_RUN_ID_TZ` で変更可）になります。GUI 起源であることは環境変数 `HVE_GUI_SESSION_ID` で識別します（正本: `hve/gui/session_workdir.py`）。
- 反復ごとに `<UTC timestamp>__iter<n>/` ディレクトリが新規作成される（同名ディレクトリは削除→新規作成）。
- 最終承認時のみ `latest-accepted/` へコピーされる（毎回上書き）。

### 4 カテゴリと検査境界

| カテゴリ | Step 1 で表示する不足 / 不整合 |
|---|---|
| `FILE` | `REQUIREMENT_TABLE` 由来の必須ファイル要件で、対象パスが存在しないもの |
| `WIZARD_INPUT` | `required_info_keys` または `StepDef.required_params` 由来の非ファイル必須入力で、未入力のもの。`default_params` で補完されるキーは対象外 |
| `SETTING` | GitHub 書き込みを伴う実行における、`repo` の `owner/repo` 形式またはベースブランチ名の Git branch 形式の不整合 |
| `AUTH` | GitHub 書き込みを伴う実行において、起動時の認証解決後も `GH_TOKEN` / `GITHUB_TOKEN` を解決できない状態 |

- GitHub 書き込みを必要としない通常のローカル実行は `SETTING` / `AUTH` の対象外です。
- `additional_prompt` や Work IQ 用プロンプトなどの Prompt 自由記述欄は内容検査の対象外です。空欄・自然言語・業務内容を理由に precheck は失敗しません。ただしプロンプトのサイズは Step 実行時に別途判定されます（下記）。
- Step 1 は UI thread で待ち時間が発生しないよう、remote `origin` と remote branch の照会を行いません。これらは GUI が起動する `hve orchestrate` 子プロセスが同じ共通 preflight を remote 検査ありで実行します。このため remote 不存在・認証・通信の結果は Step 1 の4カテゴリスナップショットには含まれず、子プロセスの実行ログに出力されます。
- `AUTH` は「[起動時の GitHub 認証確認](#起動時の-github-認証確認)」で捕捉・注入されたセッション限りの token を参照する判定であり、同じ認証解決を再実装するものではありません。token 本体はスナップショットへ保存されません。

### 含まれる情報（1 ディレクトリあたり）

| ファイル | 内容 |
|---|---|
| `metadata.json` | session_run_id / iteration / is_final_accepted / autopilot_mode / timestamp / repo_root / workflow_ids / schema_version |
| `selection.json` | 選択中の workflow_ids、Autopilot ON/OFF |
| `orchestrate-args.json` | workflow_id → `OrchestrateArgs` 全フィールド（dict 化、マスク済み） |
| `orchestrate-argv.json` | workflow_id → `python -m hve orchestrate ...` に渡される argv 配列（マスク済み） |
| `precheck-result.json` | Step 1 のローカル precheck 生結果（`FILE` / `WIZARD_INPUT` / `SETTING` / `AUTH` のカテゴリ別不足項目。remote 検査結果は含まない） |
| `plan-review.json` | プランレビュー（実行順序・ギャップ提案など） |
| `attachments.json` | additional_prompts / extra_provided / ARD 添付パス一覧 |
| `auth-snapshot.json` | provider → AuthState 名（トークン本体は含めない） |
| `env-overrides.json` | 子プロセスへ注入される env（HVE_WORK_ROOT / HVE_GUI_SESSION_ID 等、マスク済み） |

### マスキング方針

機密情報の漏洩防止のため、以下のキー名／argv フラグ名を含む値はすべて `***` に置換されます（大文字小文字無視・部分一致）:

- `token` / `secret` / `password` / `passwd`
- `api_key` / `api-key` / `access_key` / `access-key`
- `private_key` / `private-key` / `client_secret` / `client-secret`
- `bearer` / `credential`

例: `GITHUB_TOKEN` / `--github-token` / `workiq_client_secret` などは値が `***` に置換されます。
`auth-snapshot.json` は AuthState 名（`AUTHENTICATED` 等）のみ記録し、トークン本体は一切含めません。

### 動作・運用

- スナップショット保存の失敗は GUI 主処理を止めません（WARNING ログのみ出力）。
- `work/run/<session_run_id>/` は使い捨ての作業成果物です。`.gitignore` による一括除外はされていないため、コミット対象に含めないよう `git status` で確認してください（`.gitignore` が除外するのは `work/**/artifacts/` 配下の `*.env` / `*.log` / `*.key` / `*.pem` 等の秘密になり得るファイルです）。
- セッション終了時の挙動は `GuiSessionWorkdir.cleanup_policy`（既定 `keep`）に従い、`archive`（`work/archive/<session_run_id>.zip` へ zip 化して元ディレクトリを削除）/ `purge`（削除）を指定するとスナップショットも対象になります。`archive` で作成した ZIP は `.gitignore` の秘密ファイル除外規則の対象外で、元ディレクトリ内の `*.env` / `*.key` などが含まれる場合があるため、コミット前に ZIP も必ず確認・除外してください。
- スキーマは `metadata.json.schema_version` でバージョニング（現行 `1`）。

### 用途

- 「Step 1 を通ったのに Step 2 で挙動が違う」等の問い合わせ時、`latest-accepted/orchestrate-argv.json` を CLI で再実行すれば再現可能。
- ギャップ適用ループの各回の差分比較（`iter1` ↔ `iter2`）でユーザー操作の影響を確認可能。
