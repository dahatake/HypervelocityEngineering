# Users Guide

← [ルート README](../README.md)

> **📊 プレゼンテーション資料**: このリポジトリの設計思想（Prompt / Context / Harness Engineering、CLI とバッチ自動化の両立）を視覚的に紹介するサイトを用意しています → [presentation/index.html](../presentation/index.html)

---

## 目次

- [はじめに](#はじめに)
- [2 つの利用方法](#2-つの利用方法)
- [ドキュメント一覧](#ドキュメント一覧)
- [実行フェーズ別ガイド](#実行フェーズ別ガイド)
- [サンプル](#サンプル)

---

## はじめに

Copilot を使用してタスクに取り組むためのベストプラクティス:

https://docs.github.com/ja/copilot/using-github-copilot/coding-agent/best-practices-for-using-copilot-to-work-on-tasks

- プロダクション環境での利用には十二分に注意をしてください。Pull Request をマージするかどうかは、**人**の判断ですので！

---

## 2 つの利用方法

このリポジトリでは、ワークフローを実行するために **2 つの方法** を提供しています。

### 比較表

| 項目 | Web UI 方式 | SDK 版（ローカル実行） |
|------|-----------|-------------------|
| Agent 実行場所 | GitHub Actions | ローカル PC |
| Issue 作成 | 必須 | オプション（デフォルト: しない） |
| Copilot アサイン | する | しない（ローカル直接実行） |
| 並列実行 | GitHub Actions 並列ジョブ | 同時実行数を制限（デフォルト: 15） |
| MCP Server | GitHub 管理の MCP 設定 | 対応（`--mcp-config` で任意設定） |
| Custom Agents | GitHub Issue 経由で選択 | SDK の API でステップごとに指定 |
| 必要な認証 | `COPILOT_PAT` | Copilot CLI 認証（`gh auth login`） |
| モデルデフォルト | GitHub 管理 | `claude-opus-4.6` |
| 課金 | GitHub Actions 分 | Copilot ライセンスのみ |

### 方法 1: GitHub Copilot Coding Agent（Web UI 方式）

GitHub.com 上で Issue を作成し、Copilot Coding Agent が Issue にアサインされて GitHub Actions 上で自動実行されます。

> 詳細 → [web-ui-guide.md](./web-ui-guide.md)

### 方法 2: Copilot SDK 版（ローカル実行方式）

ローカル環境から Python スクリプトでワークフローを実行します。

> 詳細 → [SDK-Guide.md](./SDK-Guide.md)

---

## ドキュメント一覧

### セットアップ・利用ガイド

| ドキュメント | 内容 |
|-------------|------|
| [getting-started.md](./getting-started.md) | 初期セットアップ（Step.1〜5: リポジトリ作成・MCP 設定・PAT 設定・ラベル設定） |
| [web-ui-guide.md](./web-ui-guide.md) | 方法 1: Web UI 方式の利用手順・Custom Agent 一覧 |
| [SDK-Guide.md](./SDK-Guide.md) | 方法 2: Copilot SDK 版コマンドリファレンス |
| [workflow-reference.md](./workflow-reference.md) | ワークフロー一覧・ラベル一覧・Custom Agent 完全一覧 |
| [prompt-examples.md](./prompt-examples.md) | 便利なプロンプト例（敵対的レビュー・質問票・エラー対応） |
| [troubleshooting.md](./troubleshooting.md) | トラブルシューティング |

### ツール

- **GitHub Copilot Coding Agent**: Issue から Coding Agent に作業を依頼
  - https://github.blog/news-insights/product-news/github-copilot-meet-the-new-coding-agent/
- **GitHub Spark**: React での画面作成とリポジトリとの同期によるプレビュー
  - https://github.com/features/spark
- **Visual Studio Code + GitHub Copilot Agent Mode**: Markdown プレビュー・ファイル編集・コード修正
  - Azure SDK を使う場合は [GitHub Copilot for Azure](https://learn.microsoft.com/ja-jp/azure/developer/github-copilot-azure/introduction) も活用

---

## 実行フェーズ別ガイド

| フェーズ | ガイド | ワークフロー ID |
|---------|--------|:---:|
| **01 — 要求定義** | [01-Business-Requirement.md](./01-Business-Requirement.md) | — |
| **02 — アプリ選定** | [02-App-Selection.md](./02-App-Selection.md) | `aas` |
| **03 — Microservice 設計** | [03-App-Design-Microservice-Azure.md](./03-App-Design-Microservice-Azure.md) | `aad` |
| **04 — Batch 設計** | [04-App-Design-Batch.md](./04-App-Design-Batch.md) | `abd` |
| **05 — Microservice 実装** | [05-App-Dev-Microservice-Azure.md](./05-App-Dev-Microservice-Azure.md) | `asdw` |
| **06 — Batch 実装** | [06-App-Dev-Batch-Azure.md](./06-App-Dev-Batch-Azure.md) | `abdv` |
| **07 — AI Agent（Quick）** | [07-AIAgent-Simple.md](./07-AIAgent-Simple.md) | — |
| **08 — AI Agent（本格）** | [08-AIAgent.md](./08-AIAgent.md) | — |
| **IoT 設計** | — | `aid` |

> 01（要求定義）と 07（AI Agent Quick）は手動実行です。それ以外はワークフローによる自動実行が可能です。

---

## サンプル

**会員サービス**を題材にしたサンプルの要求定義や設計書などのサンプルです。

[サンプル](../sample/)
