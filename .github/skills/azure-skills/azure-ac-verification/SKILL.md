---
name: azure-ac-verification
description: >
  Azure デプロイ後の Acceptance Criteria 検証結果を ac-verification.md に記録する共通仕様。PASS / NEEDS-VERIFICATION / FAIL 判定、Azure リソース存在確認、provisioningState 判定、Azure CLI 利用不可時の扱いを定義する。 USE FOR: Azure AC verification, ac-verification.md, deployment verification evidence. DO NOT USE FOR: Azure リソース作成スクリプトの設計、テストコード実装、実デプロイ実行。 WHEN: Azure デプロイ後の AC 検証結果を記録・レビューするとき。
metadata:
  origin: user
  version: 1.0.0
---

# azure-ac-verification

## 目的

Azure デプロイ後の受け入れ条件（AC）を、Agent / prompt 間で一貫した形式で記録する。`ac-verification.md` は Orchestrator gate や人手レビューが参照する証跡であり、未検証の成功扱い・推測による Resource ID / URL / 状態値の記載を禁止する。

## 適用対象

- Azure リソース作成後の `ac-verification.md`
- Azure Functions / Static Web Apps / データストア / 追加 Azure サービスの存在確認
- `verify-*.sh` の結果を AC 判定に転記する作業

## Non-goals

- Azure CLI スクリプト自体の設計は `azure-cli-deploy-scripts` を参照する。
- GitHub Actions の OIDC / workflow 設計は `github-actions-cicd` を参照する。
- Azure Portal での手動確認手順の網羅は本 Skill の対象外。CLI 不可時の代替記録に限定する。

## 公式根拠

本 Skill の規約は以下の Microsoft Learn 確認事項に基づく。

| 確認事項 | Microsoft Learn |
|---|---|
| Resource Group の存在確認には `az group show` を使用できる。 | [Manage Azure resource groups by using Azure CLI](https://learn.microsoft.com/azure/azure-resource-manager/management/manage-resource-groups-cli) |
| Azure リソース一覧・絞り込みには `az resource list` を使用でき、Resource Group / resource type / location 等で絞り込める。 | [az resource list](https://learn.microsoft.com/cli/azure/resource?view=azure-cli-latest#az-resource-list) |
| Resource ID 等で単一 Azure リソースを確認するには `az resource show` を使用できる。 | [az resource show](https://learn.microsoft.com/cli/azure/resource?view=azure-cli-latest#az-resource-show) |
| Azure Resource Manager は全リージョンでサポートされるが、個別リソース種別は全リージョンでサポートされるとは限らない。対応 location は `az provider show` で確認できる。 | [Azure resource providers and types](https://learn.microsoft.com/azure/azure-resource-manager/management/resource-providers-and-types#azure-cli) |
| Azure Resource Manager SDK では `ResourcesProvisioningState.Succeeded` が `Succeeded` 状態を表す。 | [ResourcesProvisioningState.Succeeded Property](https://learn.microsoft.com/dotnet/api/azure.resourcemanager.resources.models.resourcesprovisioningstate.succeeded?view=azure-dotnet) |

---

## §1 `ac-verification.md` テンプレート

`ac-verification.md` は、各 AC を 1 行 1 AC の表形式で記録する。

必須列:

| 列 | 内容 |
|---|---|
| AC | `AC-1` などの識別子 |
| 観点 | 何を満たすべきか |
| 状態 | `PASS` / `NEEDS-VERIFICATION` / `FAIL`、または Agent が明示した `✅` / `⏳` / `❌` |
| 証跡 | コマンド名、抜粋ログ、Resource ID、URL、理由。秘密情報は禁止 |

最小例:

| AC | 観点 | 状態 | 証跡 |
|---|---|---|---|
| AC-1 | Azure 上に対象 Resource Group が存在する | PASS | `az group show --name <rg>` exit 0 |
| AC-2 | 対象リソースの provisioningState が Succeeded | NEEDS-VERIFICATION | Azure CLI 未認証のため未確認。再実行手順: ... |

記録ルール:

- 成功・未検証・失敗のいずれでも、AC 行自体は省略しない。
- ブロッカー発生時もファイルを作成し、未達 AC を `FAIL` または `NEEDS-VERIFICATION` として理由付きで記録する。
- セクション見出しだけで AC を記録しない。表の行を正とする。

---

## §2 統一ステータス名

| 状態 | 絵文字別名 | 意味 | 完了判定 |
|---|---|---|---|
| `PASS` | `✅` | 実コマンド・テスト・公式状態確認により満たした | 完了可 |
| `NEEDS-VERIFICATION` | `⏳` | 実行環境・権限・伝播待ち等により未確認 | 原則、実在系 AC の最終完了には不可 |
| `FAIL` | `❌` | 実行結果または検証結果が AC 未達 | 完了不可 |

Agent / prompt が `✅` / `❌` / `⏳` を状態欄として指定している場合は、その指定を優先してよい。ただし完了報告では、必要に応じて対応する `PASS` / `FAIL` / `NEEDS-VERIFICATION` も併記する。

実在系 AC（リソース存在、デプロイ成功、HTTP 200 など）を `NEEDS-VERIFICATION` のまま完了してよいかは、各 Agent の `<output_contract>` を優先する。`✅ のみ許容` と明記されている場合、`NEEDS-VERIFICATION` / `FAIL` のまま正常完了してはならない。

---

## §3 Azure リソース存在確認パターン

### §3.1 基本確認

Azure リソースの存在確認は、次のいずれかの実結果を証跡にする。

- `az group show --name <resource-group>`
- `az resource show --ids <resource-id>`
- `az resource list --resource-group <resource-group> --resource-type <namespace/type>`
- サービス固有の `az <service> show` コマンド
- GitHub Actions / Azure CLI / verify script のログ抜粋（対象リソース識別子、実行コマンドまたは workflow 名、成功/失敗の結果が分かるもの）

`az account show` が失敗する、または対象サブスクリプションが不明な場合は、存在確認済みとして扱わない。

### §3.2 検証コマンドパターン

検証コマンドは以下を満たす。

- Resource Group、リソース名、resource type、location のいずれで照合したかを証跡に残す。
- 可能な場合は Resource ID を記録する。
- 秘密情報を含むプロパティは `--query` で除外する。
- 対象 resource type の location 非対応が疑われる場合は `az provider show` で対応 location を確認する。
- 一時的な伝播遅延があり得る場合は、上限付きリトライを行い、最終結果だけでなくリトライした事実も記録する。

### §3.3 `provisioningState` 判定

`provisioningState` を持つ Azure リソースでは、以下を基本とする。

- `Succeeded` は作成・更新操作が成功した状態として `PASS` 判定に使える。
- `Failed` / `Canceled` / 空値 / 取得不能は `PASS` にしない。
- リソース種別によって状態プロパティ名や意味が異なる場合があるため、サービス固有の状態値は Microsoft Learn / Azure CLI help / `az <service> show` の出力で確認する。
- `provisioningState` が存在しないリソースでは、サービス固有の状態・HTTP 応答・接続テスト等の別証跡を用いる。

---

## §4 Azure CLI 利用不可時フォールバック

Azure CLI が利用できない場合でも、`ac-verification.md` を未作成のまま終了してはならない。

必須記録:

1. 実行できなかったコマンド名。
2. 失敗理由（未インストール、未認証、権限不足、ネットワーク制約、タイムアウト等）。
3. 該当 AC の状態を `NEEDS-VERIFICATION` または `FAIL` にした理由。
4. 再実行手順または代替確認手段。

禁止:

- Azure CLI が実行できない状態で Resource ID / URL / `Succeeded` を推測記載する。
- `NEEDS-VERIFICATION` を `PASS` と同等に扱う。
- 証跡欄を空欄にする。

---

## §5 証跡品質

証跡は短くてよいが、第三者が「何を確認したか」を追跡できる必要がある。

推奨:

- コマンド名と主要 query を記録する。
- Resource ID / URL / location / provisioning state を、秘密情報を除いて記録する。
- GitHub Actions の場合は workflow 名、run ID、結論を記録する。
- 手動確認の場合は確認主体（個人名ではなくロール名またはチーム名）・日時・確認画面を記録する。ただし個人情報・内部 URL は出力しない。

## Related Skills

| Skill | 関係 | 説明 |
|---|---|---|
| `azure-cli-deploy-scripts` | 前提 | verify スクリプトと Azure CLI 失敗時の扱い |
| `azure-region-policy` | 関連 | location fallback の理由記録 |
| `harness-verification-loop` | 後続 | build / lint / test / security / diff 検証 |
| `harness-safety-guard` | 前提 | 破壊的操作・秘密情報漏洩リスクの抑止 |