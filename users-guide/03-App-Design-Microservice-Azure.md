# Web Application 設計（AAD-WEB）

← [02-app-architecture-design.md](./02-app-architecture-design.md) | [05-app-dev-microservice-azure.md](./05-app-dev-microservice-azure.md) →

---

## 目次

- [対象読者](#対象読者)
- [前提](#前提)
- [次のステップ](#次のステップ)
- [概要](#概要)
- [Agent チェーン図 AAD-WEB](#agent-チェーン図-aad-web)
- [ツール](#ツール)
- [ステップ概要](#ステップ概要)
- [手動実行ガイド](#手動実行ガイド)
- [自動実行ガイド ワークフロー](#自動実行ガイド-ワークフロー)
- [動作確認手順](#動作確認手順)

---

## 対象読者

- AAS 完了後に Web アプリ詳細設計（画面・サービス・テスト仕様）を自動化したい人
- `web-app-design.yml` と `auto-app-detail-design-web-reusable.yml` を使って運用する人

## 前提

- AAS の成果物が存在すること（`docs/catalog/app-catalog.md`、`docs/catalog/service-catalog-matrix.md` など）
- `COPILOT_PAT` が設定済みであること
- セットアップ手順は [getting-started.md](./getting-started.md) を参照

## 次のステップ

- AAD-WEB 完了後は [05-app-dev-microservice-azure.md](./05-app-dev-microservice-azure.md)（ASDW-WEB）へ進む

---

## 概要

AAD-WEB（Web App Design）は、Issue Form から親 Issue を作成するだけで、
Step.1〜Step.2.3 の設計タスクを Sub-issue として生成し、依存関係に従って実行するワークフローです。

> [!NOTE]
> 旧 AAD の Step.1.1〜6（ドメイン分析・サービス一覧・データモデル・データカタログ・サービスカタログ・テスト戦略書）は
> AAS（[02-app-architecture-design.md](./02-app-architecture-design.md)）に統合されています。

- `knowledge/` の活用方法は [km-guide.md](./km-guide.md) を参照

## Agent チェーン図 AAD-WEB

![AAD-WEB: Arch-UI-List → Arch-UI-Detail/Arch-Microservice-ServiceDetail → Arch-TDD-TestSpec](./images/chain-aad-web.svg)

### アーキテクチャ図

![AAD-WEB アーキテクチャ: 入力ファイル → auto-app-detail-design-web Workflow → Custom Agent チェーン → 成果物](./images/infographic-aad-web.svg)

### データフロー図（AAD-WEB）

![AAD-WEB データフロー: 各 Custom Agent の入出力ファイル](./images/orchestration-task-data-flow-aad-web.svg)

---

## ツール

- GitHub Copilot cloud agent
- GitHub Actions（`auto-app-detail-design-web-reusable.yml`）

---

## ステップ概要

### 依存グラフ

```text
step-1 ──┬──► step-2.1 ──┐
         └──► step-2.2 ──┴──► step-2.3
```

### 各ステップの入出力

| Step ID | タイトル | Custom Agent | 入力 | 出力 | 依存 |
|---------|---------|-------------|------|------|------|
| step-1 | 画面一覧と遷移図 | `Arch-UI-List` | `docs/catalog/domain-analytics.md`, `docs/catalog/service-catalog.md`, `docs/catalog/data-model.md`, `docs/catalog/app-catalog.md` | `docs/catalog/screen-catalog.md` | AAS 完了 |
| step-2.1 | 画面定義書 | `Arch-UI-Detail` | `docs/catalog/screen-catalog.md`, `docs/catalog/app-catalog.md`, `docs/catalog/test-strategy.md`（存在する場合） | `docs/screen/{screenId}-{screenNameSlug}-description.md` | step-1 |
| step-2.2 | マイクロサービス定義書 | `Arch-Microservice-ServiceDetail` | `docs/catalog/service-catalog-matrix.md`, `docs/catalog/app-catalog.md`, `docs/catalog/test-strategy.md`（存在する場合） | `docs/services/{serviceId}-{serviceNameSlug}-description.md` | step-1 |
| step-2.3 | TDDテスト仕様書 | `Arch-TDD-TestSpec` | `docs/catalog/test-strategy.md`（存在する場合）, 画面定義書, サービス定義書, `docs/catalog/service-catalog-matrix.md`, `docs/catalog/app-catalog.md` | `docs/test-specs/{serviceId}-test-spec.md`, `docs/test-specs/{screenId}-test-spec.md` | step-2.1, step-2.2 |

---

## 手動実行ガイド

### Step 1. 画面一覧と遷移図

- Custom Agent: `Arch-UI-List`
- 入力: `docs/catalog/domain-analytics.md`, `docs/catalog/service-catalog.md`, `docs/catalog/data-model.md`, `docs/catalog/app-catalog.md`
- 出力: `docs/catalog/screen-catalog.md`

### Step 2.1. 画面定義書

- Custom Agent: `Arch-UI-Detail`
- 入力: `docs/catalog/screen-catalog.md`, `docs/catalog/app-catalog.md`
- 出力: `docs/screen/{screenId}-{screenNameSlug}-description.md`

### Step 2.2. マイクロサービス定義書

- Custom Agent: `Arch-Microservice-ServiceDetail`
- 入力: `docs/catalog/service-catalog-matrix.md`, `docs/catalog/app-catalog.md`
- 出力: `docs/services/{serviceId}-{serviceNameSlug}-description.md`

### Step 2.3. TDD テスト仕様書

- Custom Agent: `Arch-TDD-TestSpec`
- 入力: `docs/catalog/test-strategy.md`（存在する場合）, 画面定義書, サービス定義書
- 出力: `docs/test-specs/{serviceId}-test-spec.md`, `docs/test-specs/{screenId}-test-spec.md`

---

## 自動実行ガイド ワークフロー

### 関連ファイル

- Issue Template: `.github/ISSUE_TEMPLATE/web-app-design.yml`
- Workflow: `.github/workflows/auto-app-detail-design-web-reusable.yml`

### ラベル体系

| ラベル | 意味 |
|-------|------|
| `auto-app-detail-design-web` | トリガーラベル（Issue Template で自動付与） |
| `aad-web:initialized` | Bootstrap 実行済み |
| `aad-web:ready` | 実行可能 |
| `aad-web:running` | 実行中 |
| `aad-web:done` | 完了 |
| `aad-web:blocked` | ブロック |

### フォーム入力（主要）

`web-app-design.yml` の主要入力:

- `branch`
- `runner_type`
- `app_ids`
- `steps`
- `model` / `review_model` / `qa_model`

### 実行手順

1. Issues → New Issue → **Web App Design** を選択
2. 必要項目（branch / runner / app_ids / steps）を入力して Submit
3. `auto-app-detail-design-web` が付与され、`AAD-WEB: Web App Design (Reusable)` が起動

---

## 動作確認手順

1. `.github/ISSUE_TEMPLATE/web-app-design.yml` が存在することを確認
2. `.github/workflows/auto-app-detail-design-web-reusable.yml` が存在することを確認
3. Issues で **Web App Design** テンプレートが表示されることを確認
4. Issue 作成後に親 Issue に `aad-web:initialized` が付与されることを確認
5. Step Issue が `step-1` → (`step-2.1`,`step-2.2`) → `step-2.3` の順に遷移することを確認
6. 最終的に Root Issue に `aad-web:done` が付与されることを確認
