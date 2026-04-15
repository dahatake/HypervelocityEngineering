# はじめかた（初期セットアップ）

← [README](../README.md)

---

## 目次

- [前提条件](#前提条件)
- [Step.1. リポジトリの作成](#step1-リポジトリの作成)
- [Step.2. ファイルのコピー](#step2-ファイルのコピー)
- [Step.3. MCP Server 設定](#step3-mcp-server-設定)
- [Step.3.1. GitHub Copilot Skills 設定](#step31-github-copilot-skills-設定推奨)
- [Step.4. 認証設定（COPILOT_PAT）](#step4-認証設定copilot_pat)
- [ワークフロー権限設定](#ワークフロー権限設定)
- [Step.5. ラベル設定](#step5-ラベル設定)
- [Copilot 有効化](#copilot-有効化)

---

## 前提条件

| ツール | 必須 / オプション | 用途 |
|--------|-----------------|------|
| GitHub アカウント | **必須** | リポジトリ操作・Copilot 利用 |
| GitHub Copilot ライセンス | **必須** | Copilot cloud agent 利用 |
| Git | **必須** | リポジトリのクローン |
| Web ブラウザ | **必須** | GitHub.com の操作（Web UI 方式） |
| Python 3.9+ | GitHub Copilot CLI SDK 版のみ | GitHub Copilot CLI SDK 版ワークフロー実行 |
| GitHub Copilot CLI | GitHub Copilot CLI SDK 版のみ | GitHub Copilot CLI SDK 版ワークフロー実行 |
| Node.js（npm/npx） | オプション | MCP Server（filesystem 等）使用時 |

---

## Step.1. リポジトリの作成

GitHub リポジトリを作成します。GitHub Copilot cloud agent が作業をするためのリポジトリです。

### Step.1.1. テンプレートリポジトリを使う（推奨）

本リポジトリ（`dahatake/HypervelocityEngineering-Japanese`）はテンプレートリポジトリです。GitHub の「Use this template」ボタンから自分のリポジトリを作成できます。

1. [dahatake/HypervelocityEngineering-Japanese](https://github.com/dahatake/HypervelocityEngineering-Japanese) を開く
2. 右上の **「Use this template」** ボタンをクリック
3. **「Create a new repository」** を選択
4. リポジトリ名・可視性を設定して作成

### Step.1.2. Git Clone で取得する場合

```bash
git clone https://github.com/dahatake/HypervelocityEngineering-Japanese.git
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

> SDK 版の MCP Server 設定については [SDK ユーザーガイド 付録A](./sdk-guide.md#付録a-mcp-server-設定ガイド) を参照してください。

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
> このステップは **Step.3.2（Web App デプロイ）** を実行する場合の確認です。

SWA デプロイは OIDC 認証（`azure/login@v2`）+ `shibayan/swa-deploy@v1` の `app-name` モードを使用するため、**`AZURE_STATIC_WEB_APPS_API_TOKEN` や `GITHUB_PAT` の設定は不要**です。

以下の 3 つの Secrets は Functions deploy（Step.2.8）でも使用するものと共通です。すでに設定済みであれば追加作業は不要です。

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

## ワークフロー権限設定

> [!IMPORTANT]
> **Step.5（ラベル設定）より前に、この権限設定を完了してください。**
> `setup-labels.yml` ワークフローはラベル作成 API を呼び出すため、**Read and write permissions** でないとラベル作成が 403 エラーで失敗します。

リポジトリの **Settings → Actions → General → Workflow permissions** を **Read and write permissions** に設定してください。

---

## Step.5. ラベル設定

ワークフローのトリガーに使用するラベルを GitHub リポジトリに作成します。

> [!WARNING]
> **このステップは、他のワークフローを使い始める前に必ず完了してください。**
>
> ラベルが未設定の状態では、**すべての Issue テンプレート経由のワークフロー起動が動作しません**。これは `setup-labels` だけでなく、`auto-app-selection`・`auto-app-design`・`qa-knowledge-management` など**全ワークフロートリガー系ラベル**に影響します。
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
2. **Settings → Labels** を開き、`auto-app-selection`・`auto-app-design`・`setup-labels` などのラベルが作成されていることを目視確認する
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

**ワークフロートリガー系（8 個）**

| ラベル名 | 色 | 用途 |
|---------|-----|------|
| `auto-app-selection` | `#0E8A16` | AAS ワークフロートリガー |
| `auto-app-design` | `#0E8A16` | AAD ワークフロートリガー |
| `auto-app-dev-microservice` | `#0E8A16` | ASDW ワークフロートリガー |
| `auto-batch-design` | `#0E8A16` | ABD ワークフロートリガー |
| `auto-batch-dev` | `#0E8A16` | ABDV ワークフロートリガー |
| `qa-knowledge-management` | `#0E8A16` | AQKM ワークフロートリガー |
| `self-improve` | `#0E8A16` | 自己改善ループトリガー |

**PR 制御系（5 個）**

| ラベル名 | 色 | 用途 |
|---------|-----|------|
| `auto-context-review` | `#1D76DB` | Copilot 敵対的レビュートリガー |
| `auto-qa` | `#BFD4F2` | Copilot 質問票作成トリガー |
| `create-subissues` | `#E4E669` | Sub Issue 自動作成トリガー |
| `split-mode` | `#D93F0B` | 分割モード PR 識別 |
| `plan-only` | `#D93F0B` | plan.md のみの PR 識別 |

**セットアップ系（1 個）**

| ラベル名 | 色 | 用途 |
|---------|-----|------|
| `setup-labels` | `#C5DEF5` | Setup Labels ワークフロートリガー |

> [!IMPORTANT]
> **ステートラベル**（`aas:initialized`, `aas:ready`, `aas:running`, `aas:done`, `aas:blocked` など）は、各オーケストレーターワークフローが自動作成します。手動作成は不要です。

ラベルの詳細一覧は [workflow-reference.md](./workflow-reference.md#ワークフロートリガー系ラベル) を参照してください。

ラベル設定後の画面例:

![Label設定の例](../images/subissue-label.png)

設定後は PR のコメントで以下のように指示を出すと、Copilot cloud agent が Sub Issue を作成します。

![Label設定の後のPRのコメント](../images/subissue-label-IssueCreated.png)

### レガシー方式: 手動でラベルを作成する

Setup Labels ワークフローを使わず、手動でラベルを作成することもできます:

| ラベル名 | 色 | 用途 |
|---------|-----|------|
| `auto-app-selection` | `#0E8A16` | AAS ワークフロートリガー |
| `auto-app-design` | `#0E8A16` | AAD ワークフロートリガー |
| `auto-app-dev-microservice` | `#0E8A16` | ASDW ワークフロートリガー |
| `auto-batch-design` | `#0E8A16` | ABD ワークフロートリガー |
| `auto-batch-dev` | `#0E8A16` | ABDV ワークフロートリガー |
| `qa-knowledge-management` | `#0E8A16` | AQKM ワークフロートリガー |
| `self-improve` | `#0E8A16` | 自己改善ループトリガー |
| `auto-context-review` | `#1D76DB` | Copilot 敵対的レビュートリガー |
| `auto-qa` | `#BFD4F2` | Copilot 質問票作成トリガー |
| `create-subissues` | `#E4E669` | Sub Issue 自動作成トリガー |
| `split-mode` | `#D93F0B` | 分割モード PR 識別 |
| `plan-only` | `#D93F0B` | plan.md のみの PR 識別 |
| `setup-labels` | `#C5DEF5` | Setup Labels ワークフロートリガー |

GitHub リポジトリの **Settings → Labels** からこれらのラベルを手動作成してください。

---

## Copilot 有効化

リポジトリで GitHub Copilot cloud agent が有効になっていることを確認してください。

**Settings → Copilot → Cloud agent** から有効化できます。

---


## knowledge/ ディレクトリについて

`knowledge/` フォルダーには業務要件ドキュメント（D01〜D21）が格納されます。これらは `qa-knowledge-management` ワークフロー（[09-qa-knowledge-management.md](./09-qa-knowledge-management.md) 参照）によって生成されます。ただし、**生成されるのは `qa/` の質問データに QA マッピングが存在する D クラスのみ**です（マッピングがない D クラスのファイルは生成されません）。

| ドキュメント（生成されたもののみ存在） | 内容 |
|--------------------------------------|------|
| `knowledge/D01-事業意図-成功条件定義書.md` | 経営課題・KPI・成功条件・ROI仮説 |
| `knowledge/D02-スコープ-対象境界定義書.md` | スコープ・対象境界 |
| `knowledge/D04-業務プロセス仕様書.md` | 業務プロセス |
| `knowledge/D05-ユースケース-シナリオカタログ.md` | ユースケース・シナリオ |
| `knowledge/D06-業務ルール-判定表仕様書.md` | 業務ルール・判定表 |
| `knowledge/D07-用語集-ドメインモデル定義書.md` | 用語・ドメインモデル |
| `knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md` | データモデル・SoR/SoT |
| `knowledge/D09-システムコンテキスト-責任境界-再利用方針書.md` | システムコンテキスト・責任境界 |
| `knowledge/D10-API-Event-File-連携契約パック.md` | API/イベント/ファイル連携契約 |
| `knowledge/D11-画面-UX-操作意味仕様書.md` | 画面UX・操作仕様 |
| `knowledge/D12-権限-認可-職務分掌設計書.md` | 権限・認可・職務分掌 |
| `knowledge/D13-セキュリティ-プライバシー-監査-法規マトリクス.md` | セキュリティ・プライバシー・監査 |
| `knowledge/D14-国際化-地域差分仕様書.md` | 国際化・地域差分 |
| `knowledge/D15-非機能-運用-監視-DR-仕様書.md` | 非機能・運用・監視・DR |
| `knowledge/D16-移行-導入-ロールアウト計画書.md` | 移行・導入計画 |
| `knowledge/D17-品質保証-UAT-受入パッケージ.md` | 品質保証・UAT |
| `knowledge/D18-Prompt-ガバナンス-入力統制パック.md` | Promptガバナンス |
| `knowledge/D19-ソフトウェアアーキテクチャ-ADR-パック.md` | ソフトウェアアーキテクチャ・ADR |
| `knowledge/D20-セキュア設計-実装ガードレール.md` | セキュア設計・実装ガードレール |
| `knowledge/D21-CI-CD-ビルド-リリース-供給網管理仕様書.md` | CI/CD・ビルド・リリース |

`knowledge/` ファイルが存在すると、設計・開発の各 Custom Agent が業務要件・制約のコンテキストとして自動参照します。アプリケーション設計・開発ワークフローを開始する前に、`qa-knowledge-management` ワークフローを実行しておくことを推奨します。

## 次のステップ

セットアップが完了したら、まず全体像を把握してから方式を選んでください。

- **全体像の把握**: まず [overview.md](./overview.md) で全体像と 3 つの使い方を把握してください
- **方式1（個別 Issue + Custom Agent 手動実行）**: [web-ui-guide.md](./web-ui-guide.md#方式1-copilot-cloud-agent-手動実行)
- **方式2（ワークフローオーケストレーション Web）**: [web-ui-guide.md](./web-ui-guide.md#方式2-ワークフローオーケストレーションweb)
- **方式3（ローカル: GitHub Copilot CLI SDK 版）**: [sdk-guide.md](./sdk-guide.md)
- **フェーズ別ガイド**: [README](../README.md)
