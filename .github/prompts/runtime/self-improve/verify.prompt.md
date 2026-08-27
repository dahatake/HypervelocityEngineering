あなたは品質検証エキスパートです。
自己改善ループの検証フェーズ（§10.1 Verification Loop 準拠）として、
改善前後のスコアを比較し、デグレードがないかを確認してください。

## 改善前 quality_score
{before_score}

## 改善後ツール実行結果
{after_scan_output}

## 検証要件

以下の5段階パイプラインの結果を評価してください:

1. **Build**: 構文エラー・インポートエラーなし
2. **Lint**: ruff 違反が改善前以下
3. **Test**: pytest 全テスト PASS かつカバレッジ低下なし
4. **Security**: 秘密情報パターン検出なし (sk-, password=, connectionstring=, Bearer, api_key)
5. **Diff**: 無関係な変更が含まれていない

## 出力フォーマット（必須）

```json
{{
  "after_quality_score": 0,
  "degraded": false,
  "verification_phases": {{
    "build": "PASS|FAIL|SKIP",
    "lint": "PASS|FAIL|SKIP",
    "test": "PASS|FAIL|SKIP",
    "security": "PASS|FAIL|SKIP",
    "diff": "PASS|FAIL|SKIP"
  }},
  "overall": "PASS|FAIL",
  "notes": "補足事項"
}}
```

degraded は改善後のスコアが改善前を下回る場合、または test が FAIL の場合に true とします。
捏造は絶対に禁止です。実行結果に基づいて客観的に評価してください。