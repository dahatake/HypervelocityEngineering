# SDK ユーザーガイド（Copilot SDK版ワークフローオーケストレーション）

> 最終更新日: 2026-03-26

---

## 目次

- [はじめに](#はじめに)
- [環境設定](#環境設定)
- [コマンドリファレンス](#コマンドリファレンス)
- [ワークフロー一覧](#ワークフロー一覧)
- [付録A: MCP Server 設定ガイド](#付録a-mcp-server-設定ガイド)
- [付録B: Custom Agents 設定ガイド](#付録b-custom-agents-設定ガイド)
- [付録C: DAG 並列実行と Post-step 自動プロンプト](#付録c-dag-並列実行と-post-step-自動プロンプト)
- [付録D: トラブルシューティング](#付録d-トラブルシューティング)
- [付録E: セキュリティ・SSO・関連リンク](#付録e-セキュリティsso関連リンク)

---

## はじめに

### このガイドの目的

このガイドは、このリポジトリの `hve/` パッケージを使って、**ローカル PC 上で完結して**ワークフローを実行するための手順を解説します。実行には PyPI パッケージ `github-copilot-sdk`（`pip install github-copilot-sdk`）が依存ライブラリとして必要です。

> **注意**: `hve/` はこのリポジトリに含まれるローカルパッケージです。`python -m hve` はリポジトリルートをカレントディレクトリとして実行してください。

本ガイドは **SDK 版（ローカル実行方式）** に特化しています。Web UI 方式との比較や全体の利用ガイドについては [README.md](./README.md#2つの利用方法) を参照してください。

### ポイント

- **GitHub Actions 不要** — `python -m hve orchestrate` コマンド 1 本で実行
- **COPILOT_PAT 不要** — ローカルで直接 Agent を実行するため、Copilot アサイン用 PAT は不要
- **基本実行に GH_TOKEN 不要** — `--create-issues` / `--create-pr` / `--auto-coding-agent-review` を使わなければ環境変数の設定は不要
- MCP Server・Custom Agents・asyncio による並列実行など、高度な機能を利用可能

### 対象読者

- **開発者**: ローカル PC 上でワークフローを完結させたい方
- **アーキテクト**: MCP Server や Custom Agents を活用した高度なオーケストレーションを構築したい方
- **前提知識**: Python の基本的なスクリプト実行ができる方、`gh auth login` などの GitHub CLI 操作ができる方

---

## 環境設定

### 前提条件

| ソフトウェア | 必須 / オプション | 説明 |
|-------------|-----------------|------|
| Python 3.9+ | **必須** | スクリプト実行環境 |
| Copilot CLI | **必須** | SDK の実行エンジン |
| GitHub CLI（`gh`） | **必須** | 認証管理に使用 |
| Git | **必須** | リポジトリのクローンに使用 |
| Node.js（npm/npx） | オプション | MCP Server（filesystem 等）を使用する場合 |

### Copilot CLI のインストール

公式ドキュメント: https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli

```bash
copilot --version   # インストール確認
```

> **注意**: GitHub Copilot のサブスクリプションが有効なアカウントが必要です。

### Python 環境セットアップ

```bash
git clone https://github.com/dahatake/RoyalytyService2ndGen.git
cd RoyalytyService2ndGen
python -m venv .venv
```

```bash
# macOS / Linux
source .venv/bin/activate
```

> **Windows**: PowerShell は `.venv\Scripts\Activate.ps1`、コマンドプロンプトは `.venv\Scripts\activate.bat` を使用してください。

```bash
pip install github-copilot-sdk
python -m hve --help   # インストール確認
```

> 作業終了時は `deactivate` で仮想環境を終了してください。

### 認証設定

#### 認証手段A: `gh auth login`（推奨）

```bash
gh auth login
gh auth status   # 「Logged in to github.com」と表示されれば成功
```

基本実行ではこれだけで十分です。追加の環境変数設定は不要です。

#### 認証手段B: 環境変数 `GH_TOKEN`（Issue/PR 作成・Code Review Agent 使用時）

以下のオプションを使用する場合のみ `GH_TOKEN` が必要です。

| オプション | GH_TOKEN |
|-----------|----------|
| `--create-issues` | 必要（未設定ならエラー終了） |
| `--create-pr` | 必要（未設定ならエラー終了） |
| `--auto-coding-agent-review` | **必須** |
| MCP Server（GitHub HTTP） | **必須** |
| 上記以外（基本実行） | **不要** |

#### Fine-grained PAT の作成手順

1. GitHub.com > **プロフィールアイコン** > **Settings** > **Developer settings**
2. **Personal access tokens** > **Fine-grained tokens** > **Generate new token**
3. 基本情報を入力:
   - **Token name**: 任意（例: `copilot-sdk-tools`）
   - **Expiration**: 90日以内を推奨
4. **Repository access**: **Only select repositories** → `dahatake/RoyalytyService2ndGen` を選択
5. **Permissions**（Repository permissions）:

| 権限 | 設定値 | 用途 |
|------|--------|------|
| **Issues** | Read and write | `--create-issues` |
| **Pull requests** | Read and write | `--create-pr` |
| **Metadata** | Read-only（自動付与） | — |
| **Contents** | Read and write | `--create-issues` / `--create-pr` / `--auto-coding-agent-review` 使用時 |

> **最小権限の原則**: `--create-issues` / `--create-pr` / `--auto-coding-agent-review` はいずれもブランチ作成・commit・push を伴うため、Contents も Read and write が必要です。

6. **Generate token** をクリックし、表示されたトークン（`github_pat_` で始まる文字列）を**必ずこの時点でコピー**

> ⚠️ トークンはこの画面を離れると二度と表示されません。

7. 環境変数に設定:

```bash
# macOS / Linux
export GH_TOKEN="github_pat_xxxxxxxxxxxxxxxxxxxx"
```

> **Windows**: PowerShell は `$env:GH_TOKEN = "github_pat_xxxx"`、コマンドプロンプトは `set GH_TOKEN=github_pat_xxxx`（`=`前後にスペース不可、ダブルクォート不可）。

#### 既存の Fine-grained PAT を使う場合

Settings > Developer settings > Fine-grained tokens で対象トークンを開き、以下を確認してください:

- 有効期限が切れていないこと
- リポジトリ範囲に `dahatake/RoyalytyService2ndGen` が含まれていること
- 上記の権限が付与されていること

不足がある場合は **Regenerate token** で再生成してください（トークン文字列が変わります）。

#### トークンの動作確認

```bash
gh api user --jq '.login'                                              # トークン有効性
gh api repos/dahatake/RoyalytyService2ndGen --jq '.full_name'          # リポジトリアクセス
python -m hve orchestrate --workflow aas --branch main --dry-run       # SDK dry-run
```

### MCP Server 設定（オプション）

MCP Server を使用する場合は JSON 設定ファイルを作成し、`--mcp-config` で指定します。詳細は [付録A: MCP Server 設定ガイド](#付録a-mcp-server-設定ガイド) を参照してください。

```json
{
  "filesystem": {
    "type": "local",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
    "tools": ["*"]
  },
  "github": {
    "type": "http",
    "url": "https://api.githubcopilot.com/mcp/",
    "headers": {"Authorization": "Bearer ${GH_TOKEN}"},
    "tools": ["*"]
  }
}
```

---

## コマンドリファレンス

### 基本構文

```bash
python -m hve orchestrate --workflow <WORKFLOW_ID> [OPTIONS]
```

### 最もシンプルな実行

```bash
python -m hve orchestrate --workflow aad
```

### --dry-run（事前確認）

`--dry-run` を付けると SDK 呼び出し・Issue/PR 作成を行わず、実行計画のみ表示します。初回は必ず使用してください。

```bash
python -m hve orchestrate --workflow aas --branch main --dry-run
```

出力例:
```
[DRY RUN] orchestrate: workflow=aas, branch=main
[DRY RUN] DAG Traversal:
[DRY RUN]   Wave 1: Step.1 (root)
[DRY RUN]   Wave 2: Step.2 (depends_on: Step.1)
[DRY RUN] Would execute: Step.1 - アプリケーション候補の選定
[DRY RUN] Would execute: Step.2 - アプリ一覧（アーキタイプ）概要
[DRY RUN] No SDK calls were made (dry-run mode).
```

### 全オプション指定例

```bash
# コピーして不要なオプションを削除して使用してください
# ⚠️ --auto-coding-agent-review / --create-issues / --create-pr 使用時は GH_TOKEN が必要です
python -m hve orchestrate \
  --workflow asdw \
  --model claude-opus-4.6 \
  --max-parallel 15 \
  --auto-qa \
  --auto-contents-review \
  --auto-coding-agent-review \
  --auto-coding-agent-review-auto-approval \
  --create-issues \
  --create-pr \
  --repo dahatake/RoyalytyService2ndGen \
  --branch main \
  --app-id APP-04 \
  --resource-group rg-dev \
  --usecase-id UC-01 \
  --batch-job-id JOB-01 \
  --steps Step.1,Step.2,Step.3 \
  --mcp-config mcp-servers.json \
  --cli-path /usr/local/bin/copilot \
  --timeout 300 \
  --review-timeout 600 \
  --show-stream \
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
| `--workflow`, `-w` | ワークフロー ID（`aas` / `aad` / `asdw` / `abd` / `abdv` / `aid`） | なし（**必須**） |
| `--branch` | ターゲットブランチ名 | `main` |
| `--steps` | 実行ステップをカンマ区切りで指定 | 全ステップ |
| `--dry-run` | 事前確認モード（SDK 呼び出しなし） | `false` |
| `--verbose`, `-v` | 詳細ログ出力 | `true`（`--quiet` 未指定時） |
| `--quiet`, `-q` | 出力抑制（`--verbose` と排他） | `false` |

#### Agent 実行オプション

| オプション | 説明 | デフォルト値 |
|-----------|------|------------|
| `--model`, `-m` | 使用する AI モデル | `claude-opus-4.6` |
| `--max-parallel` | 同時実行するステップ数の上限 | `15` |
| `--auto-qa` | 各ステップ後に自動 QA を実行（対話的） | `false` |
| `--auto-contents-review` | 各ステップ後に自動レビューを実行 | `false` |
| `--auto-coding-agent-review` | 全ステップ完了後に Code Review Agent レビューを実行（`--repo` + `GH_TOKEN` 必須） | `false` |
| `--auto-coding-agent-review-auto-approval` | Code Review Agent の修正プランを全て自動承認 | `false` |
| `--timeout` | idle タイムアウト秒数 | `300` |
| `--review-timeout` | Code Review Agent レビュー完了待ちタイムアウト秒数 | `600` |
| `--show-stream` | モデル応答のトークンストリーム表示 | `false` |

#### MCP Server・CLI 接続オプション

| オプション | 説明 | デフォルト値 |
|-----------|------|------------|
| `--mcp-config` | MCP Server 設定 JSON ファイルのパス | なし |
| `--cli-path` | Copilot CLI 実行ファイルパス | 自動検出 |
| `--cli-url` | 外部 CLI サーバー URL（`--cli-path` の代わり） | なし |

#### Issue/PR 作成オプション

| オプション | 説明 | デフォルト値 |
|-----------|------|------------|
| `--create-issues` | 実行前に GitHub Issue を作成 | `false` |
| `--create-pr` | 実行後に GitHub PR を作成 | `false` |
| `--repo` | リポジトリ名（`owner/repo` 形式） | `$REPO` |

#### その他のオプション

> **注**: 以下は主要な追加オプションです。完全なオプション一覧は `python -m hve orchestrate --help` で確認してください。

| オプション | 説明 | デフォルト値 |
|-----------|------|------------|
| `--ignore-paths` | `git add` 時に除外するパス（スペース区切りで複数指定可） | config デフォルト値 |
| `--additional-prompt` | 全 Custom Agent のプロンプト末尾に追記する文字列 | なし |
| `--issue-title` | Root Issue 作成時のタイトルを上書き | ワークフロー名から自動生成 |

#### ワークフロー固有オプション

| オプション | 説明 | 対応ワークフロー |
|-----------|------|--------------|
| `--app-id` | アプリケーション ID（例: `APP-04`） | `asdw` |
| `--resource-group` | Azure リソースグループ名（例: `rg-dev`） | `asdw`, `abdv` |
| `--usecase-id` | ユースケース ID（例: `UC-01`） | `asdw` |
| `--batch-job-id` | バッチジョブ ID（カンマ区切り可。例: `JOB-01,JOB-02`） | `abdv` |

### 使い方の例

#### 基本実行

```bash
python -m hve orchestrate --workflow aad
```

#### QA + Review 有効

```bash
python -m hve orchestrate \
  --workflow aad \
  --branch main \
  --auto-qa \
  --auto-contents-review
```

> QA 有効時はステップごとにユーザーの回答入力が求められる対話的な実行になります。

#### MCP Server 付き実行

```bash
python -m hve orchestrate \
  --workflow aad \
  --branch main \
  --mcp-config mcp-servers.json
```

#### Issue/PR 作成有効

```bash
python -m hve orchestrate \
  --workflow aas \
  --branch main \
  --repo dahatake/RoyalytyService2ndGen \
  --create-issues \
  --create-pr
```

> `GH_TOKEN` が必要です。`--create-issues` または `--create-pr` を指定している状態で `GH_TOKEN` が未設定の場合、前提条件エラーとしてコマンドは終了します。

#### Code Review Agent 有効

```bash
python -m hve orchestrate \
  --workflow aad \
  --branch main \
  --auto-coding-agent-review \
  --repo dahatake/RoyalytyService2ndGen
```

自動承認を有効にする場合は `--auto-coding-agent-review-auto-approval` を追加してください。

> **前提**: `GH_TOKEN` + `--repo` が必須。Agent の成果物がリモートブランチに push されている必要があります。

---

## ワークフロー一覧

### 逆引き表

| やりたいこと | ワークフロー | コマンド |
|------------|------------|---------|
| アプリケーション選定 | `aas` | `python -m hve orchestrate --workflow aas` |
| アプリケーション設計 | `aad` | `python -m hve orchestrate --workflow aad` |
| Azure Web アプリ実装 | `asdw` | `python -m hve orchestrate --workflow asdw --app-id APP-04 --resource-group rg-dev --usecase-id UC-01` |
| バッチ設計 | `abd` | `python -m hve orchestrate --workflow abd` |
| バッチ実装 | `abdv` | `python -m hve orchestrate --workflow abdv --resource-group rg-batch --batch-job-id JOB-01` |
| IoT 設計 | `aid` | `python -m hve orchestrate --workflow aid` |

### 各ワークフローの詳細

#### aas — Auto App Selection（アプリケーション選定）

| 項目 | 内容 |
|------|------|
| **目的** | ユースケース一覧からアプリケーション候補を自動選定 |
| **前提条件** | `users-guide/01-Business-Requirement.md` 等の要求定義が存在すること |
| **ステップ数** | 2 |
| **固有オプション** | なし |

#### aad — Auto App Design（アプリケーション設計）

| 項目 | 内容 |
|------|------|
| **目的** | ドメイン分析・データモデル・サービスカタログ等の設計を自動実行 |
| **前提条件** | `aas` ワークフローによるアプリ選定が完了していること |
| **ステップ数** | 16 |
| **固有オプション** | なし |

#### asdw — Auto App Dev Azure Web（Azure Web アプリ実装）

| 項目 | 内容 |
|------|------|
| **目的** | Azure マイクロサービスの実装・デプロイを自動実行 |
| **前提条件** | `aad` ワークフローによる設計が完了していること |
| **ステップ数** | 24 |
| **固有オプション** | `--app-id`（必須）, `--resource-group`（必須）, `--usecase-id`（必須） |

#### abd — Auto Batch Design（バッチ設計）

| 項目 | 内容 |
|------|------|
| **目的** | バッチ処理の設計（ドメイン分析・データソース分析・ジョブカタログ等）を自動実行 |
| **前提条件** | `aad` ワークフローによる設計が完了していること |
| **ステップ数** | 9 |
| **固有オプション** | なし |

#### abdv — Auto Batch Dev（バッチ実装）

| 項目 | 内容 |
|------|------|
| **目的** | バッチジョブの実装・デプロイを自動実行 |
| **前提条件** | `abd` ワークフローによる設計が完了していること |
| **ステップ数** | 7 |
| **固有オプション** | `--resource-group`（必須）, `--batch-job-id`（必須、カンマ区切り可） |

#### aid — Auto IoT Design（IoT 設計）

| 項目 | 内容 |
|------|------|
| **目的** | IoT システムの設計を自動実行 |
| **前提条件** | `aas` ワークフローによるアプリ選定が完了していること |
| **ステップ数** | 10 |
| **固有オプション** | なし |

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

ワークフロー定義（`workflow_registry`）で特定のステップにのみ MCP Server を適用できます。詳細は [付録B](#付録b-custom-agents-設定ガイド) を参照してください。

---

## 付録B: Custom Agents 設定ガイド

### workflow_registry の custom_agent フィールド

ワークフロー定義でステップごとに `custom_agent` を指定します。

```python
WORKFLOW_REGISTRY = {
    "aad": {
        "steps": [
            {
                "id": "Step.1.1",
                "title": "ドメイン分析",
                "custom_agent": "Arch-Microservice-DomainAnalytics",
                "depends_on": []
            },
            {
                "id": "Step.1.2",
                "title": "データモデリング",
                "custom_agent": "Arch-DataModeling",
                "depends_on": ["Step.1.1"]
            }
        ]
    }
}
```

`custom_agent` に指定した名前が `.github/agents/*.agent.md` の Agent 定義ファイル名に対応します。

### Agent の選択優先順位

1. ステップ固有の `custom_agent`（workflow_registry で定義）
2. デフォルト Agent（Copilot SDK のデフォルト）

---

## 付録C: DAG 並列実行と Post-step 自動プロンプト

### DAG 並列実行

ワークフローの各ステップは DAG（有向非巡回グラフ）として管理され、依存関係を解決しながら `asyncio.Semaphore(max_parallel)` で並列実行されます。

| パターン | 説明 | 例 |
|---------|------|-----|
| sequential | 前ステップ完了後に次が開始 | Step.1 → Step.2 |
| fork | 1ステップ完了後に複数が並列開始 | Step.6 → Step.7.1 ‖ Step.7.2 |
| AND join | 複数ステップがすべて完了後に次が開始 | Step.7.1 AND Step.7.2 → Step.7.3 |
| skip fallback | 条件不一致時にスキップ | skip_if 条件に合致 → スキップ |

> メモリ不足が発生する場合は `--max-parallel` を小さくしてください（例: `--max-parallel 3`）。

### Post-step 自動プロンプト（QA / Review）

| フラグ | 動作 |
|--------|------|
| なし | メインタスクのみ実行 |
| `--auto-qa` のみ | メインタスク → QA → ユーザー回答 |
| `--auto-contents-review` のみ | メインタスク → Review |
| 両方 | メインタスク → QA → ユーザー回答 → Review |

### Code Review Agent フェーズ（`--auto-coding-agent-review`）

全ステップ完了後: Root Issue 作成 → ブランチ作成 → 全ステップ実行 → PR 作成 → Code Review Agent レビュー依頼 → レビュー完了ポーリング（デフォルト 600秒） → 修正プロンプト

---

## 付録D: トラブルシューティング

### Copilot CLI が見つからない

```
エラーメッセージ: command not found: copilot
```

[公式ドキュメント](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli)に従ってインストールし、`copilot --version` で確認してください。PATH 上の場所は `which copilot`（macOS/Linux）または `where copilot`（Windows）で確認できます。

### SDK がインストールされていない / `python -m hve` が動かない

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
| 利用ガイド（README） | [users-guide/README.md](./README.md) |
| GitHub Copilot SDK（リポジトリ） | https://github.com/github/copilot-sdk |
| SDK Getting Started | https://github.com/github/copilot-sdk/blob/main/docs/getting-started.md |
| Custom Agents ドキュメント | https://github.com/github/copilot-sdk/blob/main/docs/features/custom-agents.md |
| MCP Servers ドキュメント | https://github.com/github/copilot-sdk/blob/main/docs/features/mcp.md |
| Copilot CLI インストールガイド | https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli |
| Model Context Protocol（MCP）仕様 | https://modelcontextprotocol.io/ |
| Code Review Agent ドキュメント | https://docs.github.com/en/copilot/using-github-copilot/code-review/using-copilot-code-review |
