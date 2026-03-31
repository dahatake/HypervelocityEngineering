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
- [Step.5. ラベル設定](#step5-ラベル設定)
- [ワークフロー権限設定](#ワークフロー権限設定)
- [Copilot 有効化](#copilot-有効化)

---

## 前提条件

| ツール | 必須 / オプション | 用途 |
|--------|-----------------|------|
| GitHub アカウント | **必須** | リポジトリ操作・Copilot 利用 |
| GitHub Copilot ライセンス | **必須** | Copilot Coding Agent 利用 |
| Git | **必須** | リポジトリのクローン |
| Web ブラウザ | **必須** | GitHub.com の操作（Web UI 方式） |
| Python 3.9+ | GitHub Copilot CLI SDK 版のみ | GitHub Copilot CLI SDK 版ワークフロー実行 |
| GitHub Copilot CLI | GitHub Copilot CLI SDK 版のみ | GitHub Copilot CLI SDK 版ワークフロー実行 |
| Node.js（npm/npx） | オプション | MCP Server（filesystem 等）使用時 |

---

## Step.1. リポジトリの作成

GitHub リポジトリを作成します。GitHub Copilot Coding Agent が作業をするためのリポジトリです。

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
├── AGENTS.md
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

GitHub リポジトリに GitHub Copilot Coding Agent が MCP Server を利用できるように設定します。

GitHub リポジトリの **Settings → Copilot → Coding agent → MCP Servers** で以下の設定を追加してください。

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

> SDK 版の MCP Server 設定については [SDK ユーザーガイド 付録A](./SDK-Guide.md#付録a-mcp-server-設定ガイド) を参照してください。

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

インストール後、`.github/skills/` 配下に SKILL.md ファイルが配置され、GitHub Copilot Coding Agent が Azure 関連タスクで自動的に Skills を活用します（AGENTS.md §4.2 参照）。

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

---

## Step.5. ラベル設定

ワークフローのトリガーに使用するラベルを GitHub リポジトリに作成します。

ラベルの詳細一覧は [workflow-reference.md](./workflow-reference.md#ワークフロートリガー系ラベル) を参照してください。

> [!IMPORTANT]
> GitHub の Issue Template の `labels:` フィールドは、**リポジトリに既に存在するラベルのみ**を Issue に自動付与します。ラベルが存在しない場合、Issue 作成時にラベルの自動付与はサイレントにスキップされます。上記のラベルは必ず事前に作成してください。

ラベル設定後の画面例:

![Label設定の例](../images/subissue-label.png)

設定後は PR のコメントで以下のように指示を出すと、Coding Agent が Sub Issue を作成します。

![Label設定の後のPRのコメント](../images/subissue-label-IssueCreated.png)

---

## ワークフロー権限設定

リポジトリの **Settings → Actions → General → Workflow permissions** を **Read and write permissions** に設定してください。

---

## Copilot 有効化

リポジトリで GitHub Copilot Coding Agent が有効になっていることを確認してください。

**Settings → Copilot → Coding agent** から有効化できます。

---

## 次のステップ

セットアップが完了したら、いずれかの方法でワークフローを開始してください。

- **Web UI 方式**: [web-ui-guide.md](./web-ui-guide.md)
- **GitHub Copilot CLI SDK 版（ローカル実行）**: [SDK-Guide.md](./SDK-Guide.md)
- **フェーズ別ガイド**: [README](../README.md)
