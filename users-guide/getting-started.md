# はじめかた（初期セットアップ）

← [README](../README.md)

> **対象読者**: このリポジトリを初めて使うユーザー（Web UI 方式 / HVE CLI Orchestrator 方式のいずれも対象）  
> **前提**: GitHub リポジトリへのアクセス権と、初期セットアップを実施できる権限があること  
> **次のステップ**: セットアップ完了後は [web-ui-guide.md](./web-ui-guide.md) または [hve-cli-orchestrator-guide.md](./hve-cli-orchestrator-guide.md) の利用手順へ進んでください

---

## 目次

- [利用方式の選択（最初に確認）](#利用方式の選択最初に確認)
- [前提条件](#前提条件)
- [Step.1. リポジトリの作成](#step1-リポジトリの作成)
- [Step.2. ファイルのコピー](#step2-ファイルのコピー)
- [Step.3. MCP Server 設定](#step3-mcp-server-設定)
- [Step.3.1. GitHub Copilot Skills 設定](#step31-github-copilot-skills-設定推奨)
- [Step.4. 認証設定（COPILOT_PAT）](#step4-認証設定copilot_pat)
- [認証・認可の用途一覧（Cloud / Local / Azure）](#認証認可の用途一覧cloud--local--azure)
- [ワークフロー権限設定](#ワークフロー権限設定)
- [HVE Cloud Agent Orchestrator 初回セットアップ チェックリスト](#hve-cloud-agent-orchestrator-初回セットアップ-チェックリスト)
- [Step.4.5. Self-hosted Runner 設定（オプション）](#step45-self-hosted-runner-設定オプション)
- [Step.5. ラベル設定](#step5-ラベル設定)
- [初回疎通確認（HVE Cloud Agent Orchestrator）](#初回疎通確認hve-cloud-agent-orchestrator)
- [Copilot 有効化](#copilot-有効化)

---

## 利用方式の選択（最初に確認）

このリポジトリには **HVE Cloud Agent Orchestrator**（GitHub Actions）と **HVE CLI Orchestrator**（ローカル実行）の 2 つの実行方式があります。まず使いたい方式を選んでセットアップを進めてください。

| 使いたい方式 | 進む先 |
|---|---|
| GitHub.com 上で Issue Template からワークフローを実行したい | このガイドの全ステップ → [web-ui-guide.md](./web-ui-guide.md) |
| ローカル PC/Mac/Linux から `python -m hve` で実行したい | Step.1〜Step.4 の共通セットアップ → [hve-cli-orchestrator-guide.md](./hve-cli-orchestrator-guide.md) |
| 両方使いたい | Step.1〜Step.5 の共通セットアップ完了後、[web-ui-guide.md](./web-ui-guide.md) → [hve-cli-orchestrator-guide.md](./hve-cli-orchestrator-guide.md) の順に進む |

> **HVE Cloud Agent Orchestrator 初回チェックリスト**: セットアップ手順を進める前に、[HVE Cloud Agent Orchestrator 初回セットアップ チェックリスト](#hve-cloud-agent-orchestrator-初回セットアップ-チェックリスト) で必要な手順の全体像を確認しておくことを推奨します。

---

## 前提条件

| ツール | 必須 / オプション | 用途 |
|--------|-----------------|------|
| GitHub アカウント | **必須** | リポジトリ操作・Copilot 利用 |
| GitHub Copilot ライセンス | **必須** | Copilot cloud agent 利用 |
| Git | **必須** | リポジトリのクローン |
| Web ブラウザ | **必須** | GitHub.com の操作（Web UI 方式） |
| Python 3.11+ | HVE CLI Orchestrator のみ | HVE CLI Orchestrator ワークフロー実行 |
| GitHub Copilot CLI（外部 `copilot` コマンド） | オプション | SDK 同梱ではなく外部 CLI を明示利用する場合 |
| Node.js（npm/npx） | オプション | MCP Server（filesystem 等）/ Work IQ / npm 方式の外部 Copilot CLI 使用時 |
| Microsoft Work IQ（`@microsoft/workiq`） | オプション | HVE CLI Orchestrator で M365 補助情報を参照する場合（[詳細](./hve-cli-orchestrator-guide.md#work-iq-mcp-連携オプション)） |

> Issue Template から実行する場合は、フォーム内の **「使用するモデル」** で `Auto`（既定: GitHub が最適モデルを動的選択。0.9x 計上）または任意モデルを選択できます。公式: https://docs.github.com/en/copilot/concepts/auto-model-selection

> Work IQ のセットアップ手順は [hve-cli-orchestrator-guide.md — Work IQ MCP 連携](./hve-cli-orchestrator-guide.md#work-iq-mcp-連携オプション) を参照してください。

---

## セットアップフロー

![初期セットアップ フロー: Step.1〜5 + Copilot 有効化](./images/getting-started-setup-flow.svg)

---

## Step.1. リポジトリの作成

GitHub リポジトリを作成します。GitHub Copilot cloud agent が作業をするためのリポジトリです。

### Step.1.1. テンプレートリポジトリを使う（推奨）

本リポジトリ（`dahatake/RoyalytyService2ndGen`）はテンプレートリポジトリです。GitHub の「Use this template」ボタンから自分のリポジトリを作成できます。

1. [dahatake/RoyalytyService2ndGen](https://github.com/dahatake/RoyalytyService2ndGen) を開く
2. 右上の **「Use this template」** ボタンをクリック
3. **「Create a new repository」** を選択
4. リポジトリ名・可視性を設定して作成

> **注意**: このリポジトリは `HypervelocityEngineering-Japanese` テンプレートから作成されたインスタンスです。テンプレートから直接作成する場合は [dahatake/HypervelocityEngineering-Japanese](https://github.com/dahatake/HypervelocityEngineering-Japanese) も参照してください。

### Step.1.2. Git Clone で取得する場合

```bash
git clone https://github.com/dahatake/RoyalytyService2ndGen.git
```

---

## Step.2. ファイルのコピー

「Use this template」を使った場合は、このステップは不要です。

Git Clone でファイルを取得した場合は、ダウンロードしたファイルを**あなたのプロジェクトのリポジトリ**に全てコピーします。

フォルダー構造は以下のようになります:

```
your-project/
├── .github/
│   ├── agents/
│   │   ├── Arch-Microservice-DomainAnalytics.agent.md
│   │   ├── Arch-Microservice-ServiceIdentify.agent.md
│   │   └── ... (その他の Custom Agent ファイル)
│   ├── ISSUE_TEMPLATE/
│   ├── workflows/
│   ├── scripts/
│   └── copilot-instructions.md
├── README.md
├── users-guide/
└── ... (その他のプロジェクトファイル)
```

### Custom Agent ファイルの編集（オプション）

各 Custom Agent ファイルは、プロジェクトの要件に応じてカスタマイズできます。

```markdown
## ユースケースID
- UC-xxx  ← あなたのユースケース ID に変更

## ユースケース
  - docs/usecase/{ユースケースID}/usecase-description.md  ← パスを変更
```

**編集する際の注意点:**
- ファイル先頭の YAML フロントマター（`---` で囲まれた部分）の `name` と `description` は Custom Agent の識別に使用されます
- `tools: ["*"]` は全てのツールへのアクセスを許可する設定です

詳細: [Copilot ベストプラクティス](https://docs.github.com/ja/copilot/using-github-copilot/coding-agent/best-practices-for-using-copilot-to-work-on-tasks#adding-custom-instructions-to-your-repository)

---

## Step.3. MCP Server 設定

GitHub リポジトリに GitHub Copilot cloud agent が MCP Server を利用できるように設定します。

GitHub リポジトリの **Settings → Copilot → Cloud agent → MCP Servers** で以下の設定を追加してください。

### 設定文字列

```json
{
  "mcpServers": {
    "Azure": {
      "type": "local",
      "command": "npx",
      "args": [
        "-y",
        "@azure/mcp@latest",
        "server",
        "start"
      ],
      "tools": ["*"]
    },
    "MicrosoftDocs": {
      "type": "http",
      "url": "https://learn.microsoft.com/api/mcp",
      "tools": ["*"]
    }
  }
}
```

### 参考リンク

- Azure MCP Server 設定: [Microsoft Learn](https://learn.microsoft.com/ja-jp/azure/developer/azure-mcp-server/how-to/github-copilot-coding-agent)
- Microsoft Learn Docs MCP Server: [Qiita 解説記事](https://qiita.com/dahatake/items/4f6f0deb53333c0200ef)

> HVE CLI Orchestrator の MCP Server 設定については [HVE CLI Orchestrator ユーザーガイド 付録A](./hve-cli-orchestrator-guide.md#付録a-mcp-server-設定ガイド) を参照してください。

---

## Step.3.1. GitHub Copilot Skills 設定（推奨）

Azure 関連の作業を効率化するため、**Azure Skills** のインストールを推奨します。

- **Azure Skills**: https://github.com/microsoft/azure-skills
- **Skills CLI**: https://github.com/microsoft/skills

### 初回インストール

対話モード（スキルを選択してインストール）:

```bash
npx -y skills add microsoft/skills
```

全スキルを一括インストール（非対話モード）:

```bash
npx skills add microsoft/skills --skill '*' --agent copilot --yes --copy
```

インストール後、`.github/skills/` 配下に SKILL.md ファイルが配置され、GitHub Copilot cloud agent が Azure 関連タスクで自動的に Skills を活用します（`.github/copilot-instructions.md` §1「ワークフロー概要」および §2「Skills ルーティングテーブル」参照）。

### 自動同期（推奨）

このリポジトリには Azure Skills の定期同期ワークフロー（`.github/workflows/sync-azure-skills.yml`）が設定されています。

- **スケジュール**: 毎週月曜 9:00 UTC に自動実行
- **動作**: microsoft/skills の最新版と差分を検出し、変更がある場合は PR を自動作成
- **カスタムスキル保護**: `large-output-chunking`, `repo-onboarding-fast`, `task-dag-planning`, `work-artifacts-layout` は同期対象外

手動で即座に同期する場合は、GitHub Actions タブから `Sync Azure Skills` ワークフローを手動実行してください。

---

## Step.4. 認証設定（COPILOT_PAT）

PAT（Personal Access Token）をリポジトリのシークレットに設定します。Copilot が Issue に自動アサインされるために必要です。

### 1. Personal Access Token（PAT）を作成

1. GitHub.com → プロフィールアイコン → **Settings** → **Developer settings**
2. **Personal access tokens** → **Fine-grained tokens** → **Generate new token**
3. 基本情報を入力:
   - **Token name**: 任意（例: `copilot-pat`）
   - **Expiration**: 90日以内を推奨
4. **Repository access**: 対象リポジトリを選択
5. **Permissions（Repository permissions）**:
   - `Issues`: Read and write
   - `Metadata`: Read-only（自動付与）
6. **Generate token** をクリックし、表示されたトークン文字列を**必ずこの時点でコピー**

> ⚠️ トークンはこの画面を離れると二度と表示されません。

### 2. リポジトリのシークレットに登録

1. リポジトリの **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** をクリック
3. Name: `COPILOT_PAT`
4. Value: 作成した PAT を貼り付け

MCP と PAT の設定が完了すると、Repository には以下のように secret が設定されます。

![RepositoryのSecret設定](../images/secret-setting.png)

### 3. Azure Static Web Apps デプロイ用 Secrets（SWA デプロイ時）

> [!NOTE]
> このステップは **Web App デプロイ** を実行する場合の確認です。

SWA デプロイは OIDC 認証（`azure/login@v2`）+ `shibayan/swa-deploy@v1` の `app-name` モードを使用するため、**`AZURE_STATIC_WEB_APPS_API_TOKEN` や `GITHUB_PAT` の設定は不要**です。

以下の 3 つの Secrets は Functions deploy でも使用するものと共通です。すでに設定済みであれば追加作業は不要です。

| Secret 名 | 説明 |
|-----------|------|
| `AZURE_CLIENT_ID` | OIDC サービスプリンシパルのクライアント ID |
| `AZURE_TENANT_ID` | Azure AD テナント ID |
| `AZURE_SUBSCRIPTION_ID` | Azure サブスクリプション ID |

#### スクリプト実行（PAT 不要）

```bash
# GITHUB_PAT は不要。Azure リソース作成のみ実行する。
bash infra/azure/create-azure-webui-resources.sh
```

スクリプトが Azure Static Web Apps リソースを作成します。CI/CD ワークフローが OIDC 経由でデプロイトークンを自動取得します。

---

## 認証・認可の用途一覧（Cloud / Local / Azure）

初回セットアップ時に使う主な認証情報と設定の役割を整理します。  
**`COPILOT_PAT`（Cloud の Copilot 自動アサイン用）と `GH_TOKEN`（HVE CLI Orchestrator の Issue/PR 作成用）は用途が異なります。**

| 認証情報 / 設定 | 主な使用場所 | 用途 |
|---|---|---|
| GitHub Copilot ライセンス | Cloud / Local | Copilot cloud agent / Copilot SDK の利用 |
| Repository の Copilot Cloud agent 有効化 | Cloud | GitHub Issues から Copilot agent を動かす |
| `COPILOT_PAT` | Cloud Orchestrator | `assign-copilot.sh` が Copilot を Issue にアサインするため |
| `GITHUB_TOKEN` | GitHub Actions | ワークフロー内でラベル、Issue、コメント等を操作する自動付与トークン |
| Actions Workflow permissions: Read and write | Cloud | `setup-labels.yml` などがラベル作成 API を呼ぶため |
| `gh auth login` | HVE CLI Orchestrator | GitHub CLI の認証状態を利用する基本認証 |
| `GH_TOKEN` | HVE CLI Orchestrator | `--create-issues` / `--create-pr` 等で Issue / PR を作成する場合に必要 |
| `AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID` | Azure deploy | OIDC で Azure にログインするため |
| MCP Servers 設定 | Cloud / Local | Azure Docs / Microsoft Learn / Work IQ 等の外部情報参照 |

### Cloud Orchestrator 側の認証前提（初回推奨）

- GitHub Copilot ライセンスが有効であること
- Repository の **Settings → Copilot → Cloud agent** で有効化されていること
- MCP Servers は **Settings → Copilot → Cloud agent → MCP Servers** で設定すること
- `COPILOT_PAT` は Copilot 自動アサインに利用（未設定時は既存スクリプト設計で警告してスキップされる場合あり）
- 初回セットアップでは `COPILOT_PAT` の設定を推奨（実運用では実質必須）
- Workflow permissions は **Read and write permissions** が必要
- `GITHUB_TOKEN` は GitHub Actions の自動付与トークン（`GH_TOKEN` / `COPILOT_PAT` とは別物）

### Static Web Apps / Azure 認証方針（正本）

- Azure Static Web Apps デプロイは **OIDC 認証を基本方針** とします
- 通常は `AZURE_STATIC_WEB_APPS_API_TOKEN` / `GITHUB_PAT` は不要です
- 必要な Secrets は `AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID` です
- 一部の Issue Template / reusable workflow 本文に旧トークン記述が残る場合がありますが、初期セットアップは本セクションの OIDC 方針を正本としてください（文言統一は後続 PR で対応予定）

---

## ワークフロー権限設定

> [!IMPORTANT]
> **Step.5（ラベル設定）より前に、この権限設定を完了してください。**
> `setup-labels.yml` ワークフローはラベル作成 API を呼び出すため、**Read and write permissions** でないとラベル作成が 403 エラーで失敗します。

リポジトリの **Settings → Actions → General → Workflow permissions** を **Read and write permissions** に設定してください。

---

## HVE Cloud Agent Orchestrator 初回セットアップ チェックリスト

HVE Cloud Agent Orchestrator（GitHub Actions + Issue Template）を初めて使う場合、以下のチェックリストで抜け漏れを確認してください。各項目はこのガイドの対応ステップで設定します。

| # | チェック項目 | 参照ステップ | 必須 / オプション |
|---|---|---|---|
| 1 | リポジトリを作成した（テンプレートから `Use this template` または Clone） | [Step.1](#step1-リポジトリの作成) | **必須** |
| 2 | GitHub Copilot Cloud agent を有効化した（Settings → Copilot → Cloud agent） | [Copilot 有効化](#copilot-有効化) | **必須** |
| 3 | MCP Server を設定した（Settings → Copilot → Cloud agent → MCP Servers） | [Step.3](#step3-mcp-server-設定) | **必須** |
| 4 | GitHub Copilot Skills を設定した（推奨） | [Step.3.1](#step31-github-copilot-skills-設定推奨) | 推奨 |
| 5 | `COPILOT_PAT`（Fine-grained, Issues Read/Write）をリポジトリ Secret に登録した | [Step.4](#step4-認証設定copilot_pat) | **必須**（未設定時はアサインがスキップされ警告） |
| 6 | Actions Workflow permissions を **Read and write permissions** に設定した | [ワークフロー権限設定](#ワークフロー権限設定) | **必須** |
| 7 | Azure OIDC Secrets（`AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID`）を登録した（Azure デプロイ時） | [Step.4 - Azure Secrets](#3-azure-static-web-apps-デプロイ用-secretsswa-デプロイ時) | Azure 利用時必須 |
| 8 | Self-hosted Runner を設定した（GitHub-hosted runner を使う場合はスキップ可） | [Step.4.5](#step45-self-hosted-runner-設定オプション) | オプション |
| 9 | Setup Labels workflow を Actions タブから**手動実行**した（初回必須） | [Step.5](#step5-ラベル設定) | **必須** |
| 10 | 必要なラベル（`auto-app-selection`, `setup-labels` 等）が作成されたことを確認した | [Step.5 - 実行後の確認](#実行後の確認手順) | **必須** |
| 11 | 初回疎通確認を実施した | [初回疎通確認](#初回疎通確認hve-cloud-agent-orchestrator) | 推奨 |
| 12 | HVE Cloud Agent Orchestrator の利用手順（web-ui-guide.md）へ進む | [web-ui-guide.md](./web-ui-guide.md) | — |

### （任意）Cloud setup preflight を実行する

初回セットアップの抜け漏れをローカルから確認したい場合は、以下を実行してください。

```bash
bash .github/scripts/preflight-cloud-setup.sh OWNER/REPO
```

Self-hosted runner の label も確認する場合:

```bash
bash .github/scripts/preflight-cloud-setup.sh OWNER/REPO --self-hosted-runner-label <runner-label>
```

- 実行タイミングは **Setup Labels 実行前 / 実行後のどちらでも可** です。
- `setup-labels` や `auto-app-selection` が未作成でも、初回セットアップ前なら正常な場合があります。`WARN` が出たら [Step.5. ラベル設定](#step5-ラベル設定) の手順で Setup Labels workflow を手動実行してください。
- API 権限不足で取得できない項目は、未設定と断定せず手動確認に回してください。

---

## Step.4.5. Self-hosted Runner 設定（オプション）

> [!NOTE]
> **このステップは省略可能です。** GitHub-hosted runner（`ubuntu-latest` 等）を使う場合はスキップして [Step.5. ラベル設定](#step5-ラベル設定) に進んでください。

組織のセキュリティ要件、閉域ネットワーク、固定 IP、専用ツール利用などの理由で、自前の実行環境でワークフローを動かしたい場合に設定します。**ラベル初期化（Step.5）や Orchestrator 実行前**に設定しておくことを推奨します。

**設定が必要なケース（例）:**

- 組織のネットワークポリシーで GitHub-hosted runner からのアクセスが制限されている
- ワークフロー内で固定 IP が必要（Azure Firewall の IP 制限等）
- Python や Azure CLI など特定ツールをイメージにプリインストールしておきたい

**設定手順:** [setup-self-hosted-runner.md](./setup-self-hosted-runner.md) を参照してください。

> [!IMPORTANT]
> **runner label の整合性に注意してください。** Issue Template や workflow ファイルで `runs-on:` に指定する runner label（例: `[self-hosted, linux, x64, aca]`）は、Self-hosted Runner 側に設定したラベルと**一致している必要があります**。不一致の場合、ジョブが `Waiting for a runner...` のまま進まなくなります。

---

## Step.5. ラベル設定

ワークフローのトリガーに使用するラベルを GitHub リポジトリに作成します。

> [!WARNING]
> **このステップは、他のワークフローを使い始める前に必ず完了してください。**
>
> ラベルが未設定の状態では、**すべての Issue テンプレート経由のワークフロー起動が動作しません**。これは `setup-labels` だけでなく、`auto-app-selection`・`auto-app-detail-design`・`knowledge-management` など**全ワークフロートリガー系ラベル**に影響します。
>
> GitHub の Issue Template の `labels:` フィールドは、リポジトリに**既に存在するラベルのみ**を Issue に自動付与します。ラベルが存在しない場合は Issue 作成時にラベルの付与がサイレントにスキップされ、**ラベル付与を前提とした対象ジョブや処理は実行されません（ジョブがスキップされます）**。

### 初回セットアップの全体フロー

```
新規リポジトリ作成
  → Step.4. COPILOT_PAT 設定
  → ワークフロー権限設定（Read and write permissions）
  → Step.5. Actions タブから Setup Labels を手動実行  ← ★ ここが最重要
  → ラベル作成完了
  → 以降は Issue テンプレートからワークフローを起動可能
```

### 推奨方法: Setup Labels ワークフローを実行する

> [!NOTE]
> リポジトリ作成後に **1度だけ** 実行する想定です。ラベル定義（`.github/labels.json`）が更新された場合は再実行できます（冪等設計のため、複数回実行しても安全です）。

#### 初回実行（Actions タブから手動実行）

##### なぜ手動実行が必要か（鶏と卵問題）
`setup-labels` ワークフロー自体は Issue の `opened` でも起動しますが、実際のラベル作成ジョブは `setup-labels` ラベルの有無を `if:` 条件で判定しています。新規リポジトリの初回は `setup-labels` ラベル自体がまだ存在しないため、Issue テンプレートから起動しても処理がスキップされます。このため、初回は Issue テンプレートからではなく、Actions タブから直接手動実行する必要があります。

> [!IMPORTANT]
> 手動実行の前提条件: **ワークフロー権限が「Read and write permissions」** になっていることを確認してください（上記「ワークフロー権限設定」セクション参照）。権限が「Read-only」のままでは、ラベル作成 API が 403 エラーで失敗します。

`setup-labels` ラベルがまだリポジトリに存在しない場合は、以下の手順で手動実行してください:

1. GitHub リポジトリの **Actions** タブを開く
2. 左サイドバーから **Setup Labels** ワークフローを選択
3. **Run workflow** ボタンをクリック
4. **Run workflow** で実行する

#### 実行後の確認手順

1. Actions タブでワークフローの実行結果が **✅ 成功**（緑チェック）になっていることを確認する
2. **Settings → Labels** を開き、`auto-app-selection`・`auto-app-detail-design`・`setup-labels` などのラベルが作成されていることを目視確認する
3. （オプション）Issues タブ → **New issue** → **Setup Labels: ラベル初期セットアップ** テンプレートを選択し、Issue を作成したときに `setup-labels` ラベルが自動付与されることを確認する（2回目以降の動作確認）

#### 2回目以降（Issue テンプレートから実行）

`setup-labels` ラベルが作成済みの場合は、Issue テンプレートから実行できます:

1. GitHub リポジトリの **Issues** タブを開く
2. **New issue** をクリック
3. **Setup Labels: ラベル初期セットアップ** テンプレートを選択
4. 確認チェックボックスにチェックを入れて Issue を作成する

### トラブルシューティング

<details>
<summary>Issue テンプレートから Issue を作成したが、ワークフローが起動しない</summary>

**原因:** ラベルがリポジトリに存在しないため、Issue 作成時にラベルが付与されませんでした。

**対処法:** Actions タブから **Setup Labels** ワークフローを手動実行してください（上記「初回実行」手順参照）。

</details>

<details>
<summary>Setup Labels ワークフローが失敗する（ラベル作成 API が 403 を返す）</summary>

**原因:** ワークフロー権限が「Read-only」になっています。

**対処法:** **Settings → Actions → General → Workflow permissions** を **「Read and write permissions」** に変更してから、再度 Actions タブから Setup Labels ワークフローを手動実行してください。

</details>

### 管理対象ラベル

Setup Labels ワークフローが作成・更新するラベル一覧です:

**ワークフロートリガー系（13 個）**

| ラベル名 | 色 | 用途 |
|---------|-----|------|
| `auto-app-selection` | `#0E8A16` | AAS ワークフロートリガー |
| `auto-app-detail-design` | `#0E8A16` | AAD ワークフロートリガー |
| `auto-app-detail-design-web` | `#1D76DB` | AAD-WEB ワークフロートリガー |
| `auto-ai-agent-design` | `#7B68EE` | AAG ワークフロートリガー |
| `auto-app-dev-microservice` | `#1D76DB` | ASDW ワークフロートリガー |
| `auto-app-dev-microservice-web` | `#0E8A16` | ASDW-WEB ワークフロートリガー |
| `auto-ai-agent-dev` | `#6A5ACD` | AAGD ワークフロートリガー |
| `auto-batch-design` | `#0E8A16` | ABD ワークフロートリガー |
| `auto-batch-dev` | `#0E8A16` | ABDV ワークフロートリガー |
| `auto-app-documentation` | `#0E8A16` | ADOC ワークフロートリガー |
| `knowledge-management` | `#0E8A16` | AKM ワークフロートリガー |
| `self-improve` | `#0E8A16` | 自己改善ループトリガー |
| `original-docs-review` | `#0E8A16` | AQOD ワークフロートリガー |

**PR 制御系（6 個）**

| ラベル名 | 色 | 用途 |
|---------|-----|------|
| `auto-context-review` | `#1D76DB` | Copilot 敵対的レビュートリガー |
| `auto-qa` | `#BFD4F2` | Copilot 質問票作成トリガー |
| `create-subissues` | `#E4E669` | Sub Issue 自動作成トリガー |
| `split-mode` | `#D93F0B` | 分割モード PR 識別 |
| `plan-only` | `#D93F0B` | plan.md のみの PR 識別 |
| `auto-approve-ready` | `#1D76DB` | PR 自動 Approve & Auto-merge トリガー |

**モデル選択系（15 個 = main 5 + review 5 + qa 5）**

| ラベル名 | 色 | 用途 |
|---------|-----|------|
| `model/Auto` | `#6f42c1` | Copilot cloud agent モデル指定: Auto（GitHub が最適モデルを動的選択。0.9x 計上、1x 超モデルは対象外） |
| `model/claude-opus-4.7` | `#6f42c1` | Copilot cloud agent モデル指定: claude-opus-4.7 |
| `model/claude-opus-4.6` | `#6f42c1` | Copilot cloud agent モデル指定: claude-opus-4.6 |
| `model/gpt-5.5` | `#6f42c1` | Copilot cloud agent モデル指定: gpt-5.5 |
| `model/gpt-5.4` | `#6f42c1` | Copilot cloud agent モデル指定: gpt-5.4 |
| `review-model/Auto` | `#6f42c1` | Copilot cloud agent レビュー用モデル指定: Auto |
| `review-model/claude-opus-4.7` | `#6f42c1` | Copilot cloud agent レビュー用モデル指定: claude-opus-4.7 |
| `review-model/claude-opus-4.6` | `#6f42c1` | Copilot cloud agent レビュー用モデル指定: claude-opus-4.6 |
| `review-model/gpt-5.5` | `#6f42c1` | Copilot cloud agent レビュー用モデル指定: gpt-5.5 |
| `review-model/gpt-5.4` | `#6f42c1` | Copilot cloud agent レビュー用モデル指定: gpt-5.4 |
| `qa-model/Auto` | `#6f42c1` | Copilot cloud agent QA 用モデル指定: Auto |
| `qa-model/claude-opus-4.7` | `#6f42c1` | Copilot cloud agent QA 用モデル指定: claude-opus-4.7 |
| `qa-model/claude-opus-4.6` | `#6f42c1` | Copilot cloud agent QA 用モデル指定: claude-opus-4.6 |
| `qa-model/gpt-5.5` | `#6f42c1` | Copilot cloud agent QA 用モデル指定: gpt-5.5 |
| `qa-model/gpt-5.4` | `#6f42c1` | Copilot cloud agent QA 用モデル指定: gpt-5.4 |

**セットアップ系（1 個）**

| ラベル名 | 色 | 用途 |
|---------|-----|------|
| `setup-labels` | `#C5DEF5` | Setup Labels ワークフロートリガー |

> [!IMPORTANT]
> **ステートラベル**（`aas:initialized`, `aas:ready`, `aas:running`, `aas:done`, `aas:blocked` など）は、各オーケストレーターワークフローが自動作成します。手動作成は不要です。
>
> `auto-app-documentation` / `knowledge-management` / `auto-approve-ready` は `.github/labels.json` の管理対象です。ラベル定義を更新した場合は Setup Labels ワークフローを再実行してください。

ラベルの詳細一覧は [workflow-reference.md](./workflow-reference.md#ワークフロートリガー系ラベル) を参照してください。

ラベル設定後の画面例:

![Label設定の例](../images/subissue-label.png)

設定後は PR のコメントで以下のように指示を出すと、Copilot cloud agent が Sub Issue を作成します。

![Label設定の後のPRのコメント](../images/subissue-label-IssueCreated.png)

### レガシー方式（過去互換）: 手動でラベルを作成する

> [!NOTE]
> 現在は Setup Labels ワークフローで自動管理されています。このセクションは過去バージョンとの互換運用や緊急時の手動作成が必要な場合のために残しています。

過去互換や緊急時に手動作成する場合は、以下を **Settings → Labels** から作成してください:

| ラベル名 | 色 | 用途 |
|---------|-----|------|
| `auto-app-documentation` | `#0E8A16` | ADOC ワークフロートリガー |
| `knowledge-management` | `#0E8A16` | AKM ワークフロートリガー |
| `auto-approve-ready` | `#1D76DB` | PR 自動 Approve & Auto-merge トリガー |

GitHub リポジトリの **Settings → Labels** から上記を手動作成してください。  
それ以外のラベルは Setup Labels ワークフロー（`.github/labels.json`）で管理されます。

---

## Copilot 有効化

リポジトリで GitHub Copilot cloud agent が有効になっていることを確認してください。

**Settings → Copilot → Cloud agent** から有効化できます。

---

## 初回疎通確認（HVE Cloud Agent Orchestrator）

Step.5 のラベル設定完了後、以下の確認を順に実施してください。すべてパスすれば HVE Cloud Agent Orchestrator が正常に動作しています。

### 1. Setup Labels ワークフローの確認

- [ ] Actions タブで `Setup Labels` ワークフローの最新実行が **✅ 成功**（緑チェック）になっている

### 2. 必要なラベルの存在確認

- [ ] **Settings → Labels** を開き、以下のラベルが存在する
  - `auto-app-selection`
  - `setup-labels`
  - `auto-app-detail-design-web`（その他のワークフロートリガー系ラベル）

### 3. Issue Template からのテスト起動

- [ ] **Issues → New issue** を開いて Issue Template の一覧が表示される
- [ ] `Setup Labels: ラベル初期セットアップ` テンプレートを選択すると、Issue 作成時に `setup-labels` ラベルが自動付与される（2 回目以降の確認）
- [ ] いずれかのワークフロー用テンプレート（例: `app-architecture-design.yml`）を選択すると、フォームが表示される

### 4. Dispatcher ワークフローの起動確認

- [ ] テスト Issue を作成後、Actions タブで `HVE Cloud Agent Orchestrator Dispatcher` ワークフローが起動している（数秒〜数十秒で表示されます）

### 5. Reusable Workflow の呼び出し確認

- [ ] Dispatcher が正常完了し、対応する reusable workflow（例: `AAS Orchestrator`）が起動している

### 6. Copilot アサイン確認

- [ ] Sub Issue に `@copilot` がアサインされている
- [ ] `COPILOT_PAT` 未設定の場合は、ワークフローログに警告メッセージが表示されてアサインがスキップされる（既存設計どおりの動作）

> トラブルが発生した場合は [troubleshooting.md](./troubleshooting.md) を参照してください。初期セットアップ中は特に [Setup Labels / ラベル初期化](./troubleshooting.md#2-setup-labels--ラベル初期化) と [Copilot 自動アサイン](./troubleshooting.md#3-copilot-自動アサイン) を優先して確認してください。

---

## knowledge/ ディレクトリについて

`knowledge/` フォルダーには業務要件ドキュメント（D01〜D21）が格納されます。詳細は [README.md](../README.md#knowledge-と-qa-と-original-docs-の関係) を参照してください。

`knowledge/` ファイルが存在すると、設計・開発の各 Custom Agent が業務要件・制約のコンテキストとして自動参照します。アプリケーション設計・開発ワークフローを開始する前に、`knowledge-management` ワークフローを実行しておくことを推奨します。

## 次のステップ

セットアップが完了したら、まず全体像を把握してから方式を選んでください。

- **全体像の把握**: まず [README.md](../README.md) で全体像と 3 つの使い方を把握してください
- **Custom Agent エコシステム図**: [agent-ecosystem-overview.svg](./images/agent-ecosystem-overview.svg)
- **方式1（個別 Issue + Custom Agent 手動実行）**: [web-ui-guide.md](./web-ui-guide.md#方式1-copilot-cloud-agent-手動実行)
- **方式2（ワークフローオーケストレーション Web）**: [web-ui-guide.md](./web-ui-guide.md#方式2-ワークフローオーケストレーションweb)
- **方式3（ローカル: HVE CLI Orchestrator）**: [hve-cli-orchestrator-guide.md](./hve-cli-orchestrator-guide.md)
- **中断と再開（Resume）**: [hve-cli-orchestrator-guide.md#中断と再開resume](./hve-cli-orchestrator-guide.md#中断と再開resume)
- **フェーズ別ガイド**: [README.md](../README.md#実行フェーズ別ガイド)
