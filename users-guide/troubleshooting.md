# トラブルシューティング

← [README](../README.md)

> **対象読者**: Web UI 方式または HVE CLI Orchestrator 方式で実行時エラーに遭遇したユーザー  
> **前提**: 失敗した Issue / Workflow / CLI 実行ログを確認できる状態であること  
> **次のステップ**: 解決しない場合は [prompt-examples.md](./prompt-examples.md) のエラー対応プロンプトを使って追加調査してください

---

## 目次

- [初期セットアップで詰まったとき](#初期セットアップで詰まったとき)
  - [1) HVE Cloud Agent Orchestrator 初期セットアップ](#1-hve-cloud-agent-orchestrator-初期セットアップ)
  - [2) Setup Labels / ラベル初期化](#2-setup-labels--ラベル初期化)
  - [3) Copilot 自動アサイン](#3-copilot-自動アサイン)
  - [4) GitHub Actions / Workflow permissions](#4-github-actions--workflow-permissions)
  - [5) Azure OIDC / Static Web Apps deploy](#5-azure-oidc--static-web-apps-deploy)
  - [6) MCP Servers / GitHub Copilot Skills](#6-mcp-servers--github-copilot-skills)
  - [7) Self-hosted runner（オプション）](#7-self-hosted-runnerオプション)
  - [8) HVE CLI Orchestrator Pythonアプリケーション](#8-hve-cli-orchestrator-pythonアプリケーション)
  - [8-1) `ModuleNotFoundError: No module named 'cq'` / `'config'`](#8-1-modulenotfounderror-no-module-named-cq--config)
  - [9) `GH_TOKEN` / `REPO` / `gh auth login`](#9-gh_token--repo--gh-auth-login)
  - [9-1) GUI の「GitHub CLI でログイン」で端末が開かない](#9-1-gui-のgithub-cli-でログインで端末が開かない)
  - [9-2) GUI の Copilot パネルが対話セッションを開始できない](#9-2-gui-の-copilot-パネルが対話セッションを開始できない)
  - [9-3) 実行ジョブへ送った指示が反映されない / 結果を Copilot で開けない](#9-3-実行ジョブへ送った指示が反映されない--結果を-copilot-で開けない)
  - [10) Cloud preflight スクリプト](#10-cloud-preflight-スクリプト)
- [Web UI 方式のトラブル](#web-ui-方式のトラブル)
  - [Bootstrap ワークフローが起動しない](#bootstrap-ワークフローが起動しない)
  - [Sub Issue API が失敗する](#sub-issue-api-が失敗する)
  - [Copilot が assign されない](#copilot-が-assign-されない)
  - [ワークフローがエラーで終了する](#ワークフローがエラーで終了する)
  - [Azure Static Web Apps デプロイエラー](#azure-static-web-apps-デプロイエラー)
  - [Copilot cloud agent のタスク実行エラー](#copilot-cloud-agent-のタスク実行エラー)
- [HVE CLI Orchestrator のトラブル](#hve-cli-orchestrator-のトラブル)
   - [Resume 関連のよくある質問](#resume-関連のよくある質問)
- [HVE GUI Orchestrator のトラブル](#hve-gui-orchestrator-のトラブル)
- [公式出典](#公式出典)

---

## 初期セットアップで詰まったとき

HVE Cloud Agent Orchestrator と HVE CLI Orchestrator は、前提設定と認証情報が異なります。まず利用方式を切り分けてから確認してください。

以降の各項目は、原則として **症状 → 確認 → 原因候補 → 安全な復旧 → 検証 → エスカレーション** の順に読みます。ログを共有する場合は、`GH_TOKEN` / `COPILOT_PAT` / Azure の client / tenant / subscription 情報、Issue 本文に含まれる個人情報や内部 URL を必ずマスクしてください。

### 1) HVE Cloud Agent Orchestrator 初期セットアップ

**症状例**:

- Issue Template から Issue を作成したが workflow が起動しない
- dispatcher workflow が起動しない
- reusable workflow が呼び出されない
- Setup Labels workflow が失敗する
- ラベルが付与されない
- Copilot が Issue にアサインされない
- workflow が queued のまま進まない

**確認観点（上から順に）**:

1. `Setup Labels` workflow を初回に Actions タブから手動実行したか
2. `setup-labels`, `auto-app-selection`, `auto-app-detail-design-web` など必要ラベルが存在するか
3. Issue Template 作成時に想定ラベルが実際に付与されているか
4. 対象 workflow の `permissions:` と Settings → Actions → General → Workflow permissions が、ラベル操作・Issue/PR コメントに必要な最小権限を許可しているか
5. `COPILOT_PAT` が repository secret に設定されているか（未設定時は設計上スキップ警告になる場合あり）
6. Settings → Copilot → Cloud agent で Cloud agent が有効か
7. self-hosted runner を使う場合は runner が online で、workflow 側 label と一致しているか
8. `bash .github/scripts/preflight-cloud-setup.sh OWNER/REPO` の結果を確認したか

---

### 2) Setup Labels / ラベル初期化

初回セットアップでは、Issue Template 起点ではなく **Actions タブから `Setup Labels` を手動実行** してください。

| 段階 | 対応 |
|---|---|
| 症状 | `setup-labels` ラベルがなく Issue Template 起点のラベル付与・workflow 起動が期待どおりに動かない、または `Setup Labels` が 403 で失敗する。 |
| 確認 | `.github/labels.json` と `.github/workflows/setup-labels.yml` が存在し、Actions タブの `Setup Labels` が有効か確認する。 |
| 原因候補 | 初回手動実行前、または workflow の `permissions: issues: write` が有効に使えていない。 |
| 安全な復旧 | [hve-cloud-getting-started.md Step.5](./hve-cloud-getting-started.md#step5-ラベル設定) に従い Actions タブから `Setup Labels` を手動実行する。権限変更が必要な場合も、まず workflow YAML の明示 `permissions` とリポジトリ設定を確認し、不要な `contents: write` やオーナー権限 PAT を追加しない。 |
| 検証 | Labels 画面に `setup-labels` / `auto-app-selection` / `auto-app-detail-design-web` などが作成され、最新 workflow run が成功していることを確認する。 |
| エスカレーション | 403 が続く場合は、値を伏せた Actions ログ、リポジトリの Actions permissions 状態、対象 workflow 名を管理者へ共有する。 |

---

### 3) Copilot 自動アサイン

| 段階 | 対応 |
|---|---|
| 症状 | Sub Issue は作成されたが `copilot-swe-agent` / `Copilot` が assignee に入らない。Actions ログに `WARNING: COPILOT_PAT が設定されていません。Copilot アサインをスキップします。` が出る。 |
| 確認 | repository secret `COPILOT_PAT` の存在、Settings → Copilot → Cloud agent の有効化、Actions ログの GraphQL warning を確認する。 |
| 原因候補 | `COPILOT_PAT` 未設定・失効・権限不足、Copilot cloud agent 未有効化、GraphQL API の一時障害。 |
| 安全な復旧 | `COPILOT_PAT` は Copilot 自動アサイン専用に管理し、ログへ値を出さない。`GH_TOKEN` は HVE CLI Orchestrator の Issue / PR 作成向けであり、Cloud 側の Copilot 自動アサイン用途ではない。手動復旧時は Issue 右サイドバーの Assignees から `copilot-swe-agent` または `Copilot` を選ぶ。 |
| 検証 | Issue の assignees に Copilot が入り、PR または Copilot session が開始されていることを確認する。 |
| エスカレーション | 失敗通知コメントが投稿された場合は、秘密情報をマスクした GraphQL warning と Issue 番号を管理者へ共有する。 |

---

### 4) GitHub Actions / Workflow permissions

| 段階 | 対応 |
|---|---|
| 症状 | `Setup Labels`、dispatcher、reusable workflow がラベル操作・Issue コメント・PR コメントで失敗する。 |
| 確認 | 対象 workflow の `permissions:` に `issues: write` / `pull-requests: write` / 必要時のみ `contents: write` / Azure OIDC 時のみ `id-token: write` が明示されているか確認する。 |
| 原因候補 | `GITHUB_TOKEN` の workflow-level 権限不足、またはリポジトリ側 Workflow permissions の制約。 |
| 安全な復旧 | まず workflow YAML の最小権限を確認する。リポジトリ設定を **Read and write permissions** へ上げるのは、既存 workflow が明示 `permissions` を持たず失敗する場合の暫定回避として扱い、不要な `contents: write` や広範な PAT を追加しない。 |
| 検証 | 再実行した workflow の該当ジョブが成功し、ラベル・Issue コメント・PR コメントのいずれか期待する副作用だけが発生していることを確認する。 |
| エスカレーション | 403 が続く場合は、workflow 名、job 名、失敗した API 操作、`permissions:` 抜粋を秘密情報なしで共有する。 |

---

### 5) Azure OIDC / Static Web Apps deploy

| 段階 | 対応 |
|---|---|
| 症状 | Azure deploy / Static Web Apps deploy が認証エラー、または `::warning::` でスキップされる。 |
| 確認 | workflow が OIDC 方針か、`AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID` が secret または workflow input として渡されているか、`permissions: id-token: write` があるか確認する。 |
| 原因候補 | Federated credential の subject 条件不一致、Azure 側ロール不足、GitHub secret 不足、または Azure deploy を使わない構成で OIDC secret を期待している。 |
| 安全な復旧 | 長期資格情報や `AZURE_STATIC_WEB_APPS_API_TOKEN` / `GITHUB_PAT` を新規追加する前に、OIDC federated credential と最小ロールを確認する。ログ共有時は client / tenant / subscription ID とリソース名を必要に応じてマスクする。 |
| 検証 | `azure/login` 相当の認証ステップと、対象 SWA / Resource Group の read 操作が成功することを確認する。 |
| エスカレーション | Federated credential 条件、GitHub workflow の `permissions`、Azure role assignment の scope を伏せ字付きで Azure 管理者へ共有する。 |

---

### 6) MCP Servers / GitHub Copilot Skills

- HVE Cloud Agent Orchestrator の MCP Servers は GitHub UI の Settings → Copilot → Cloud agent → MCP Servers で設定します
- HVE CLI Orchestrator の MCP は `--mcp-config`（または hve 側設定ファイル）で指定します
- Cloud と Local の MCP 設定は混同しないでください
- GitHub Copilot Skills は Azure 関連タスクを効率化する推奨設定です。必要時に有効化状態を確認してください

#### markdown-query Skill のトラブルシューティング

| 症状 | 確認 | 原因候補 | 安全な復旧 | 検証 | エスカレーション |
|---|---|---|---|---|---|
| `ModuleNotFoundError: No module named 'rank_bm25'` または `tiktoken` | `python -c "import rank_bm25, tiktoken"` | 任意依存の未導入 | フォールバック動作（MiniBM25 / char/4 推定）で継続するか、ネットワーク復帰後に `.venv\Scripts\python.exe -m pip install -e ".[mdq-watch]"`（Windows）/ `.venv/bin/python -m pip install -e ".[mdq-watch]"`（macOS / Linux）を実行する。 | import が成功、または `python -m mdq search --q "<語>"` が fallback で返る。 | extras 導入ログを共有する場合は内部パス・プロキシ情報をマスクする。 |
| `python -m mdq stats` が `{"files": 0, "chunks": 0}` | `python -m mdq stats` と `--root` 指定 | 未索引、または対象 root 外 | 引数なしの `python -m mdq index` を実行する。 | `files` / `chunks` が 1 以上になる。 | 対象 Markdown が存在するのに 0 の場合は `mdq.toml` と実行 cwd を共有する。 |
| 検索結果が 0 件 | `--paths` / `--mode` / クエリ長 | 絞り込み過多、日本語短文の再現率低下 | `--mode grep` で再試行、または `--paths` フィルタを外す。 | 期待ファイルがヒットする。 | 検索語、対象ファイル、`python -m mdq stats` の結果を共有する。 |
| 削除済みファイルのチャンクが残る | `python -m mdq index` の prune 有無 | `--no-prune` 指定、索引の stale | `--no-prune` を外して `python -m mdq index`。解消しない場合は `python -m mdq index --rebuild`。`.mdq/index.sqlite` の削除は最終手段とし、同時実行中でないことを確認する。 | 削除済みパスが検索結果から消える。 | 再索引ログは秘密情報を含まない範囲で共有する。 |

---

### 7) Self-hosted runner（オプション）

Self-hosted runner は **オプション** です。GitHub-hosted runner を使う場合はこの確認はスキップできます。

**症状例**:

- workflow が queued のまま進まない
- self-hosted runner が使われない
- runner label を指定した workflow が実行されない
- runner 上で必要ツールが見つからない
- GitHub / Azure / npm / PyPI へ到達できない

**確認観点**:

1. self-hosted runner が online か
2. workflow / Issue Template 側の runner label と runner 側 label が一致しているか
3. runner が対象リポジトリまたは組織に登録されているか
4. runner に必要ツールがインストール済みか
5. ネットワーク制限下では GitHub / Azure / npm / PyPI への到達性があるか

詳細は [setup-self-hosted-runner.md](./setup-self-hosted-runner.md) を参照してください。

---

### 8) HVE CLI Orchestrator Pythonアプリケーション

**症状例**:

- `python -m hve` が起動しない
- Python バージョンが不足している
- `github-copilot-sdk` が見つからない
- `gh auth status` が失敗する
- Issue / PR 作成で失敗する
- MCP / Work IQ が動かない

**確認観点**:

1. Python 3.11+ を使っているか
2. `.venv` が有効化されているか
3. `github-copilot-sdk` がインストールされているか
4. `gh auth login` 済みで `gh auth status` が成功するか
5. GitHub 書込み startup preflight 対象では `GH_TOKEN` または `GITHUB_TOKEN`、`REPO` / `--repo`、`origin` のベースブランチが設定されているか
6. `GH_TOKEN` と Cloud 側の `COPILOT_PAT` を混同していないか
7. Work IQ を使う場合は Node.js / npx / `@microsoft/workiq` が利用可能か
8. MCP の入出力を見たい場合は `work/run/<run-id>/mcp-<サーバー名>.log` を確認（[MCP 通信ログ](./hve-cli-orchestrator-guide.md#mcp-通信ログ)）

詳細は [hve-cli-orchestrator-guide.md 付録D](./hve-cli-orchestrator-guide.md#付録d-トラブルシューティング) も参照してください。

---

### 8-0) Work IQ の回答案が QA へ 1 件も統合されない

**症状**: 実行ログに次のような警告が出て、`qa/` の回答済み質問票に Work IQ 回答案が入らない。

```text
⚠️ Work IQ [Q2]: Work IQ MCP ツール呼び出しを SDK イベント上で確認できませんでした。
  応答 status: FOUND（一次情報ありと申告されています）
  当該区間で観測されたツール: retrieve
Work IQ: 3 件の応答を得ましたが、0 件の質問にしか回答案を統合できませんでした。
```

**原因と対処**:

| 原因 | 確認方法 | 対処 |
|---|---|---|
| 実際に呼ばれたツールが HVE の実行確認集合に無い | 警告の「当該区間で観測されたツール」を見る | 参照系ツールなのに検出されない場合は不具合。ツール名を添えて報告してください |
| LLM がツールを呼ばずに説明文だけ返した | 観測されたツールが空 | `python -m hve workiq-doctor --sdk-tool-probe --sdk-event-trace` で実呼び出しを確認 |
| SDK のイベント形式が変わり抽出できない | `python -m hve workiq-doctor --event-extractor-self-test` | 自己診断が FAIL なら抽出ロジックの更新が必要 |

> 実際に送ったプロンプトと Work IQ の応答全文は `work/run/<run-id>/mcp-_hve_workiq.log` に残ります。`session_prompt` / `session_response` / `mcp_request` / `mcp_response` の各レコードを見ると、「プロンプトは送られたがツールが呼ばれていない」のか「ツールは呼ばれたが結果が空だった」のかを直接切り分けられます（[MCP 通信ログ](./hve-cli-orchestrator-guide.md#mcp-通信ログ)）。

> `STATUS: NOT_FOUND` の応答は「一次情報が見つからなかった」という正常な結果であり、この警告は出ません。統合 0 件でもすべて `NOT_FOUND` なら異常ではありません。

**修正後の確認**: Workflow を丸ごと再実行せずに、次の診断で統合可否だけを確認できます。

```bash
python -m hve workiq-doctor --skip-mcp-probe --qa-integration-probe --sdk-tool-probe-timeout 300
```

`workiq_qa_merge_decision` が `PASS` なら本番でも統合されます。`FAIL` の場合は同じチェックに観測されたツール名が出るため、上表で切り分けてください。

---

### 8-0-1) Work IQ の可用性判定が初回だけ失敗する

**症状**: npx キャッシュが無い環境で 1 回目の実行だけ Work IQ が無効化され、2 回目以降は有効になる。

**原因**: 初回は `npx -y @microsoft/workiq` が npm レジストリからパッケージを取得するため、可用性判定がタイムアウトすることがあります。

**対処**: 現在の HVE はタイムアウトを「判定不能」として扱い、同一プロセス内で再試行します（不可用として恒久キャッシュしません）。それでも失敗する場合は、事前に次を実行してキャッシュを温めてください。

```bash
npx -y @microsoft/workiq version
```

---

### 8-0-2) QA 起点 AKM が失敗したが原因が分からない

**症状**: 親実行のログに `QA 起点 AKM は N 件失敗しました` と出る。

**確認**: 警告に子実行の `returncode` と子ログのパスが併記されます。

```text
QA 起点 AKM は 3 件失敗しました（source Workflow は継続、境界=DAG 完了後）。
  - returncode=1 対象 3 件 / ログ: work/run/qa-akm-<id>/child-stdio.log
  子が status=blocked で停止した場合は HVE ソースの未コミット変更（FR-CLI-74）が最も多い原因です。
```

**対処**:

1. 表示された `child-stdio.log` を開いて子実行のエラー本文を確認する
2. `status=blocked` で停止していた場合は `git status --porcelain hve mdq hve-dev .github` で未コミット変更を確認し、コミットまたは退避してから再実行する（この検査を無効化するオプションはありません）
**登録時にスキップされる場合**: 登録時点で既に HVE ソースが dirty なら、子を起動せずに即時で次の警告が出ます。

```text
QA 起点 AKM の登録を 1 件スキップしました（source Workflow は継続、境界=DAG 完了後）。
  - qa/<run-id>-1-pre-execution-qa.md
```

コミット後に `--workflow akm --sources qa --target-files <当該ファイル>` で手動取り込みしてください。
---

### 8-1) `ModuleNotFoundError: No module named 'cq'` / `'config'`

**症状**: `hve` コマンドが以下で落ちる。

```text
File ".../hve/config.py", line 11, in <module>
    from cq.watcher import DEFAULT_DEBOUNCE_MS as _CQ_DEFAULT_DEBOUNCE_MS
ModuleNotFoundError: No module named 'cq'
```

**原因**: グローバル Python に `pip install -e .` された **古い hve** が PATH 上で `.venv` を隠している。setuptools の editable install はインストール時点のパッケージ一覧を凍結するため、後から追加された `cq` を解決できない。

**診断**:

```powershell
Get-Command hve -All | Format-List Name,Source
```

`Source` が `<repo>\.venv\Scripts\` 配下でなければ該当。

**対処**: セットアップスクリプトが検出・除去します。

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File hve\setup-hve.ps1 -CheckOnly   # 検出のみ
pwsh -NoProfile -ExecutionPolicy Bypass -File hve\setup-hve.ps1              # 検出 + 除去
```

```bash
./hve/setup-hve.sh --check-only
./hve/setup-hve.sh
```

除去したくない場合は `-NoGlobalCleanup` / `--no-global-cleanup` を付けてください。

**予防**:

- **グローバル Python に対して `pip install -e .` を実行しない**。セットアップスクリプトは必ず `.venv` に導入します。
- 起動はリポジトリ root の `.\hve.cmd`（Windows）/ `./hve.sh`（macOS / Linux）を使う。venv の activate 漏れに依存しません。
- `PYTHONPATH` / `PYTHONHOME` / `PIP_TARGET` 等をシェルに設定しない。設定されているとセットアップが警告します。

---

### 9) `GH_TOKEN` / `REPO` / `gh auth login`

用途の混同を避けるため、次を分けて確認してください。

- `gh auth login` / `gh auth status`: GitHub CLI の認証。startup preflight の token 存在検査とは別であり、`gh auth login` だけでは token 不足を満たしません
- `GH_TOKEN`（未設定時は `GITHUB_TOKEN`）+ `REPO`: HVE CLI Orchestrator の GitHub 書込み startup preflight 対象で必要
- `COPILOT_PAT`: HVE Cloud Agent Orchestrator の Copilot 自動アサイン用途
- `GITHUB_TOKEN`: GitHub Actions が workflow 実行時に自動付与するトークン
- このリポジトリの既存 Copilot 自動アサイン処理は `COPILOT_PAT` 前提です

---

### 9-1) GUI の「GitHub CLI でログイン」で端末が開かない

**症状**: HVE GUI の **設定 → 各サービス連携 → GitHub → 「GitHub CLI でログイン」** を押すと、埋め込み端末が起動せず「埋め込み端末でのログインは利用できません。」という案内文だけが表示される。

**直接原因**: ダイアログは端末を起動する前に 2 つの前提を検査します。どちらか一方でも満たさないと案内文パスへ分岐します。

| 案内文 | 直接原因 |
|---|---|
| `GitHub CLI (gh) が見つかりません。` | `gh` バイナリを PATH 上で解決できない |
| `PTY バックエンド 'pywinpty' が見つかりません。` / `... 'ptyprocess' ...` | 実行中の `.venv` に OS 別 PTY backend が入っていない |

**復旧手順**: どちらの原因でも、OS 別の通常セットアップを再実行してください。通常セットアップは `gh` を OS ツールとして導入し、同一リポジトリの `.venv` へ PTY backend を導入したうえで、完了前に双方の利用可能性を検証します。

```cmd
REM Windows
hve\setup-hve.cmd
```

```bash
# macOS / Linux
./hve/setup-hve.sh
```

- 既存の `.venv` が正常であれば `-Force` / `--force` は不要です。不足分だけが追加・修復されます。
- `-NoGui` / `--no-gui` / `-Minimal` / `--minimal` を付けると、この `gh` / PTY の構築・検証は行われません（明示的な opt-out）。

**成功したかの確認方法**:

- セットアップ出力に `[OK] PTY backend for the embedded GitHub CLI terminal` が出て、終了コードが 0 であること。
- 変更を伴わない現状確認だけをしたい場合は `-CheckOnly` / `--check-only` を付けます。このモードは `gh` / PTY backend の不足を **警告** として報告し、非ゼロ終了はしません。
- 個別に確認する場合:

```cmd
REM Windows
.venv\Scripts\python.exe -c "from hve.gui.pty_backend import is_pty_available; print(is_pty_available())"
gh --version
```

```bash
# macOS / Linux
.venv/bin/python -c "from hve.gui.pty_backend import is_pty_available; print(is_pty_available())"
gh --version
```

**それでも復旧しない場合**:

- Windows 10 1809 未満は ConPTY 非対応のため `pywinpty` を利用できません。端末で `gh auth login` を実行してください。
- セットアップが `gh` の自動導入に失敗する場合は、<https://cli.github.com/> から手動導入したうえで、もう一度通常セットアップを実行して検証を通してください。
- `gh auth status` が未認証を返すこと自体は正常な開始状態です。セットアップの失敗条件ではありません（認証は GUI またはターミナルの `gh auth login` で行います）。

---

### 9-2) GUI の Copilot パネルが対話セッションを開始できない

**症状**: Copilot ドックの **Copilot CLI** タブで [セッション開始] を押しても端末が起動せず、案内文だけが表示される。

**直接原因**: 起動前に 2 つの前提を検査し、どちらか一方でも欠けると起動しません（fail-closed）。

| 案内文 | 直接原因 |
|---|---|
| `GitHub Copilot CLI が見つかりません。` | `copilot` バイナリを解決できない |
| `PTY バックエンド 'pywinpty' が見つかりません。` / `... 'ptyprocess' ...` | 実行中の `.venv` に OS 別 PTY backend が入っていない |

**復旧手順**: [9-1](#9-1-gui-のgithub-cli-でログインで端末が開かない) と同じ OS 別の通常セットアップ（`hve\setup-hve.cmd` / `./hve/setup-hve.sh`）を再実行します。

**個別に確認する場合**:

```cmd
REM Windows
.venv\Scripts\python.exe -c "from hve.gui.copilot_cli_bridge import CopilotCliBridge; print(CopilotCliBridge().find_binary())"
```

```bash
# macOS / Linux
.venv/bin/python -c "from hve.gui.copilot_cli_bridge import CopilotCliBridge; print(CopilotCliBridge().find_binary())"
```

**関連する注意点**:

- セッション内でツール実行の確認を求められるのは仕様です。HVE は権限緩和フラグ（`--allow-all-tools` 等）を付与しません。方針を変えたい場合はセッション内で `/permissions` を実行してください。
- 対話タブの `/resume` は **Copilot CLI のチャットセッション**を選び直す機能です。HVE ワークフローの再開ではありません（[Resume 関連のよくある質問](#resume-関連のよくある質問)）。

---

### 9-3) 実行ジョブへ送った指示が反映されない / 結果を Copilot で開けない

**症状 A: 送信したのに反映されない**

- **宛先違い**: 並列実行中は複数ステップが同時に進行します。**[対象ジョブ]** が意図したステップになっているかを確認し、[更新] で一覧を取り直してください。
- **送信方法の選択**: 「キューに追加」は現在の応答が終わるまで処理されません。即時に反映させたい場合は「いま割り込む」を選んでください。
- **失敗表示**: 送信結果が **失敗** と表示された場合、その指示は送られていません。ステップが送信前に終了した場合などが該当しますので、実行中の別ステップを選び直して送り直してください。

**症状 B: [結果を Copilot で開く] で参照先が見つからない**

- **クリーンアップ設定**: セッション作業フォルダーのクリーンアップが `purge` の場合、GUI 終了後に参照先が残りません。実行後に結果を相談する運用では `keep`（既定）または `archive` を選んでください。
- **初期メッセージに含まれるのはパスだけです**。ファイルの中身は埋め込まれないため、Copilot が読み取る際にツール実行の確認を求めることがあります。

---

### 10) Cloud preflight スクリプト

実行例:

```bash
bash .github/scripts/preflight-cloud-setup.sh OWNER/REPO
bash .github/scripts/preflight-cloud-setup.sh OWNER/REPO --self-hosted-runner-label <runner-label>
```

**よくある失敗と確認ポイント**:

- `OWNER/REPO` 引数がない: 引数を `owner/repo` 形式で再指定
- `gh` が見つからない: GitHub CLI をインストール
- `gh auth status` が失敗: `gh auth login` を実行して再認証
- workflow が見つからない: `Setup Labels` と workflow ファイル配置を確認
- labels が見つからない: 初回なら `Setup Labels` 手動実行前のため `WARN` になり得る
- secrets を確認できない: 権限不足の可能性があるため UI で手動確認（未設定と断定しない）

**WARN / FAIL の解釈**:

- `FAIL`: 必須チェック失敗（終了コード non-zero）
- `WARN`: 権限不足・API 制約・任意項目未実施・初回状態の可能性あり
- API 権限不足による `WARN` と、実際に設定が未完了の状態は混同しないでください
- secret は名前の存在のみ確認し、値は表示されません

---

## Web UI 方式のトラブル

### Bootstrap ワークフローが起動しない

**症状**: Issue にラベルを付与しても GitHub Actions が起動しない。

**確認事項**:

1. 対応するトリガーラベルが正しく付与されているか確認
   - ラベル名のスペルミスがないか確認
   - ラベルがリポジトリに存在するか確認（[ラベル一覧](./workflow-reference.md#ワークフロートリガー系ラベル)を参照）
2. Actions タブでワークフローが有効になっているか確認
   - **Settings → Actions → General → Actions permissions** が適切に設定されているか確認
3. リポジトリの Workflow permissions と workflow YAML の `permissions:` が対象操作を許可しているか確認
   - **Settings → Actions → General → Workflow permissions** と対象 workflow の `permissions:` を確認

---

### Sub Issue API が失敗する

**症状**: Sub Issue が作成されず、エラーログに API エラーが記録されている。

**原因と対応**:

- Sub Issue API の利用可否は GitHub の機能提供状況に依存します（詳細なプラン条件は要確認）
- 現行の `create-subissues-from-pr.yml` は Sub Issues API を最大3回試行し、失敗時は warning として記録します
- 親子リンクだけが失敗した場合でも個別 Issue は作成済みの可能性があるため、親 Issue と作成済み Issue の番号を確認し、必要に応じて GitHub UI から既存 Issue を Sub-Issue として追加してください

---

### Copilot が assign されない

**症状**: Sub Issue が作成されたが、Copilot が自動アサインされない。

**確認事項**:

1. Actions ログを確認してください
2. Copilot が利用可能なプランであることを確認してください
3. `COPILOT_PAT` シークレットが正しく設定されているか確認してください
   - **Settings → Secrets and variables → Actions** で `COPILOT_PAT` が存在するか確認
   - PAT の有効期限が切れていないか確認
4. リポジトリで Copilot Cloud agent が有効化されているか確認してください
   - **Settings → Copilot → Cloud agent** を確認
5. **手動アサインする場合**: Issue 右サイドバーの「Assignees」から `@copilot` を選択

---

### ワークフローがエラーで終了する

**症状**: GitHub Actions のジョブが失敗している。

| 段階 | 対応 |
|---|---|
| 症状 | GitHub Actions のジョブが失敗し、Issue / PR コメントやラベル遷移が止まる。 |
| 確認 | **Actions タブ**で失敗した job / step / API 操作を確認し、`GITHUB_TOKEN` の workflow-level `permissions` を見る。 |
| 原因候補 | `issues: write` / `pull-requests: write` 不足、対象 workflow の無効化、入力ラベル不足、外部 API の一時失敗。 |
| 安全な復旧 | workflow を再実行する前に、ログから秘密情報をマスクして原因 step を特定する。権限追加は必要最小限にし、`contents: write` はファイル作成・PR 更新が実装上必要な workflow に限定する。 |
| 検証 | 再実行で失敗 step が成功し、期待するラベル・コメント・PR 状態だけが更新される。 |
| エスカレーション | 同じ API が再現性を持って失敗する場合は、workflow 名、run URL、失敗 step、HTTP status を共有する。 |

---

### `docs/catalog/app-arch-catalog.md` 関連エラー

AAD-WEB / ASDW-WEB / ADFD / ADFDV ワークフローで以下のエラーが Issue にコメントされた場合の対処:

| エラー文言（先頭） | 原因 | 対処 |
|---|---|---|
| `... が見つかりません。Architecture Design (AAS) を先に実行してください` | catalog ファイル自体が未生成 | AAS ワークフローを先に実行する |
| `... の見出し \`## A) サマリ表（全APP横断）\` セクションが見つかりません` | catalog の見出しが出力契約と大きく異なる（`サマリ表` / `選定結果一覧` を含まない） | `.github/skills/architecture-questionnaire/assets/output-format.md` §7.2 に沿って見出しを `## A) サマリ表（全APP横断）` に修正、または AAS Step.1 を再実行（`選定結果一覧（サマリ表）` などの軽微な揺れは受理されるが WARN が出ます） |
| `... のサマリ表に必要な列 ...` | テーブル列名（APP-ID / 推薦アーキテクチャ）の不在/誤表記 | サマリ表の列ヘッダを出力契約に揃える |
| `... が予期せず失敗しました（exit 1, 詳細不明）` | Python 自体の起動失敗等 | ワークフローログで `python3 -m hve.app_arch_filter` のスタックトレースを確認 |

---

### preflight-cloud-setup.sh で FAIL / WARN が出る

**症状**: `bash .github/scripts/preflight-cloud-setup.sh OWNER/REPO` の結果で `FAIL` または `WARN` が表示される。

**確認事項（チェック順）**:

1. `gh` がインストール済みで `gh auth status` が成功するか
2. `OWNER/REPO` が正しいか、`gh repo view OWNER/REPO` が成功するか
3. `Setup Labels` workflow が存在するか（なければテンプレートコピー漏れを確認）
4. ラベル不足の `WARN` は初回状態なら正常な場合があるため、[hve-cloud-getting-started.md Step.5](./hve-cloud-getting-started.md#step5-ラベル設定) に従って Setup Labels を手動実行する
5. secret / runner の確認で取得失敗した場合は、権限不足の可能性があるため GitHub UI で手動確認する（未設定と断定しない）

---

### ADOC / AKM が起動しない

**症状**: `auto-app-documentation` または `knowledge-management` ラベル付き Issue を作成しても実行されない。

**確認事項**:

1. Issue に `auto-app-documentation` または `knowledge-management` ラベルが付いているか
2. **Actions** タブで `auto-orchestrator-dispatcher.yml` と `auto-app-documentation-reusable.yml` / `auto-knowledge-management-reusable.yml` が有効か
3. ラベル未作成の場合は [hve-cloud-getting-started.md Step.5](./hve-cloud-getting-started.md#step5-ラベル設定) を参照し、`Setup Labels` を再実行する

**原因候補**:

- 旧 workflow 名を前提にしている（現行実装では `auto-orchestrator-dispatcher.yml` が reusable workflow を呼び出す）
- ラベル未作成、または Issue に対象ラベルが付いていない

**安全な復旧**:

- Issue に対象ラベルを付け直す、または Actions タブから関連 workflow を再実行する
- workflow ファイルや prompt を直接編集して回避しない

**検証**:

- dispatcher の run が作成され、対応 reusable workflow の job が開始されることを確認する

**エスカレーション**:

- ラベル、Issue 番号、dispatcher run URL、reusable workflow 名を共有する

---

### PR 完全自動化が動かない（Auto Approve / Auto-merge）

**症状**: チェックボックスを有効化したのに自動 Approve / Auto-merge されない。

**確認事項**:

1. PR に `auto-approve-ready` ラベルが付与されているか
2. PR が `split-mode` になっていないか（`split-mode` 付きは自動化対象外）
3. `auto-review-to-approve-transition.yml` / `auto-approve-and-merge.yml` の実行ログに失敗がないか

---

### 選択したモデルで 400 エラーになる

**症状**: Issue Template でモデル指定後、Copilot アサイン時に 400 系エラーになる。

**対処**:
- Issue Template のモデルを `Auto` に戻す
- SDK 実行時にモデルを一時固定する場合は、`copilot` コマンドの `/model` または HVE のモデル選択 UI で利用可能な ID を確認してから指定する
- workflow 実行ログを確認し、必要に応じて `Auto`（既定）に戻して再実行する
- `Auto` は GitHub が最適モデルを動的選択し、プラン・管理者ポリシー・モデル可用性の影響を受けます
- 公式: https://docs.github.com/en/copilot/concepts/auto-model-selection

> **モデル ID の確認**: HVE 実装では `Auto` と `claude-opus-4.7` などのモデル ID が扱われます。正確な利用可能 ID は環境・契約・管理者ポリシーで変わるため、固定値を断定せず、`copilot` コマンドの `/model` または HVE のモデル選択 UI で確認してください。旧モデル指定は HVE 側で `Auto` にフォールバックする場合があります（warning ログを確認）。

---

### Azure Static Web Apps デプロイエラー

**症状**: SWA デプロイ workflow が失敗する、または `::warning::` でスキップされる。

**確認事項（チェック順）**:

SWA デプロイは OIDC 認証方式を使用しています。`AZURE_STATIC_WEB_APPS_API_TOKEN` の設定は不要です。以下の Secrets が正しく設定されていることを確認してください。

APP-009 の workflow は `workflow_dispatch` 専用です。Actions タブまたは `gh workflow run` から、対象subscription内に実在する `resource_group` と `static_web_app_name` を毎回明示してください。workflow は OIDC 認証後、deployment token を取得する前に同じ値で `az staticwebapp show` を実行します。

1. **OIDC 認証 Secrets が設定されているか確認**
   ```bash
   gh secret list --repo <owner>/<repo>
   ```
   以下の 3 つが存在することを確認:
   - `AZURE_CLIENT_ID`
   - `AZURE_TENANT_ID`
   - `AZURE_SUBSCRIPTION_ID`
   
   未設定の場合は [hve-cloud-getting-started.md Step.4（認証設定）](./hve-cloud-getting-started.md#step4-認証設定copilot_pat) を参照してください。

2. **Azure リソースが存在するか確認**
   ```bash
   az staticwebapp show --name <SWA_NAME> --resource-group <RESOURCE_GROUP>
   ```
   - リソースが存在しない場合は、該当 Azure deploy Step が生成した `src/infra/azure/create-azure-webui-resources.sh` の有無を確認し、生成元 Step の手順に戻ってください（このファイルは実装時に生成される成果物であり、常にリポジトリに存在するとは限りません）

3. **`AZURE_CLIENT_ID` のサービスプリンシパルに SWA 権限があるか確認**
   - サービスプリンシパルに対象 SWA / Resource Group を操作できる最小ロールが付与されているか確認してください。広すぎる subscription-wide 権限を追加する前に scope を確認してください。

**原因候補**:

- OIDC federated credential の subject / audience 条件不一致
- `permissions: id-token: write` 不足
- SWA リソース未作成、または `RESOURCE_GROUP` / `SWA_NAME` の取り違え
- `workflow_dispatch` の `resource_group` / `static_web_app_name` 未指定

**安全な復旧**:

- `AZURE_STATIC_WEB_APPS_API_TOKEN` や長期 PAT を追加する前に OIDC 設定を修正する
- `az` コマンド出力を共有する場合は subscription ID、tenant ID、リソース名、内部 URL を必要に応じてマスクする

**検証**:

- `az staticwebapp show --name <SWA_NAME> --resource-group <RESOURCE_GROUP>` が成功し、deploy workflow の認証 step と deploy step が成功する

**エスカレーション**:

- Federated credential 条件、workflow run URL、`az staticwebapp show` のマスク済みエラーを Azure 管理者へ共有する

> [!NOTE]
> 初期セットアップの正本方針は OIDC です（`AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID`）。  
> 一部の Issue Template / workflow 本文に旧トークン記述が残る場合がありますが、認証設定は [hve-cloud-getting-started.md の認証・認可の用途一覧](./hve-cloud-getting-started.md#認証認可の用途一覧cloud--local--azure) を優先してください。

---

### Copilot cloud agent のタスク実行エラー

**症状**: Pull Request の Session の中で `Run Bash command` が繰り返され、何も処理が行われていない。

> [!IMPORTANT]
> この状況では、まず PR コメントで Copilot に停止条件・調査対象・安全な次アクションを明示してください。GitHub UI から Copilot session を手動 Stop すると PR タイムラインにキャンセルイベントが残るため、運用上の最終手段として扱います。

| 段階 | 対応 |
|---|---|
| 症状 | `Run Bash command` が反復し、変更・検証・完了報告が進まない。 |
| 確認 | PR session の最新ログ、同じコマンドの反復回数、対象ブランチの差分有無を確認する。ログ共有時は秘密情報をマスクする。 |
| 原因候補 | prompt の停止条件不足、コマンド失敗時の同一リトライ、外部依存の一時障害、作業範囲の過大化。 |
| 安全な復旧 | [prompt-examples.md — Copilot cloud agent エラー対応](./prompt-examples.md#copilot-cloud-agent-エラー対応) のプロンプトを PR コメントで送り、反復停止・現状要約・次アクション提示を依頼する。費用・暴走懸念が高い場合は運用者へエスカレーションし、PR close / Issue close による自動終了を検討する。 |
| 検証 | Copilot が反復を止め、差分・失敗原因・残作業をコメントまたは commit に反映する。 |
| エスカレーション | PR URL、反復している command 名、マスク済みログ、直近の Copilot 応答を共有する。 |

**対応策**: 以下のプロンプトを PR コメントで Copilot に送信してください。

> 詳細なプロンプトは [prompt-examples.md — Copilot cloud agent エラー対応](./prompt-examples.md#copilot-cloud-agent-エラー対応) を参照してください。

その他の便利なプロンプトは [prompt-examples.md](./prompt-examples.md) を参照してください。

---

## HVE CLI Orchestrator のトラブル

HVE CLI Orchestrator（ローカル実行方式）のトラブルシューティングは [hve-cli-orchestrator-guide.md 付録D](./hve-cli-orchestrator-guide.md#付録d-トラブルシューティング) を参照してください。

### GitHub 書込み startup preflight に失敗する

`--create-issues` / `--create-pr`、ADFDV の auto-merge、または active `requires_remote_cicd` Step で auto-merge を使う場合は、GitHub 書込み startup preflight が動きます。対象外の通常 run は GitHub token・`origin`・remote branch を検査しません。

次をこの順で確認してください。

1. `REPO` または `--repo` が非空の `owner/repo` 形式か確認
2. `GH_TOKEN` または `GITHUB_TOKEN` が存在するか、値を表示せずに確認
3. `--branch` が有効な Git branch 名で、`git remote get-url origin` が成功するか確認
4. `git ls-remote --exit-code --heads origin refs/heads/<branch>` で完全一致する remote branch を確認
5. token は Cloud の `COPILOT_PAT` と別用途であることを確認

**症状 1: repo / token 不足で startup preflight が停止する**

```text
起動前の設定整合性チェックに失敗しました:
   - repo: GitHub リポジトリが owner/repo 形式ではありません。
      対処: --repo または REPO に owner/repo 形式の値を設定してください。
   - token: GitHub token を解決できません。
      対処: GH_TOKEN または GITHUB_TOKEN を設定してください。
```

**安全な復旧**: `REPO` または `--repo` を `owner/repo` 形式へ直し、資格情報ストア等から `GH_TOKEN` または `GITHUB_TOKEN` を環境へ注入して再実行します。`gh auth login` だけでは token 不足を満たしません。token の具体値はコマンド引数、ログ、Issue、PR、文書へ貼らないでください。

**症状 2: `couldn't find remote ref` の後に `not a commit` が出る**

> 以下は startup preflight 導入前、または preflight を経由しない旧実装で観測された参考症例です。現行のローカル起動面では同じ不整合を branch 作成前に停止します。

```text
fatal: couldn't find remote ref <branch>
fatal: '<branch>' is not a commit and a branch '<working-branch>' cannot be created from it
```

**原因**: 設定したベースブランチと完全一致する `refs/heads/<branch>` が `origin` にありません。現行 preflight はこの状態を branch 作成前に検出し、`remote branch 'origin/<branch>' は存在しません。` と表示して、ローカル branch や `main` への fallback を行わず停止します。

**安全な復旧**:

1. `git remote get-url origin` で意図した remote か確認します。
2. 上記 `git ls-remote` が status `2` なら ref 不在です。`--branch` / GUI のベースブランチを `origin` に実在する名前へ直すか、必要な branch をリポジトリの保護ルールとレビュー手順に従って remote に作成します。
3. status `2` 以外の非 0 なら、branch 不在とは断定せず、Git の認証・ネットワーク・`origin` 到達性を復旧して再検査します。
4. `git checkout -b main`、同名ローカル branch、強制 push で検査を迂回しないでください。

startup preflight の対象条件、5 検査、実行順序、`--dry-run` の扱いは [CLI ガイド](./hve-cli-orchestrator-guide.md#github-書込み-startup-preflightfr-cli-3182) を参照してください。

主なトラブルと対応:

| 症状 | 参照箇所 |
|------|---------|
| `copilot: command not found` | [付録D: Copilot CLI が見つからない](./hve-cli-orchestrator-guide.md#copilot-cli-が見つからない) |
| `ModuleNotFoundError: No module named 'copilot'` | [付録D: github-copilot-sdk がインストールされていない](./hve-cli-orchestrator-guide.md#github-copilot-sdk-がインストールされていない--python--m-hve-が動かない) |
| セッションタイムアウト | [付録D: セッションタイムアウト](./hve-cli-orchestrator-guide.md#セッションタイムアウト) |
| MCP Server が接続できない | [付録D: MCP Server が接続できない](./hve-cli-orchestrator-guide.md#mcp-server-が接続できない) |
| 並列実行でメモリ不足 | [付録D: 並列実行でメモリ不足](./hve-cli-orchestrator-guide.md#並列実行でメモリ不足) |
| PR 作成時に HTTP 422 エラー | [付録D: PR 作成時に HTTP 422 エラー](./hve-cli-orchestrator-guide.md#pr-作成時に-http-422-エラー) |

**安全な復旧**:

- `GH_TOKEN` / `GITHUB_TOKEN` をログや Issue 本文へ貼らず、必要な場合も値をマスクして認証状態だけを共有してください。
- `REPO` は `owner/repo` 形式で再指定し、Cloud 側の `COPILOT_PAT` と入れ替えないでください。
- PR 作成失敗時に履歴書き換えや強制 push で復旧しないでください。未作成なら入力・認証・既存 PR の有無を確認して再実行します。

**検証**:

- GitHub 書込み対象の `--dry-run` が startup preflight を通過し、その後に実行計画を表示すること。
- GitHub 書込みを要求しない通常 run は、token や remote branch がなくても本 preflight で停止しないこと。
- 実行後に `work/run/<run-id>/.../completion-report.md` が生成され、失敗 Step がある場合は `auto-approve-ready` が付かないこと。

**エスカレーション**:

- `git ls-remote` の終了 status、token 値を除いた stderr、`REPO` 形式、対象 workflow / active step を共有してください。

### Resume 関連のよくある質問

現在は、SQLite の耐久制御状態を使う **durable execution resume** と、JSON Lines の成功記録だけを使う **legacy run-id resume** の 2 系統があります。v1.1 で廃止された旧 `session-state/`、`Ctrl+R`、旧 Session State の復元機構が復活したわけではありません。

| 再開方式 | 識別子 | 保存状態 | SDK セッション |
|---|---|---|---|
| `python -m hve resume` | execution ID | SQLite の execution、workflow、step、lease、state version | 明示した `reuse-session` で保存済み Main session だけを再利用可能。`restart-step` は新しい session を作る。 |
| `python -m hve orchestrate --workflow <workflow-id> --resume-run <run-id>` | run-id | `hve/.run-progress.jsonl` の成功 Step | 常に新しい session。durable execution へ変換しない。 |
| Copilot CLI 対話タブの `/resume` | Copilot CLI の session | Copilot CLI 側の会話状態 | HVE workflow の再開ではない。 |

#### Durable execution resume の基本手順

`hve resume` は、現在のリポジトリに対応する未完了の **standard local execution** だけを候補にします。元の実行と同じ checkout / worktree のルートで実行してください。Cloud、fleet、dry-run、legacy `--resume-run` は durable resume の対象ではありません。

```bash
python -m hve resume
python -m hve resume <execution-id>
python -m hve resume --latest
```

- execution ID を省略すると、対話端末では候補を選択します。`--latest` は「最後に更新された候補」を明示的に選びます。
- plan には execution、workflow、instance、state version、action、risk、missing replay key、resume SHA-256 が表示されます。内容を確認してから承認してください。
- risk がない場合の既定 action は `restart-step` です。risk がある非対話実行では `--action` の明示が必要です。
- `reuse-session` は保存済み Main session ID を再利用します。`restart-step` は保存済み session ID を使わず、対象 Step を新しい session で再実行します。
- action、再入力値、HEAD、state version、risk のいずれかが変わった場合は別 plan です。plan を作り直し、新しい SHA-256 を確認して再承認してください。

> [!IMPORTANT]
> HVE は `reuse-session` の失敗を `restart-step` へ自動的に切り替えません。DB、schema、lease、CAS、SDK session の異常も自動削除・自動修復しません。資格情報、token、接続文字列、内部 URL、自由記述の prompt、tool payload は state DB、ログ、Issue、PR へ保存・貼付しないでください。必要な資格情報は既存の資格情報ストアまたは環境注入経路から渡します。

#### 候補選択で停止する

| 症状 | 意味 | 安全な復旧 |
|---|---|---|
| `再開候補がありません。` | 現在のリポジトリキーに未完了の durable execution がない。完了済み、別 worktree、未登録の実行、または対象外モードの可能性がある。 | 実行したリポジトリまたは worktree のルートへ移動し、元ログの execution ID を確認する。legacy run-id しかない場合は `--resume-run` を使う。候補を作る目的で state DB を削除しない。 |
| 非対話実行で `候補が複数あります。execution IDまたは--latestを指定してください。` | HVE は候補を推測できないため、子 process を起動せず停止した。 | 対象 execution ID を指定する。最新更新を意図すると確認できた場合だけ `--latest` を使う。 |
| `durable execution was not found` | 指定した execution ID が state DB にない。run-id を誤って渡した可能性もある。 | 元ログから execution ID を再確認する。`--resume-run` の run-id と相互に置換しない。 |
| `durable execution belongs to another repository` | execution は存在するが、現在のリポジトリキーと一致しない。 | 元のリポジトリまたは worktree で plan を作り直す。別リポジトリの state をコピー・編集して紐付けない。 |

#### plan の risk / error 語彙

risk は実装の snake_case 名で表示されます。複数ある場合も、各行の意味をすべて確認してから action を決めます。

| 症状 | 意味 | 安全な復旧 |
|---|---|---|
| `unsupported_mode` または `durable resume mode is unsupported` | 保存された workflow instance が durable resume 対象の `standard` ではない。 | action で上書きできない。元の surface と mode の通常手順から新規実行し、state DB の mode を編集しない。 |
| `active_owner` または `durable workflow instance has an active owner` | 有効期限内の fenced lease を別 process が保持している。明示 action があっても takeover できない。 | 元 process が実行中か確認し、正常終了または停止処理を待つ。lease が失効した後に新しい plan を作る。強制的な DB 更新や二重起動を行わない。 |
| `failed` | 前回 attempt が terminal failure として記録されている。 | 先に元の失敗原因を解消する。保存済み Main session を継続できる根拠がある場合だけ `reuse-session`、それ以外は副作用を確認して `restart-step` を明示し、plan を再承認する。 |
| `non_terminal` | instance が `running`、`suspended`、`blocked` のいずれか、または owner 情報を残したまま lease が失効している。 | 元 process が終了済みであることを確認する。`active_owner` が消えた後、`reuse-session` または `restart-step` を明示して新しい plan を承認する。 |
| `head_drift` | 起動時に checkpoint した Git HEAD と現在の HEAD が異なる。保存済み prompt や成果物の前提が変わり得る。 | Git 差分と履歴を確認する。同じ前提が必要なら元 commit を安全な作業環境で復元する。現在の HEAD で続けるなら `restart-step` を選び、再実行範囲と副作用を確認して再承認する。 |
| `missing_output` | succeeded と記録された Step の必須成果物がない。依存先も再実行対象へ戻される。GUI の `purge` 後にも発生し得る。 | 信頼できる backup があれば成果物を戻して plan を作り直す。戻せない場合は workflow の対象 Step と依存先を確認し、`restart-step` を明示する。DB の succeeded 状態を手編集しない。 |
| `missing_replay_value` または `再入力が必要です: <key>` | 自由記述、任意 path、endpoint 等の値は state DB に保存せず、key 名だけを保持している。 | 対話端末で要求された値を再入力し、更新された plan を確認する。credential や token 自体を replay 値、コマンドライン、ログ、Issue、PR に入れない。非対話では保護された controller 入力経路がない限り停止する。 |
| `sdk_missing` または `stored SDK session cannot be reused` | `reuse-session` に必要な Main phase の保存済み session ID がない、対象 Step が一意でない、または保存 phase が Main ではない。 | session ID を推測・手入力しない。`restart-step` へ action を変更して plan を作り直し、新しい SHA-256 を承認する。 |
| `durable SDK session is active or already in use` | `reuse-session` の開始時に、保存済み SDK session が別 process で active、または SDK が already-in-use と報告した。これは事前 plan の risk 名ではなく、SDK の resume event を確認した実行時エラーである。 | `reuse-session` は停止する。元 session の完了・切断を確認する。`restart-step` に切り替える場合も自動縮退させず、action を変更した新しい plan を承認する。 |

`reuse-session` の RPC 失敗、deadline 超過、または `session.resume` event 未受信も fail-closed です。HVE は新しい session を黙って作りません。原因を確認した後、同じ action で plan を作り直すか、`restart-step` に変更した別 plan を承認してください。

#### 承認、CAS、heartbeat で停止する

| 症状 | 意味 | 安全な復旧 |
|---|---|---|
| `resume planがstaleです。` | controller が提示した resume SHA-256 と、実行直前に再計算した plan が一致しない。 | 古い hash を再利用しない。最新状態から plan を再生成し、risk、action、再入力 key、state version を再確認して承認し直す。 |
| `次のworkflowは新しいresume planです。表示したhashの再承認後に再開してください。` | GUI / Prompt controller が渡したhashで最初の承認済みinstanceは完了したが、次のinstanceには別のplanとhashが必要。正常なfail-closed停止であり、先行hashは後続へ流用されない。 | 表示された次のplanを利用者へ再提示し、別の明示承認を得てからcontrollerが新しいhashで`hve resume`へ再委譲する。手作業でhashを転記させたり、古いhashで再試行したりしない。 |
| `resume planが承認後に変化しました。再提示が必要です。` | 承認と lease 取得の間に HEAD、state、出力、または replay 条件が変化した。 | 子 process は起動されない。変化の原因を確認し、新しい plan を再提示・再承認する。自動 retry しない。 |
| `reconciled outputs changed before workflow completion` | 実行対象0件として承認された後、fenced完了前の再確認で必須outputまたはStep状態が変化した。 | instanceを成功扱いにせず停止する。outputとstateを確認し、最新planを作り直して再承認する。DBを手編集しない。 |
| `resume plan state is stale`、`durable state version is stale`、`durable lease compare-and-swap failed` | 別 process または直前の transition が state version / lease generation を更新し、承認済み snapshot が古くなった。 | 実行中 owner の有無を確認し、最新 state から plan を作り直す。同じ expected state version を強制的に再利用しない。 |
| `durable heartbeat failed`、`durable heartbeat was fenced`、`durable heartbeat worker failed` | lease の鮮度または所有権を安全に証明できなくなった。HVE は executor を停止し、可能なら instance を `suspended` にして失敗を表面化する。 | 元 process の停止を確認する。`active_owner` の間は再開せず、lease 失効後に新しい plan と明示 action で復旧する。DB や lease を手編集しない。 |
| `durable heartbeat worker could not be stopped` または `heartbeat worker did not stop within the timeout` | 終了処理の上限内に heartbeat thread の停止を確認できず、quiescence が不明なためエラーになった。DB corruption を意味するとは限らない。 | 元 HVE process が完全に終了したことを確認する。残存 process があれば管理者の通常手順で停止し、lease が active でなくなってから plan を作り直す。繰り返し resume を起動しない。 |

#### state DB の integrity / schema エラー

state DB は `platformdirs` が解決するユーザー state directory の `hve/state.sqlite3` です。以下のエラーでは候補選択や lease 取得より前に停止し、HVE は DB を削除・初期化・修復しません。

| 症状 | 意味 | 安全な復旧 |
|---|---|---|
| `durable state database could not be opened`、`database disk image is malformed` 等 | SQLite file、権限、filesystem、または DB bytes に異常がある。 | 全 HVE process を停止し、元 DB と存在する SQLite sidecar を byte-for-byte で保全する。権限・disk・backup を確認し、管理者へエスカレーションする。元 DB を削除したり書込み修復を試したりしない。 |
| `unsupported durable state schema version`、`unversioned durable state schema is not empty`、`unexpected schema`、`unexpected objects` | HVE が対応しない version、未 version 化の非空 DB、または期待外の table / column / foreign key がある。 | 実行に使用した HVE version を確認し、互換版または信頼できる backup からの復元を管理者判断で行う。`user_version`、table、column を手編集しない。 |
| `durable state database failed quick_check` または `durable state quick_check could not run` | SQLite の `PRAGMA quick_check` が正確に `ok` を返さず、候補を安全に信用できない。 | resume を中止して DB を保全する。storage 障害と backup を確認し、管理者へエスカレーションする。検査を迂回して候補を起動しない。 |

エスカレーション時は HVE version、OS、error type、execution ID、workflow ID、risk 名、state version、発生時刻だけを共有します。state DB 本体、raw replay 値、credential、token、接続文字列、内部 URL、prompt/tool payload は通常のログや Issue / PR に添付しないでください。

#### GUI の `purge` 後に候補だけが残る

| 症状 | 意味 | 安全な復旧 |
|---|---|---|
| GUI 終了後も execution 候補は表示されるが、結果ファイルが見つからない、または `missing_output` になる。 | cleanup policy の `purge` は GUI session の run-scoped 作業ディレクトリを削除するが、ユーザー state directory の durable DB は削除しない。 | archive policy で作成済みの信頼できる ZIP があれば復元して plan を作り直す。`purge` 済みで backup がなければ、再実行範囲を確認して `restart-step` を明示する。今後 resume が必要な実行では事前に `keep` または `archive` を選ぶ。 |

#### Legacy `--resume-run` の run-id が見つからない

legacy resume は、成功済み Step を `hve/.run-progress.jsonl` から除外し、未完了 Step を新しい SDK session で実行する仕組みです。durable execution ID、lease、CAS、`reuse-session` は使いません。

```bash
python -m hve orchestrate --workflow aas --resume-run <run-id>
```

| 症状 | 意味 | 安全な復旧 |
|---|---|---|
| `--resume-run に指定された run-id の進捗記録が見つかりません: <run-id>` | 指定 run-id と workflow に一致する進捗記録が 1 件もない。HVE は全 Step 実行へ縮退せず停止する。 | run-id と workflow ID を元ログで確認して再指定する。記録がない場合は resume ではなく通常の新規実行として範囲を明示する。execution ID を run-id として渡さず、JSON Lines を捏造・手編集しない。 |

成功済み Step はスキップされますが、fan-out する Step は取りこぼし防止のため再実行されます。`--steps` を併用する場合は、再実行対象と副作用を確認してください。

### 起動時の索引差分更新で警告が出る / 実行開始が遅い

| 段階 | 対応 |
|---|---|
| 症状 | 起動直後に `index refresh: mdq <lang>/<strategy> の差分更新に失敗しました` または `index refresh: cq <profile> ...` が stderr へ出る。あるいは `hve orchestrate` で watcher の起動が数十秒遅れる。 |
| 確認 | 他の HVE プロセス（GUI と子プロセス、複数の `hve orchestrate` 等）が同時に走っていないか。`.mdq/` / `.cq/` を別ツールが開いていないか。 |
| 原因候補 | 同一の索引 DB への並行書き込み（SQLite のファイルロック）。watcher は差分更新の完了後に起動する仕様のため、初回起動や大量のファイル変更後は待ち時間が伸びる。 |
| 安全な復旧 | 失敗は当該対象のスキップだけで、Workflow の実行は継続される（索引は次回起動または `python -m mdq index` / `python -m cq index` で追いつく）。常に切りたい場合は `HVE_STARTUP_INDEX_REFRESH=0` を設定する。 |
| 検証 | 再実行して警告が出ないこと。`python -m mdq stats` / `python -m cq stats --profile <名前>` で files / chunks が期待値になっていること。 |
| エスカレーション | 警告行全文、同時に走らせていた HVE プロセス数、OS、`.mdq/` / `.cq/` のファイル一覧を共有する。 |

> 仕様の詳細は [hve-cli-orchestrator-guide.md §F.8.1](./hve-cli-orchestrator-guide.md#f81-起動時の索引差分更新hve-cli--gui) を参照してください。

### プロンプトが大きすぎて Step が停止する

| 段階 | 対応 |
|---|---|
| 症状 | Step 開始前、Phase 0 前、またはメインタスク送信直前に、受領済み／確定済み／最終のいずれかのプロンプトが HVE 内部予算を超えた旨が出て Step が失敗する。プロンプトのバイト数・予算バイト数・成分別バイト数が併記される。 |
| 確認 | 表示された成分別バイト数のうち、どれが支配的かを見る。`step_prompt` が大きい場合は Step テンプレートの展開結果、`pre_qa_context` が大きい場合は事前 QA の注入、`agent_prefix` が大きい場合は Agent Prompt 本文が原因。固定見出し・区切り・各 suffix も個別成分として計上され、合計は最終 Prompt と一致する。 |
| 原因候補 | `--additional-prompt` に長文を直接貼り付けた。ARD の `target_business` に巨大なフォルダを指定した。事前 QA の回答が長大になった。 |
| 安全な復旧 | 長文は直接貼らずファイルへ保存し、プロンプトにはそのパスだけを書く。`target_business` は対象を絞ったフォルダ／ファイルに変更する。`--steps` で実行範囲を分割する。 |
| 検証 | 再実行して同じメッセージが出ないこと。 |
| エスカレーション | 表示されたバイト数・予算・成分別内訳（本文は不要）と、使用した Workflow / Step ID を共有する。 |

> HVE はこの判定でプロンプトを自動的に切り詰めたり要約したりしません。要求が欠落したまま実行が続くと、成果物の欠落を検出できなくなるためです。自動再送・複数ターンへの自動分割も行いません。
>
> 予算超過時に 0 回となるのは Phase 1 の主モデル呼び出しです。事前 QA コンテキストを加えた最終段階で初めて超過した場合、事前 QA は既に実行されています。dry-run はモデルを呼ばないため、この予算では失敗しません。
>
> 予算値は HVE 内部の安全余白であり、GitHub Copilot API の公開仕様値ではありません。CLI オプション・GUI 設定・環境変数では変更できません。
>
> 診断にはバイト数などのメタデータだけが表示され、プロンプト本文、追加プロンプト本文、事前 QA 応答本文、認証情報は表示されません。問い合わせ時も本文を共有する必要はありません。
>
> **Work IQ との切り分け**: この停止判定は Phase 1 のメインタスクが対象であり、Work IQ の `ask` クエリを分割・再送する機能ではありません。Work IQ は QA フェーズでのみ使用されます（[QA フェーズにおける Work IQ の扱い](./hve-cli-orchestrator-guide.md#qa-フェーズにおける-work-iq-の扱い) 参照）。

---

## HVE GUI Orchestrator のトラブル

### GUI が起動せず CLI にフォールバックする

| 段階 | 対応 |
|---|---|
| 症状 | 引数なしの `python -m hve` で GUI が開かず、`PySide6 未導入のため CLI モードにフォールバックします。` が表示される、または `ModuleNotFoundError: No module named 'PySide6'` が出る。 |
| 確認 | 通常セットアップを `-NoGui` / `--no-gui` / `-Minimal` / `--minimal` 付きで実行していないか確認する。 |
| 原因候補 | GUI extras（`PySide6`, `PySide6.QtWebEngineWidgets` など）が `.venv` に未導入。 |
| 安全な復旧 | Windows は `hve\setup-hve.cmd`、macOS / Linux は `./hve/setup-hve.sh` を通常モードで再実行する。CLI 専用運用ならフォールバックは異常ではありません。 |
| 検証 | `.venv` の Python で `import PySide6` と `import PySide6.QtWebEngineWidgets` が成功し、GUI が起動する。 |
| エスカレーション | OS、Python バージョン、セットアップに付けたオプション、マスク済み stderr を共有する。 |

### GUI 実行が異常終了する / 自動停止しない

| 段階 | 対応 |
|---|---|
| 症状 | GUI の Step 実行が fatal 後も止まらない、または想定より早く止まる。 |
| 確認 | `HVE_GUI_STOP_ON_FATAL` を設定しているか確認する。実装上、`0` / `1` 以外は無視されます。 |
| 原因候補 | 環境変数の値誤り、GUI 設定と CLI 引数の混在。 |
| 安全な復旧 | `HVE_GUI_STOP_ON_FATAL=1` で fatal 時停止、`0` で継続に切り替える。実行中のログを共有する場合は token / 内部 URL / 顧客情報をマスクする。 |
| 検証 | 次回実行で fatal 時の停止挙動が期待どおりになる。 |
| エスカレーション | GUI の該当ログ、設定値、実行した workflow / step を共有する。 |

### 起動直後に実行ボタンが押せない

| 段階 | 対応 |
|---|---|
| 症状 | GUI 起動直後、ワークフローを選んでも実行開始ボタンが無効のままで、ステータス欄に「索引 (markdown-query / code-query) の差分更新中です。完了後に実行を開始できます。」と出る。 |
| 確認 | 仕様どおりの挙動。差分更新が終わるとボタンは自動で有効へ戻る。 |
| 原因候補 | 子プロセスの索引 watcher と同一の索引 DB へ同時に書き込むのを避けるため、更新中は実行開始を受け付けない（FR-GUI-22）。初回起動や大量のファイル変更後は待ち時間が伸びる。 |
| 安全な復旧 | 待つ。待ちたくない場合は `HVE_STARTUP_INDEX_REFRESH=0` を設定して GUI を起動し、索引は `python -m mdq index` / `python -m cq index` で手動更新する。GUI 専用の設定項目はありません。 |
| 検証 | ステータス欄が「ワークフローの選択: ...」へ戻り、実行開始ボタンが押せること。 |
| エスカレーション | 待機が終わらない場合は、stderr の `index refresh:` 行、`.mdq/` / `.cq/` のファイル一覧、同時に走らせている HVE プロセス数を共有する。 |

### GitHub ウィンドウの Issue / Pull Request 一覧が空になる

| 段階 | 対応 |
|---|---|
| 症状 | ヘッダーの [GitHub] から開いた画面で、Issue（または Pull Request）が 1 件も表示されない。 |
| 確認 | 画面下部のステータス欄を読む。「オープンな Issue は 0 件です。…」と出ていれば **取得は成功しており、オープンな対象が無い** 状態。「GitHub の認証に失敗しました」「権限が不足」「対象が見つかりません」等が出ていれば取得自体の失敗。 |
| 原因候補 | (1) 一覧の既定の絞り込みが `オープン` のため、すべてクローズ済みのリポジトリでは 0 件になる。(2) `GH_TOKEN` / `GITHUB_TOKEN` が未設定。(3) リポジトリ欄の `owner/repo` が誤っている。(4) 一覧上の絞り込み欄に文字列が残っていて表示だけが減っている。 |
| 安全な復旧 | (1) 「状態」を **すべて** に変えて [更新]。(2) 設定 → GitHub → 「GitHub CLI でログイン」でトークンを注入してから [更新]。(3) リポジトリ欄を `owner/repo` に直して [適用]。(4) 一覧上の絞り込み欄を空にする（この欄は取得済み一覧をローカルで絞るだけで、再取得はしない）。 |
| 検証 | ステータス欄が「{n} 件の Issue を取得しました。」に変わり、一覧に行が並ぶこと。 |
| エスカレーション | ステータス欄の文言全文、リポジトリ名、`gh auth status` の結果（トークン値は伏せる）を共有する。 |

> 一覧は更新日時の新しい順に先頭 50 件までを取得します。2 ページ目以降の取得とキーワード検索はこの画面の対象外です。目的の Issue / PR が 50 件より古い場合は github.com 側で番号を確認し、設定 → GitHub の番号欄へ直接入力してください。


## knowledge/ ドキュメント関連のトラブル

### knowledge/ フォルダーが空の場合

**症状**: Prompt の設計精度が低い、業務要件が反映されていない。

**対処法**:
1. `qa/` フォルダーに質問票ファイルが存在するか確認する
2. 質問票が存在する場合は `knowledge-management` ワークフローを実行する（[km-guide.md](./km-guide.md) 参照）
3. `knowledge/business-requirement-document-status.md` で D01〜D21 のカバレッジを確認する

### knowledge/ ファイルが期待通り参照されない

**症状**: Prompt が `knowledge/` の内容を無視して設計している。

**確認事項**:
1. 各 Prompt ファイル（`.github/prompts/*.prompt.md`）の `knowledge/ 参照（任意・存在する場合のみ）` セクションに対象ファイルが記載されているか確認する
2. `knowledge/` のファイル名が正しい形式（`D{NN}-<文書名>.md`）になっているか確認する
3. `knowledge/` ファイルの `**Prompt投入可否**:` フィールドが `Yes（Confirmed のみ）` になっているか確認する（`No（Draft）` の場合は未確定事項があります）

---

## 公式出典

外部サービス固有の復旧策は、以下の公式ページで確認した範囲に限定しています。

| 領域 | title | URL | 確認事項 |
|---|---|---|---|
| GitHub Actions token | Use GITHUB_TOKEN for authentication in workflows | <https://docs.github.com/en/actions/tutorials/authenticate-with-github_token> | `GITHUB_TOKEN` は workflow 内で使え、最小権限の `permissions` を設定することが推奨される。 |
| GitHub Actions OIDC + Azure | Configuring OpenID Connect in Azure | <https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure> | Azure 連携では長期 secret ではなく OIDC / federated identity を使える。 |
| Azure Static Web Apps | Build configuration for Azure Static Web Apps | <https://learn.microsoft.com/en-us/azure/static-web-apps/build-configuration> | Static Web Apps の GitHub Actions build / deploy 設定確認先。 |
| Copilot cloud agent | Starting GitHub Copilot sessions | <https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/start-copilot-sessions> | Copilot cloud agent session の開始経路と PR 生成の前提。 |
| GitHub Sub-Issues | Adding sub-issues | <https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues> | Sub-Issue の基本動作、親子関係、件数・階層制限。 |
