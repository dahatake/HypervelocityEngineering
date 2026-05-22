# 危険パターン一覧・Azure固有コマンド・ホワイトリスト・判定フロー

> 本ファイルは `harness-safety-guard/SKILL.md` の §1〜§4 詳細を収容する参照資料です。

---

## §1 危険パターン一覧

### CRITICAL（絶対停止）— 確認なしに即時停止

| カテゴリ | 正規表現パターン | 説明 |
|---|---|---|
| ファイル破壊 | `rm\s+-[rf]+\s+/` | ルートからの再帰削除 |
| ファイル破壊 | `rm\s+-[rf]+\s+~` | ホームディレクトリの再帰削除 |
| ファイル破壊 | `rm\s+-[rf]+\s+\.` | カレントディレクトリの再帰削除 |
| DB 破壊 | `[Dd][Rr][Oo][Pp]\s+[Tt][Aa][Bb][Ll][Ee]\b` | テーブル削除 |
| DB 破壊 | `[Dd][Rr][Oo][Pp]\s+[Dd][Aa][Tt][Aa][Bb][Aa][Ss][Ee]\b` | データベース削除 |
| DB 破壊 | `TRUNCATE\s+TABLE\b` | テーブル全件削除 |
| Azure 破壊 | `az\s+resource\s+delete` | Azure リソース削除 |
| Azure 破壊 | `az\s+group\s+delete` | Azure リソースグループ削除 |
| Azure 破壊 | `az\s+deployment\s+delete` | Azure デプロイメント削除 |
| Azure 破壊 | `az\s+keyvault\s+delete` | Key Vault 削除 |
| Azure 破壊 | `az\s+storage\s+account\s+delete` | ストレージアカウント削除 |
| Azure 破壊 | `az\s+cosmosdb\s+delete` | Cosmos DB アカウント削除 |
| Azure 破壊 | `az\s+sql\s+server\s+delete` | SQL Server 削除 |
| Azure 破壊 | `az\s+functionapp\s+delete` | Function App 削除 |

### HIGH（確認要求）— 実行前にユーザー確認を取る

| カテゴリ | 正規表現パターン | 説明 |
|---|---|---|
| Git 破壊 | `git\s+push\s+.*--force` | 強制プッシュ |
| Git 破壊 | `git\s+reset\s+--hard` | ハードリセット |
| Git 破壊 | `git\s+checkout\s+\.` | 全変更の破棄 |
| 秘密情報 | `sk-[A-Za-z0-9]{20,}` | OpenAI API キー等 |
| 秘密情報 | `password\s*=\s*['"][^'"]{4,}` | ハードコードされたパスワード |
| 秘密情報 | `connectionstring\s*=\s*['"][^'"]{10,}` | ハードコードされた接続文字列 |
| 秘密情報 | `Bearer\s+[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+` | ハードコードされた JWT/Bearer トークン |

### MEDIUM（警告+理由記録）— 実行可能だが理由を記録する

| カテゴリ | 正規表現パターン | 説明 |
|---|---|---|
| 検証スキップ | `--no-verify` | Git hooks スキップ |
| 検証スキップ | `--skip-tests` | テストスキップ |
| 検証スキップ | `-DskipTests` | Maven テストスキップ |
| 大量削除 | `DELETE\s+FROM\s+\w+\s*;` | WHERE 句なしの DELETE |

---

## §2 Azure 固有の破壊的コマンド（本リポジトリ特化）

以下のコマンドは CRITICAL: 絶対停止:

```bash
az resource delete / az group delete / az deployment delete / az keyvault delete
az storage account delete / az cosmosdb delete / az sql server delete / az sql db delete
az functionapp delete / az staticwebapp delete / az servicebus namespace delete
az eventhubs namespace delete / az apim delete / az containerapp delete
az acr delete / az aks delete
```

---

## §3 ホワイトリスト（誤検知を避けるための除外例）

| ケース | 例 | 理由 |
|---|---|---|
| テストコード内の DROP TABLE | `test/`, `tests/`, `*.test.*` 配下の `DROP TABLE` | テストデータ初期化用途 |
| プレースホルダー | `password=your-password-here`, `password=<YOUR_PASSWORD>` | ドキュメント・テンプレートの例示 |
| コメント行 | `# password=example` | 説明のためのコメント |
| 環境変数参照 | `password=$DB_PASSWORD`, `connectionstring=${CONNECTION_STRING}` | 実値でなく環境変数参照 |
| Key Vault 参照 | `@Microsoft.KeyVault(...)` | シークレット直書きでなく KV 参照 |

---

## §4 停止レベル別の判定フロー

```
操作・コードを実行/コミットしようとする
            ↓
    CRITICAL パターン検出?
    ├── YES → 【絶対停止】操作を実行しない / エラーメッセージを出力 / stop_condition を宣言 / PR に [BLOCKED] を付与
    └── NO → HIGH パターン検出?
             ├── YES → 【確認要求】操作の詳細と影響範囲を明示 / ユーザーから明示的な承認を得る / 承認なし → スキップして記録
             └── NO → MEDIUM パターン検出?
                       ├── YES → 【警告+記録】警告メッセージを出力 / verification-report.md に理由と承認者を記録 / 操作は実行可能
                       └── NO → 【正常実行】
```
