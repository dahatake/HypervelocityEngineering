# エラー分類・リカバリフロー・stop_conditionテンプレート

> 本ファイルは `harness-error-recovery/SKILL.md` の §1〜§3 詳細を収容する参照資料です。

---

## §1 エラー分類と対処手順

### 分類 E-01: Build 失敗

**症状**: `dotnet build` / `python -m py_compile` / `bash -n` が exit code 非 0

**リカバリフロー**: エラーメッセージから対象ファイル・行番号を特定 → 構文エラー/参照エラー/依存不足を判別 → 依存不足なら `dotnet restore` / `pip install` を実行 → コード修正後 Phase 1 を再実行（最大3回）→ 3回失敗 → stop_condition を出力

**3要素出力例**:
```markdown
## エラーリカバリ
- root_cause_hint:        dotnet build failed at {ファイルパス}:{行番号} - {エラー種別}
- safe_retry_instruction: エラー箇所を修正後、`dotnet build --no-restore` を再実行する。依存不足なら先に `dotnet restore` を実行する。
- stop_condition:         3回の修正試行後も Build が通らない場合、実装を停止し [WIP] PR でブロック理由を記録する。
```

---

### 分類 E-02: Test 失敗

**症状**: `dotnet test` / `pytest` が失敗テストを報告

**リカバリフロー**: 失敗テストの名前とエラーメッセージを確認 → 環境依存かロジックエラーかを判別 → 環境依存なら `SKIP(環境依存)` として記録し次 Phase へ → ロジックエラーなら実装コードを修正し該当テストを再実行 → テスト修正は行わない（テストは正解定義）→ 3回失敗 → stop_condition を出力

**3要素出力例**:
```markdown
## エラーリカバリ
- root_cause_hint:        {テスト名} が失敗 - {期待値} vs {実際値}。実装の {関数名} のロジックに不整合。
- safe_retry_instruction: {関数名} の実装を確認し、修正後 `dotnet test --filter "{テスト名}"` で単体再実行する。
- stop_condition:         テスト失敗が仕様の矛盾に起因する場合、実装を停止しユーザーに仕様確認を要求する。
```

---

### 分類 E-03: ファイル書き込み失敗

**症状**: ファイル作成/編集後の read 確認で空ファイルまたは不正内容を検出

**リカバリフロー（copilot-instructions.md §0 リトライルール準拠）**: 書き込み後に read で内容を確認 → 空または不正の場合 → チャンクサイズを 2,000〜5,000 文字に分割して再試行 → 最大3回まで再試行 → 3回失敗 → stop_condition を出力

**3要素出力例**:
```markdown
## エラーリカバリ
- root_cause_hint:        {ファイルパス} への書き込み後、内容が空または不正。大きなチャンクによるバッファ超過の可能性。
- safe_retry_instruction: ファイルを削除し、2,000〜5,000 文字以下のチャンクに分割して段階的に書き込む。
- stop_condition:         3回のチャンク分割試行後も書き込みに失敗した場合、ユーザーに手動確認を依頼する。
```

---

### 分類 E-04: API 制限 / タイムアウト

**症状**: Azure CLI / GitHub API / 外部サービスからレート制限またはタイムアウトエラー

**リカバリフロー**: 429 → Retry-After 待機後に再試行 / 504 → 30秒待機後に再試行 → 最大3回 → 3回失敗 → stop_condition を出力し後続ステップをスキップ

**3要素出力例**:
```markdown
## エラーリカバリ
- root_cause_hint:        Azure CLI が 429 (レート制限) を返した。連続リクエスト過多の可能性。
- safe_retry_instruction: {N}秒待機後に再試行する。大量リソース操作の場合はバッチ分割を検討する。
- stop_condition:         3回の待機+再試行後も 429 が続く場合、デプロイを中断し、翌日または手動での実行を推奨する。
```

---

### 分類 E-05: 権限不足

**症状**: `AuthorizationFailed` / `403 Forbidden` / `Access Denied` エラー

**リカバリフロー**: 必要な権限ロールを特定 → 現在のサービスプリンシパル/マネージドIDの権限を確認 → 権限付与は Agent 自身では行わない → 必要な権限と付与手順をユーザーに報告し stop_condition を出力

**3要素出力例**:
```markdown
## エラーリカバリ
- root_cause_hint:        {リソース} へのアクセスで 403。現在の ID に {必要なロール} ロールが付与されていない可能性。
- safe_retry_instruction: `az role assignment create` でサービスプリンシパルに {必要なロール} を付与後、再実行する。
- stop_condition:         権限付与は Agent の権限外。ユーザーによる手動対応が必要なため、デプロイを停止する。
```

---

## §2 stop_condition テンプレート

```markdown
## エラーリカバリ
- root_cause_hint:        [推定される原因: エラーメッセージ・ファイル・行番号を含める]
- safe_retry_instruction: [再試行手順: 具体的なコマンドまたは操作を記載する]
- stop_condition:         [停止宣言: これ以上進めない理由と、次に人間が行うべき作業を明示する]
```

---

## §3 copilot-instructions.md §0 リトライルールとの整合性

| 項目 | copilot-instructions.md §0（既存ルール） | §10.4（本セクション） |
|---|---|---|
| 適用スコープ | ファイル書き込み操作のみ | 全エラー種別 |
| リトライ上限 | 最大3回 | copilot-instructions.md §0 準拠（最大3回） |
| チャンクサイズ | 2,000〜5,000 文字 | copilot-instructions.md §0 準拠 |
| 超過時の動作 | 記述なし | stop_condition を出力する |

**優先関係**: copilot-instructions.md §0 のファイル書き込みリトライルールはそのまま維持する。本セクションは他のエラー種別（E-01〜E-05）へ適用範囲を拡張する。
