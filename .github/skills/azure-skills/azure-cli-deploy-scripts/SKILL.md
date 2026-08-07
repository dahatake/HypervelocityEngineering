---
name: azure-cli-deploy-scripts
description: >
  Azure CLI デプロイスクリプトの共通仕様。prep/create/verify の 3 点セット、冪等性、Pre-flight、検証ログ、Azure CLI 利用不可時のフォールバックを定義する。 USE FOR: Azure CLI deploy scripts, idempotent deployment, prep/create/verify scripts. DO NOT USE FOR: Azure サービス仕様の網羅的説明、実デプロイ実行、破壊的削除。 WHEN: Azure リソース作成・検証スクリプトを作成またはレビューするとき。
metadata:
  origin: user
  version: 1.0.0
---

# azure-cli-deploy-scripts

## 目的

Azure CLI で Azure リソースを作成・確認する Agent / prompt が共通で使う **スクリプト作成規約** を定義する。各 Agent はサービス固有のリソース名・SKU・設定値だけを Agent 側に記載し、実行規律・冪等性・証跡形式は本 Skill に従う。

## 適用対象

- `src/infra/azure/*create*.sh` / `*prep*.sh` / `*verify*.sh` などの Azure CLI スクリプト
- GitHub Actions から呼び出す Azure CLI 手順
- Azure Functions / Static Web Apps / データストア / 追加 Azure サービスの作成・検証手順

## Non-goals

- Azure サービスごとの SKU / 制限 / REST API 仕様を本 Skill に固定しない。必要時は Microsoft Learn / Azure CLI help を確認する。
- `az delete` 系の破壊的操作テンプレートは提供しない。削除・ロールバックは個別 Agent と `harness-safety-guard` の制約下で扱う。
- 実際の Azure デプロイ実行は行わない。本 Skill は作成・レビュー時の規約である。

## 公式根拠

本 Skill の規約は以下の Microsoft Learn 確認事項に基づく。

| 確認事項 | Microsoft Learn |
|---|---|
| Azure CLI で Resource Group を作成するには `az group create` を使用する。Resource Group は関連リソースのコンテナーで、location は Resource Group のメタデータ格納場所を表す。 | [Manage Azure resource groups by using Azure CLI](https://learn.microsoft.com/azure/azure-resource-manager/management/manage-resource-groups-cli) |
| `az group create` の `--location` は `az account list-locations` の値を使用できる。 | [az group create](https://learn.microsoft.com/cli/azure/group?view=azure-cli-latest#az-group-create) |
| `az group exists` は Resource Group の存在確認に使える。 | [az group exists](https://learn.microsoft.com/cli/azure/group?view=azure-cli-latest#az-group-exists) |
| 現在のサブスクリプションでサポートされるリージョン一覧は `az account list-locations` で取得できる。 | [az account list-locations](https://learn.microsoft.com/cli/azure/account?view=azure-cli-latest#az-account-list-locations) |
| Resource ID 等で単一 Azure リソースを確認するには `az resource show` を使用できる。 | [az resource show](https://learn.microsoft.com/cli/azure/resource?view=azure-cli-latest#az-resource-show) |
| Azure Resource Manager は全リージョンでサポートされるが、デプロイするリソース種別は全リージョンでサポートされるとは限らない。リソース種別の対応 location は `az provider show --namespace <namespace> --query "resourceTypes[?resourceType=='<type>'].locations | [0]"` で確認できる。 | [Azure resource providers and types](https://learn.microsoft.com/azure/azure-resource-manager/management/resource-providers-and-types#azure-cli) |
| Azure Policy の `modify` は Resource Provider が create / update 要求を処理する前に要求内容を変更する。 | [Azure Policy definitions modify effect](https://learn.microsoft.com/azure/governance/policy/concepts/effect-modify#modify-evaluation) |
| Azure Policy の `append` は Resource Provider 処理前に field を追加し、要求の既存値と競合すると deny として動作する。 | [Azure Policy append effect](https://learn.microsoft.com/azure/governance/policy/concepts/effect-append#append-evaluation) |
| Assignment は scope、definition version、resource selectors、overrides、enforcement mode、notScopes、parameters を持ち、実効評価に影響する。 | [Azure Policy assignment structure](https://learn.microsoft.com/azure/governance/policy/concepts/assignment-structure) |
| Initiative parameter は `policyDefinitions[].parameters` から child policy parameter へ渡される。 | [Azure Policy initiative definition structure](https://learn.microsoft.com/azure/governance/policy/concepts/initiative-definition-structure) |
| Policy applicability は rule、mode、notScopes、resource selectors、exemption で決まる。 | [Azure Policy applicability](https://learn.microsoft.com/azure/governance/policy/concepts/policy-applicability) |
| Policy exemption は assignment と initiative 内 reference ID、期限、resource selectors を持つ。 | [Azure Policy exemption structure](https://learn.microsoft.com/azure/governance/policy/concepts/exemption-structure) |
| Azure SQL Database は Private Endpoint と VNet 内から接続でき、公開アクセスを別途無効化できる。 | [Azure Private Link - Azure SQL Database & Azure Synapse Analytics](https://learn.microsoft.com/azure/azure-sql/database/private-endpoint-overview) |
| Azure Cosmos DB for NoSQL の Private Endpoint は group ID `Sql` と Private DNS zone `privatelink.documents.azure.com` を使用する。 | [Azure Private Link を構成する - Azure Cosmos DB](https://learn.microsoft.com/azure/cosmos-db/how-to-configure-private-endpoints) |
| Private DNS zone は Azure cloud ごとに異なるため、cloud と service/API の公式マトリクスから選択する。 | [Azure Private Endpoint DNS zone values](https://learn.microsoft.com/azure/private-link/private-endpoint-dns) |
| VNet 内の Azure Container Instances は専用の委任済み subnet と、outbound 接続用 NAT Gateway を必要とする。 | [Azure 仮想ネットワークへのコンテナー グループのデプロイ](https://learn.microsoft.com/azure/container-instances/container-instances-vnet) |
| Azure Container Instances は User-assigned Managed Identity を `--assign-identity` で利用できる。 | [コンテナー グループでマネージド ID を有効にする](https://learn.microsoft.com/azure/container-instances/container-instances-managed-identity) |
| NSP の既定は Transition mode であり、Enforced mode だけが境界外 traffic を既定拒否する。SQL Database / Cosmos DB の NSP 対応は Public Preview である。 | [Network Security Perimeter concepts](https://learn.microsoft.com/azure/private-link/network-security-perimeter-concepts) |
| Azure CLI は明示しないと active subscription を使うため、write 前に対象 subscription / tenant を固定・照合する。 | [Manage Azure subscriptions with Azure CLI](https://learn.microsoft.com/cli/azure/manage-azure-subscriptions-azure-cli) |
| Private Endpoint subnet では NSG / UDR 用 network policy を有効化できる。 | [Manage network policies for private endpoints](https://learn.microsoft.com/azure/private-link/disable-private-endpoint-network-policy) |
| Private Endpoint subnet の NSG 対応を有効化し、推奨 Private DNS zone を使うことがセキュリティ推奨である。 | [Secure your Azure Private Link deployment](https://learn.microsoft.com/azure/private-link/secure-private-link#network-security) |

---

## §1 3点セットテンプレート

Azure CLI によるリソース作成では、原則として以下の 3 点セットを用意する。

| 種別 | 目的 | 必須要件 |
|---|---|---|
| prep | 環境・入力・Resource Group・サブスクリプション状態の確認 | 破壊的操作なし、秘密情報を出力しない、未認証時は明確に fail |
| create | リソース作成または既存リソース再利用 | 冪等、既存リソースは skip / update 方針を明記、作成結果をログ化 |
| verify | 作成済みリソースの存在・状態・接続性を検証 | AC / Test-ID と紐づく出力、成功・失敗を機械判定しやすくする |

### §1.1 共通ヘッダー

Shell スクリプトでは以下を満たす。

- `set -euo pipefail` を基本とする。
- 入力値は環境変数または引数で受け取り、未設定時は `TBD` ではなく明確なエラーにする。
- 対象 `SUBSCRIPTION_ID` を必須入力とする。複数候補から推測せず、明示入力がなければ停止する。
- `az account list --all` から `id == SUBSCRIPTION_ID` のレコードを一意に取得し、その `tenantId` を対象 subscription の期待値として保持する。0件または複数件なら停止する。
- `az account set --subscription "$SUBSCRIPTION_ID"` を必須実行し、active subscription を固定する。「各コマンドで個別指定するだけ」の代替方式は使用しない。
- 固定後に `az account show --query '{id:id,tenantId:tenantId}'` を実行し、返された `id == SUBSCRIPTION_ID` かつ `tenantId == 期待値` を確認する。どちらかが一致しない場合は write を開始しない。
- サブスクリプション・Resource Group・location はログに出してよいが、キー・トークン・接続文字列は出力しない。

### §1.2 Resource Group の冪等作成

Resource Group が必要な場合は次の順序に従う。

1. `az account show` で認証済みサブスクリプションを確認する。
2. `az group exists --name <resource-group>` で存在確認する。
3. 存在しない場合のみ `az group create --name <resource-group> --location <location>` を実行する。
4. 作成・既存再利用のどちらでも、最終的に `az group show --name <resource-group>` で確認する。

`az group delete` は本節の対象外。削除は rollback 手順として別ファイルに隔離し、実行前に `harness-safety-guard` を通す。

### §1.2.1 Azure Policy pre-flight（Azure write 前に必須）

データサービスのネットワーク設定を create / update する Agent は、**最初の Azure write** より前に Azure Policy pre-flight を実行する。Activity Log は write 後の証跡であり、pre-flight の代替にしない。

1. planned request の Azure cloud (`az cloud show --query name`)、resource ID / type / name / location、使用する API version、create / update payload を確定する。未確定値を推測しない。
2. create は予定 resource scope の全祖先、update は対象 resource ID の direct assignment と全祖先の inherited assignment を read-only で取得する。assignment scope と `notScopes` / `resourceSelectors` を planned request に適用する。
3. 有効期限内の `policyExemptions` を、`policyAssignmentId`、exemption scope、`policyDefinitionReferenceId`、exemption 側 `resourceSelectors`、要求主体に対する `userPrincipalId` / `groupPrincipalId` で child definition 単位に照合する。解決不能な exemption を assignment 全体の除外として扱わない。
4. `enforcementMode` を評価する。`DoNotEnforce` は create / update に effect を適用しないため強制経路の根拠にせず、観測情報として記録する。
5. assignment の `policyDefinitionId` と `definitionVersion` を解決する。`policyDefinitions` は定義本体を、`policySetDefinitions` は該当 version の initiative と全 `policyDefinitionReferenceId` を取得する。
6. parameter は、assignment parameter → initiative parameter / `defaultValue` → `policyDefinitions[].parameters` の reference mapping → child definition parameter / `defaultValue` の順で解決する。reference mapping の式や型を決定できない場合は推測しない。
7. assignment の `overrides`（`policyEffect` / `policyVersion`）と selector を declaration order で適用し、各 child definition の **effective effect** と version を確定する。
8. definition の `mode` を取得し、effect / mode に対応する Azure Policy applicability 規則で planned request への適用可否を判定する。未知の mode は推測しない。
9. planned request に対して policy rule の applicability と `if` を評価し、`modify.details.operations` ごとの `condition` を評価する。Azure Policy expression を同等に解決できない場合は推測しない。
10. `modify` は planned API version の alias metadata が `Modifiable` か、token type が一致するか、適用不能時の `conflictEffect` が `audit` / `deny` / `disabled` のどれかを確認する。`addOrReplace` の対象 field 自体が不在でも追加可能なケースと、入れ子 field に必要な親 property が payload にないため operation がスキップされるケースを区別する。tag / array alias も同じ規則へ単純化しない。
11. `append` は `append.details` の field / value / `[*]` array alias を評価する。planned payload の既存値と競合して deny として動作する場合を経路判定へ含める。
12. 選定サービスの public network access alias に実効適用される `modify` / `append` / `deny` を抽出し、§2.3 の経路を決定する。特定組織の Policy 名や assignment 名による判定は禁止する。
13. direct / inherited scope、exemption、mode、version、parameter、override、expression、alias、operation のいずれかを権限不足・構文不明・取得失敗で決定できない場合は `blocked` とし、**fail-closed** で Azure write を開始しない。

証跡には秘密情報を含めず、Policy scope、effect、対象 alias、置換値、decision source、および参照した Microsoft Learn の title / URL / 確認事項だけを記録する。

### §1.3 create スクリプト

create スクリプトは以下を満たす。

- 既存リソース検出時は **skip / update / fail** のいずれかを明示する。
- 再実行しても不要な重複リソースを作らない。
- Azure CLI の戻り値を握りつぶさない。
- リソース名・Resource ID・location・provisioning state 等の証跡を、秘密情報を除外して出力する。
- 長時間操作はタイムアウト・再試行回数・失敗時の記録先を Agent 側で明示する。

### §1.4 verify スクリプト

verify スクリプトは以下を満たす。

- 検証対象ごとに Test-ID または AC-ID を出力する。
- `OK` / `FAIL` / `WARN` など、集計しやすい状態語を使う。
- Azure リソース存在確認は `az resource show`、サービス固有の `az <service> show`、または Resource ID ベースの確認を使う。
- 検証コマンドの出力は `--query` などで秘密情報を含むプロパティを除外する。
- location / provider 非対応が疑われる場合は、`az provider show` で対象 resource type の対応 location を確認し、fallback した location と理由を記録する。
- DNS / CDN / Functions cold start など一時的遅延があり得る検証は、Agent / prompt が指定する上限時間内でリトライする。
- `FAIL` が 1 件以上ある場合は非ゼロ exit とする。ただし Agent が別途 `NEEDS-VERIFICATION` 記録を求める場合は、その規約に従う。

---

## §2 冪等性パターン

### §2.1 基本方針

Azure CLI スクリプトは、同一入力で再実行したときに以下のいずれかの安定動作をする。

- 既存リソースを検出して skip する。
- 既存リソースの差分だけを update する。
- 既存状態が期待と矛盾する場合は、破壊的修復をせず fail する。

リソース名にランダム suffix を使う場合も、suffix 生成元・再利用条件・証跡出力先を明示する。

### §2.2 チェックリスト

create スクリプト完成後、次を確認する。

- [ ] 1 回目の実行で必要リソースが作成または既存再利用される。
- [ ] 2 回目の実行で不要な重複作成が起きない。
- [ ] 2 回目の exit code が期待どおりである。
- [ ] verify スクリプトで作成後状態を確認できる。
- [ ] 秘密情報がログ・成果物・git diff に含まれない。
- [ ] fallback した location / SKU / 作成経路がある場合、理由を記録する。

### §2.3 Policy / network route decision matrix

| Route | 選択条件 | 必須動作 | 禁止 |
|---|---|---|---|
| `public` | public access を強制変更する effective Policy がなく、入力設計も public endpoint を許可する | 最小 firewall と実在検証を行う | Policy 未解決時の既定採用 |
| `private` | effective `modify` / `deny` が public access を無効化する、effective `append` が無効値を補完する、または入力設計が Private Endpoint を要求する。`append` が enabled payload と競合して deny になる場合も含む | §2.4 の private topology を作成/再利用する。`append` と両立する planned payload を決定できない場合は `blocked` | public access enable や firewall rule の反復 |
| `nsp` | 既存かつ承認済みで `provisioningState=Succeeded` / access mode=`Enforced` の Network Security Perimeter association と利用根拠が実在する | target service / Azure cloud の対応状況、受信・送信規則、`SecuredByPerimeter` を read-only 検証する。SQL / Cosmos は Public Preview 利用が明示承認済みの場合だけ選択する | Transition mode、NSP の推測作成、未承認 association、未承認 preview |
| `blocked` | Policy を解決不能、CIDR 未承認、必要権限不足、または経路が矛盾する | work 証跡へ理由を記録して停止する | 別経路への黙示 fallback |

Policy exemption を自動作成・変更してはならない。Policy 除外用の許可タグを自動設定してはならない。これらはガバナンス所有者の明示承認を伴う別作業とする。

### §2.4 `private` route の最小 topology

- subscription 全体の VNet / peering / subnet address prefix を read-only で棚卸しし、**固定 CIDR** を推測しない。非重複候補と write 対象を提示し、**人手承認**後だけ作成する。
- **Private Endpoint 専用 subnet** と **Azure Container Instances 専用 subnet** を分離する。
  - Private Endpoint subnet: ACI delegation を設定しない。NSG / UDR を Private Endpoint traffic に適用できるよう、既定は network policy を有効化する（Azure CLI: `--disable-private-endpoint-network-policies false`）。対象 service/API の現行制約で無効化が必要な場合だけ、公式根拠と理由を記録して無効化する。
  - ACI subnet: 空の専用 subnet とし、`Microsoft.ContainerInstance/containerGroups` へ委任する。Private Endpoint を混在させない。
- VNet 内 ACI の outbound 接続には **NAT Gateway** を関連付ける。未構成のまま image pull / Microsoft Entra token / Azure control plane 到達を成功扱いしない。
- SQL / Cosmos の Private Endpoint、VNet link、Private DNS zone、DNS zone group を冪等に作成/再利用する。
  - `az cloud show --query name` で cloud を確認し、公式 Private Endpoint DNS matrix の該当 cloud / service / API 行から zone を選ぶ。未掲載の組合せは `blocked` とし、suffix を推測しない。
  - 現行 ASDW-WEB の固定 zone 値は `AzureCloud`（commercial）だけを対象にする。Azure SQL は `privatelink.database.windows.net`（接続時は通常の `<server>.database.windows.net` FQDN）、Cosmos DB for NoSQL は group ID `Sql` / `privatelink.documents.azure.com`。他 cloud は固定値を流用せず `blocked` とする。
- 登録・検証用 Linux ACI には **User-assigned Managed Identity** を割り当て、対象 SQL / Cosmos に必要な最小権限だけを付与する。接続文字列、共有キー、長期 token を保存しない。

### §2.5 ASDW data network contract

ASDW-WEB Step 1.2 / 1.3 の network key、route、topology、ACI lifecycle、passwordless data-plane 契約は、[ASDW data network contract](references/asdw-data-verifier-contract.md) を正本として適用する。

---

## §3 Azure CLI 利用不可時フォールバック

Azure CLI が未インストール、未認証、権限不足、またはネットワーク制約で利用できない場合、Agent は推測で成功扱いにしない。

必須対応:

1. 実行できなかったコマンド、exit code、主要 stderr を秘密情報を除いて記録する。
2. `ac-verification.md` や作業ログに `NEEDS-VERIFICATION` または `FAIL` と理由を記録する。
3. 代替案として Azure Portal / GitHub Actions / Azure Cloud Shell / 管理者による再実行手順を記載する。
4. 成功確認がない Resource ID / URL / provisioning state を捏造しない。

---

## §4 禁止事項

- 秘密情報、接続文字列、アクセストークン、Function key をログ・成果物・PR 本文に出力しない。
- `az delete` / `az group delete` / `rm -rf` / `git push --force` を本 Skill のテンプレートとして提示しない。
- Azure CLI の失敗を `|| true` で握りつぶさない。
- 存在確認なしに「作成済み」「Succeeded」と記録しない。
- Resource Group やリソースが存在しない状態で verify を GREEN としない。
- Azure Policy pre-flight が未完了または `blocked` の状態で create / update を開始しない。
- public access を無効化する effective Policy がある状態で public access enable / firewall rule 作成を retry しない。
- CIDR、既存 NSP、Policy exemption、許可タグ、Private DNS 構成を推測で生成しない。

## Related Skills

| Skill | 関係 | 説明 |
|---|---|---|
| `azure-region-policy` | 前提 | location 選択・fallback 理由記録 |
| `azure-ac-verification` | 後続 | verify 結果を AC 判定として記録 |
| `github-actions-cicd` | 関連 | GitHub Actions から Azure CLI を実行する場合の OIDC / workflow 規約 |
| `harness-safety-guard` | 前提 | 破壊的操作の実行前検出 |
| `harness-verification-loop` | 後続 | build / lint / test / security / diff 検証 |