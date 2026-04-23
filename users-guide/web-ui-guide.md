# Web UI 方式ガイド

← [README](../README.md)

---

## 目次

- [概要](#概要)
- [Firewall 設定](#firewall-設定)
- [利用手順](#利用手順)
  - [方式1: Copilot cloud agent 手動実行](#方式1-copilot-cloud-agent-手動実行)
  - [方式2: ワークフローオーケストレーション（Web）](#方式2-ワークフローオーケストレーションweb)
- [利用可能な Custom Agent 一覧](#利用可能な-custom-agent-一覧)
- [ヒント](#ヒント)

---

## 概要

**Web UI 方式**には、2 つの利用パターンがあります。

- **方式1: Copilot cloud agent 手動実行** — GitHub.com 上で Issue を個別に作成し、Custom Agent を選択して Copilot をアサインする最小単位の使い方
- **方式2: ワークフローオーケストレーション（Web）** — Issue Template から親 Issue を作成すると、Bootstrap Workflow が Sub Issue を自動生成し、Copilot が依存関係順に自動実行するフル自動の使い方

> [!NOTE]
> 全体像と 3 つの使い方の比較は [overview.md](./overview.md) を参照してください。

### 基本フロー（方式2）

```
Issue 作成 → GitHub Actions 起動 → Sub Issue 一括生成
  → Copilot が各 Sub Issue に自動アサイン → PR 作成 → マージ → 次 Step 自動起動
```

### メリット

- Web ブラウザのみで操作可能（ローカル環境のセットアップ不要）
- GitHub Actions の自動化による一貫した実行

### デメリット

- GitHub Actions の課金が発生する
- `COPILOT_PAT` シークレットの設定が必要

> **GitHub Copilot CLI SDK 版（ローカル実行）** との比較は [overview.md](./overview.md#方式比較表) を参照してください。

---

## Firewall 設定

Azure リソースにアクセスする場合は、Firewall の設定が必要です。

リポジトリの **Settings → Copilot → Cloud agent → Internet access → Custom allowlist** で、以下のドメインを追加してください。

| ドメイン | 用途 |
|---------|------|
| `https://management.azure.com` | Azure Resource Manager API |
| `https://login.microsoftonline.com` | Azure 認証 |
| `https://aka.ms` | Microsoft 短縮 URL |
| `https://app.aladdin.microsoft.com` | Azure 関連サービス |

> **ヒント**: 多様な MCP Server を使うために、**Enable Firewall** を `Off` にする選択肢もあります。必要なドメインが不明な場合は、エラーメッセージを確認して追加してください。

---

## 利用手順

### 前提条件

> [!IMPORTANT]
> 方式2（ワークフローオーケストレーション）で Issue テンプレートからワークフローを起動するには、**ラベルの初期セットアップが完了している必要があります**。
> ラベルが未設定の状態では、Issue テンプレートから Issue を作成してもトリガーラベルが付与されず、ワークフローは起動しません。
>
> 初回セットアップがまだの場合は、先に [getting-started.md の Step.5](./getting-started.md#step5-ラベル設定) を完了してください。

---

### 方式1: Copilot cloud agent 手動実行

1 つの Issue に 1 つの Custom Agent を割り当て、Copilot に個別のタスクを実行させる最もシンプルな使い方です。

#### Step.1. Issue を作成する

1. リポジトリの **Issues** タブを開く
2. **New issue** をクリック
3. Issue のタイトルとタスク内容を記述する（テンプレートを使わずに Blank Issue でも可）

#### Step.2. Custom Agent を選択する

Issue 作成時または `@copilot` へのアサイン時に、右側サイドバーの **「Copilot」** セクションで **「Select agent」** から使用したい Custom Agent を選択します。

![Custom Agent の選択](../images/assign-githubcopilot-customagent.jpg)

> **手動アサインの場合**: Issue 右サイドバーの「Assignees」から `@copilot` を選択、または Issue のコメント欄で `@copilot` をメンションしてください。

#### Step.3. タスクの詳細を Issue に記述する

Custom Agent が適切に動作するために、タスクの詳細・要件・参照すべきファイルパスなどを明確に記述してください。

以下は**記述例**です。参照ファイルは、リポジトリ内の**実在するパス**に置き換えてください。

```markdown
## タスク
要求定義ドキュメント（docs/business-requirement.md）を基に、ドメインモデリングを実施してください。

## 参照ファイル
- docs/business-requirement.md
- （例）関連する設計ドキュメントの実在パス
```

#### Step.4. 実行結果を確認する

- 選択した Custom Agent がタスクを実行し、Pull Request を作成します
- 進捗状況は **Pull Requests** タブで確認できます
- 実行中のログは **Actions** タブで確認できます

> [!IMPORTANT]
> GitHub Copilot cloud agent でタスクを実行する際は、Agent のアクションが起動するまでや、実行結果が Web 画面に反映されるまでに遅延があります。画面の更新を待ってから、あるいは Web ブラウザーの画面リフレッシュを行ってから、次のアクションを実行してください。

> **応用パターン**: 複数の Custom Agent を使ったフルワークフローを手動で実行したい場合は、DAG の依存関係順（[workflow-reference.md](./workflow-reference.md) 参照）に従って Issue を順番に作成・アサインしてください。

---

### 方式2: ワークフローオーケストレーション（Web）

Issue Template から親 Issue を作成し、Bootstrap Workflow が Sub Issue を一括生成して自動実行するフル自動の使い方です。

#### 前提条件（方式2 固有）

> [!IMPORTANT]
> 方式2 を使用するには `COPILOT_PAT` シークレットが設定されている必要があります。設定がまだの場合は [getting-started.md の Step.4](./getting-started.md#step4-認証設定copilot_pat) を完了してください。

#### Step.1. Issue を作成する（Issue Template から）

1. リポジトリの **Issues** タブを開く
2. **New issue** をクリック
3. Issue テンプレートの一覧から使用するワークフローを選択

| Issue テンプレート | ワークフロー |
|-----------------|------------|
| `app-architecture-design.yml` | アプリケーションアーキテクチャ設計（AAS） |
| `app-detail-design.yml` | アプリケーション設計（AAD） |
| `app-dev-microservice.yml` | マイクロサービス実装（ASDW） |
| `batch-design.yml` | バッチ設計（ABD） |
| `batch-dev.yml` | バッチ実装（ABDV） |
| `sourcecode-to-documentation.yml` | Source Codeからのドキュメント作成（ADOC） |
| `knowledge-management.yml` | knowledge ドキュメント管理（AKM: qa/original-docs/both） |
| `original-docs-review.yml` | Original Docs Review 質問票生成（AQOD） |
| `self-improve.yml` | セルフ改善ループ |


#### ワークフロー別チェーン図

| ワークフロー | チェーン図 |
|---|---|
| AAS | [chain-aas.svg](./images/chain-aas.svg) |
| AAD | [chain-aad.svg](./images/chain-aad.svg) |
| ASDW | [chain-asdw.svg](./images/chain-asdw.svg) |
| ABD | [chain-abd.svg](./images/chain-abd.svg) |
| ABDV | [chain-abdv.svg](./images/chain-abdv.svg) |
| AKM | [chain-akm.svg](./images/chain-akm.svg) |
| AQOD | [chain-aqod.svg](./images/chain-aqod.svg) |
| ADOC | [chain-adoc.svg](./images/chain-adoc.svg) |
| Self-Improve | [chain-self-improve.svg](./images/chain-self-improve.svg) |

> **補足**: `self-improve.yml` については、`.github/workflows/` 配下に対応する GitHub Actions ワークフローが存在しないため、Issue 作成のみでは Web UI から自動実行されません。このテンプレートを実行する場合は、Issue に対して手動で `@copilot` をアサインするか、GitHub Copilot CLI SDK 版から実行してください。`knowledge-management.yml` は `auto-knowledge-management.yml`、`sourcecode-to-documentation.yml` は `auto-app-documentation.yml` により自動実行されます。

#### Step.1.5 PR 完全自動化チェックボックス（対応テンプレートのみ）

`app-architecture-design.yml` / `app-detail-design.yml` / `app-dev-microservice.yml` / `batch-design.yml` / `batch-dev.yml` / `knowledge-management.yml` には **「PR完全自動化設定」** チェックボックスがあります。

- チェック ON: `auto-approve-ready` ラベル連携により、レビュー完了後に Auto Approve / Auto-merge まで自動実行
- チェック OFF: 通常どおり人手レビュー・手動マージ

> ⚠️ 自動マージを有効化すると人手の最終確認なしでマージされるため、用途を限定してください。

#### Step.1.6 モデル選択 dropdown

Issue Template の **「使用するモデル」** で Copilot cloud agent のモデルを選択できます。

- 選択肢: `Auto` / `claude-opus-4.7` / `claude-opus-4.6` / `claude-sonnet-4.6` / `gpt-5.4` / `gpt-5.3-codex` / `gemini-2.5-pro`
- `Auto` は GitHub が最適モデルを動的に選択（10% ディスカウント適用）
- `Auto` は可用性・レイテンシ・レート制限・プラン/ポリシーを考慮して選択され、プレミアム乗数 1x 超のモデルは対象外
- 空欄時も `Auto` として扱う
- API 側が指定モデルを未サポートの場合は、`Auto`（既定）に戻して再実行してください
- 公式: https://docs.github.com/en/copilot/concepts/auto-model-selection

#### Step.2. Custom Agent を選択する

Bootstrap Workflow が自動的に Sub Issue を生成し、Copilot を各 Sub Issue に自動アサインします。特定の Sub Issue のみ別の Custom Agent を使いたい場合は、対象の Sub Issue の右サイドバーから **「Select agent」** で変更できます。

![Custom Agent の選択](../images/assign-githubcopilot-customagent.jpg)

#### Step.3. タスクの詳細を親 Issue に記述する

親 Issue に記述した内容をもとに、Bootstrap Workflow が各 Sub Issue を生成します。Custom Agent が適切に動作するために、タスクの詳細・要件・参照すべきファイルパスなどを明確に記述してください。

以下は**記述例**です。参照ファイルは、リポジトリ内の**実在するパス**に置き換えてください。

```markdown
## タスク
要求定義ドキュメント（docs/business-requirement.md）を基に、ドメインモデリングを実施してください。

## 参照ファイル
- docs/business-requirement.md
- （例）関連する設計ドキュメントの実在パス
```

#### Step.4. 実行結果を確認する

- Bootstrap Workflow が Sub Issue を生成し、Copilot が各 Sub Issue を順番に実行します
- 進捗状況は **Pull Requests** タブで確認できます
- 実行中のログは **Actions** タブで確認できます

> [!IMPORTANT]
> GitHub Copilot cloud agent でタスクを実行する際は、Agent のアクションが起動するまでや、実行結果が Web 画面に反映されるまでに遅延があります。画面の更新を待ってから、あるいは Web ブラウザーの画面リフレッシュを行ってから、次のアクションを実行してください。

---

## 利用可能な Custom Agent 一覧

`.github/agents/` 配下に **65 個** の Custom Agent が定義されています。6 カテゴリに分類されます。

| カテゴリ | 接頭辞 | 個数 | 主な役割 |
|---------|--------|:---:|----------|
| ビジネス分析・要求定義 | `Arch-Application*`, `Arch-Architecture*` | 2 | ユースケース分析・候補アーキテクチャ選定 |
| アーキテクチャ設計 | `Arch-*`（Application/Architecture を除く） | 21 | ドメイン設計・データモデル・テスト設計 |
| 実装 | `Dev-*` | 17 | Azure リソース作成・コード生成・デプロイ |
| ドキュメント生成 | `Doc-*` | 19 | API/データモデル/依存関係等の文書生成 |
| QA / レビュー | `QA-*` | 5 | コード品質・アーキテクチャレビュー |
| Knowledge Management | `KnowledgeManager` | 1 | qa/original-docs → knowledge/ D01〜D21 |

> 完全な一覧（入出力マップ・knowledge/ 参照関係を含む）は [workflow-reference.md](./workflow-reference.md#custom-agent-一覧) を参照してください。

---

## ヒント

- **適切な Custom Agent を選択**: タスクの内容に応じた Agent を選択することで、より高品質な結果が得られます
- **段階的に進める**: 大きなプロジェクトは複数の Custom Agent を順番に使用して段階的に進めることを推奨します
- **カスタマイズ**: Custom Agent ファイルはテンプレートです。プロジェクトの要件に応じて自由に編集・追加できます
- **フィードバック**: Custom Agent の実行結果を確認し、必要に応じて Issue のコメントで追加指示を出せます
- **tools**: GitHub Spark を使うと React での画面作成とリポジトリとの同期によるプレビューが便利です

---

## トラブルシューティング

Web UI 方式で問題が発生した場合は [troubleshooting.md](./troubleshooting.md) を参照してください。
