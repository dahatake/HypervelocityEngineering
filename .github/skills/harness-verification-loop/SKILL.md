---
name: harness-verification-loop
description: "§10.1 検証ループの詳細手順。各言語（C#/Python/Shell）× 各 Phase（Build/Lint/Test/Security/Diff）の具体的コマンドライン、Phase 失敗時の対処法、verification-report.md テンプレートを提供する。"
---

# harness-verification-loop

## 目的

AGENTS.md §10.1 で定義した5段階検証パイプラインの **実行手順と具体的コマンド** を提供する。

---

## §1 Phase 別コマンドリファレンス

### Phase 1: Build（構文・コンパイルチェック）

| 言語 | コマンド | 成功条件 |
|---|---|---|
| C# | `dotnet build --no-restore` | exit code 0、error 行なし |
| Python | `python -m py_compile {ファイルパス}` または `python -m compileall {ディレクトリ}` | exit code 0 |
| Shell | `bash -n {スクリプトパス}` | exit code 0 |
| JSON/YAML | `python -c "import json,sys; json.load(open('{file}'))"` | exit code 0 |

**失敗時の一般的な原因と対処**:
- C#: 参照パッケージ不足 → `dotnet restore` を先に実行
- Python: インデントエラー / 構文ミス → エラーメッセージの行番号を確認して修正
- Shell: 未対応の構文 → `#!/bin/bash` シバン確認、`[[` 等の bash 固有構文の誤用確認

---

### Phase 2: Lint（静的解析）

| 言語 | コマンド | 成功条件 |
|---|---|---|
| C# | `dotnet format --verify-no-changes` | exit code 0 |
| Python | `ruff check .` | 警告・エラー 0 件 |
| Shell | `shellcheck {スクリプトパス}` | 警告・エラー 0 件 |
| Markdown | `markdownlint "**/*.md"` | エラー 0 件（利用可能な場合） |

**ツールが利用できない場合**: `SKIP(ツール未インストール)` として記録し、次 Phase に進む。

**失敗時の一般的な原因と対処**:
- C#: フォーマット差異 → `dotnet format` を実行して自動修正
- Python: `ruff check --fix .` で自動修正可能な項目を修正
- Shell: shellcheck の指摘に従い、引用符・変数展開・リダイレクトを修正

---

### Phase 3: Test（テスト実行）

| 言語 | コマンド | 成功条件 |
|---|---|---|
| C# | `dotnet test --no-build --verbosity normal` | 全テスト PASS、失敗 0 件 |
| Python | `pytest -x --tb=short` | 全テスト PASS、`-x` で最初の失敗で停止 |
| Shell | スクリプト固有の検証手段（bats 等） | exit code 0 |

**失敗時の一般的な原因と対処**:
- テストが存在しない場合: `SKIP(テストファイルなし)` として記録
- 環境依存（DB 接続等）の失敗: `SKIP(環境依存 - ローカル実行不可)` として記録
- ロジックエラー: スタックトレースを確認し、実装コードを修正

---

### Phase 4: Security Scan（秘密情報検出）

```bash
# 秘密情報パターン検出
grep -rnE \
  -e "sk-" \
  -e "password=" \
  -e "connectionstring=" \
  -e "Bearer " \
  -e "api[_-]?key" \
  --include="*.cs" --include="*.py" --include="*.sh" \
  --include="*.json" --include="*.yaml" --include="*.yml" \
  --include="*.env" \
  . 2>/dev/null | grep -v ".git/"
```

**判定基準**:
- 検出 0 件 → PASS
- 検出あり → 内容を確認する
  - テストデータ/モックのみ → `PASS(テストデータのみ - ホワイトリスト確認済み)` として記録
  - 実際の秘密情報 → **即時停止**。§10.2 安全ガードの HIGH レベル処理を適用

**除外対象（ホワイトリスト）**:
- `*.test.*`, `*.spec.*`, `test/`, `tests/` 配下のモック値
- `password=your-password-here` 等のプレースホルダー
- コメント行内の説明テキスト

---

### Phase 5: Diff Review（変更差分確認）

```bash
# 変更サマリー確認
git diff --stat

# 変更ファイルの一覧
git diff --name-only

# ステージング済みの変更も確認
git diff --cached --stat
```

**確認事項**:
1. 変更ファイル数・行数が想定スコープ内か
2. 意図しないファイルが含まれていないか
3. `work/`, `docs/` 等の除外対象が混入していないか

---

## §2 検証レポートテンプレート（コピペ用）

以下を `{WORK}verification-report.md` としてコピーして使用する。

```markdown
# VERIFICATION REPORT
==================
Agent:     {Agent名}
Issue:     #{Issue番号}
Timestamp: {UTC timestamp - 例: 2026-01-01T00:00:00Z}

## Phase Results

Build:     [PASS/FAIL/SKIP(理由)]
Lint:      [PASS/FAIL/SKIP(理由)]
Tests:     [PASS/FAIL/SKIP(理由)] ({X}/{Y} passed)
Security:  [PASS/FAIL/SKIP(理由)] (検出パターン数: {N})
Diff:      [{X} files changed, +{Y}/-{Z} lines]

## Overall

Overall:   [READY/NOT READY] for PR
Notes:     {補足事項}

## Failure Details（失敗 Phase がある場合のみ）

Phase {N} FAIL:
- Error: {エラーメッセージ}
- File:  {ファイルパス:行番号}
- Action: {対処内容または §10.4 エラーリカバリ参照}
```

---

## §3 Phase 失敗時のエスカレーション手順

1. 失敗 Phase の詳細を `verification-report.md` に記録する
2. AGENTS.md §10.4 エラーリカバリの3要素（`root_cause_hint` / `safe_retry_instruction` / `stop_condition`）を出力する
3. 修正を試みる（最大3回: AGENTS.md §1 リトライルール準拠）
4. 3回試みても失敗 → `stop_condition` を宣言し、作業を停止する
5. PR には `[WIP]` を付与し、失敗 Phase と詳細をコメントに記載する
