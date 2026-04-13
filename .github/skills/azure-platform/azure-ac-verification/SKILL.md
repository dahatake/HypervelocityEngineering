---
name: azure-ac-verification
description: "AC 検証フレームワークの共通仕様。ac-verification.md テンプレート、PASS/NEEDS-VERIFICATION/FAIL 完了判定基準、Azure リソース存在確認パターン（provisioningState 検証）、Azure CLI 利用不可時フォールバックを提供する。Deploy Agent が AC 検証を実施する際に参照する。"
---

# azure-ac-verification

## 目的

AC（受け入れ条件）検証の **共通フレームワーク** を一元管理する。
各 Deploy Agent は本 Skill を参照し、固有の AC 項目リスト（AC-1〜AC-N の個別内容）のみを Agent 側に記載する。

本 Skill は以下の共通仕様を提供する:
- **§1**: `ac-verification.md` テンプレート（検証結果の記録フォーマット）
- **§2**: PASS / NEEDS-VERIFICATION / FAIL の完了判定基準（統一ステータス名）
- **§3**: Azure リソース存在確認パターン（`provisioningState: Succeeded` の検証）
- **§4**: Azure CLI 利用不可時のフォールバック（`⏳（手動実行待ち）`）

---

## §1. ac-verification.md テンプレート

AC 検証結果を `{WORK}ac-verification.md` に以下のフォーマットで記録する。

```markdown
# AC 検証結果

- 検証日時: YYYY-MM-DD HH:MM (UTC)
- 検証者: Copilot cloud agent / 人間（手動検証の AC のみ）
- Azure CLI 利用: 可 / 不可
- `az account show` 結果: （サブスクリプション名 or エラー出力を記載 — 判定根拠の必須記録項目）
- リソースグループ状態: 既存 / 新規作成 / 作成失敗

## チェックリスト

| # | AC | 判定 | エビデンス要約 |
|---|-----|------|---------------|
| AC-1 | （Agent 固有の AC 項目） | ✅ / ❌ / ⏳ | （検証結果の要約） |
| AC-2 | （Agent 固有の AC 項目） | ✅ / ❌ / ⏳ | （検証結果の要約） |
| ... | ... | ... | ... |

## Azure リソース検証詳細（リソース存在確認 AC のみ）

| リソース種類 | リソース名 | Resource ID | provisioningState | location |
|-------------|-----------|-------------|-------------------|----------|
| （リソース種類） | （実際のリソース名） | （Resource ID） | Succeeded | Japan East |
| ... | ... | ... | ... | ... |

## 総合判定
- 結果: PASS / NEEDS-VERIFICATION / FAIL（§2 の判定基準に従う）
- 未達 AC: （未達の AC 番号と理由）
- 必要な手動対応: （手動検証が必要な場合の手順）
```

### テンプレート利用ルール

- テーブル内のプレースホルダー（`（Agent 固有の AC 項目）` 等）は実際の値に置き換えること（そのまま出力しない）
- 「Azure リソース検証詳細」セクションはリソース存在確認 AC がある場合のみ記載する
- `ac-verification.md` に **アクセスキー / 接続文字列 / SAS トークン** は絶対に記録しない。これらが出力に含まれる場合はマスクする
- **Subscription ID / Tenant ID は許容** する（公開リポジトリの場合は要判断）

---

## §2. 完了判定基準（統一ステータス名）

全 Deploy Agent で以下の統一ステータス名を使用する。

| 状態 | 条件 | PR の扱い |
|------|------|----------|
| **PASS** | 全 AC が ✅ | PR description に「AC 全項目検証済み」と記載。最終品質レビューへ進む |
| **NEEDS-VERIFICATION** | いずれかの AC が ⏳（Azure CLI 利用不可等による Azure リソース確認など）で、❌ が 1 つもない | PR description に未検証 AC と手動実行手順を明記。最終品質レビューは実施する。⏳ の AC がある場合、PR マージ前に人間がすべて検証し ✅ に更新すること |
| **FAIL** | いずれかの AC が ❌ | 自動修正可能 → 修正して再検証（最大3回）。手動対応が必要 → PR コメントで報告。根本的に不可能 → 対象 AC の除外を人間に相談 |

### 判定フロー（疑似コード）

```
if Azure リソース確認 AC が ❌:
    判定 = "FAIL"
    → 最重要 AC の FAIL は他の AC 結果に関わらず FAIL
    → 修正して再検証（最大3回）。解消しなければ [WIP] で提出

elif いずれかの AC が ❌:
    判定 = "FAIL"
    → 修正して再検証（最大3回）

elif 全 AC が ✅:
    判定 = "PASS"
    → 最終品質レビューへ進む

else:  # ❌ なし、⏳ が存在
    判定 = "NEEDS-VERIFICATION"
    → 最終品質レビューへ進む
    → PR description に手動検証手順を明記
```

### PR タイトルの付与ルール

- **PASS**: 通常の PR タイトル
- **NEEDS-VERIFICATION**: PR タイトルに `[NEEDS-VERIFICATION]` を付与
- **FAIL（修正不能）**: PR タイトルに `[WIP]` を付与

> `[NEEDS-VERIFICATION]` は実装完了だが外部検証待ちの状態を示す。AGENTS.md の `[WIP]` （分割モード / Plan-Only 用）とは異なる。

---

## §3. Azure リソース存在確認パターン

Azure リソースの存在確認は、Deploy Agent の最も重要な AC である。

### 3.1 検証基準

各リソースについて以下を確認する：
1. コマンドが exit code 0 で返ること（リソースが存在する）
2. JSON レスポンスの `provisioningState` が `Succeeded` であること
3. `location` が Region Policy に準拠していること
4. リソース名が期待値と一致すること

### 3.2 検証コマンドパターン

リソース種類に応じて、以下の優先順でコマンドを使用する：

1. **サービス固有コマンド**（最優先）: `az <service> show --name {名前} --resource-group {RG}`
2. **汎用コマンド**（固有コマンドが存在しない/失敗した場合）: `az resource show --name {名前} --resource-group {RG} --resource-type {type}`

代表的なリソース種類のコマンド例：

| リソース種類 | 検証コマンド例 | 状態フィールド |
|-------------|--------------|---------------|
| リソースグループ | `az group show --name {RG} --query "properties.provisioningState" --output tsv` | `properties.provisioningState` |
| Storage Account | `az storage account show --name {SA} --resource-group {RG} --query "provisioningState" --output tsv` | `provisioningState` |
| Function App | `az functionapp show --name {APP} --resource-group {RG} --query "state" --output tsv` | `state`（`Running` で正常） |
| Static Web App | `az staticwebapp show --name {SWA} --resource-group {RG} --output json` | JSON 全体（`defaultHostname` 取得可で正常） |
| SQL Server | `az sql server show --name {SQL} --resource-group {RG} --query "state" --output tsv` | `state`（`Ready` で正常） |

> **注意**: リソース種類によって状態を示すフィールド名と正常値が異なる。`provisioningState: Succeeded` は多くのリソースで共通だが、Function App は `state: Running`、SQL Server は `state: Ready` 等、サービス固有のフィールドを使用する。既存の verify スクリプト（`infra/azure/verify-*.sh`）のパターンを優先すること。

### 3.3 provisioningState の判定

| 状態 | 判定 | 対応 |
|------|------|------|
| `Succeeded` | **PASS** | 正常。次のリソースへ進む |
| `Creating` / `Updating` | **待機** | 30秒間隔で再確認（最大5分 = 10回ポーリング）。最終的に `Succeeded` にならなければ **FAIL** |
| `Failed` / `Deleting` | **FAIL** | リソースに問題あり。原因調査が必要 |
| リソース不存在（コマンドエラー） | **FAIL** | リソースが作成されていない |

### 3.4 セキュリティ上の注意

- `ac-verification.md` に Azure CLI の出力を記録する際、**Subscription ID / Tenant ID は許容** する（公開リポジトリの場合は要判断）
- **アクセスキー / 接続文字列 / SAS トークン** は絶対に記録しない。これらが出力に含まれる場合はマスクする

---

## §4. Azure CLI 利用不可時のフォールバック

Azure CLI の利用可否は以下の条件により変動し得る:

- `copilot-setup-steps.yml` が **未設定** の場合: Azure CLI は **利用できない**
- `copilot-setup-steps.yml` が **設定済み** の場合: Azure CLI は **利用可能になり得る**（Secrets 未設定・workflow 未実行・login 失敗等で利用不能なケースもある）

最終的な Azure CLI の利用可否は、Agent §0.1 の判定手順（`az account show` の実行結果）で確定すること。
AC のうち Azure リソース存在確認は、Azure CLI 利用不可時に以下の手順で対応する。

### 4.1 フォールバック手順

1. **AC 判定を `⏳（手動実行待ち）` とする**
   - Azure リソース確認 AC は `⏳` とし、`ac-verification.md` に記録する
   - 構文チェック通過のみでは「リソースが作成された」とはみなさない
2. **検証コマンドを `ac-verification.md` に記録する**
   - 人間がコピー＆ペーストで即実行可能な形で、検証コマンドを記録する
3. **PR description に手動検証手順を明記する**
   - 以下のテンプレートを使用する（Agent 固有のスクリプト名に置き換えること）
4. **総合判定を NEEDS-VERIFICATION とする**
   - §2 の判定基準に従い、PR タイトルに `[NEEDS-VERIFICATION]` を付与する

### 4.2 PR description テンプレート（Azure リソース未検証時）

```markdown
## ⚠️ AC 手動検証待ち（Azure リソース存在確認）

Azure CLI が利用できない環境のため、Azure リソースの存在確認が未実施です。
以下の検証コマンドを実行し、`ac-verification.md` の該当 AC を ✅ / ❌ に更新してください：

### 検証コマンド
（Agent 固有の検証コマンドを記載）

### 期待される結果
- 全リソースの `provisioningState` が `Succeeded` であること
- `location` が Region Policy に準拠していること
```

---

## 参照元

- `work/Issue-skills-migration-investigation/duplication-patterns.md` — P-05 詳細（6 Agent）
- `work/Issue-skills-migration-investigation/extraction-candidates.md` — 抽出判定
- `work/Issue-skills-migration-investigation/migration-matrix.md` — GO-6 評価
