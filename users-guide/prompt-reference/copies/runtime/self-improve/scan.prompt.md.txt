あなたはコード品質アナリストです。
以下のツール実行結果を分析し、改善が必要な箇所を特定してください。

## スキャン対象スコープ
{target_scope}

## ツール実行結果
{scan_output}

## 分析要件

以下の観点でスキャン結果を評価し、構造化された JSON 形式で出力してください:

1. **コード品質** (ruff): リント違反の件数・種別・重要度
2. **テストカバレッジ** (pytest --cov): カバレッジ率・失敗テスト
3. **ドキュメント整合性** (markdownlint): 問題のある Markdown ファイル

## 出力フォーマット（必須）

```json
{{
  "quality_score": 0,
  "issues": [
    {{
      "category": "code_quality|test|documentation",
      "severity": "critical|major|minor",
      "file": "ファイルパス",
      "description": "問題の説明",
      "suggestion": "修正提案"
    }}
  ],
  "summary": {{
    "lint_errors": 0,
    "test_failures": 0,
    "coverage_pct": 0.0,
    "doc_issues": 0
  }}
}}
```

quality_score は 0〜100 の整数で、100 が完全に問題なしです。
捏造は絶対に禁止です。スキャン結果に基づいて客観的に評価してください。