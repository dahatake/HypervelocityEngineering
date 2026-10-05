# HVE リポジトリ フォルダー構成と役割

作成日: 2026-10-03 / 対象: リポジトリ直下の各フォルダー（Git 管理外の生成物を含む）

## 1. 全体像

このリポジトリは **HVE**（業務要件の整理から設計・実装・検証までを再現可能な Workflow として運用する仕組み）の本体と、HVE が生成した対象アプリケーション（ロイヤルティ／会員サービス）の成果物を同居させている。フォルダーは次の 6 グループに分けて理解できる。

| グループ | 該当フォルダー |
|---|---|
| A. HVE 本体・ツール | `hve/` `cq/` `mdq/` `tools/` `hve-dev/` `local-llm-dev/` `.github/` |
| B. 入力（人が用意する情報） | `docs-original/` `qa/` `template/` `sample/` |
| C. 中核ナレッジ | `knowledge/` |
| D. 生成成果物（設計・実装） | `docs/` `src/` `docs-generated/` |
| E. 利用者向けドキュメント | `users-guide/` `README.md` `CHANGELOG.md` |
| F. テスト・作業・実行時の一時領域 | `tests/` `work/` `artifacts/` `gui-logs/` `.hve/` `.cq/` `.mdq/` ほか |

## 2. 直下フォルダー一覧

### A. HVE 本体・ツール

| フォルダー | 役割 | 備考 |
|---|---|---|
| `hve/` | HVE アプリケーション本体（Python パッケージ。`python -m hve` で CLI/GUI、Workflow 実行、Prompt 版、autopilot、bootstrap、pricing、toolsearch 等） | `hve/tests/` に単体テスト。`hve/work/` は本体内部の作業領域 |
| `cq/` | code-query。ソースコードの定義・参照を検索するローカル検索ツール（`python -m cq`）。設定は `cq.toml` | インデックスは `.cq/` |
| `mdq/` | markdown-query。Markdown 要件・設計を BM25 等で検索するローカルツール（`python -m mdq`）。設定は `mdq.toml` | インデックスは `.mdq/` |
| `tools/` | 補助ツール群。`runner/`（実行用 Docker/デプロイ）、`skills/`（code_query / markdown_query Skill）、`copy-hve-other-repo/` `for-other-repo/`（他リポジトリへの HVE 展開）、トークン計測・翻訳などのスクリプト | |
| `hve-dev/` | HVE 開発者向け資料・インベントリ（`hve-app-tools.md`、機能／サーフェス／テスト棚卸し CSV、TDD 変更方針、各種生成スクリプト） | 要件トレーサビリティの根拠。HVE 保守時に参照 |
| `local-llm-dev/` | ローカル LLM 開発環境のセットアップ資料（Windows/macOS、チュートリアル、検証、テンプレート） | |
| `.github/` | Copilot / GitHub 設定一式。`copilot-instructions.md`、`AGENTS.md`、`prompts/`（Workflow 各 Step の Prompt）、`skills/`（Agent Skill）、`instructions/`、`io-contracts/`（Prompt の入出力契約）、`workflows/`（GitHub Actions）、`ISSUE_TEMPLATE/`、`scripts/`（bash/powershell/python）、`labels.json`、`CODEOWNERS` など | 実行入口（Issue Template）と Prompt の置き場 |
| `.vscode/` | VS Code 設定（ターミナル自動承認の allowlist 等） | |

### B. 入力

| フォルダー | 役割 | 備考 |
|---|---|---|
| `docs-original/` | 原本ドキュメント（既存システムの設計書等。日本語の処理仕様書など） | **読み取り専用**。編集しない |
| `qa/` | 質問票・回答（`*-pre-execution-qa.md`、WorkIQ による事前 QA 下書き等） | Workflow 実行前の不明点解消の記録 |
| `template/` | 成果物のひな形（`atdd-template.md`、業務要件文書マスターリスト、典型クエリ、`decisions/`） | |
| `sample/` | サンプル成果物（`business-requirement.md`、画面・サービス例、アーキテクチャ要件例） | 書き方の参照用 |

### C. 中核ナレッジ

| フォルダー | 役割 |
|---|---|
| `knowledge/` | 確定済みドメイン知識（D01〜D21：事業意図、スコープ、ステークホルダー、業務プロセス、ユースケース、データモデル等。各文書に `-ChangeLog.md`）。`business-requirement-document-status.md` で状況管理。`docs-original/`・`qa/`・既存コードから整理した情報の中核ストア |

### D. 生成成果物

| フォルダー | 役割 |
|---|---|
| `docs/` | 設計成果物。`catalog/`（app / data / service 等カタログ）、`usecase/`、`screen/`、`services/`、`dataflow/`、`agent/`、`azure/`、`test-specs/`、`original-design-doc-ingest/`、`attached/`、APP 別アーキテクチャ要件（`architectural-requirements-app-XXX.md`） |
| `src/` | 実装成果物。`api/`（SVC-xx マイクロサービス）、`app/`（APP-xxx 画面・Web アプリ）、`data/`（データ／ジョブ）、`infra/`（インフラ／デプロイ）、`test/`（生成アプリのテスト） |
| `docs-generated/` | 既存コードから生成した解説ドキュメント（`architecture/` `components/` `files/` `guides/`） |

### E. 利用者向けドキュメント

| フォルダー／ファイル | 役割 |
|---|---|
| `users-guide/` | **HVE アプリを使う人向けドキュメント**。Workflow 別ガイド（`00-`〜）、`prompts/` `prompt-reference/`（Prompt 版リファレンス）、`images/`（図） |
| `README.md` | リポジトリ概要・目的・全体像・使い方の入口 |
| `CHANGELOG.md` | HVE の変更履歴（Unreleased を保持し PATCH 更新） |

### F. テスト・作業・一時領域

| フォルダー | 役割 | Git 管理 |
|---|---|---|
| `tests/` | **HVE 本体のシステムテスト**。`system-test/`、`system-test-ledger/`（増分実行の台帳）、`prompt-version/`、`run/<run-id>/`（実行結果の保持）、CLI/GUI 全件テスト手順、分析レポート、`README.md` | 管理対象 |
| `work/` | **一時作業フォルダー**。`work/run/<run-id>/.../artifacts/` に作業ファイル、計画・分析メモを置く | 一時 |
| `artifacts/` | テスト実行の出力（`contract-*.log/xml` 等） | `.gitignore` 対象 |
| `gui-logs/` | HVE GUI のログ（`log-*.log`） | 生成物 |
| `.hve/` | HVE 実行時状態（ロック、QA/steering の IPC、テスト実行用ディレクトリ） | `.gitignore` 対象 |
| `.cq/` `.mdq/` | cq / mdq の検索インデックス・ベクトル DB・利用ログ（SQLite / jsonl） | 生成物 |
| `hve.egg-info/` | `pip install -e` によるパッケージメタデータ | 生成物 |
| `node_modules/` | npm 依存（Jest / Playwright 等） | `.gitignore` 対象 |
| `.venv/` | Python 仮想環境 | 生成物 |
| `.mypy_cache/` `.pytest_cache/` `.ruff_cache/` | 各ツールのキャッシュ | 生成物 |
| `.git/` | Git 管理データ | — |

## 3. 直下の主なファイル

| ファイル | 役割 |
|---|---|
| `pyproject.toml` | Python パッケージ（hve / cq / mdq）の定義・依存 |
| `cq.toml` / `mdq.toml` | code-query / markdown-query の設定 |
| `hve.cmd` / `hve.sh` | HVE 起動ラッパー（Windows / Linux・macOS） |
| `package.json` / `package-lock.json` / `jest.config.js` / `babel.config.js` / `playwright.config.js` | JS テスト（Jest・Playwright）関連 |
| `.env` | ローカル環境変数（秘密値を含み得る。コミット・共有しない） |
| `.gitattributes` / `.gitignore` | Git 設定 |
| `testResults.xml` | テスト結果の出力（生成物） |
| `LICENSE` | ライセンス |

## 4. データの流れ（要約）

`docs-original/`・`qa/` → `knowledge/`（中核ストア）→ `docs/`（設計）→ `src/`（実装・テスト）。実行は `.github/prompts/` の Prompt を `hve/` の Workflow が起動し、途中の一時ファイルは `work/`、検証は `tests/` と `src/test/`、利用方法は `users-guide/` に記載する。

## 5. 運用上の注意

- `docs-original/` は読み取り専用。
- 一時ファイルは `work/` へ。HVE 自己テストの出力は `tests/run/<run-id>/` へ保持する。
- 秘密値（`.env` 等）をドキュメント・コードへ転記しない。

