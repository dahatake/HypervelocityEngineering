# GitHub Copilot CLI SDK ユーザーガイド（GitHub Copilot CLI SDK 版ワークフローオーケストレーション）

← [README](../README.md)

---

## 目次

- [はじめに](#はじめに)
- [クイックスタート](#クイックスタート)
- [環境設定](#環境設定)
- [インタラクティブモード（推奨）](#インタラクティブモード推奨)
- [コマンドリファレンス（CLI モード）](#コマンドリファレンスcli-モード)
- [ワークフロー一覧](#ワークフロー一覧)
- [付録A: MCP Server 設定ガイド](#付録a-mcp-server-設定ガイド)
- [付録B: Custom Agents 設定ガイド](#付録b-custom-agents-設定ガイド)
- [付録C: DAG 並列実行と Post-step 自動プロンプト](#付録c-dag-並列実行と-post-step-自動プロンプト)
- [付録D: トラブルシューティング](#付録d-トラブルシューティング)
- [付録E: セキュリティ・SSO・関連リンク](#付録e-セキュリティsso関連リンク)

---

## はじめに

### このガイドの目的

このガイドは、このリポジトリの `hve/` パッケージを使って、**ローカル PC 上で完結して**ワークフローを実行するための手順を解説します。実行には PyPI パッケージ `github-copilot-sdk`（`pip install github-copilot-sdk`）が依存ライブラリとして必要です。

> **注意**: `hve/` はこのリポジトリに含まれるローカルパッケージです。`python -m hve` はリポジトリルートをカレントディレクトリとして実行してください。

本ガイドは **GitHub Copilot CLI SDK 版（ローカル実行方式）** に特化しています。Web UI 方式との比較や全体の利用ガイドについては [README.md](../README.md#2-つの実行方法) を参照してください。

### ポイント

- **GitHub Actions 不要** — `python -m hve` で対話型 wizard が起動し、ガイド付きで実行可能
- **2つの実行モード** — インタラクティブモード（初回推奨）と CLI モード（`orchestrate` サブコマンド、スクリプト/CI 向け）を用意
- **COPILOT_PAT 不要** — ローカルで直接 Agent を実行するため、Copilot アサイン用 PAT は不要
- **基本実行に GH_TOKEN 不要** — `--create-issues` / `--create-pr` / `--auto-coding-agent-review` を使わなければ環境変数の設定は不要
- MCP Server・Custom Agents・asyncio による並列実行など、高度な機能を利用可能

### 対象読者

- **初めてのユーザー**: まず `python -m hve` でインタラクティブモードを試すことを推奨します。オプションの知識がなくても wizard が順番にガイドします
- **開発者**: ローカル PC 上でワークフローを完結させたい方
- **アーキテクト**: MCP Server や Custom Agents を活用した高度なオーケストレーションを構築したい方
- **前提知識**: Python の基本的なスクリプト実行ができる方、`gh auth login` などの GitHub CLI 操作ができる方

---

## クイックスタート

3 ステップで実行を開始できます。

```bash
# 1. 依存パッケージをインストール
pip install github-copilot-sdk

# 2. GitHub CLI で認証（初回のみ）
gh auth login

# 3. インタラクティブモードで実行
python -m hve
```

wizard が起動し、ワークフロー選択・オプション設定・実行確認を対話的にガイドします。
詳しい環境構築手順は以下の「環境設定」セクション、wizard の詳細は「インタラクティブモード（推奨）」セクションを参照してください。

---

## 環境設定

### 前提条件

| ソフトウェア | 必須 / オプション | 説明 |
|-------------|-----------------|------|
| Python 3.9+ | **必須** | スクリプト実行環境 |
| Copilot CLI | **必須** | SDK の実行エンジン |
| GitHub CLI（`gh`） | **必須** | 認証管理に使用 |
| Git | **必須** | リポジトリのクローンに使用 |
| Node.js（npm/npx） | オプション | MCP Server（filesystem 等）を使用する場合 |

### Copilot CLI のインストール

公式ドキュメント: https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli

```bash
copilot --version   # インストール確認
```

> **注意**: GitHub Copilot のサブスクリプションが有効なアカウントが必要です。

### Python 環境セットアップ

```bash
git clone https://github.com/dahatake/RoyalytyService2ndGen.git
cd RoyalytyService2ndGen
python -m venv .venv
```

```bash
# macOS / Linux
source .venv/bin/activate
```

> **Windows**: PowerShell は `.venv\Scripts\Activate.ps1`、コマンドプロンプトは `.venv\Scripts\activate.bat` を使用してください。

```bash
pip install github-copilot-sdk
python -m hve --help   # インストール確認
```

> **ヒント**: `python -m hve`（引数なし）を実行するとインタラクティブモードが起動します。`--help` で全オプションを確認できます。

> 作業終了時は `deactivate` で仮想環境を終了してください。

### 認証設定

#### 認証手段A: `gh auth login`（推奨）

```bash
gh auth login
gh auth status   # 「Logged in to github.com」と表示されれば成功
```

基本実行ではこれだけで十分です。追加の環境変数設定は不要です。

#### 認証手段B: 環境変数 `GH_TOKEN`（Issue/PR 作成・Code Review Agent 使用時）

以下のオプションを使用する場合のみ `GH_TOKEN` が必要です。

| オプション | GH_TOKEN |
|-----------|----------|
| `--create-issues` | 必要（未設定ならエラー終了） |
| `--create-pr` | 必要（未設定ならエラー終了） |
| `--auto-coding-agent-review` | **必須** |
| MCP Server（GitHub HTTP） | **必須** |
| 上記以外（基本実行） | **不要** |

#### Fine-grained PAT の作成手順

1. GitHub.com > **プロフィールアイコン** > **Settings** > **Developer settings**
2. **Personal access tokens** > **Fine-grained tokens** > **Generate new token**
3. 基本情報を入力:
   - **Token name**: 任意（例: `copilot-sdk-tools`）
   - **Expiration**: 90日以内を推奨
4. **Repository access**: **Only select repositories** → `dahatake/RoyalytyService2ndGen` を選択
5. **Permissions**（Repository permissions）:

| 権限 | 設定値 | 用途 |
|------|--------|------|
| **Issues** | Read and write | `--create-issues` |
| **Pull requests** | Read and write | `--create-pr` |
| **Metadata** | Read-only（自動付与） | — |
| **Contents** | Read and write | `--create-issues` / `--create-pr` / `--auto-coding-agent-review` 使用時 |

> **最小権限の原則**: `--create-issues` / `--create-pr` / `--auto-coding-agent-review` はいずれもブランチ作成・commit・push を伴うため、Contents も Read and write が必要です。

6. **Generate token** をクリックし、表示されたトークン（`github_pat_` で始まる文字列）を**必ずこの時点でコピー**

> ⚠️ トークンはこの画面を離れると二度と表示されません。

7. 環境変数に設定:

```bash
# macOS / Linux
export GH_TOKEN="github_pat_xxxxxxxxxxxxxxxxxxxx"
```

> **Windows**: PowerShell は `$env:GH_TOKEN = "github_pat_xxxx"`、コマンドプロンプトは `set GH_TOKEN=github_pat_xxxx`（`=`前後にスペース不可、ダブルクォート不可）。

#### 既存の Fine-grained PAT を使う場合

Settings > Developer settings > Fine-grained tokens で対象トークンを開き、以下を確認してください:

- 有効期限が切れていないこと
- リポジトリ範囲に `dahatake/RoyalytyService2ndGen` が含まれていること
- 上記の権限が付与されていること

不足がある場合は **Regenerate token** で再生成してください（トークン文字列が変わります）。

#### トークンの動作確認

```bash
gh api user --jq '.login'                                              # トークン有効性
gh api repos/dahatake/RoyalytyService2ndGen --jq '.full_name'          # リポジトリアクセス
python -m hve orchestrate --workflow aas --branch main --dry-run       # SDK dry-run
```

### MCP Server 設定（オプション）

MCP Server を使用する場合は JSON 設定ファイルを作成し、`--mcp-config` で指定します。詳細は [付録A: MCP Server 設定ガイド](#付録a-mcp-server-設定ガイド) を参照してください。

```json
{
  "filesystem": {
    "type": "local",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
    "tools": ["*"]
  },
  "github": {
    "type": "http",
    "url": "https://api.githubcopilot.com/mcp/",
    "headers": {"Authorization": "Bearer ${GH_TOKEN}"},
    "tools": ["*"]
  }
}
```

---

## インタラクティブモード（推奨）

`python -m hve` を引数なしで実行すると、GitHub Copilot CLI スタイルの対話型 wizard が起動します。オプションの知識がなくても、画面のガイドに従うだけでワークフローを実行できます。

### 起動方法

```bash
python -m hve          # 引数なしで wizard 起動
python -m hve run      # 明示的に run サブコマンドを指定（同等）
```

### wizard フロー

wizard は以下の段階で進行します。ステップ 4（モデル選択）の直後に **レビュー/QA サブモデル選択（任意）** と **実行モード選択** が追加されています。

```
┌──────────────────────────────────────────────────────────┐
│  1. ウェルカムバナー表示                                      │
│  2. ワークフロー選択（番号入力）               ← 手動          │
│  3. ステップ選択（カンマ区切り / Enter = 全選択） ← 手動         │
│  4. モデル選択（番号入力）                     ← 手動          │
│  4a. レビュー/QA サブモデル選択（任意）         ← 手動          │
│                                                            │
│  ★ 実行モード選択（番号入力）                 ← 新規追加      │
│     1) クイック全自動  — デフォルト値で即実行（確認あり）          │
│     2) カスタム全自動  — 全設定を手動入力後に自動実行              │
│     3) 手動           — 従来どおり（実行中も対話あり）            │
│                                                            │
│  5. オプション設定       ← 1)スキップ / 2)手動 / 3)手動         │
│  6. ワークフロー固有パラメータ ← 1)必須のみ / 2)手動 / 3)手動   │
│  7. 追加プロンプト      ← 1)スキップ / 2)手動 / 3)手動          │
│  7. 設定サマリー表示 + 実行確認 ← 全モード共通                   │
│  8. ワークフロー実行                                          │
└──────────────────────────────────────────────────────────┘
```

各段階の詳細を以下に説明します。

#### ステップ 1: ウェルカムバナー

起動すると、ボックス装飾付きのウェルカムバナーが表示されます。

```text
╭──────────────────────────────────────────────────────────╮
│  HVE — GitHub Copilot SDK Workflow Orchestrator          │
│  ワークフローをインタラクティブに実行します                    │
╰──────────────────────────────────────────────────────────╯
```

#### ステップ 2: ワークフロー選択

登録されている全ワークフローが番号付きリストで表示されます。番号を入力して選択します。

```text
? ワークフローを選択してください
  1) App Architecture Design (aas — 2 steps)
  2) App Design (aad — 16 steps)
  3) App Dev Microservice Azure (asdw — 24 steps)
  4) Batch Design (abd — 9 steps)
  5) Batch Dev (abdv — 7 steps)
  6) Knowledge Management (akm — 1 step)
  7) Source Codeからのドキュメント作成 (adoc — 23 steps)
> 2
```

#### ステップ 3: ステップ選択

選択したワークフローのステップ一覧が表示されます。実行したいステップの番号をカンマ区切りで入力します。**Enter キーだけ押すと全ステップが選択されます。**

```text
? 実行するステップを選択（Enter = 全16ステップ）
  1) [Step.1.1] ドメイン分析
  2) [Step.1.2] データモデリング
  3) [Step.2] サービス識別
  ...
> 1,2,3      ← カンマ区切りで指定
>            ← Enter のみ = 全ステップ
```

> **AKM の場合**: AKM はステップが 1 つのみのため、ステップ選択はスキップされ自動で全選択されます。

#### ステップ 4: モデル選択

使用する AI モデルを番号で選択します。

```text
? 使用するモデルを選択
  1) Auto
  2) claude-opus-4.7
  3) claude-opus-4.6
  4) claude-sonnet-4.6
  5) gpt-5.4
  6) gpt-5.3-codex
  7) gemini-2.5-pro
> 1
```

> **Auto を選択した場合**: デフォルトモデル（`claude-opus-4.7`）が自動的に使用されます。確認パネルでは `Auto` と表示されます。

#### ステップ 4a: レビュー/QA サブモデル選択（任意）

メインモデル選択後に「レビュー/QA にメインモデルとは別のモデルを使う？」を確認します。

- `No` を選択: レビュー/QA もメインモデルを使用
- `Yes` を選択: レビュー用モデルと QA 用モデルを個別に選択
- メインモデルと同じモデルを選んだ場合は「メインと同じ」扱いになります

#### ステップ 4.5: 実行モード選択（新規追加）

モデル選択の直後に、ワークフロー実行の自動化レベルを選択します。

```text
? 実行モードを選択
  1) クイック全自動  — デフォルト値で即実行（確認あり）
  2) カスタム全自動  — 全設定を手動入力後に自動実行
  3) 手動           — 従来どおり（実行中も対話あり）
> 1
```

##### 3つのモードの比較

| 項目 | クイック全自動 | カスタム全自動 | 手動 |
|------|------------|------------|------|
| ステップ5〜7a の設定 | デフォルト値で自動設定 | 手動入力 | 手動入力 |
| タイムアウトデフォルト | 86400 秒（24時間） | 86400 秒（24時間） | 21600 秒（6時間） |
| 出力レベルデフォルト | `normal` (2) | `compact` (1) | `compact` (1) |
| 実行確認プロンプト | あり（Y/N） | あり（Y/N） | あり（Y/N） |
| 実行中の対話 | なし（全自動） | なし（全自動） | あり |
| 推奨場面 | 素早く実行したい場合 | 設定を細かく制御しつつ長時間放置 | 通常利用 |

##### クイック全自動のデフォルト値

| 設定項目 | 自動設定される値 |
|---------|----------------|
| ベースブランチ | `main` |
| 並列実行数 | `15`（AKM は `1`） |
| 出力レベル | `normal` (2) |
| タイムアウト | `86400` 秒（24時間） |
| ログレベル | `error` |
| QA 自動投入 | OFF |
| Review 自動投入 | OFF |
| Issue 作成 | OFF |
| PR 作成 | OFF |
| Code Review Agent | OFF |
| ドライラン | OFF |
| リポジトリ | `$REPO` 環境変数 または 空 |
| 追加プロンプト | なし |

> **注意**: クイック全自動でも、AKM 以外のワークフローで**必須パラメータ**（`app_id`、`usecase_id` 等）がある場合は、それらの入力のみ求められます。

##### 全自動モード実行時のメッセージ

実行確認後、全自動モードでは以下のメッセージが表示されて自動実行が開始されます：

```text
✓ 全自動モードで実行を開始します。実行中の入力は不要です。
```

**クイック全自動モード**では、これらのオプション設定をスキップして実行されます。カスタム全自動モードおよび手動モードでは、各種オプションを順番に設定します。Y/N のプロンプトでは Enter キーでデフォルト値が適用されます。

```text
? ベースブランチ [main]: main
? 並列実行数 [15]: 15
? Copilot CLI ログレベルを選択
  1) none
  2) error
  3) warning
  4) info
  5) debug
  6) all
> 2
? セッション idle タイムアウト（秒。デフォルト: 21600 = 6時間） [21600]: 21600
? QA 自動投入を有効にする？ [y/N]: N
? Review 自動投入を有効にする？ [y/N]: N
? GitHub Issue を作成する？ [y/N]: y
? GitHub PR を作成する？ [y/N]: ← Issue 作成が Y の場合は自動で ON
? リポジトリ (owner/repo) []: dahatake/MembershipServiceForHVE
? ドライラン（実際の SDK 呼び出しをしない）？ [y/N]: N
```

> **リポジトリ入力について**: 「GitHub Issue を作成する？」または「GitHub PR を作成する？」に `y` と回答した場合のみ、`owner/repo` 形式でリポジトリの入力を求められます。環境変数 `REPO` が設定されている場合はその値がデフォルトとして表示されます。Issue/PR 作成が両方とも OFF の場合、このプロンプトは表示されません。

| 設定項目 | デフォルト | CLI モードでの対応オプション |
|---------|-----------|--------------------------|
| ベースブランチ | `main` | `--branch` |
| 並列実行数 | `15` | `--max-parallel` |
| ログレベル | `error` | `--log-level` |
| タイムアウト | `21600`（6時間） | `--timeout` |
| QA 自動投入 | OFF | `--auto-qa` |
| Review 自動投入 | OFF | `--auto-contents-review` |
| GitHub Issue 作成 | OFF | `--create-issues` |
| GitHub PR 作成 | OFF | `--create-pr` |
| リポジトリ (owner/repo) | `$REPO` または空 | `--repo` |
| ドライラン | OFF | `--dry-run` |

> **AKM ワークフローの場合**: 並列実行数（15 固定）、QA 自動投入（OFF 固定）、Review 自動投入（OFF 固定）のプロンプトはスキップされます。タイムアウト設定は AKM でもスキップされず、全ワークフロー共通で個別設定可能です。

> **各出力レベルで何が表示されるか**: 「コマンドリファレンス」の「コンソール出力レベル詳細」セクションに、各レベルの出力比較テーブルとサンプル出力例を掲載しています。

#### ステップ 6: ワークフロー固有パラメータ

選択したワークフローに固有のパラメータがある場合、自動的にプロンプトが表示されます（全て必須入力）。

```text
# asdw ワークフローの場合（複数 APP-ID 指定可）
? 対象アプリケーション (APP-ID) — カンマ区切りで複数指定可: APP-04, APP-05
? resource_group: rg-dev
? usecase_id: UC-01
```

固有パラメータを持つワークフロー:
- `asdw`: `app_ids`（複数 APP-ID、カンマ区切り）, `resource_group`, `usecase_id`
- `abdv`: `resource_group`, `batch_job_id`
- `akm`: `sources`, `target_files`, `force_refresh`, `custom_source_dir`

> **AKM ワークフローの場合**: 固有パラメータ（sources=qa, target_files=sourcesに応じた全件, force_refresh=true, custom_source_dir=空）はデフォルト値で自動設定され、プロンプトはスキップされます。

> 固有パラメータのないワークフロー（`aas`, `aad`, `abd`）ではこのステップはスキップされます。

パラメータ入力後、追加プロンプト（全 Agent のプロンプトに末尾に追記される文字列）のオプション入力も行えます。

```text
? 追加プロンプト（省略可）: 日本語で出力してください
```

#### ステップ 7: 設定サマリーと実行確認

入力した全設定が一覧パネルとして表示されます。内容を確認し、実行するかどうかを選択します。

```text
┌─ 実行設定 ────────────────────────────────────────┐
│  ワークフロー : App Design (aad)                   │
│  ステップ     : 全ステップ                          │
│  モデル       : claude-opus-4.7                    │
│  ブランチ     : main                               │
│  並列数       : 15                                 │
│  ログレベル   : error                              │
│  タイムアウト  : 21600 秒                          │
│  QA 自動      : OFF                               │
│  Review 自動  : OFF                               │
│  Issue 作成   : ON                                │
│  PR  作成     : ON                                │
│  リポジトリ   : dahatake/MembershipServiceForHVE   │
│  ドライラン   : OFF                                │
└───────────────────────────────────────────────────┘

? この設定で実行しますか？ [Y/n]: Y
```

`N` を選択するとキャンセルされ、プログラムが終了します。

#### ステップ 8: ワークフロー実行

確認後、スピナーアニメーション付きでワークフローが実行されます。実行中は `Ctrl+C` でいつでも中断できます。

### ターミナル要件

| 環境 | 表示 |
|------|------|
| **TTY 接続時**（通常のターミナル） | ANSI カラー + ボックス装飾 + スピナーアニメーション |
| **非 TTY 時**（パイプ / リダイレクト / CI） | プレーンテキスト（ANSI エスケープなし、装飾なし） |

カラー表示の有無はターミナルの TTY 接続状態を自動判定するため、特別な設定は不要です。

### インタラクティブモードと CLI モードの比較

| 項目 | 手動モード | クイック全自動 | カスタム全自動 | CLI モード (`orchestrate`) |
|------|----------|------------|------------|--------------------------|
| 起動方法 | `python -m hve` | `python -m hve` | `python -m hve` | `python -m hve orchestrate --workflow aad ...` |
| 設定方法 | wizard が順番にガイド | デフォルト値を自動適用 | wizard がガイド + 自動実行 | コマンドライン引数で全て指定 |
| 推奨場面 | 初回利用・探索的実行 | 素早く実行したい場合 | 設定を細かく制御しつつ長時間放置 | スクリプト・CI/CD・繰り返し実行 |
| タイムアウトデフォルト | `21600`（6時間） | `86400`（24時間） | `86400`（24時間） | `21600`（6時間） |
| 実行中の対話 | あり | なし | なし | なし |
| ステップ選択 | 画面上で番号選択 | 画面上で番号選択 | 画面上で番号選択 | `--steps Step.1,Step.2` |
| 固有パラメータ | 自動プロンプト表示 | 必須のみプロンプト表示 | 自動プロンプト表示 | `--app-id APP-04` 等を明示指定 |
| GH_TOKEN | Issue/PR 作成時のみ必要 | 同左 | 同左 | 同左 |
| MCP Server | 非対応（CLI モードを使用） | 非対応 | 非対応 | `--mcp-config` で指定 |
| 出力制御 | カラー + 装飾（TTY 自動判定） | カラー + 装飾 | カラー + 装飾 | `--verbose` / `--quiet` で制御 |

> **推奨**: 初めて使用する場合や設定を確認したい場合はインタラクティブモードを使用してください。長時間の実行で放置したい場合は「クイック全自動」または「カスタム全自動」が最適です。繰り返し実行やスクリプト化が必要な場合は CLI モードが適しています。

---

## コマンドリファレンス（CLI モード）

CLI モード（`orchestrate` サブコマンド）は、全てのオプションをコマンドライン引数で指定して実行するモードです。スクリプトや CI/CD パイプラインからの呼び出しに適しています。

### サブコマンド

| サブコマンド | 説明 |
|------------|------|
| （なし） | インタラクティブモードを起動（`run` と同等） |
| `run` | インタラクティブモードを明示的に起動 |
| `orchestrate` | CLI モードでワークフローを実行（全オプションを引数で指定） |

### 基本構文

```bash
python -m hve orchestrate --workflow <WORKFLOW_ID> [OPTIONS]
```

### 最もシンプルな実行

```bash
# インタラクティブモード（wizard が起動）
python -m hve

# CLI モード（ワークフローを直接指定）
python -m hve orchestrate --workflow aad
```

### --dry-run（事前確認）

`--dry-run` を付けると SDK 呼び出し・Issue/PR 作成を行わず、実行計画のみ表示します。初回は必ず使用してください。

```bash
python -m hve orchestrate --workflow aas --branch main --dry-run
```

出力例:
```
[DRY RUN] orchestrate: workflow=aas, branch=main
[DRY RUN] DAG Traversal:
[DRY RUN]   Wave 1: Step.1 (root)
[DRY RUN]   Wave 2: Step.2 (depends_on: Step.1)
[DRY RUN] Would execute: Step.1 - アプリケーション候補の選定
[DRY RUN] Would execute: Step.2 - アプリ一覧（アーキタイプ）概要
[DRY RUN] No SDK calls were made (dry-run mode).
```

### モデル使い分け例（メイン/レビュー/QA）

```bash
# メインタスクは GPT-5.4、レビューは Opus-4.6 で実行
python -m hve orchestrate --workflow aad \
  --model gpt-5.4 --review-model claude-opus-4.7 \
  --auto-contents-review
```

### 全オプション指定例

```bash
# コピーして不要なオプションを削除して使用してください
# ⚠️ --auto-coding-agent-review / --create-issues / --create-pr 使用時は GH_TOKEN が必要です
python -m hve orchestrate \
  --workflow asdw \
  --model claude-opus-4.7 \
  --max-parallel 15 \
  --auto-qa \
  --auto-contents-review \
  --auto-coding-agent-review \
  --auto-coding-agent-review-auto-approval \
  --create-issues \
  --create-pr \
  --repo dahatake/RoyalytyService2ndGen \
  --branch main \
  --app-ids APP-01,APP-02,APP-03 \
  --resource-group rg-dev \
  --usecase-id UC-01 \
  --batch-job-id JOB-01 \
  --steps Step.1,Step.2,Step.3 \
  --mcp-config mcp-servers.json \
  --cli-path /usr/local/bin/copilot \
  --timeout 7200 \
  --review-timeout 7200 \
  --show-stream \
  --log-level info \
  --verbose \
  --dry-run
```

> **行継続文字**: `\` は macOS / Linux / Git Bash 用です。PowerShell は `` ` ``（バッククォート）、コマンドプロンプトは `^` に置き換えるか、1行にまとめてください。
>
> **排他オプション**: `--verbose` と `--quiet` は排他です。

### オプション一覧

#### 基本オプション

| オプション | 説明 | デフォルト値 |
|-----------|------|------------|
| `--workflow`, `-w` | ワークフロー ID（`aas` / `aad` / `asdw` / `abd` / `abdv` / `akm` / `adoc`） | なし（**必須**） |
| `--branch` | ターゲットブランチ名 | `main` |
| `--steps` | 実行ステップをカンマ区切りで指定 | 全ステップ |
| `--dry-run` | 事前確認モード（SDK 呼び出しなし） | `false` |
| `--verbose`, `-v` | 詳細ログ出力（`--verbosity verbose` の省略形） | `true`（`--quiet` 未指定時） |
| `--quiet`, `-q` | 出力抑制（`--verbosity quiet` の省略形） | `false` |
| `--verbosity` | 出力レベルを明示指定（`quiet`/`compact`/`normal`/`verbose`）。指定した場合は `--verbose`/`--quiet` より優先 | `compact` |

#### Agent 実行オプション

| オプション | 説明 | デフォルト値 |
|-----------|------|------------|
| `--model`, `-m` | 使用する AI モデル（`Auto` を指定するとデフォルトモデルが自動選択されます） | `claude-opus-4.7` |
| `--review-model` | 敵対的レビュー（`--auto-contents-review`）および Code Review Agent（`--auto-coding-agent-review`）で使用するモデル（省略時は `--model` と同じ） | `None`（`--model` にフォールバック） |
| `--qa-model` | QA 質問票生成（`--auto-qa`）で使用するモデル（省略時は `--model` と同じ） | `None`（`--model` にフォールバック） |
| `--max-parallel` | 同時実行するステップ数の上限 | `15` |
| `--auto-qa` | 各ステップ後に自動 QA を実行（対話的） | `false` |
| `--auto-contents-review` | 各ステップ後に自動レビューを実行 | `false` |
| `--auto-coding-agent-review` | 全ステップ完了後に Code Review Agent レビューを実行（`--repo` + `GH_TOKEN` 必須） | `false` |
| `--auto-coding-agent-review-auto-approval` | Code Review Agent の修正プランを全て自動承認 | `false` |
| `--timeout` | idle タイムアウト秒数 | `21600`（6時間） |
| `--review-timeout` | Code Review Agent レビュー完了待ちタイムアウト秒数 | `7200`（2時間） |
| `--show-stream` | モデル応答のトークンストリーム表示 | `false` |
| `--log-level` | Copilot CLI のログレベル (`none`/`error`/`warning`/`info`/`debug`/`all`) | `error` |

#### 環境変数

| 環境変数 | 説明 | 既定値 |
|---------|------|--------|
| `GH_TOKEN` | GitHub API 認証トークン（Issue/PR 作成や Code Review Agent 実行時に必要） | なし |
| `GITHUB_TOKEN` | `GH_TOKEN` 未設定時のフォールバックトークン | なし |
| `REPO` | 対象リポジトリ（`owner/repo`） | なし |
| `COPILOT_CLI_PATH` | Copilot CLI 実行ファイルパス | 自動検出 |
| `REVIEW_MODEL` | レビュー用モデルの環境変数既定値（CLI 未指定時に使用） | なし |
| `QA_MODEL` | QA 用モデルの環境変数既定値（CLI 未指定時に使用） | なし |

> **注意**: `--review-model` / `--qa-model` を使って別モデルを指定すると、1ステップあたり最大 3 セッション（メイン + QA + レビュー）が起動する場合があります。
>
> **注意**: GitHub Actions 経路（`@copilot` メンション起動）ではモデル指定はできません。

### コンソール出力レベル詳細（--verbosity / --log-level）

`hve` には **2 つの独立したログ関連パラメータ** があります。それぞれが制御する対象と影響範囲を理解することで、用途に応じた最適な設定が可能になります。

#### --verbosity と --log-level の関係

| 項目 | `--verbosity` | `--log-level` |
|------|--------------|--------------|
| 制御対象 | hve オーケストレーターの出力 | Copilot CLI プロセスの内部ログ |
| デフォルト | `compact`（1） | `error` |
| 影響範囲 | ステップ進捗・ツール実行・Agent 応答・セッション情報 | CLI プロセスの環境読み込み・ファイル操作・検索活動 |

> **注**: `--verbose` / `--quiet` フラグは `--verbosity verbose` / `--verbosity quiet` の省略形。`--verbosity` が明示指定された場合はそちらが優先される。

#### --verbosity 各レベルの出力比較

`console.py` のメソッドごとの振る舞いをソースコードから正確に反映した表です。

| 出力イベント | quiet (0) | compact (1) | normal (2) | verbose (3) |
|------------|-----------|------------|-----------|------------|
| **エラー (error)** | ✅ 常に表示 | ✅ 常に表示 | ✅ 常に表示 | ✅ 常に表示 |
| **警告 (warning)** | 非表示 | ✅ 表示 | ✅ 表示 | ✅ 表示 |
| **セッションエラー** | ✅ 常に表示 | ✅ 常に表示 | ✅ 常に表示 | ✅ 常に表示 |
| **ステップ開始/完了** | 非表示 | ✅ 確定行 | ✅ 確定行 | ✅ 確定行 |
| **実行計画・DAG 進捗** | 非表示 | ✅ 確定行 | ✅ 確定行 | ✅ 確定行 |
| **Wave 開始** | 非表示 | ✅ 確定行 | ✅ 確定行 | ✅ 確定行 |
| **最終サマリー** | 非表示 | ✅ 確定行 | ✅ 確定行 | ✅ 確定行 |
| **ツール実行 (tool)** | 非表示 | スピナー更新 | スピナー更新 | ✅ 確定行 |
| **ツール失敗 (tool_result)** | 非表示 | ✅ 確定行 | ✅ 確定行 | ✅ 確定行 |
| **エージェント意図 (intent)** | 非表示 | スピナー更新 | ✅ 確定行 | ✅ 確定行 |
| **Sub-agent 開始** | 非表示 | スピナー更新 | スピナー更新 | ✅ 確定行 |
| **Sub-agent 完了/失敗** | 非表示 | スピナー更新 | ✅ 確定行 | ✅ 確定行 |
| **Agent 選択** | 非表示 | スピナー更新 | スピナー更新 | ✅ 確定行 |
| **Skill 読み込み** | 非表示 | スピナー更新 | スピナー更新 | ✅ 確定行 |
| **ターン開始/終了** | 非表示 | スピナー更新 / 非表示 | スピナー更新 / 非表示 | ✅ 確定行 |
| **アシスタント応答概要** | 非表示 | スピナー更新 | スピナー更新 | ✅ 確定行 |
| **トークン使用量 (usage)** | 非表示 | スピナー更新 | スピナー更新 | ✅ 確定行 |
| **コンテキスト使用率** | 非表示 | ⚠️ 80%超時のみ確定行 | ⚠️ 80%超時のみ確定行 | ✅ 確定行 |
| **コンテキスト圧縮** | 非表示 | スピナー更新 | スピナー更新 | ✅ 確定行 |
| **タスク完了 (task_complete)** | 非表示 | スピナー更新 | ✅ 確定行 | ✅ 確定行 |
| **セッション終了統計** | 非表示 | ✅ 確定行 | ✅ 確定行 | ✅ 確定行 |
| **パーミッション** | 非表示 | スピナー更新 | スピナー更新 | ✅ 確定行 |
| **並列バッチ (dag_batch)** | 非表示 | 非表示 | 非表示 | ✅ 確定行 |
| **ストリーム表示** | 非表示 | `--show-stream` 時のみ | `--show-stream` 時のみ | `--show-stream` 時のみ |

> **「確定行」と「スピナー更新」の違い**: 確定行はターミナルに行として残り、ログとしてスクロールバックで確認可能。スピナー更新は最終行を上書きし続けるため、最新の状態のみ表示される（TTY 接続時のみ）。

#### --verbosity 各レベルの出力サンプル例

以下のコマンドをベースとした想定出力例です。

```bash
python -m hve orchestrate --workflow aad --branch main --verbosity <LEVEL>
```

**quiet — エラーのみ**:

```text
(正常時は何も表示されません。エラー発生時のみ表示されます)
[14:30:22] ❌ ERROR: Step.1.1 実行中にエラーが発生しました: Session expired
```

**compact — 重要イベントのみ（デフォルト）**:

```text
[14:30:15] ⠋ 🔧 [1.1] bash(1) ruff check src/...     ← スピナー（最終行を上書き）
[14:30:15]   ┊ ● Environment loaded: 22 custom instructions
[14:30:15]   ▶ [Step.1.1] ドメイン分析 (Agent: Arch-Microservice-DomainAnalytics)
[14:30:15]   ── Wave 1/5 ────────────────────────────────────
[14:30:15]   ▸ Step.1.1 ‖ Step.1.2
[14:30:15]   進捗: ████░░░░░░░░░░░░ 4/16 完了 | 実行中 2 | 残り 10
[14:30:15]   ✅ [Step.1.1] success (45.2s) [tokens: in=12500 out=3200 tools=8]
[14:30:15]   📈 [1.1] Stats: +120/-15 lines, 3 files, 5 reqs, 45200ms
  ┌────────────────────────────────────────────────┐
  │ 実行サマリー                                     │
  ├────────────────────────────────────────────────┤
  │ 合計ステップ : 16                                │
  │ ✅ 成功      : 16                               │
  │ ❌ 失敗      : 0                                │
  │ ⏭️  スキップ  : 0                               │
  │ ⏱️  合計時間  : 320.5s                          │
  └────────────────────────────────────────────────┘
```

**normal — compact + intent/subagent**:

```text
[14:30:15]   ┊ ● Environment loaded: 22 custom instructions
[14:30:15]   ┊ ● Read-only remote session
[14:30:15]   ▶ [Step.1.1] ドメイン分析 (Agent: Arch-Microservice-DomainAnalytics)
[14:30:15]   ┊ Phase 1/2: メインタスク
[14:30:16]   💡 [1.1] docs/ 配下のドメイン分析テンプレートを参照します
[14:30:20]   ✅ [1.1] Sub-agent 完了: Arch-Microservice-DomainAnalytics
[14:30:25]   🏁 [1.1] タスク完了: ドメインモデル定義を docs/domain-model.md に出力
[14:30:25]   ┊ Phase 1/2: メインタスク ✓ (10.2s)
[14:30:25]   ✅ [Step.1.1] success (45.2s) [tokens: in=12500 out=3200 tools=8]
[14:30:25]   📈 [1.1] Stats: +120/-15 lines, 3 files, 5 reqs, 45200ms
```

**verbose — 全詳細**:

```text
[14:30:15]   ┊ ● Environment loaded: 22 custom instructions
[14:30:15]   ┊ ● Read-only remote session
[14:30:15]   ┊ ○ List directory docs
[14:30:15]   ┊   └ ".github/agents/Arch-Microservice*"
[14:30:15]   ▶ [Step.1.1] ドメイン分析 (Agent: Arch-Microservice-DomainAnalytics)
[14:30:15]   ┊ Phase 1/2: メインタスク
[14:30:15]   🤖 [1.1] Agent 選択: Arch-Microservice-DomainAnalytics
[14:30:15]   📚 [1.1] Skill: domain-analysis
[14:30:15]   🔄 [1.1] ターン開始
[14:30:16]   💡 [1.1] docs/ 配下のドメイン分析テンプレートを参照します
[14:30:16]   🔧 [1.1] bash(1) ruff check src/
[14:30:16]   ✓ [1.1] ツール完了
[14:30:17]   🔧 [1.1] edit_file(2) docs/domain-model.md
[14:30:17]   ✓ [1.1] ツール完了
[14:30:18]   🔧 [1.1] grep(3) pattern:Entity
[14:30:18]   ✓ [1.1] ツール完了
[14:30:19]   💬 [1.1] 応答 (2450 chars, ツール要求: 2)
[14:30:20]   📊 [1.1] claude-opus-4.7 in=8500 out=2450 3200ms
[14:30:20]   ▶ [1.1] Sub-agent: Arch-Microservice-DomainAnalytics
[14:30:25]   ✅ [1.1] Sub-agent 完了: Arch-Microservice-DomainAnalytics
[14:30:25]   📏 [1.1] Context: 15200/200000 (8%) msgs=12
[14:30:25]   🔄 [1.1] ターン終了
[14:30:25]   🏁 [1.1] タスク完了: ドメインモデル定義を docs/domain-model.md に出力
[14:30:25]   🔐 [1.1] パーミッション要求: file_write
[14:30:25]   🔐 [1.1] パーミッション: approved
[14:30:25]   ┊ Phase 1/2: メインタスク ✓ (10.2s)
[14:30:25]   ✅ [Step.1.1] success (45.2s) [tokens: in=12500 out=3200 tools=8]
[14:30:25]   📈 [1.1] Stats: +120/-15 lines, 3 files, 5 reqs, 45200ms
```

#### --log-level の出力説明

`--log-level` は Copilot CLI プロセスの内部ログ制御であり、hve の `console.cli_log()` メソッド経由で表示されます。ただし表示は `--verbosity` の設定にも依存します。

| log-level | CLI が出力するログの範囲 |
|-----------|----------------------|
| `none` | ログ出力なし |
| `error` | エラーのみ（デフォルト） |
| `warning` | error + 警告 |
| `info` | warning + 情報（Agent ロード、ファイル操作等） |
| `debug` | info + デバッグ詳細（API リクエスト/レスポンス等） |
| `all` | 全ログ出力 |

> **自動昇格**: `--verbosity verbose` かつ `--log-level` が `error` の場合、CLI のログレベルは自動的に `debug` に昇格されます（`error` がデフォルト値のため、`--log-level` 未指定時もこれに含まれます）。

#### 推奨設定ガイド

| 用途 | 推奨設定 |
|------|---------|
| 通常運用 | `--verbosity compact`（デフォルト） |
| 進捗を詳しく確認したい | `--verbosity normal` |
| 問題調査・デバッグ | `--verbosity verbose --log-level debug` |
| CI/CD パイプライン | `--quiet` または `--verbosity quiet` |
| ログファイルに保存 | `--verbosity verbose --log-level all 2>&1 \| tee run.log` |

#### MCP Server・CLI 接続オプション

| オプション | 説明 | デフォルト値 |
|-----------|------|------------|
| `--mcp-config` | MCP Server 設定 JSON ファイルのパス | なし |
| `--cli-path` | Copilot CLI 実行ファイルパス | 自動検出 |
| `--cli-url` | 外部 CLI サーバー URL（`--cli-path` の代わり） | なし |

#### Issue/PR 作成オプション

| オプション | 説明 | デフォルト値 |
|-----------|------|------------|
| `--create-issues` | 実行前に GitHub Issue を作成 | `false` |
| `--create-pr` | 実行後に GitHub PR を作成 | `false` |
| `--repo` | リポジトリ名（`owner/repo` 形式） | `$REPO` 環境変数の値、未設定時は空（`--create-issues` / `--create-pr` / `--auto-coding-agent-review` 使用時は必須） |

> **`$REPO` 環境変数の設定方法**: `--create-issues` または `--create-pr` を使用する場合は `owner/repo` 形式でリポジトリを指定してください。環境変数で設定する場合は以下のコマンドを使用します。
> ```bash
> # macOS / Linux
> export REPO="owner/your-repository-name"
> # Windows PowerShell
> $env:REPO = "owner/your-repository-name"
> ```
> 未設定かつ `--repo` オプションも省略された場合、`--create-issues` / `--create-pr` 使用時はエラーになります。

#### その他のオプション

> **注**: 以下は主要な追加オプションです。完全なオプション一覧は `python -m hve orchestrate --help` で確認してください。

| オプション | 説明 | デフォルト値 |
|-----------|------|------------|
| `--ignore-paths` | `git add` 時に除外するパス（スペース区切りで複数指定可） | `docs images infra qa src test work` |
| `--additional-prompt` | 全 Custom Agent のプロンプト末尾に追記する文字列 | なし |
| `--issue-title` | Root Issue 作成時のタイトルを上書き | ワークフロー名から自動生成 |

#### ワークフロー固有オプション

| オプション | 説明 | 対応ワークフロー |
|-----------|------|--------------|
| `--app-ids` | アプリケーション ID（カンマ区切りで複数指定可。例: `APP-01,APP-02,APP-03`） | `asdw` |
| `--app-id` | アプリケーション ID（例: `APP-04`。後方互換のため残す。複数指定は `--app-ids` を推奨） | `asdw` |
| `--resource-group` | Azure リソースグループ名（例: `rg-dev`） | `asdw`, `abdv` |
| `--usecase-id` | ユースケース ID（例: `UC-01`） | `asdw` |
| `--batch-job-id` | バッチジョブ ID（カンマ区切り可。例: `JOB-01,JOB-02`） | `abdv` |
| `--scope` | 分類対象スコープ (`all` / `specified`、省略時は `all`) | `akm` |
| `--target-files` | 対象ファイルパス（スペース区切り、省略時は `qa/*.md`） | `akm` |
| `--force-refresh` / `--no-force-refresh` | 既存 status.md を完全に再生成（デフォルト: 有効） | `akm` |

### 使い方の例

#### 基本実行

```bash
python -m hve orchestrate --workflow aad
```

#### QA + Review 有効

```bash
python -m hve orchestrate \
  --workflow aad \
  --branch main \
  --auto-qa \
  --auto-contents-review
```

> QA 有効時はステップごとにユーザーの回答入力が求められる対話的な実行になります。

#### MCP Server 付き実行

```bash
python -m hve orchestrate \
  --workflow aad \
  --branch main \
  --mcp-config mcp-servers.json
```

#### Issue/PR 作成有効

```bash
python -m hve orchestrate \
  --workflow aas \
  --branch main \
  --repo dahatake/RoyalytyService2ndGen \
  --create-issues \
  --create-pr
```

> `GH_TOKEN` が必要です。`--create-issues` または `--create-pr` を指定している状態で `GH_TOKEN` が未設定の場合、前提条件エラーとしてコマンドは終了します。

#### 複数 APP-ID 指定（ASDW）

```bash
# 複数の APP-ID をカンマ区切りで指定
python -m hve orchestrate \
  --workflow asdw \
  --app-ids APP-01,APP-02,APP-03 \
  --resource-group rg-dev \
  --usecase-id UC-01

# 単一 APP-ID（後方互換、--app-ids 推奨）
python -m hve orchestrate \
  --workflow asdw \
  --app-id APP-01 \
  --resource-group rg-dev
```

> **2度目実行時の既存成果物再利用**: ワークフロー実行開始時に `docs/`・`src/`・`test/`・`knowledge/` 配下の既存成果物が自動検出されます。既存成果物が見つかった場合、「既存成果物を検出しました（N 件）。再利用モードで実行します。」と表示され、各ステップのプロンプトに再利用ルールが追記されます。Catalog ファイルは既存エントリを保持したまま新規エントリが追加されます。

#### Code Review Agent 有効

```bash
python -m hve orchestrate \
  --workflow aad \
  --branch main \
  --auto-coding-agent-review \
  --repo dahatake/RoyalytyService2ndGen
```

自動承認を有効にする場合は `--auto-coding-agent-review-auto-approval` を追加してください。

> **前提**: `GH_TOKEN` + `--repo` が必須。Agent の成果物がリモートブランチに push されている必要があります。

---

## ワークフロー一覧

### 逆引き表

| やりたいこと | ワークフロー | コマンド |
|------------|------------|---------|
| アプリケーションアーキテクチャ設計 | `aas` | `python -m hve orchestrate --workflow aas` |
| アプリケーション設計 | `aad` | `python -m hve orchestrate --workflow aad` |
| Azure Web アプリ実装 | `asdw` | `python -m hve orchestrate --workflow asdw --app-ids APP-01,APP-02 --resource-group rg-dev --usecase-id UC-01` |
| バッチ設計 | `abd` | `python -m hve orchestrate --workflow abd` |
| バッチ実装 | `abdv` | `python -m hve orchestrate --workflow abdv --resource-group rg-batch --batch-job-id JOB-01` |
| QA Knowledge ドキュメント管理 | `akm` | `python -m hve orchestrate --workflow akm` |
| Original Docs 取り込み | `akm` | `python -m hve orchestrate --workflow akm` |
| Source Codeからのドキュメント作成 | `adoc` | `python -m hve orchestrate --workflow adoc --target-dirs src/,hve/ --doc-purpose all` |

> **ヒント**: インタラクティブモード（`python -m hve`）では、上記のワークフローが番号付きメニューとして表示されます。ワークフロー固有のオプション（`--app-ids` 等）も wizard 内で自動的にプロンプトされるため、コマンドを暗記する必要はありません。

### 各ワークフローの詳細

#### aas — App Architecture Design（アプリケーションアーキテクチャ設計）

| 項目 | 内容 |
|------|------|
| **目的** | ユースケース一覧からアプリケーションアーキテクチャを自動設計 |
| **前提条件** | `users-guide/01-business-requirement.md` 等の要求定義が存在すること |
| **ステップ数** | 2 |
| **固有オプション** | なし |

#### aad — App Design（アプリケーション設計）

| 項目 | 内容 |
|------|------|
| **目的** | ドメイン分析・データモデル・サービスカタログ等の設計を自動実行 |
| **前提条件** | `aas` ワークフローによるアプリケーションアーキテクチャ設計が完了していること |
| **ステップ数** | 16 |
| **固有オプション** | なし |

#### asdw — App Dev Microservice Azure（Azure Web アプリ実装）

| 項目 | 内容 |
|------|------|
| **目的** | Azure マイクロサービスの実装・デプロイを自動実行 |
| **前提条件** | `aad` ワークフローによる設計が完了していること |
| **ステップ数** | 24 |
| **固有オプション** | `--app-ids`（推奨）または `--app-id`（後方互換）、`--resource-group`（必須）, `--usecase-id`（必須） |

#### abd — Batch Design（バッチ設計）

| 項目 | 内容 |
|------|------|
| **目的** | バッチ処理の設計（ドメイン分析・データソース分析・ジョブカタログ等）を自動実行 |
| **前提条件** | `aad` ワークフローによる設計が完了していること |
| **ステップ数** | 9 |
| **固有オプション** | なし |

#### abdv — Batch Dev（バッチ実装）

| 項目 | 内容 |
|------|------|
| **目的** | バッチジョブの実装・デプロイを自動実行 |
| **前提条件** | `abd` ワークフローによる設計が完了していること |
| **ステップ数** | 7 |
| **固有オプション** | `--resource-group`（必須）, `--batch-job-id`（必須、カンマ区切り可） |

#### akm — QA Knowledge Management（QA Knowledge ドキュメント管理）

| 項目 | 内容 |
|------|------|
| **目的** | `qa/` の質問ファイルを D01〜D21 に分類し、`knowledge/business-requirement-document-status.md` を生成・更新。QA マッピングが存在する D クラスごとに `knowledge/D{NN}-<文書名>.md` を個別生成 |
| **前提条件** | `qa/` 配下に `.md` ファイルが存在し、`template/business-requirement-document-master-list.md` が存在すること |
| **ステップ数** | 1（Agent 内部で 9 ステップを順次処理） |
| **固有オプション** | `--scope`（省略時は `all`）, `--target-files`（省略時は `qa/*.md`）, `--force-refresh` / `--no-force-refresh`（デフォルト: 有効） |

**実行例:**

```bash
# デフォルト設定で実行（scope=all, target_files=qa/*.md, force_refresh=true）
python -m hve orchestrate --workflow akm

# 指定ファイルのみ分類
python -m hve orchestrate --workflow akm --scope specified \
  --target-files qa/AAS-Step1-context-review.md qa/AAD-Step1-2-service-list-context-review.md

# 増分更新（force_refresh を無効化）
python -m hve orchestrate --workflow akm --no-force-refresh
```

> **`work/` フォルダーの扱い**: AKM の主成果物は `knowledge/business-requirement-document-status.md` に出力されます。`--create-pr` を使用する際、`work` を `--ignore-paths` で除外リストから外す必要があるのは、`work/` 配下の中間成果物も PR に含めたい場合のみです。なお、`qa` はデフォルトの `ignore_paths` に含まれています（`docs images infra qa src test work`）。

#### akm — Original Docs Import（original-docs 取り込み）

| 項目 | 内容 |
|------|------|
| **目的** | `original-docs/` の原本ドキュメントを D01〜D21 に分類し、`knowledge/` を更新 |
| **前提条件** | `original-docs/` 配下の入力ファイルと `template/business-requirement-document-master-list.md` が存在すること |
| **ステップ数** | 1 |
| **固有オプション** | `--scope`（省略時は `all`）, `--target-files`（省略時は `original-docs/*`）, `--force-refresh` / `--no-force-refresh` |

#### adoc — Source Codeからのドキュメント作成（アプリ文書生成）

| 項目 | 内容 |
|------|------|
| **目的** | ソースコードを段階分析し `docs-generated/` 配下へ技術文書を生成 |
| **前提条件** | 対象コードがブランチ上に存在し、`docs-generated/` への書き込み権限があること |
| **ステップ数** | 23（コンテナステップ含む） |
| **固有オプション** | `--target-dirs`, `--exclude-patterns`, `--doc-purpose`（`all`/`onboarding`/`refactoring`/`migration`）, `--max-file-lines` |

---

## 付録A: MCP Server 設定ガイド

### Local/Stdio サーバー

ローカルのコマンドを起動して MCP Server として使用します。

```json
{
  "filesystem": {
    "type": "local",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
    "tools": ["*"]
  },
  "custom-tool": {
    "type": "local",
    "command": "python",
    "args": ["-m", "my_mcp_server"],
    "env": {
      "MY_API_KEY": "${MY_API_KEY}"
    },
    "tools": ["search", "fetch_data"]
  }
}
```

| フィールド | 説明 |
|----------|------|
| `type` | `"local"` を指定 |
| `command` | 起動コマンド（`npx`, `python`, `node` 等） |
| `args` | コマンドの引数リスト |
| `env` | 環境変数（`${VAR}` 形式で参照可能） |
| `tools` | 使用するツール名のリスト。`["*"]` で全許可 |

### Remote HTTP/SSE サーバー

外部の HTTP エンドポイントに接続します。

```json
{
  "github": {
    "type": "http",
    "url": "https://api.githubcopilot.com/mcp/",
    "headers": {
      "Authorization": "Bearer ${GH_TOKEN}"
    },
    "tools": ["*"]
  }
}
```

| フィールド | 説明 |
|----------|------|
| `type` | `"http"` を指定 |
| `url` | MCP Server の URL |
| `headers` | HTTP ヘッダー（認証トークン等） |
| `tools` | 使用するツール名のリスト |

### Agent 固有の MCP Server

ワークフロー定義（`workflow_registry`）で特定のステップにのみ MCP Server を適用できます。詳細は [付録B](#付録b-custom-agents-設定ガイド) を参照してください。

---

## 付録B: Custom Agents 設定ガイド

### workflow_registry の custom_agent フィールド

ワークフロー定義でステップごとに `custom_agent` を指定します。

```python
WORKFLOW_REGISTRY = {
    "aad": {
        "steps": [
            {
                "id": "Step.1.1",
                "title": "ドメイン分析",
                "custom_agent": "Arch-Microservice-DomainAnalytics",
                "depends_on": []
            },
            {
                "id": "Step.1.2",
                "title": "データモデリング",
                "custom_agent": "Arch-DataModeling",
                "depends_on": ["Step.1.1"]
            }
        ]
    }
}
```

`custom_agent` に指定した名前が `.github/agents/*.agent.md` の Agent 定義ファイル名に対応します。

### Agent の選択優先順位

1. ステップ固有の `custom_agent`（workflow_registry で定義）
2. デフォルト Agent（Copilot SDK のデフォルト）

---

## 付録C: DAG 並列実行と Post-step 自動プロンプト

### DAG 並列実行

ワークフローの各ステップは DAG（有向非巡回グラフ）として管理され、依存関係を解決しながら `asyncio.Semaphore(max_parallel)` で並列実行されます。

| パターン | 説明 | 例 |
|---------|------|-----|
| sequential | 前ステップ完了後に次が開始 | Step.1 → Step.2 |
| fork | 1ステップ完了後に複数が並列開始 | Step.6 → Step.7.1 ‖ Step.7.2 |
| AND join | 複数ステップがすべて完了後に次が開始 | Step.7.1 AND Step.7.2 → Step.7.3 |
| skip fallback | 条件不一致時にスキップ | skip_if 条件に合致 → スキップ |

> メモリ不足が発生する場合は `--max-parallel` を小さくしてください（例: `--max-parallel 3`）。

### Post-step 自動プロンプト（QA / Review）

| フラグ | 動作 |
|--------|------|
| なし | メインタスクのみ実行 |
| `--auto-qa` のみ | メインタスク → QA → ユーザー回答 |
| `--auto-contents-review` のみ | メインタスク → Review |
| 両方 | メインタスク → QA → ユーザー回答 → Review |

> **インタラクティブモードでの設定**: wizard 内で「QA 自動投入を有効にする？ [y/N]」「Review 自動投入を有効にする？ [y/N]」と順番に確認されます。CLI モードの `--auto-qa` / `--auto-contents-review` フラグに相当します。

### Code Review Agent フェーズ（`--auto-coding-agent-review`）

全ステップ完了後: Root Issue 作成 → ブランチ作成 → 全ステップ実行 → PR 作成 → Code Review Agent レビュー依頼 → レビュー完了ポーリング（デフォルト 7200秒） → 修正プロンプト

---

## 付録D: トラブルシューティング

### Copilot CLI が見つからない

```
エラーメッセージ: command not found: copilot
```

[公式ドキュメント](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli)に従ってインストールし、`copilot --version` で確認してください。PATH 上の場所は `which copilot`（macOS/Linux）または `where copilot`（Windows）で確認できます。

### SDK がインストールされていない / `python -m hve` が動かない

```
エラーメッセージ: ModuleNotFoundError: No module named 'copilot'
```

仮想環境が有効化されていることを確認し、`pip install github-copilot-sdk` を実行してください。`pip show github-copilot-sdk` でインストール状態を確認できます。

### セッションタイムアウト

```
エラーメッセージ: Session expired. Please re-authenticate.
```

`gh auth logout` → `gh auth login` で再認証してください。長時間実行時は `--max-parallel` を小さくすることで実行時間を短縮できます。

### MCP Server が接続できない

```
エラーメッセージ: Failed to connect to MCP server: filesystem
```

**Local/Stdio の場合**: `npx --version` で npx が使えることを確認し、設定ファイルの JSON 構文を `python -m json.tool < mcp-servers.json` で検証してください。

**Remote HTTP の場合**: URL の正しさ、ネットワーク疎通（`curl <URL>`）、認証トークンの正しさを確認してください。

### 並列実行でメモリ不足

```
エラーメッセージ: MemoryError / OSError: [Errno 12] Cannot allocate memory
```

`--max-parallel` を小さくして実行してください（例: `--max-parallel 3`）。

### PR 作成時に HTTP 422 エラー

```
PR 作成に失敗しました (HTTP 422)
原因: ブランチ間に差分が存在しない可能性があります。
```

Agent の成果物がリモートブランチに push されているか確認してください。`git log --oneline` でコミットが存在することを確認してください。

### `--auto-coding-agent-review` で前提条件エラー

```
❌ --auto-coding-agent-review の前提条件が満たされていません
```

`GH_TOKEN` 環境変数と `--repo` オプションの両方が設定されているか確認してください。

### デバッグ情報を増やしたい

Copilot CLI の内部ログを詳細に出力するには `--log-level debug` を指定します。

```bash
python -m hve orchestrate -w aad --log-level debug
```

有効な値は `none` / `error`（デフォルト）/ `warning` / `info` / `debug` / `all` です。問題の切り分け時に `debug` または `all` を使い、通常運用では `error` のままにしてください。

> **`--verbosity` との併用**: `--log-level debug` は Copilot CLI プロセスのログ詳細度のみを制御します。hve オーケストレーター自体の出力を増やすには `--verbosity verbose` も併用してください。最大の情報量で問題調査するコマンド例:
> ```bash
> python -m hve orchestrate -w aad --verbosity verbose --log-level debug
> ```

### インタラクティブモードが起動せず orchestrate のヘルプが表示される

`python -m hve` を実行した際に `orchestrate` サブコマンドのヘルプが表示される場合は、`hve/` パッケージが古い可能性があります。`hve/__main__.py` が最新版であることを確認してください。

### ターミナルでカラー表示が崩れる / 文字化けする

ANSI エスケープシーケンスに対応していないターミナルでは表示が崩れることがあります。以下を確認してください:

- **Windows**: Windows Terminal または PowerShell 7+ を推奨。古い `cmd.exe` では ANSI 非対応の場合があります
- **パイプ/リダイレクト時**: `python -m hve | tee log.txt` のように TTY 非接続環境ではカラー出力が自動的に無効化されます
- **CI/CD 環境**: 非 TTY のため自動でプレーンテキスト出力になります。CI では `orchestrate` サブコマンドの使用を推奨します

---

## 付録E: セキュリティ・SSO・関連リンク

### セキュリティ上の注意事項

| 注意事項 | 説明 |
|---------|------|
| **トークンをコードにハードコードしない** | `.env` ファイルや環境変数で管理し、Git にコミットしないでください |
| **`.gitignore` に追加** | `.env` ファイルを使う場合は `.gitignore` に含めてください |
| **有効期限を設定する** | 無期限トークンは避け、90日以内を推奨します |
| **不要になったら削除する** | Settings > Developer settings > Personal access tokens から削除できます |
| **漏洩した場合は即座に無効化** | トークンが漏洩した場合は、同画面から **Delete** で即座に無効化してください |

### SAML SSO が有効な組織の場合

組織で SAML シングルサインオンが有効になっている場合は、トークン作成後に **SSO 認証** が必要です。

1. **Settings** > **Developer settings** > **Personal access tokens** に移動
2. 対象トークンの横にある **Configure SSO** をクリック
3. 対象組織の **Authorize** をクリック

詳細: [Authorizing a personal access token for use with SAML single sign-on](https://docs.github.com/en/enterprise-cloud@latest/authentication/authenticating-with-saml-single-sign-on/authorizing-a-personal-access-token-for-use-with-saml-single-sign-on)

### 関連リンク

| リソース | URL |
|---------|-----|
| 利用ガイド（README） | [README.md](../README.md) |
| GitHub Copilot SDK（リポジトリ） | https://github.com/github/copilot-sdk |
| SDK Getting Started | https://github.com/github/copilot-sdk/blob/main/docs/getting-started.md |
| Custom Agents ドキュメント | https://github.com/github/copilot-sdk/blob/main/docs/features/custom-agents.md |
| MCP Servers ドキュメント | https://github.com/github/copilot-sdk/blob/main/docs/features/mcp.md |
| Copilot CLI インストールガイド | https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli |
| Model Context Protocol（MCP）仕様 | https://modelcontextprotocol.io/ |
| Code Review Agent ドキュメント | https://docs.github.com/en/copilot/using-github-copilot/code-review/using-copilot-code-review |

### knowledge/ ディレクトリの参照

SDK 版でワークフローを実行する際も、`knowledge/` フォルダーの業務要件ドキュメント（D01〜D21）が存在する場合、各 Custom Agent が自動参照します。SDK 版での `knowledge-management` ワークフロー実行:

```bash
python -m hve orchestrate --workflow akm
```

`knowledge/` ファイルが存在すると、以降の設計・実装ワークフロー（`aas`, `aad`, `asdw` 等）での設計品質が向上します。詳細は [km-guide.md](./km-guide.md) を参照してください。
