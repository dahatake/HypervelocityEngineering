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
  - [9) `GH_TOKEN` / `REPO` / `gh auth login`](#9-gh_token--repo--gh-auth-login)
  - [10) Cloud preflight スクリプト](#10-cloud-preflight-スクリプト)
- [Web UI 方式のトラブル](#web-ui-方式のトラブル)
  - [Bootstrap ワークフローが起動しない](#bootstrap-ワークフローが起動しない)
  - [Sub Issue API が失敗する](#sub-issue-api-が失敗する)
  - [Copilot が assign されない](#copilot-が-assign-されない)
  - [ワークフローがエラーで終了する](#ワークフローがエラーで終了する)
  - [Azure Static Web Apps デプロイエラー](#azure-static-web-apps-デプロイエラー)
  - [Copilot cloud agent のタスク実行エラー](#copilot-cloud-agent-のタスク実行エラー)
- [HVE CLI Orchestrator のトラブル](#hve-cli-orchestrator-のトラブル)

---

## 初期セットアップで詰まったとき

HVE Cloud Agent Orchestrator と HVE CLI Orchestrator は、前提設定と認証情報が異なります。まず利用方式を切り分けてから確認してください。

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
4. Settings → Actions → General → Workflow permissions が **Read and write permissions** か
5. `COPILOT_PAT` が repository secret に設定されているか（未設定時は設計上スキップ警告になる場合あり）
6. Settings → Copilot → Cloud agent で Cloud agent が有効か
7. self-hosted runner を使う場合は runner が online で、workflow 側 label と一致しているか
8. `bash .github/scripts/preflight-cloud-setup.sh OWNER/REPO` の結果を確認したか

---

### 2) Setup Labels / ラベル初期化

初回セットアップでは、Issue Template 起点ではなく **Actions タブから `Setup Labels` を手動実行** してください。

- `setup-labels` ラベルが存在しない初回状態では、Issue Template 起点のラベル付与・workflow 起動が期待どおりに動かない場合があります
- 403 エラー時は Settings → Actions → General → Workflow permissions が **Read and write permissions** か確認してください
- ラベルが作成されない場合は `.github/labels.json` と `.github/workflows/setup-labels.yml` の存在を確認してください
- 詳細手順は [getting-started.md Step.5](./getting-started.md#step5-ラベル設定) を参照してください

---

### 3) Copilot 自動アサイン

- `COPILOT_PAT` は HVE Cloud Agent Orchestrator で Copilot を Issue に自動アサインするための repository secret です
- `COPILOT_PAT` 未設定時は既存スクリプト設計上、警告してスキップされる場合があります
- 初回セットアップでは `COPILOT_PAT` 設定を推奨（Cloud自動運用では実質必須）
- Settings → Copilot → Cloud agent で対象リポジトリが有効化されているか確認してください
- `GH_TOKEN` は HVE CLI Orchestrator の Issue / PR 作成向けであり、Cloud 側の Copilot 自動アサイン用途ではありません

---

### 4) GitHub Actions / Workflow permissions

- `Setup Labels` や dispatcher/reusable workflow のラベル操作には Workflow permissions の設定が影響します
- Settings → Actions → General → Workflow permissions を **Read and write permissions** に設定してください
- workflow が起動しない・失敗する場合は、対象 workflow が有効であることとジョブログを確認してください

---

### 5) Azure OIDC / Static Web Apps deploy

- Azure Static Web Apps / Azure deploy は **OIDC 認証を基本方針** とします
- 通常、`AZURE_STATIC_WEB_APPS_API_TOKEN` や `GITHUB_PAT` は不要です
- Azure deploy を行う場合は `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` を設定してください
- workflow により `id-token: write` 権限が必要になる場合があります
- Azure deploy を使わない場合、Azure OIDC Secrets は必須ではありません

---

### 6) MCP Servers / GitHub Copilot Skills

- HVE Cloud Agent Orchestrator の MCP Servers は GitHub UI の Settings → Copilot → Cloud agent → MCP Servers で設定します
- HVE CLI Orchestrator の MCP は `--mcp-config`（または hve 側設定ファイル）で指定します
- Cloud と Local の MCP 設定は混同しないでください
- GitHub Copilot Skills は Azure 関連タスクを効率化する推奨設定です。必要時に有効化状態を確認してください

#### markdown-query Skill のトラブルシューティング

- **`ModuleNotFoundError: No module named 'rank_bm25'` または `tiktoken`** → 任意依存です。`pip install -e ".[mdq]"` を実行するか、無視してフォールバック動作（MiniBM25 / char/4 推定）で継続できます。
- **`hve/setup-hve.ps1` / `hve/setup-hve.sh` 実行中に `[mdq] extras` のインストールが失敗した** → セットアップスクリプトは警告に降格して継続するため、`python -m hve.mdq` 自体は内蔵 MiniBM25 でフォールバック動作します。ネットワーク復帰後に手動で再導入してください: PowerShell は `.venv\Scripts\python.exe -m pip install -e ".[mdq]"`、macOS / Linux は `.venv/bin/python -m pip install -e ".[mdq]"`。`python -c "import rank_bm25, tiktoken"` がエラー無しで通れば導入済です。完全に抑止したい場合は `-SkipMdq` / `--skip-mdq` を指定してください。
- **`python -m hve.mdq stats` が `{"files": 0, "chunks": 0}` を返す** → `python -m hve.mdq index` を未実行、または `--root` 指定で既定 11 フォルダから外れています。引数なしで再実行してください。
- **検索結果が 0 件** → `--mode grep` で再試行、または `--paths` フィルタを外してください。日本語は 1 文字単位トークナイズのため短いクエリは再現率が下がる場合があります。
- **削除済みファイルのチャンクが残っている / 索引が古い** → `python -m hve.mdq index` は既定で自動 prune します。`--no-prune` を指定している場合は外して再実行してください。それでも解消しない場合は `python -m hve.mdq index --rebuild`、または `.hve/mdq.sqlite` を削除して再索引してください。

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
5. `--create-issues` / `--create-pr` を使う場合は `GH_TOKEN` と `REPO` が設定されているか
6. `GH_TOKEN` と Cloud 側の `COPILOT_PAT` を混同していないか
7. Work IQ を使う場合は Node.js / npx / `@microsoft/workiq` が利用可能か

詳細は [hve-cli-orchestrator-guide.md 付録D](./hve-cli-orchestrator-guide.md#付録d-トラブルシューティング) も参照してください。

---

### 9) `GH_TOKEN` / `REPO` / `gh auth login`

用途の混同を避けるため、次を分けて確認してください。

- `gh auth login` / `gh auth status`: HVE CLI Orchestrator の基本認証
- `GH_TOKEN` + `REPO`: HVE CLI Orchestrator で `--create-issues` / `--create-pr` を使うときに必要
- `COPILOT_PAT`: HVE Cloud Agent Orchestrator の Copilot 自動アサイン用途
- `GITHUB_TOKEN`: GitHub Actions が workflow 実行時に自動付与するトークン
- このリポジトリの既存 Copilot 自動アサイン処理は `COPILOT_PAT` 前提です

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
3. リポジトリの Workflow permissions が "Read and write" になっているか確認
   - **Settings → Actions → General → Workflow permissions** を確認

---

### Sub Issue API が失敗する

**症状**: Sub Issue が作成されず、エラーログに API エラーが記録されている。

**原因と対応**:

- Sub Issue API は GitHub の一部プランでのみ利用可能です
- **フォールバック動作**: 失敗した場合でも、親 Issue にチェックリストコメントが自動投稿されます
- 手動で Sub Issue を作成する場合は、チェックリストコメントの内容をもとに個別に Issue を作成してください

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

**確認事項**:

1. **Actions タブ**で失敗したジョブのログを確認してください
2. `GITHUB_TOKEN` の権限が `issues: write` になっているか確認してください
   - **Settings → Actions → General → Workflow permissions** で確認
3. ワークフロー権限が **Read and write** になっているか確認

---

### `docs/catalog/app-arch-catalog.md` 関連エラー

AAD-WEB / ASDW-WEB / ABD / ABDV ワークフローで以下のエラーが Issue にコメントされた場合の対処:

| エラー文言（先頭） | 原因 | 対処 |
|---|---|---|
| `... が見つかりません。Architecture Design (AAS) を先に実行してください` | catalog ファイル自体が未生成 | AAS ワークフローを先に実行する |
| `... の見出し \`## A) サマリ表（全APP横断）\` セクションが見つかりません` | catalog の見出しが出力契約と大きく異なる（`サマリ表` / `選定結果一覧` を含まない） | `.github/skills/architecture-questionnaire/assets/output-format.md` §7.2 に沿って見出しを `## A) サマリ表（全APP横断）` に修正、または AAS Step.2 を再実行（`選定結果一覧（サマリ表）` などの軽微な揺れは受理されるが WARN が出ます） |
| `... のサマリ表に必要な列 ...` | テーブル列名（APP-ID / 推薦アーキテクチャ）の不在/誤表記 | サマリ表の列ヘッダを出力契約に揃える |
| `... が予期せず失敗しました（exit 1, 詳細不明）` | Python 自体の起動失敗等 | ワークフローログで `python3 -m hve.app_arch_filter` のスタックトレースを確認 |

---

### preflight-cloud-setup.sh で FAIL / WARN が出る

**症状**: `bash .github/scripts/preflight-cloud-setup.sh OWNER/REPO` の結果で `FAIL` または `WARN` が表示される。

**確認事項（チェック順）**:

1. `gh` がインストール済みで `gh auth status` が成功するか
2. `OWNER/REPO` が正しいか、`gh repo view OWNER/REPO` が成功するか
3. `Setup Labels` workflow が存在するか（なければテンプレートコピー漏れを確認）
4. ラベル不足の `WARN` は初回状態なら正常な場合があるため、[getting-started.md Step.5](./getting-started.md#step5-ラベル設定) に従って Setup Labels を手動実行する
5. secret / runner の確認で取得失敗した場合は、権限不足の可能性があるため GitHub UI で手動確認する（未設定と断定しない）

---

### ADOC / AKM が起動しない

**症状**: `sourcecode-to-documentation.yml` または `knowledge-management.yml` から Issue を作成しても実行されない。

**確認事項**:

1. Issue に `auto-app-documentation` または `knowledge-management` ラベルが付いているか
2. **Actions** タブで `auto-app-documentation-reusable.yml` / `auto-knowledge-management-reusable.yml` が有効か
3. ラベル未作成の場合は [getting-started.md Step.5](./getting-started.md#step5-ラベル設定) を参照し、少なくとも `auto-app-documentation` と `knowledge-management` を明示的に作成

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
- SDK 実行時は `MODEL=claude-opus-4.6` などで一時固定して再実行する（最新 Opus が未ロールアウトの環境での一時回避）
- workflow 実行ログを確認し、必要に応じて `Auto`（既定）に戻して再実行する
- `Auto` は GitHub が最適モデルを動的選択するため、モデル可用性・レート制限・レイテンシの影響を受けにくくなります
- `Auto` はプラン/管理者ポリシー準拠のモデルのみを候補とし、プレミアム乗数 1x 超のモデルは対象外です
- `Auto` 選択時はプレミアムリクエスト枠の消費が 0.9x（10% ディスカウント）です
- 公式: https://docs.github.com/en/copilot/concepts/auto-model-selection

> **モデル ID の命名規則**: Copilot CLI が受理するモデル ID はすべてドット区切りです（例: `claude-opus-4.7` / `claude-opus-4.6` / `gpt-5.5` / `gpt-5.4`）。`copilot` コマンドで `/model` を実行すると利用可能な正確な ID が確認できます。廃止モデル（`claude-sonnet-4.6` / `gpt-5.3-codex` / `gemini-2.5-pro`）や未サポートのモデル ID を指定した場合は `Auto` に自動フォールバックします（WARNING ログあり）。

---

### Azure Static Web Apps デプロイエラー

**症状**: SWA デプロイ workflow が失敗する、または `::warning::` でスキップされる。

**確認事項（チェック順）**:

SWA デプロイは OIDC 認証方式を使用しています。`AZURE_STATIC_WEB_APPS_API_TOKEN` の設定は不要です。以下の Secrets が正しく設定されていることを確認してください。

1. **OIDC 認証 Secrets が設定されているか確認**
   ```bash
   gh secret list --repo <owner>/<repo>
   ```
   以下の 3 つが存在することを確認:
   - `AZURE_CLIENT_ID`
   - `AZURE_TENANT_ID`
   - `AZURE_SUBSCRIPTION_ID`
   
   未設定の場合は [getting-started.md Step.4（認証設定）](./getting-started.md#step4-認証設定copilot_pat) を参照してください。

2. **Azure リソースが存在するか確認**
   ```bash
   az staticwebapp show --name <SWA_NAME> --resource-group <RESOURCE_GROUP>
   ```
   - リソースが存在しない場合は `create-azure-webui-resources.sh` を実行してください

3. **`AZURE_CLIENT_ID` のサービスプリンシパルに SWA 権限があるか確認**
   - サービスプリンシパルに `Contributor` ロールが付与されているか確認してください

> [!NOTE]
> 初期セットアップの正本方針は OIDC です（`AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID`）。  
> 一部の Issue Template / workflow 本文に旧トークン記述が残る場合がありますが、認証設定は [getting-started.md の認証・認可の用途一覧](./getting-started.md#認証認可の用途一覧cloud--local--azure) を優先してください。

---

### Copilot cloud agent のタスク実行エラー

**症状**: Pull Request の Session の中で `Run Bash command` が繰り返され、何も処理が行われていない。

> [!IMPORTANT]
> この状況になったら、即座にジョブを停止させてください。GitHub Actions の課金に影響が考えられます。

**対応策**: 以下のプロンプトを PR コメントで Copilot に送信してください。

> 詳細なプロンプトは [prompt-examples.md — Copilot cloud agent エラー対応](./prompt-examples.md#copilot-cloud-agent-エラー対応) を参照してください。

その他の便利なプロンプトは [prompt-examples.md](./prompt-examples.md) を参照してください。

---

## HVE CLI Orchestrator のトラブル

HVE CLI Orchestrator（ローカル実行方式）のトラブルシューティングは [hve-cli-orchestrator-guide.md 付録D](./hve-cli-orchestrator-guide.md#付録d-トラブルシューティング) を参照してください。

### HVE CLI Orchestrator で Issue / PR 作成に失敗する

`--create-issues` / `--create-pr` を使う場合は、次をこの順で確認してください。

1. `gh auth status` で GitHub CLI の認証状態を確認
2. `GH_TOKEN` が設定されているか確認
3. `REPO`（`owner/repo`）または `--repo` が指定されているか確認
4. `GH_TOKEN` は Cloud の `COPILOT_PAT` とは別用途であることを確認

主なトラブルと対応:

| 症状 | 参照箇所 |
|------|---------|
| `copilot: command not found` | [付録D: Copilot CLI が見つからない](./hve-cli-orchestrator-guide.md#copilot-cli-が見つからない) |
| `ModuleNotFoundError: No module named 'copilot'` | [付録D: github-copilot-sdk がインストールされていない](./hve-cli-orchestrator-guide.md#github-copilot-sdk-がインストールされていない--python--m-hve-が動かない) |
| セッションタイムアウト | [付録D: セッションタイムアウト](./hve-cli-orchestrator-guide.md#セッションタイムアウト) |
| MCP Server が接続できない | [付録D: MCP Server が接続できない](./hve-cli-orchestrator-guide.md#mcp-server-が接続できない) |
| 並列実行でメモリ不足 | [付録D: 並列実行でメモリ不足](./hve-cli-orchestrator-guide.md#並列実行でメモリ不足) |
| PR 作成時に HTTP 422 エラー | [付録D: PR 作成時に HTTP 422 エラー](./hve-cli-orchestrator-guide.md#pr-作成時に-http-422-エラー) |

### Resume 関連のよくある質問

#### Q. 実行を中断したら続きから再開したい

**A.** 実行中に `Ctrl+R` で保存し、次回 `python -m hve` 起動時の Resume プロンプト、または `python -m hve resume continue <run_id>` を使って再開してください。

#### Q. SDK バージョン差異の警告が出る

**A.** 保存時と実行時で Copilot SDK の major version が異なる可能性があります。厳密に止めたい場合は `python -m hve resume continue <run_id> --abort-on-sdk-mismatch` を利用してください。

#### Q. `Ctrl+R` を押しても反応しない

**A.** 非 TTY 環境（リダイレクト/CI）や VS Code 統合ターミナルで keybind が安定しない場合があります。`HVE_DISABLE_KEYBIND=1` を設定し、`hve resume ...` の CLI サブコマンドを使用してください。

#### Q. `state.json not found` で Resume できない

**A.** 実行時の CWD が保存時と違う可能性があります。保存時と同じディレクトリで起動するか、`--work-dir` に `work/runs` の絶対パスを指定してください。

## knowledge/ ドキュメント関連のトラブル

### knowledge/ フォルダーが空の場合

**症状**: Custom Agent の設計精度が低い、業務要件が反映されていない。

**対処法**:
1. `qa/` フォルダーに質問票ファイルが存在するか確認する
2. 質問票が存在する場合は `knowledge-management` ワークフローを実行する（[km-guide.md](./km-guide.md) 参照）
3. `knowledge/business-requirement-document-status.md` で D01〜D21 のカバレッジを確認する

### knowledge/ ファイルが期待通り参照されない

**症状**: Custom Agent が `knowledge/` の内容を無視して設計している。

**確認事項**:
1. 各 Custom Agent ファイル（`.github/agents/*.agent.md`）の `knowledge/ 参照（任意・存在する場合のみ）` セクションに対象ファイルが記載されているか確認する
2. `knowledge/` のファイル名が正しい形式（`D{NN}-<文書名>.md`）になっているか確認する
3. `knowledge/` ファイルの `**Prompt投入可否**:` フィールドが `Yes（Confirmed のみ）` になっているか確認する（`No（Draft）` の場合は未確定事項があります）
