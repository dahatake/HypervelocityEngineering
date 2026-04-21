# .github/scripts — CLI コマンド（Bash / PowerShell）

GitHub API 操作を行う CLI コマンド群。Bash / PowerShell で提供する。

## 前提条件

| ツール | バージョン | 用途 |
|--------|-----------|------|
| `gh` | 2.0+ | GitHub CLI（API 呼び出し） |
| `jq` | 1.6+ | JSON パース（Bash のみ） |
| `bash` | 4.0+ | Bash スクリプト実行 |
| `pwsh` (PowerShell) | 7.0+ | PowerShell スクリプト実行 |
| `shellcheck` | 0.8+ | Bash 静的解析（テスト・CI） |
| `Pester` | 5.0+ | PowerShell テストフレームワーク（テスト・CI） |
| `PSScriptAnalyzer` | 1.20+ | PowerShell 静的解析（テスト・CI） |

## ディレクトリ構成

```
.github/scripts/
├── README.md                   ← このファイル
├── bash/
│   ├── run-workflow.sh         ← Bash エントリポイント
│   ├── orchestrate.sh          ← ワークフローオーケストレーション
│   ├── advance.sh              ← 完了 Issue → 次ステップ遷移
│   ├── create-subissues.sh     ← Sub-Issue 一括作成
│   ├── validate-plan.sh        ← plan.md バリデーション
│   └── lib/
│       ├── gh-api.sh           ← GitHub REST API ユーティリティ
│       ├── copilot-assign.sh   ← Copilot GraphQL アサイン
│       ├── issue-parser.sh     ← Issue body パーサー
│       └── workflow-registry.sh← ワークフロー DAG レジストリ
├── powershell/
│   ├── run-workflow.ps1        ← PowerShell エントリポイント
│   ├── orchestrate.ps1         ← ワークフローオーケストレーション
│   ├── advance.ps1             ← 完了 Issue → 次ステップ遷移
│   ├── create-subissues.ps1    ← Sub-Issue 一括作成
│   ├── validate-plan.ps1       ← plan.md バリデーション
│   ├── lib/
│   │   ├── gh-api.ps1
│   │   ├── copilot-assign.ps1
│   │   ├── issue-parser.ps1
│   │   └── workflow-registry.ps1
│   └── tests/
│       ├── commands.Tests.ps1
│       ├── copilot-assign.Tests.ps1
│       ├── gh-api.Tests.ps1
│       ├── issue-parser.Tests.ps1
│       └── workflow-registry.Tests.ps1
└── tests/
    ├── test-bash.sh            ← Bash dry-run テスト
    ├── test-powershell.ps1     ← PowerShell Pester テスト
    └── fixtures/
        ├── sample-plan.md      ← テスト用 plan.md
        └── sample-subissues.md ← テスト用 subissues.md
```

## コマンド一覧（Bash / PowerShell 対照表）

| コマンド | Bash | PowerShell | 説明 |
|----------|------|------------|------|
| エントリポイント | `run-workflow.sh` | `run-workflow.ps1` | 全サブコマンドのディスパッチャー |
| orchestrate | `orchestrate.sh --workflow aas --model claude-opus-4.7 --dry-run` | `orchestrate.ps1 -Workflow aas -Model claude-opus-4.7 -DryRun` | ワークフロー実行（Issue 一括作成 + Copilot アサイン） |
| advance | `advance.sh --issue 123 --dry-run` | `advance.ps1 -Issue 123 -DryRun` | 完了 Issue → 次ステップ遷移 |
| create-subissues | `create-subissues.sh --file subs.md --parent-issue 100 --dry-run` | `create-subissues.ps1 -File subs.md -ParentIssue 100 -DryRun` | Sub-Issue 一括作成 |
| validate-plan | `validate-plan.sh --path plan.md` | `validate-plan.ps1 -Path plan.md` | plan.md メタデータ検証 |

## 環境変数一覧

| 変数名 | 説明 | 必須 |
|--------|------|------|
| `GH_TOKEN` / `GITHUB_TOKEN` | GitHub 認証トークン | ✅（API 呼び出し時） |
| `REPO` | リポジトリ名 `owner/repo` 形式 | ✅（または `--repo` 引数） |
| `COPILOT_PAT` | Copilot アサイン用 PAT | Copilot アサイン時のみ |
| `MODEL` | Copilot モデル指定（省略時は空文字 = GitHub 管理既定） | 省略可 |
| `DRY_RUN` | `1` で dry-run モード（Bash）| 省略可（`--dry-run` 推奨） |

## 使用例

### ワークフロー別

#### 1. ワークフローオーケストレーション（orchestrate）

```bash
# Bash — AAS ワークフロー（dry-run で計画確認）
cd .github/scripts/bash
./orchestrate.sh --workflow aas --dry-run

# Bash — モデルを明示指定
./orchestrate.sh --workflow aas --model claude-opus-4.7 --dry-run

# Bash — AAD ワークフロー（ステップ選択）
./orchestrate.sh --workflow aad --steps 1.1,1.2 --dry-run

# Bash — run-workflow.sh 経由
./run-workflow.sh --workflow aas --dry-run
```

```powershell
# PowerShell — AAS ワークフロー（dry-run で計画確認）
cd .github/scripts/powershell
.\orchestrate.ps1 -Workflow aas -DryRun

# PowerShell — モデルを明示指定
.\orchestrate.ps1 -Workflow aas -Model claude-opus-4.7 -DryRun

# PowerShell — AAD ワークフロー（ステップ選択）
.\orchestrate.ps1 -Workflow aad -Steps "1.1,1.2" -DryRun

# PowerShell — run-workflow.ps1 経由
.\run-workflow.ps1 -Workflow aas -DryRun
```

#### 2. 完了 → 次ステップ遷移（advance）

```bash
# Bash
./run-workflow.sh advance --issue 123 --dry-run
# or
./advance.sh --issue 123 --dry-run
```

```powershell
# PowerShell
.\run-workflow.ps1 -Action advance -Issue 123 -DryRun
# or
.\advance.ps1 -Issue 123 -DryRun
```

#### 3. Sub-Issue 一括作成（create-subissues）

```bash
# Bash
./run-workflow.sh create-subissues --file work/subissues.md --parent-issue 100 --dry-run
```

```powershell
# PowerShell
.\run-workflow.ps1 -Action create-subissues -File work/subissues.md -ParentIssue 100 -DryRun
```

#### 4. plan.md バリデーション（validate-plan）

```bash
# Bash — 単一ファイル
./validate-plan.sh --path work/Issue-123/plan.md

# Bash — ディレクトリ再帰
./validate-plan.sh --directory work/
```

```powershell
# PowerShell — 単一ファイル
.\validate-plan.ps1 -Path work/Issue-123/plan.md

# PowerShell — ディレクトリ再帰
.\validate-plan.ps1 -Directory work/
```

### `--dry-run` モード

すべての書き込み系コマンドは `--dry-run`（Bash）/ `-DryRun`（PowerShell）をサポート:

| コマンド | dry-run 時の動作 |
|----------|------------------|
| orchestrate | 実行計画（ステップ一覧・スキップ対象）を表示。API 呼び出しなし |
| advance | 次ステップの特定・表示のみ。ラベル付与・Copilot アサインはスキップ |
| create-subissues | ブロック分割結果（タイトル・依存関係・Agent）を表示。Issue 作成なし |
| validate-plan | オフラインバリデーション（常に dry-run 相当） |

> **dry-run 出力の互換性**: Bash / PowerShell ともに同一フォーマットの dry-run 出力を生成する。

## サポートするワークフロー

| ID | 名称 | ステップ数 |
|----|------|-----------|
| `aas` | App Architecture Design | 2 |
| `aad` | App Detail Design | 16 |
| `asdw` | App Dev (Microservice Azure) | 24 |
| `abd` | Batch Design | 9 |
| `abdv` | Batch Dev | 7 |

## テスト実行

### Bash テスト

```bash
# dry-run テスト（shellcheck + 出力検証）
bash .github/scripts/tests/test-bash.sh

# shellcheck 単体
shellcheck -S warning .github/scripts/bash/*.sh .github/scripts/bash/lib/*.sh
```

### PowerShell テスト

```powershell
# Pester テスト（共通 fixture ベース）
Import-Module Pester
$config = New-PesterConfiguration
$config.Run.Path = '.github/scripts/tests/test-powershell.ps1'
Invoke-Pester -Configuration $config

# 既存コマンドテスト
$config = New-PesterConfiguration
$config.Run.Path = '.github/scripts/powershell/tests'
Invoke-Pester -Configuration $config

# PSScriptAnalyzer 単体
Import-Module PSScriptAnalyzer
Invoke-ScriptAnalyzer -Path '.github/scripts/powershell/*.ps1' -Severity Warning,Error
Invoke-ScriptAnalyzer -Path '.github/scripts/powershell/lib/*.ps1' -Severity Warning,Error
```

### CI

`.github/workflows/test-cli-scripts.yml` で以下を自動実行:

| ジョブ | OS | 内容 |
|--------|----|------|
| `bash-tests` | `ubuntu-latest` | shellcheck 静的解析 + `test-bash.sh` |
| `powershell-tests` | `windows-latest` | PSScriptAnalyzer + Pester テスト |
| `powershell-ubuntu` | `ubuntu-latest` | PSScriptAnalyzer + Pester テスト（クロスプラットフォーム） |

## Copilot CLI 統合ロードマップ

### Phase 1: 現状（完了）
- [x] Bash CLI（`.github/scripts/bash/`）— 全コマンド
- [x] PowerShell CLI（`.github/scripts/powershell/`）— 全コマンド
- [x] CI ワークフロー（`.github/workflows/test-cli-scripts.yml`）

### Phase 2: Copilot CLI ラッパー（計画中）
- [ ] `run-workflow.sh copilot "プロンプト"` でプロンプト駆動のワークフロー選択
- [ ] Copilot Agent Mode から直接呼び出し可能な MCP ツール定義
- [ ] VS Code タスク定義（`.vscode/tasks.json`）との統合

### Phase 3: GitHub Copilot Extensions（将来）
- [ ] Copilot Chat Extension として CLI コマンドを公開
- [ ] `@workflow orchestrate aas --dry-run` のような自然言語インターフェース
- [ ] ワークフロー実行状況の Copilot Chat 表示
