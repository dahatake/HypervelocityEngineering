# アプリケーションのプロトタイプ開発 (GitHub Copilot Coding Agent / GitHub Copilot for Azure)


# はじめに

Copilot を使用してタスクに取り組むためのベスト プラクティス

https://docs.github.com/ja/copilot/using-github-copilot/coding-agent/best-practices-for-using-copilot-to-work-on-tasks


- プロダクション環境での利用には十二分に注意をしてください。Pull Requestをマージするかどうかは、**人**の判断ですので!

# 2つの利用方法

このリポジトリでは、ワークフローを実行するために **2つの方法** を提供しています。

## 方法1: GitHub Copilot Coding Agent（Web UI方式）

### 概要

GitHub.com 上で Issue を作成し、Copilot coding agent が Issue にアサインされて GitHub Actions 上で自動実行される方式です。

### 基本的な利用手順

1. GitHub.com でリポジトリを開く
2. **Issues** タブから新しい Issue を作成する
3. Issue にラベル（例: `auto-app-design`）を付与する
4. GitHub Actions が自動的に起動し、Copilot に Issue をアサインする
5. Copilot がタスクを実行し、Pull Request を作成する

> 詳細な利用手順（Custom Agent の選択方法、Issue への記述方法など）は [利用手順](#利用手順) セクションを参照してください。

### メリット

- Web UI のみで操作可能（ブラウザだけで完結）
- ローカル環境のセットアップ不要

### デメリット

- GitHub Actions の課金が発生する
- Copilot アサイン権限（COPILOT_PAT）が必要

---

## 方法2: Copilot SDK版（完全ローカル実行方式）

### 概要

リポジトリルートから `python -m hve orchestrate` を実行すると、**ローカル PC 上で Agent が直接実行**されます。Issue/PR の作成は不要で（オプション設定で作成可能）、GitHub Actions も使いません。

### メリット

- **GitHub Actions 不要** — クラウド課金が発生しない
- **COPILOT_PAT 不要** — `gh auth login` のみで認証完了
- **並列実行を制御可能** — 同時実行数を管理（デフォルト: 15）
- **MCP Server 対応** — JSON 設定ファイルで任意の MCP Server を組み込める
- **Custom Agents 対応** — ワークフロー定義で特定ステップに専用 Agent を割り当てられる
- **Issue/PR 作成はオプション** — デフォルトでは作成しない

### デメリット

- Copilot CLI のインストールが必要
- ローカル PC のリソース（CPU・メモリ）を消費する

> 詳細な環境構築・コマンド・チュートリアルは **[SDK ユーザーガイド](./SDK-Guide.md)** を参照してください。

---

## 比較表

| 項目 | Web UI方式 | SDK版（ローカル実行） |
|------|-----------|-------------------|
| Agent 実行場所 | GitHub Actions | ローカル PC |
| Issue 作成 | 必須 | オプション（デフォルト: しない） |
| Copilot アサイン | する | しない（ローカル直接実行） |
| 並列実行 | GitHub Actions 並列ジョブ | 同時実行数を制限（デフォルト: 15）※1 |
| MCP Server | GitHub 管理の MCP 設定 | 対応（`--mcp-config` で任意設定）※2 |
| Custom Agents | GitHub Issue 経由で選択 | SDK の API でステップごとに指定 |
| 必要な認証 | COPILOT_PAT | Copilot CLI 認証（`gh auth login`） |
| モデルデフォルト | GitHub 管理 | claude-opus-4.6 |
| 課金 | GitHub Actions 分 | Copilot ライセンスのみ |

> ※1 asyncio.Semaphore: Python の非同期処理で同時実行数を制限する仕組み。SDK 版で内部的に使用されます。
>
> ※2 Web UI 方式でも MCP Server はリポジトリ設定から利用可能です（[Step.3. MCP Server 設定](#step3-mcp-server-設定) 参照）。SDK 版ではローカルから任意の MCP Server を柔軟に追加接続できます。

# ツール

- GitHub Copilot Coding Agent

  GitHub Copilot の **Coding Agent**のIssueからCoding Agentに作業をしてもらう前提です。

  https://github.blog/news-insights/product-news/github-copilot-meet-the-new-coding-agent/


  - Firewallの設定
    - いくつかのAzureリソースにアクセスするために、Firewallの設定が必要です。GitHubのリポジトリーの [Settings] - [Copilot] - [Coding agent] - [Internet access] - [Custom allowlist] で、以下のドメインを追加してください。
      - https://management.azure.com
      - https://login.microsoftonline.com
      - https://aka.ms
      - https://app.aladdin.microsoft.com
      - 他にも必要なドメインがあれば、エラーメッセージを確認して追加してください。
  - 判断はお任せしますが。多様なMCP Serverを使うために、一時的に、Firewallの設定を[Enable Firewall]を`Off`にしても良いかもしれません。
  　　
- GitHub Spark
  Reactでの画面作成とGitHubのRepositryとの同期による、プレビューが秀逸です。リポジトリーにクローンすることで、リポジトリー側での作業結果のプレビューとしても利用できます。

  https://github.com/features/spark?locale=ja

- Visual Studio Code + GitHub Copilot Agent Mode

  **Visual Studio Code**の利用もおススメします。
  - Markdownのプレビュー機能を活用して、ドキュメントの確認や編集
  - Azure MCP Serverを利用した、各種Azure上のリソース一覧の文字列作成
  - GitHubリポジトリへ人が作成するファイルの追加
  - GitHub Copilotが作成したコードのテストや修正
  - GitHub Copilot Agentモードによるコーディング支援

  - Microsoft Azure のSDKを使う場合は、GitHub Copilot for Azure を使います。

    https://learn.microsoft.com/ja-jp/azure/developer/github-copilot-azure/introduction

- Copilot SDK版ワークフローオーケストレーション

  ローカル環境から Python スクリプトでワークフローを実行するツールです。

  [SDK ユーザーガイド](./SDK-Guide.md)



# Sample

**会員サービス**を題材にしたサンプルの要求定義や設計書などのサンプルです。

[サンプル](./samples/README.md)

# 準備

- GitHubのRepositoryの作成
- MCP Serverの設定
- GitHub CopilotにIssueを自動的にアサインする認証設定

## Step.1. GitHubのRepositoryの作成

GitHubのRepositoryを作成します。GitHub Sparkや、GitHub Copilot Coding Agentが作業をするためのリポジトリーです。

### Step.1.1. 自分のRepositoryへ、このRepositoryの内容をコピー

以下のいずれかの方法で、ファイルを取得してください:

**方法1: Git Clone でリポジトリ全体を取得**

```bash
git clone https://github.com/dahatake/HypervelocityEngineering-Japanese.git
```

**方法2: 特定のフォルダーのみダウンロード（推奨）**

GitHub の Web インターフェースから:
- 画面右上の「Download ZIP」または各ファイルを個別にダウンロード

## Step.2. 自分のリポジトリへのコピー

ダウンロードしたファイルを、あなたのプロジェクトのリポジトリに全てコピーします。

フォルダー構造は以下のようになります:

```
your-project/
├── .github/
│   ├── agents/
│   │   ├── Arch-Microservice-DomainAnalytics.agent.md
│   │   ├── Arch-Microservice-ServiceIdentify.agent.md
│   │   ├── Arch-Microservice-ServiceCatalog.agent.md
│   │   ├── Arch-Microservice-ServiceDetail.agent.md
│   │   ├── Arch-UI-List.agent.md
│   │   ├── Arch-UI-Detail.agent.md
│   │   └── ... (その他の Custom Agent ファイル)
│   └── copilot-instructions.md
├── README.md
└── ... (その他のプロジェクトファイル)
```

Copilot を使用してタスクに取り組むためのベスト プラクティス:

https://docs.github.com/ja/copilot/using-github-copilot/coding-agent/best-practices-for-using-copilot-to-work-on-tasks#adding-custom-instructions-to-your-repository

### Custom Agent ファイルの編集（オプション）

各 Custom Agent ファイルは、プロジェクトの要件に応じてカスタマイズしてください。

例えば、`Arch-Microservice-DomainAnalytics.agent.md` の中で、ユースケース ID やファイルパスを変更できます:

```markdown
## ユースケースID
- UC-xxx  ← あなたのユースケース ID に変更

## ユースケース
  - docs/usecase/{ユースケースID}/usecase-description.md  ← パスを変更
```

**編集する際の注意点:**
- ファイル先頭の YAML フロントマター（`---` で囲まれた部分）の `name` と `description` は Custom Agent の識別に使用されるため、わかりやすい名前に変更することをおすすめします
- `tools: ["*"]` は全てのツールへのアクセスを許可する設定です。必要に応じて制限できます
- プロンプトの内容は、プロジェクトの具体的な要件に合わせて調整してください


## Step.3. MCP Server 設定
GitHubのRepositoryに、GitHub Copilot Coding AgentがMCP Serverを利用できるように設定します。

以下の両方のBlog Postを参考にしてください。Microsoft Learnと、AzureのMCP Serverの両方を設定します。

- GitHub Copilot Coding agent に Azure MCP Server の設定をする:

  Microsoft 公式:

  https://learn.microsoft.com/ja-jp/azure/developer/azure-mcp-server/how-to/github-copilot-coding-agent

  私のBlog:

  https://qiita.com/dahatake/items/3230a92532c35fec7599

- GitHub Copilot Coding agent に Microsoft Learn Docs MCP Server の設定をする

  https://qiita.com/dahatake/items/4f6f0deb53333c0200ef

GitHub Copilot の Coding AgentのMCP Serverの設定文字列::

```text
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

## Step.3.1. GitHub Copilot Skills の設定（推奨）

Azure 関連の作業を効率化するため、**Azure Skills** のインストールを推奨します。Azure Skills は GitHub Copilot の Skills として動作し、Azure のリソース操作・設計・デプロイ・診断などを支援します。

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

インストール後、`.github/skills/` 配下に SKILL.md ファイルが配置され、GitHub Copilot Coding Agent が Azure 関連タスクで自動的に Skills を活用します（AGENTS.md §4.2 参照）。

### 自動同期（推奨）

このリポジトリには Azure Skills の定期同期ワークフロー（`.github/workflows/sync-azure-skills.yml`）が設定されています。

- **スケジュール**: 毎週月曜 9:00 UTC に自動実行
- **動作**: microsoft/skills の最新版と差分を検出し、変更がある場合は PR を自動作成
- **カスタムスキル保護**: `large-output-chunking`, `repo-onboarding-fast`, `task-dag-planning`, `work-artifacts-layout` は同期対象外

手動で即座に同期する場合は、GitHub Actions タブから `Sync Azure Skills` ワークフローを手動実行してください。

### 主な Skills

- Azure リソースの検索・一覧表示
- Azure デプロイの準備・実行・検証
- Azure 診断・コスト最適化
- Azure AI / Messaging / Storage 等の各種サービス操作
- Azure コンプライアンス・セキュリティ監査
- Azure RBAC ロール選定
- Azure AI Gateway / Foundry / Kusto 等

## Step.4. GitHub CopilotにIssueを自動的にアサインする認証設定

PAT（Personal Access Token）をシークレットに設定し使用します。

1. **Personal Access Token (PAT) を作成**

 - GitHub Settings → Developer settings → Personal access tokens (fine-grained)
   - 権限: `metadata: read`, `issues: read/write`（または classic PAT の場合は `repo` 相当の権限）
   - シークレット名: `COPILOT_PAT`
   - **トークン文字列**が作成されるので、保存する。


2. **リポジトリのシークレットに登録**
   - **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `COPILOT_PAT`
   - Value: 作成した PAT を貼り付け


MCPとPATの設定が完了すると、Repositoryには以下の様にsecretが設定されます。

![RepositoryのSecret設定](/images/secret-setting.png)


## Step.5. labelの設定

以下のlabelをGitHubのRepositoryに作成してください。

## ワークフロートリガー系ラベル

| ラベル名 | 役割 |
|---------|------|
| `auto-app-selection` | **アプリケーション選定ワークフロー（AAS）の起動トリガー**。Issue にこのラベルが付与されると、AAS Orchestrator ワークフローが起動し、Step.1〜2 の Sub Issue を自動生成して Copilot にアサインする。対応 Issue Template: `.github/ISSUE_TEMPLATE/auto-app-selection.yml` |
| `auto-app-design` | **アプリケーション設計ワークフロー（AAD）の起動トリガー**。Issue にこのラベルが付与されると、AAD Orchestrator ワークフローが起動し、Step.1〜7.3 の Sub Issue を自動生成して Copilot にアサインする。対応 Issue Template: `.github/ISSUE_TEMPLATE/auto-app-design.yml` |
| `auto-software-design` | **設計ワークフローの起動トリガー**。Issue にこのラベルが付与されると、ASD Orchestrator ワークフローが起動し、Step.1〜7.3 の Sub Issue を自動生成して Copilot にアサインする |
| `auto-app-dev-microservice` | **マイクロサービス開発ワークフローの起動トリガー**。Issue にこのラベルが付与されると、ASDW Orchestrator が起動し、Step.1〜4 の Sub Issue を自動生成して Copilot にアサインする。対応 Issue Template: `.github/ISSUE_TEMPLATE/auto-app-dev-microservice.yml` |
| `auto-batch-design` | **バッチ設計ワークフロー（ABD）の起動トリガー**。Issue にこのラベルが付与されると、ABD Orchestrator ワークフローが起動し、Step.1.1〜6.3 の Sub Issue を自動生成して Copilot にアサインする。対応 Issue Template: `.github/ISSUE_TEMPLATE/auto-batch-design.yml` |
| `auto-iot-design` | **IoT 設計ワークフロー（AID）の起動トリガー**。Issue にこのラベルが付与されると、AID Orchestrator ワークフローが起動し、Step.1〜7 の Sub Issue を自動生成して Copilot にアサインする。対応 Issue Template: `.github/ISSUE_TEMPLATE/auto-iot-design.yml` |
| `auto-batch-dev` | **バッチ実装ワークフロー（ABDV）の起動トリガー**。Issue にこのラベルが付与されると、ABDV Orchestrator ワークフローが起動し、Step.1〜4 の Sub Issue を自動生成して Copilot にアサインする。対応 Issue Template: `.github/ISSUE_TEMPLATE/auto-batch-dev.yml` |
| `create-subissues` | **Sub Issue 自動作成のトリガー**。人間が PR にこのラベルを手動付与すると、PR 内の `work/**/subissues.md` をパースして Sub Issue を GitHub 上に自動作成する。費用や妥当性を人間が判断するため、意図的に手動操作を要求する設計 |
| `auto-context-review` | **Copilot セルフレビューのトリガー**。PR にこのラベルが付いた状態で PR が ready（非 draft）になると、Copilot にセルフレビュー指示コメントを自動投稿する。親 Issue にこのラベルがある場合、子 Sub Issue にも自動伝播される |
| `auto-qa` | **Copilot 質問票作成のトリガー**。PR にこのラベルが付いた状態で PR が ready（非 draft）になると、Copilot に選択式の質問票作成指示コメントを自動投稿する。タスクに不明瞭な点がある場合、質問事項を15～100個リストアップし、デフォルト回答案と理由を付けた選択式質問票を作成する。親 Issue にこのラベルがある場合、子 Sub Issue にも自動伝播される |

> [!IMPORTANT]
> GitHub の Issue Template の `labels:` フィールドは、**リポジトリに既に存在するラベルのみ**を Issue に自動付与します。リポジトリにラベルが存在しない場合、Issue 作成時にラベルの自動付与はサイレントにスキップされます。このリポジトリの Orchestrator は `on: issues` で起動しますが、ゲート条件により即座にスキップされ Sub Issue は生成されません。上記のラベルは必ず事前に作成してください。

  ![Label設定の例](/images/subissue-label.png)

  設定後は、PRのコメントで以下の様に指示を出すと、Coding Agentがsub Issueを作成します。

  ![Label設定の後のPRのコメント](/images/subissue-label-IssueCreated.png)

# 利用手順  

## Issue 作成時に Custom Agent を選択

1. **GitHub リポジトリで Issue を作成**
   - リポジトリの「Issues」タブから「New issue」をクリック

2. **Copilot にアサイン**
   - Issue の右側サイドバーで「Assignees」から `@copilot` を選択
   - または、Issue のコメント欄で `@copilot` をメンションして作業を依頼

3. **Custom Agent を選択（重要）**
   - Issue 作成時または Copilot へのアサイン時に、右側サイドバーに「Copilot」セクションが表示されます
   - 「Select agent」または「エージェントを選択」ドロップダウンから、使用したい Custom Agent を選択
   - 例: 「Architecture-Design-Step1-1-ドメイン分析」を選択

4. **タスクの詳細を Issue に記述**
   - Custom Agent が適切に動作するために、タスクの詳細、要件、参照すべきファイルパス、ユースケースID、Azureのリソースグループ名などを明確に記述してください
   - 例:
     ```markdown
     ## タスク
     要求定義ドキュメント（docs/requirements.md）を基に、ドメインモデリングを実施してください。
     
     ## 参照ファイル
     - docs/requirements.md
     - docs/usecase/UC-001/usecase-description.md
     ```

5. **Copilot が作業を実行**
   - 選択した Custom Agent が、専門知識を活用してタスクを実行します
   - 進捗状況は Pull Request として確認できます

### 利用可能な Custom Agent 一覧

このリポジトリには以下のような Custom Agent が用意されています:

#### ビジネスドキュメント関連
- **PM-UseCaseDetail**: ユースケースの詳細定義書を作成

#### アーキテクチャ設計関連
- **Arch-Microservice-DomainAnalytics**: DDDの観点でドメインモデリングを実施
- **Arch-Microservice-ServiceIdentify**: マイクロサービス候補をリストアップ
- **Arch-DataModeling**: データモデル設計
- **Arch-Microservice-ServiceDetail**: 各サービスの詳細仕様作成
- **Arch-UI-List**: 画面一覧と画面遷移図の作成
- **Arch-UI-Detail**: 全画面の詳細定義書作成
- **Arch-Microservice-ServiceCatalog**: 画面・機能・API・データのマッピング表作成

#### 実装関連（Azure Web App）
- **Dev-Microservice-Azure-DataDesign**: Polyglot Persistenceアーキテクチャに基づくデータストア選定
- **Dev-Microservice-Azure-DataDeploy**: Azure CLIスクリプトでデータストア作成とサンプルデータ登録
- **Dev-Microservice-Azure-ComputeDesign**: 各マイクロサービスに最適なAzureホスティング環境の選定
- **Dev-Microservice-Azure-AddServiceDesign**: 追加で必要なAzureサービスの選定
- **Dev-Microservice-Azure-AddServiceDeploy**: Azure CLIスクリプトで追加サービスを作成
- **Dev-Microservice-Azure-ServiceCoding-AzureFunctions**: サービスのコード実装と単体テスト作成
- **Dev-Microservice-Azure-UICoding**: WebアプリケーションのUIコード実装

#### レビュー
- **QA-AzureDependencyReview**: Azureリソースの依存関係とコスト最適化のレビュー
- **QA-AzureArchitectureReview**: アーキテクチャとセキュリティのレビュー

### ヒント

- **適切な Custom Agent を選択**: タスクの内容に応じて、最も適した Custom Agent を選択することで、より高品質な結果が得られます
- **段階的に進める**: 大きなプロジェクトは、複数の Custom Agent を順番に使用して段階的に進めることをおすすめします
- **カスタマイズ**: Custom Agent ファイルはテンプレートです。プロジェクトの要件に応じて自由に編集・追加してください
- **フィードバック**: Custom Agent の実行結果を確認し、必要に応じて Issue のコメントで追加指示を出すことができます


# 実行

> [!IMPORTANT]
> GitHub Copilot Coding Agentで作業をする際は、それぞれのAgentのアクションが起動するまでや、その実行結果がWeb画面に反映されるまでに遅延があります。画面の更新を待ってから、あるいはWebブラウザーの画面リフレッシュを行ってから、次のアクションを実行するようにしてください。

## Step.1. 要求定義

→ [01-Business-Requirement.md](./01-Business-Requirement.md)

## Step.2. アプリケーション選定

→ [02-App-Selection.md](./02-App-Selection.md)

## Step.3. アプリケーション設計

- マイクロサービス: [03-App-Design-Microservice-Azure.md](./03-App-Design-Microservice-Azure.md)
- バッチ: [04-App-Design-Batch.md](./04-App-Design-Batch.md)
- AI Agent (Simple): [07-AIAgent-Simple.md](./07-AIAgent-Simple.md)
- AI Agent: [08-AIAgent.md](./08-AIAgent.md)

## Step.4. 実装・デプロイ

- Web: [05-App-Dev-Microservice-Azure.md](./05-App-Dev-Microservice-Azure.md)
- バッチ: [06-App-Dev-Batch-Azure.md](./06-App-Dev-Batch-Azure.md)

---

# 共通セットアップ手順

## ワークフロー権限設定

- リポジトリの Settings → Actions → General → "Workflow permissions" を **Read and write permissions** に設定

## ラベルの自動作成

- Bootstrap ワークフローが初回実行時に自動作成します
- 詳細ラベル一覧は [Step.5. labelの設定](#step5-labelの設定) を参照

## Copilot の有効化

- リポジトリで GitHub Copilot coding agent が有効になっていることを確認してください

## COPILOT_PAT シークレットの設定

PAT（Personal Access Token）をシークレットに設定し使用します。

1. **Personal Access Token (PAT) を作成**
   - GitHub Settings → Developer settings → Personal access tokens (fine-grained)
   - 権限: `metadata: read`, `issues: read/write`（または classic PAT の場合は `repo` 相当の権限）
   - シークレット名: `COPILOT_PAT`
   - **トークン文字列**が作成されるので、保存する

2. **リポジトリのシークレットに登録**
   - Settings → Secrets and variables → Actions → New repository secret
   - Name: `COPILOT_PAT`
   - Value: 作成した PAT を貼り付け

MCPとPATの設定が完了すると、Repositoryには以下の様にsecretが設定されます。

![RepositoryのSecret設定](/images/secret-setting.png)

---

# 共通トラブルシューティング

## Bootstrap ワークフローが起動しない

- 対応するトリガーラベルが正しく付与されているか確認
- Actions タブでワークフローが有効になっているか確認
- リポジトリの Workflow permissions が "Read and write" になっているか確認

## Sub-issues API が失敗する

- Sub-issues API は GitHub の一部プランでのみ利用可能です
- 失敗した場合でも、親 Issue にチェックリストコメントが自動投稿されます（フォールバック）

## Copilot が assign されない

- Actions ログを確認してください
- Copilot が利用可能なプランであることを確認してください
- `COPILOT_PAT` シークレットが設定されているか確認してください
- 手動アサインする場合は、Issue 右サイドバーの「Assignees」から `copilot-swe-agent` を選択

## ワークフローがエラーで終了する

- Actions タブで失敗したジョブのログを確認してください
- `GITHUB_TOKEN` の権限が `issues: write` になっているか確認してください

## Coding Agentのタスクの実行エラーの対応策

> [!IMPORTANT]
> この状況になったら、即座にジョブを停止させてください。GitHub Actionsの課金に影響が考えられます。

Coding AgentのGitHub Actionsでのタスクが失敗することがあります。
Pull Requestの`Session`の中で、`Run Back command`が繰り返されて、何も処理が行われていません。

```text
@copilot ジョブの途中でコマンド文字列を生成できずに、ジョブを実行しようとして{エラーメッセージ}が表示されています。原因を究明して、対応策を検討して、問題を修正してください。
対応策が、うまくいかない場合は、`段階的アプローチ - 各セクションを個別のコミットで追加`を試してみてください。

### エラーメッセージ
Run Bash command
$ undefined
No command provided. Please supply a valid command to execute.
```

---

> 詳細な Azure データストア情報・Tips は [05-App-Dev-Microservice-Azure.md](./05-App-Dev-Microservice-Azure.md) を参照してください。
