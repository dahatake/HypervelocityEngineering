---
name: github-actions-cicd
description: "GitHub Actions CI/CD ワークフローの共通仕様。OIDC 認証方式（azure/login 優先・secret-less）、workflow_dispatch トリガー追加（Copilot push 制約対応）、PR description への手動実行案内テンプレートを提供する。Deploy Agent が GitHub Actions ワークフローを生成する際に参照する。"
---

# github-actions-cicd

## 目的

GitHub Actions CI/CD ワークフローの **共通仕様** を一元管理する。
各 Deploy Agent は本 Skill を参照し、ワークフロー固有の設定（デプロイ先・ビルドコマンド等）のみを Agent 側に記載する。

本 Skill は以下のパターンを統合して提供する:
- **P-04**: GitHub Actions CI/CD テンプレート（OIDC 認証・`workflow_dispatch` トリガー・Copilot push 制約対応）

---

## 1. 認証方式（OIDC 優先・secret-less）

### 1.1 推奨: OIDC + `azure/login`

GitHub Actions から Azure へのデプロイには **OIDC（OpenID Connect）+ `azure/login` アクション** を優先使用する。

```yaml
# OIDC 認証の設定例
permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: copilot    # AZURE_* を Environment secrets に保存している場合は必須
    steps:
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
```

- **必要な GitHub Secrets**: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`
- **secret-less**: パスワードやクライアントシークレットは不要。OIDC フェデレーションにより一時トークンで認証する
- **environment の指定（必須）**: OIDC Secrets が **Environment secrets** として登録されている場合、ジョブに `environment: <環境名>` を必ず指定すること。
  - 未指定の場合、Secrets が空値として展開され `azure/login` が `Not all values are present` エラーで失敗する
  - `environment` には `AZURE_*` Secrets が登録されている Environment 名を指定する（例: `copilot`, `dev`, `staging`, `prod` など）
  - 本リポジトリの OIDC 用 Secrets は `copilot` Environment に登録されているため、SWA デプロイワークフローでは `environment: copilot` を使用する

### 1.2 例外: OIDC 不可の場合

OIDC が使用できない場合（例: SWA の API トークン方式、publish profile 方式）に限り、代替認証を採用する。

- 代替方式を使用する場合は、**採用理由と設定手順** を `infra/README.md` に記載する
- API トークンや publish profile は **GitHub Secrets** に格納し、コード内にハードコードしない

---

## 2. Copilot push 制約と `workflow_dispatch` トリガー

### 2.1 制約の説明

**Copilot cloud agent が push したコミットでは GitHub Actions Workflow が自動実行されない。**

これは GitHub のセキュリティ制約であり、`GITHUB_TOKEN` による push は後続 Workflow を発火しない仕様による。

### 2.2 回避策: `workflow_dispatch` トリガーの追加

全ての CI/CD ワークフローに `workflow_dispatch` トリガーを追加し、GitHub Actions タブから手動実行可能にする。

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:     # ← 必ず追加
```

### 2.3 PR description への手動実行案内（必須）

ワークフローを生成・更新した場合は、PR description に以下のテンプレートを記載すること:

```markdown
## ⚡ GitHub Actions Workflow の手動実行が必要です

Copilot cloud agent が push したコミットでは GitHub Actions Workflow が自動実行されません。
以下のいずれかの方法でワークフローを実行してください：

1. **推奨: 「Approve and run workflows」ボタン**
   - PR の merge box に表示される「Approve and run workflows」ボタンをクリック
   - 参照: https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/review-copilot-prs

2. **フォールバック: Actions タブから手動実行**
   - GitHub リポジトリの Actions タブ → 対象 Workflow を選択
   - 「Run workflow」ボタンをクリックし、対象ブランチを指定
   - ※ `workflow_dispatch` トリガーが Workflow YAML に追加されていることが前提
```

---

## 3. ワークフロー共通仕様

### 3.1 トリガー設定

- `push`: `main` ブランチへの push（必要に応じて作業ブランチも追加）
- `pull_request`: `main` ブランチへの PR（デフォルト: `opened`, `synchronize`, `reopened`。必要に応じて `types:` で `closed` を追加）
- `workflow_dispatch`: 手動実行（§2.2 参照）

### 3.2 シークレット管理

- シークレットは **GitHub Secrets** から取得する（ハードコード禁止）
- 接続文字列・API キー・パスワードをワークフロー YAML にハードコードしない
- ログ出力にシークレット値が含まれないことを確認する

### 3.3 デプロイ保護（推奨）

- `environment` にはデプロイ対象の Environment 名（例: `dev`, `staging`, `prod`, `copilot` 等）を設定する
- OIDC / Azure 認証に必要な `AZURE_*` Secrets は、上記の各 Environment から参照できるように登録する（`copilot` 固定は必須ではない）
- 本番環境へのデプロイには手動承認ステップを含める

---

## 参照元

- `work/Issue-skills-migration-investigation/duplication-patterns.md` — P-04 の詳細
- `work/Issue-skills-migration-investigation/migration-matrix.md` — GO-5 評価
