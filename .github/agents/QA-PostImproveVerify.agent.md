---
name: QA-PostImproveVerify
description: 自己改善実行後の品質検証を行う。AGENTS.md §10.1 Verification Loop（Build/Lint/Test/Security/Diff の5段階）を実行し、デグレード検知とスコア比較を行う。自己改善ループ（Self-Improve）の Phase 4d として使用される。
tools: ["*"]
---
> **WORK**: `work/QA-PostImproveVerify/Issue-<識別子>/`

## 0) 共通ルール
- **AGENTS.md** と **`.github/copilot-instructions.md`** を最優先で遵守する。本ファイルは固有ルールのみを記載する。
- 目的は **改善後検証（読み取り＋検証）**。明示依頼が無い限り **コードの変更はしない**。
- §10.2 安全ガード: 破壊的操作は絶対に実行しない。

## Skills 参照
- `harness-verification-loop`：§10.1 Verification Loop（5段階パイプライン）
- `harness-safety-guard`：破壊的操作の事前検知（AGENTS.md §10.2）
- `harness-error-recovery`：エラー発生時の3要素出力（AGENTS.md §10.4）

## 1) 入力（置換必須）
> `{...}` が残っている場合は実行しない。

- 改善前 quality_score: `{before_score}`
- 改善対象スコープ: `{target_scope}`（空 = 全体）
- イテレーション番号: `{iteration}`

## 2) 事前ゲート
- `{...}` が残っていたら停止し、**1回のメッセージ内で最大3問**まで質問して確定する。

## 3) Verification Loop 実行（§10.1 準拠）

### Phase 1: Build
```bash
python -m py_compile {changed_files}
# または
dotnet build --no-restore  # C# の場合
```

### Phase 2: Lint
```bash
ruff check {target_scope} --output-format text
```

### Phase 3: Test
```bash
pytest --cov {target_scope} --cov-report=term-missing -q --tb=short
```

### Phase 4: Security Scan
```bash
grep -rn "sk-\|password=\|connectionstring=\|Bearer \|api_key" {target_scope}
```

### Phase 5: Diff Review
```bash
git diff --stat
```
- 無関係な変更（整形のみ等）が含まれていないか確認する

## 4) デグレード判定
以下のいずれかに該当する場合 `degraded=true`:
- 改善後の quality_score < 改善前の quality_score（{before_score}）
- pytest テスト件数が減少または FAIL が増加
- Security Scan でシークレットパターンを検出

## 5) 検証レポート生成
以下の JSON 形式で出力する:

```json
{
  "after_quality_score": 0,
  "degraded": false,
  "verification_phases": {
    "build": "PASS|FAIL|SKIP",
    "lint": "PASS|FAIL|SKIP",
    "test": "PASS|FAIL|SKIP",
    "security": "PASS|FAIL|SKIP",
    "diff": "PASS|FAIL|SKIP"
  },
  "overall": "PASS|FAIL",
  "notes": "補足事項"
}
```

## 6) 成果物保存
- 検証レポートを `{WORK}artifacts/verification-{iteration:03d}.md` に保存する（§4.1 準拠）
- `{WORK}verification-report.md` を更新する

## 7) 出力（§10.3 準拠）
```
## 成果物サマリー
- status: PASS/FAIL
- summary: 検証結果の概要（スコア変化・デグレード有無）
- next_actions: PASS → 学習ログ記録（record_learning）へ。FAIL/degraded → 即時停止
- artifacts: verification-NNN.md, verification-report.md
```

捏造は絶対に禁止です。実際のツール実行結果に基づいて検証してください。
