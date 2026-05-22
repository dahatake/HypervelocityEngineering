# GitHub Actions CI/CD 共通仕様詳細

> 本ファイルは `github-actions-cicd/SKILL.md` の詳細仕様セクションを収容する参照資料です。

---

## 1. 認証方式（OIDC 優先・secret-less）

### 1.1 推奨: OIDC + `azure/login`

```yaml
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
- **secret-less**: パスワードやクライアントシークレットは不要
- **environment の指定（必須）**: OIDC Secrets が **Environment secrets** として登録されている場合、ジョブに `environment: <環境名>` を必ず指定すること。未指定の場合、Secrets が空値として展開され `azure/login` が `Not all values are present` エラーで失敗する
- 本リポジトリの OIDC 用 Secrets は `copilot` Environment に登録されているため、SWA デプロイワークフローでは `environment: copilot` を使用する

### 1.2 例外: OIDC 不可の場合

OIDC が使用できない場合（例: SWA の API トークン方式、publish profile 方式）に限り、代替認証を採用する。代替方式を使用する場合は、**採用理由と設定手順** を `infra/README.md` に記載する。

---

## 2. Copilot push 制約と `workflow_dispatch` トリガー

**Copilot cloud agent が push したコミットでは GitHub Actions Workflow が自動実行されない**（`GITHUB_TOKEN` による push は後続 Workflow を発火しない仕様）。

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:     # ← 必ず追加
```

### PR description への手動実行案内（必須）

```markdown
## ⚡ GitHub Actions Workflow の手動実行が必要です

Copilot cloud agent が push したコミットでは GitHub Actions Workflow が自動実行されません。

1. **推奨**: PR の merge box に表示される「Approve and run workflows」ボタンをクリック
2. **フォールバック**: Actions タブ → 対象 Workflow → 「Run workflow」ボタン → ブランチを指定
```

---

## 3. ワークフロー共通仕様

### 3.1 トリガー設定

- `push`: `main` ブランチへの push
- `pull_request`: `main` ブランチへの PR（デフォルト: `opened`, `synchronize`, `reopened`）
- `workflow_dispatch`: 手動実行（§2 参照）

### 3.2 シークレット管理

- シークレットは **GitHub Secrets** から取得する（ハードコード禁止）
- 接続文字列・API キー・パスワードをワークフロー YAML にハードコードしない
- ログ出力にシークレット値が含まれないことを確認する

### 3.3 デプロイ保護（推奨）

- `environment` にはデプロイ対象の Environment 名（例: `dev`, `staging`, `prod`, `copilot` 等）を設定する
- OIDC / Azure 認証に必要な `AZURE_*` Secrets は、上記の各 Environment から参照できるように登録する
- 本番環境へのデプロイには手動承認ステップを含める
