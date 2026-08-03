---
name: github-actions-cicd
description: >
  GitHub Actions CI/CD ワークフローの共通仕様。OIDC 認証・workflow_dispatch トリガー・ Copilot push 制約対応・シークレット管理・デプロイ保護の原則を提供する。 USE FOR: GitHub Actions, CI/CD workflow, OIDC authentication. DO NOT USE FOR: application code deployment (use appropriate azure-skills/ deployment skill). WHEN: GitHub Actions ワークフローを作成する、CI/CD パイプラインを設計する。
metadata:
  origin: user
  version: 2.0.0
---

# github-actions-cicd

## 目的

GitHub Actions CI/CD ワークフローの **共通仕様** を一元管理する。各 Deploy Agent は本 Skill を参照し、ワークフロー固有の設定（デプロイ先・ビルドコマンド等）のみを Agent 側に記載する。

---

## 3原則（詳細: `references/cicd-common-spec.md`）

1. **OIDC 認証優先**: `azure/login@v2` + OIDC フェデレーション（secret-less）。`environment: copilot` 指定必須
2. **workflow_dispatch トリガー必須**: Copilot push 制約（自動発火しない）の回避。PR description に手動実行案内を記載する
3. **シークレット管理**: GitHub Secrets から取得。ハードコード禁止。ログ漏洩なし

### HVE local orchestrator の Step 単位 CI/CD 境界

- HVE GUI/CLI の ASDW-WEB Step 単位 CI/CD では、Step 専用ブランチ作成・PR 作成・merge・base branch 復帰は **HVE Orchestrator の責務**。
- Deploy Agent は Orchestrator から提供された branch を、default branch に存在する workflow の `workflow_dispatch` / `gh workflow run ... --ref <branch>` に使用する。
- 同一 Step 内で新規作成した workflow を dispatch しない。workflow を新規追加する必要がある場合は、当該 workflow が default branch に反映された後の Step / run で実行する。
- Deploy Agent は新規 branch 作成、任意の checkout、`gh pr create`、merge を行わない。GitHub Actions 実行前に remote へ反映が必要な場合でも、`git push origin HEAD` を実行しない。`main` または base branch へ push しない。push が不可欠な場合は、現在 branch が Orchestrator から提供された `<branch>` と一致することを確認し、許可される push は `git push origin HEAD:<branch>` のみに限定する。一致しない場合は push せず、ブロッカーとして作業ログに記録する。

---

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/cicd-common-spec.md` | §1 認証方式（OIDC推奨・YAML例・例外）、§2 Copilot push制約と workflow_dispatch（PR description手動実行案内テンプレート）、§3 ワークフロー共通仕様（トリガー・シークレット管理・デプロイ保護） |

---

## 入出力例

> ※ 以下は説明用の架空例です

**例1（Azure Functions デプロイ）**: `on: [push, pull_request, workflow_dispatch]` + `permissions: id-token:write` + `environment: copilot` + `azure/login@v2`

**例2（Copilot push 後の手動実行）**: PR description に「⚡ GitHub Actions Workflow の手動実行が必要です」案内を記載 → 「Approve and run workflows」ボタンをクリック

## 参照元

- P-04 の詳細は旧 work スナップショット由来のため、実行時には参照しない。
