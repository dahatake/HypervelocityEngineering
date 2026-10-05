# ASDW Data Network Contract

ASDW-WEB Step 1.2 の verifier と Step 1.3 の deploy / registration が共有する network 契約の正本。
Prompt / template は本ファイルへ委譲し、network key、route、ACI lifecycle の詳細を複製しない。

## HVE launcher environment contract

生成する `verify-data-resources.sh` は、HVE Runnerがsession開始前に構築したimmutableなsanitized environment snapshotから次のキーを受け取り、**全キーを実際に参照**する。`RESOURCE_GROUP`の唯一の正本はeffective workflow parameterである。`SUBSCRIPTION_ID`の唯一の正本は`az account show`の読み取り結果であり、`DATA_VERIFY_ACR_NAME` / `DATA_VERIFY_ACI_IMAGE`を含むその他すべてのresource名・resource ID・endpointの唯一の正本は、`RESOURCE_GROUP` / `RESOURCE_SUFFIX` / `SUBSCRIPTION_ID`からHVEが決定論的に導出した値である。`RESOURCE_SUFFIX`はworkflowがAPP-IDから導出するため、利用者がAzureリソース名を事前に決めたりexportしたりする必要はない。唯一の例外は`DATA_DEPLOY_IDENTITY_CLIENT_ID`で、これはAzureがprep stageでのuser-assigned identity作成時に採番するため、launcherがprep成功後に`az identity show --query clientId`で読み戻して後続stageへ注入する。検証イメージは呼出し側が事前に用意した承認済みイメージではなく、同じrunのprep stageが作成するregistryへbuildしたHVE所有イメージであり、Agentも呼出し側もこれらの導出キーをexport・上書きしない。HVEは現在の設計からAuditRecord modeを解決した後、全必須値が非空・前後空白なし・単一行であり`DATA_NETWORK_MODE=private`であることを検証し、欠落・形式不正・外部`cli_url` runtimeではAgent sessionを開始しない。verifier 自身は `source` / `.` を使わず環境変数だけを受け取る。中間 environment file を作成・読込せず、Agentによるexport、将来用の未使用キー、同義キー、別のnetwork設定ファイルは追加しない。prep / create / registration / verify は同じHVE-owned snapshotを使用し、ambient値の後続変更や前runのfile stateを再利用しない。

- `DATA_NETWORK_MODE`
- `DATA_VNET_NAME`
- `DATA_PRIVATE_ENDPOINT_SUBNET_ID`
- `DATA_ACI_SUBNET_ID`
- `DATA_NAT_GATEWAY_NAME`
- `DATA_DEPLOY_IDENTITY_ID`
- `DATA_DEPLOY_IDENTITY_CLIENT_ID`
- `SQL_PRIVATE_ENDPOINT_NAME`
- `COSMOS_PRIVATE_ENDPOINT_NAME`
- `SQL_PRIVATE_DNS_ZONE`
- `COSMOS_PRIVATE_DNS_ZONE`

同じsnapshotで必須とする共通resource/imageキーは次の通りとする。

- `RESOURCE_GROUP`, `LOCATION`, `SUBSCRIPTION_ID`
- HVE導出の検証イメージ: `DATA_VERIFY_ACR_NAME`, `DATA_VERIFY_ACI_IMAGE`
- `SQL_SERVER`, `SQL_HOST`, `SQL_DATABASE`, `SQL_DB_SVC01`, `SQL_DB_SVC02`, `SQL_DB_SVC03`, `SQL_DB_SVC07`, `SQL_DB_SVC09`
- `COSMOS_ACCOUNT`, `COSMOS_ENDPOINT`, `COSMOS_DATABASE`, `COSMOS_CONTAINER_VOC`
- `CONFIDENTIAL_LEDGER_NAME`, `CONFIDENTIAL_LEDGER_ENDPOINT`

`sql-ledger-digest` modeでは`SQL_DB_SVC12`, `SQL_AUDIT_TABLE`を追加で必須とし、`acl-direct` modeでは`CONFIDENTIAL_LEDGER_COLLECTION`を追加で必須とする。反対modeのキーはsnapshotから除外する。HVEは外部入力の`DATA_CREATE_RUN_ID`, `DATA_REGISTER_RUN_ID`, `DATA_VERIFY_RUN_ID`, `AUDIT_RECORD_JSON`, `HVE_ASDW_SAMPLE_DATA_JSON`, `DATA_DEPLOY_ENV`, `SAMPLE_DATA`, `WORK_DIR`をsnapshotから除外する。stage run IDはlauncherがstageごとに生成し、non-Audit payloadとAuditRecord payloadはlauncherがstable `src/data/sample-data.json` snapshotから生成する。

`DATA_NETWORK_MODE` は `public` / `private` / `nsp` / `blocked` のいずれかだけを受理する。値が空、未知、または当該 mode の必須キーが空なら `[ERROR]` を出して非ゼロ終了する。別 mode への黙示 fallback、特に private / nsp の失敗時に public endpoint へ fallback してはならない。

network分岐は外側に1つだけ置き、selectorを厳密に`case "${DATA_NETWORK_MODE:?}" in`とする。`${DATA_NETWORK_MODE:-}`、command substitution、alias selectorは使用しない。`public)`、`private)`、`nsp)`、`blocked)`を各1回と、最後の`*)`を1回だけ置く。4 mode間の相対順序は規定しないが、最終wildcardは必ず最後に置き、staticな`[ERROR]`出力と直接の`exit 1`だけを実行する。未知値・空値をcase後へfall-throughさせない。複合pattern、先行wildcard、重複clause、2つ目のcaseを追加しない。

private-capable verifier の実行ホストは GNU coreutils の `timeout` を提供する Bash 環境とする。verifier 実行前に `command -v timeout` で確認し、未提供なら別の待機実装を追加せず停止する。

### `public` mode

固定 evidence schema が未定義のため、最初の Azure CLI / SDK / data-plane 呼び出しより前に `[ERROR]` を出力して非ゼロ終了する。
直接接続、一時 ACI、retry、fallback を開始しない。
呼出し側が mode 値を設定しただけで承認済みとみなさず、public access enable、firewall rule、Policy exemption、許可タグ変更を開始しない。

### `private` mode

検証順序を次の通り固定する。前段が失敗した場合は後段へ進まない。

1. **launcher環境入力の受領**: HVE launcher はRunnerがpre-sessionでfreezeしたnetwork contractの11キー、HVE導出の`DATA_VERIFY_ACI_IMAGE`、および上記resource名キーを受け取る。loader / shell hook / PATH injection値を除外したsanitized環境を子processへ渡し、cryptographically secureな32桁小文字16進run IDの`DATA_VERIFY_RUN_ID`だけをlauncher自身が補う。verifier自身は中間 environment file を読み込まず、環境変数だけを受け取る。

2. **mode 別必須値検証**: `DATA_NETWORK_MODE`、`DATA_VNET_NAME`、`DATA_PRIVATE_ENDPOINT_SUBNET_ID`、`DATA_ACI_SUBNET_ID`、`DATA_NAT_GATEWAY_NAME`、`DATA_DEPLOY_IDENTITY_ID`、`DATA_DEPLOY_IDENTITY_CLIENT_ID`、`SQL_PRIVATE_ENDPOINT_NAME`、`COSMOS_PRIVATE_ENDPOINT_NAME`、`SQL_PRIVATE_DNS_ZONE`、`COSMOS_PRIVATE_DNS_ZONE`、`DATA_VERIFY_ACI_IMAGE`、`DATA_VERIFY_RUN_ID` が空でなく、`DATA_NETWORK_MODE=private` であることを検証する。`DATA_VERIFY_RUN_ID` は `^[0-9a-f]{32}$` に完全一致しなければならない。さらに `command -v timeout` が成功することを確認する。形式不正・不足・`timeout` 不在時は最初の Azure CLI 呼び出しより前に非ゼロ終了する。

3. **read-only topology 検証**: データプレーン検証より前に、Azure CLI の `show` / `list` 系コマンドだけで次を検証する。topology 不一致時は一時 ACI を作成せず非ゼロ終了する。

- `DATA_VNET_NAME` の実在と、`DATA_PRIVATE_ENDPOINT_SUBNET_ID` / `DATA_ACI_SUBNET_ID` がその VNet に属する別 subnet であること。
- ACI subnet が `Microsoft.ContainerInstance/containerGroups` へ委任され、関連付く NAT Gateway 名が `DATA_NAT_GATEWAY_NAME` と一致すること。
- `SQL_PRIVATE_ENDPOINT_NAME` / `COSMOS_PRIVATE_ENDPOINT_NAME` の Private Endpoint connection state が `Approved` で、各 Private Endpoint の subnet ID が `DATA_PRIVATE_ENDPOINT_SUBNET_ID` と一致すること。
- `SQL_PRIVATE_DNS_ZONE` / `COSMOS_PRIVATE_DNS_ZONE` の Private DNS zone、各 Private Endpoint の DNS zone group、対象 VNet への VNet link が実在すること。
- `DATA_DEPLOY_IDENTITY_ID` の User-assigned Managed Identity が実在し、その client ID が `DATA_DEPLOY_IDENTITY_CLIENT_ID` と一致すること。

`verify-data-resources.sh` は Azure CLI 実行前に正確に `set -euo pipefail` を有効化する。private case branch の必須 topology / ACI lifecycle コマンドは `private)` 直下の直列文として実行する。branch 内で許容する関数定義は `cleanup_aci` だけとし、必須コマンドを未呼出helper、`if` / loop / `case` の内部、`eval` / `source` / `.` / 間接展開 / 動的command名へ隠さない。各 topology guard は true branch を直接の `exit 1` として直後に終了する。host側の実行文は必須値チェック、固定名代入、単一の direct `az` 結果代入、direct `az`、比較用 `if`、`exit 1`、`fi`、`trap cleanup_aci EXIT INT TERM` だけとし、これらの外側へ `;` / `&&` / `||` / `&` を連結しない。

4. **one-shot ACI 作成**: 1〜3 の成功後に限り、`aci_name="verify-data-$DATA_VERIFY_RUN_ID"` と秘密を含まない `aci_command` を確定する。`aci_created=0` を `trap` 前に初期化する。`cleanup_aci` は `aci_created` が `1` の場合だけ、`az container show --query "tags.hveVerifyRunId"` で同一run IDタグを再照合してから `az container delete --resource-group "$RESOURCE_GROUP" --name "$aci_name" --yes || true` を実行する。ACI 作成前に同名のACIが存在したら非ゼロ終了し、cleanup対象にしない。

同名ACIの事前確認は直列の `aci_name_count="$(az container list --resource-group "$RESOURCE_GROUP" --query "[?name=='$aci_name'] | length(@)" --output tsv)"` を実行し、そのコマンドが成功して `aci_name_count` が厳密に `0` の場合だけ create を許可する。`az container show` の非ゼロを一律に不存在扱いしてはならない。

ACI 作成**前**に `trap cleanup_aci EXIT INT TERM` を登録する。`--tags hveVerifyRunId="$DATA_VERIFY_RUN_ID"` 付きの `az container create --resource-group "$RESOURCE_GROUP" --name "$aci_name" --image "$DATA_VERIFY_ACI_IMAGE" --subnet "$DATA_ACI_SUBNET_ID" --acr-identity "$DATA_DEPLOY_IDENTITY_ID" --assign-identity "$DATA_DEPLOY_IDENTITY_ID" --restart-policy Never --os-type Linux --cpu 1 --memory 1 --command-line "$aci_command"` を1回だけ実行した**直後**に `aci_created=1`、次に `aci_wait_failed=0` を設定する。create失敗または応答不明時にはフラグを立てず、既存ACIを削除してはならない。cleanup deleteの失敗で元の終了状態を上書きしない。

終了コードやログを判定する前に、固定の `aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)" || aci_wait_failed=1` で終了を待つ。この限定されたOR-listだけを例外とする。canonicalな `aci_exit_code="$(az container show --resource-group "$RESOURCE_GROUP" --name "$aci_name" --query "containers[0].instanceView.currentState.exitCode" --output tsv)"` を取得し、wait失敗、非ゼロexit、空ログで非ゼロ終了する。待機なし、無制限の`--follow`、timeout値変更、`Start-Sleep`による手動pollingは禁止する。実行順序は ACI 作成、`aci_created=1`、`aci_wait_failed=0`、終了待機、終了コード取得、結果判定に固定する。

検証 ACI の作成と cleanup は verifier が所有し、DataDeploy の登録 ACI 内で verifier を実行しない。private mode ではローカル端末から SQL / Cosmos / Azure confidential ledger の data-plane へ直接接続しない。public endpoint / firewall rule / 共有キー / SAS / 秘密を含む接続文字列 / 長期 token への fallback を禁止する。

ACI内は `DefaultAzureCredential` を使用する。SQL件数取得は `mssql-python` と `UID=$DATA_DEPLOY_IDENTITY_CLIENT_ID;Authentication=ActiveDirectoryMSI;Encrypt=yes;TrustServerCertificate=no` のpasswordless接続にする。Cosmos件数取得は `azure-cosmos` を使い、`credential = DefaultAzureCredential(managed_identity_client_id=DATA_DEPLOY_IDENTITY_CLIENT_ID); client = CosmosClient(endpoint, credential=credential)` のように同じcredentialを渡す。ODBC版 `sqlcmd -G` のvariantを確認せずUAMI認証として扱うことを禁止する。

ACI内Pythonは、`src/data/sample-data.json` から生成時に算出した非ゼロ期待件数を `actual == expected or sys.exit(1)` で比較する。APP-009では `Member`, `ConsentRecord`, `DataRightsRequest`, `LoyaltyAccount`, `PointTransaction`, `Reward`, `RewardExchange`, `PaidMembershipContract`, `SupportCase`, `CaseResolution`, `VocRecord`, `AuditRecord` の対象エンティティ集合を過不足なく検証する。先頭10件のSQLエンティティは各SQLテーブルを正しい`SQL_DB_SVC*`へ対応付け、`AuditRecord`は次のstorage mode契約へ従う。`assert`、`PYTHONOPTIMIZE`、`python -O` / `-OO` を用いてはならない。ACI内Pythonは`try/finally`を使用し、全 SQL cursor / connection、および CosmosClient / DefaultAzureCredential を必ず `close()` してから終了する。

#### AuditRecord storage mode contract

`AuditRecord`のstorage modeは、`docs/azure/azure-services-data.md`の「エンティティ別ストア選定」表にある`Entity`列と`Chosen Azure service`列だけを読む単一resolverから解決する。`## 1. エンティティ別ストア選定`見出しとその直下の表、表内の`Entity`列、`Chosen Azure service`列、`Entity`値が`AuditRecord`と完全一致する行は、それぞれ厳密に1件でなければならない。0件または複数件は`blocked`とする。`Alternatives`、`Rationale`、`Evidence`、別表の`AuditRecord の整合性証明`はmode判定に使用しない。未知方式、両方式に一致する曖昧な記述は`blocked`として、最初のAzure CLI / SDK / data-plane呼び出しより前に非ゼロ終了する。direct modeへの既定fallbackは禁止する。Step 1.2とStep 1.3は同じresolverを使用し、Step 1.3は最初のAzure writeより前にも現在の設計からmodeを再解決する。Step 1.3は入力verifierが現在のmodeに適合することを同じvalidatorで再検査し、不一致またはstaleなら最初のwrite前に`blocked`とする。別ファイルまたは環境変数へmodeを複製しない。

受理するmodeは次の2つだけとし、Step 1.2 verifierとStep 1.3 deploy / registrationは同じmodeを使用する。

DataDesignの`Chosen Azure service（正式名称）`で推奨するcanonical値は、SQL modeを`Azure SQL Database の append-only ledger table（SVC-12 の監査証拠 SoT）+ Azure confidential ledger（信頼済み database digest 保管先、条件付き）`、direct modeを`Azure confidential ledger（AuditRecord を直接格納）`とする。resolverはbalancedな`**...**` / `` `...` `` / `*...*`装飾と末尾の`。`または`.`を1個だけ除去した後も有限canonical集合への完全一致を維持し、否定・曖昧・両方式混在を受理しない。

- `sql-ledger-digest`: `Chosen Azure service`が、業務ペイロードのSoTとしてAzure SQL Databaseのappend-only ledger tableを選定し、Azure confidential ledgerを信頼済みdatabase digest保管先として選定した場合。Step 1.2は`SQL_DB_SVC12`の`dbo.${SQL_AUDIT_TABLE}`から`AuditRecord`件数を取得してsample-data期待件数と比較し、対象tableの`ledger_type_desc`が`APPEND_ONLY_LEDGER_TABLE`であること、およびcurrentな`sys.database_ledger_digest_locations`に`CONFIDENTIAL_LEDGER_ENDPOINT`と同じhostのpathと非空の`last_digest_block_id`があることを検証する。Step 1.3は最初のAzure create / update / data-plane writeより前に既存SVC-12 database、table type、current digest targetをread-onlyでpreflightする。既存値が同じmodeに一致しなければ一切writeせず`blocked`とし、対象が存在しない場合だけpreflight成功後にdatabase、append-only ledger table、database digest uploadを作成する。`AuditRecord`業務ペイロードはSQL tableだけへ登録し、Azure confidential ledgerへ直接登録・同期してはならない。
- `acl-direct`: `Chosen Azure service`が、`AuditRecord`業務ペイロードをAzure confidential ledgerへ直接格納する方式を選定した場合。`CONFIDENTIAL_LEDGER_COLLECTION`をStep 1.2 / 1.3が共有する専用collection IDの正本キーとし、両Stepは呼出し側からexportされた同じ非空値をconsumeする。空値、暗黙の既定値、別collectionへのfallbackは最初のAzure CLI / SDK / data-plane呼び出しより前に`blocked`とする。Step 1.2はverifier-owned private ACI内で、同じUser-assigned Managed Identityを使用して対象専用collectionのapplication entriesを実際に列挙・集計し、sample-data期待件数と比較する。Azure confidential ledger Python SDKの必須TLS契約として、`TemporaryDirectory()`配下のまだ存在しない`ledger_certificate.pem`を`ledger_certificate_path`へ渡し、SDKにledger TLS certificateを取得・保存させる。`ConfidentialLedgerClient`とcredentialをSQL / Cosmos clientと同じ`finally`で`close()`した後、certificate directoryを`cleanup()`する。Step 1.3は同じ専用collectionへ`AuditRecord`を登録する。このmodeでは`AuditRecord`用の`SQL_DB_SVC12`または`SQL_AUDIT_TABLE`を必須にしない。

### `nsp` mode

固定 evidence schema が未定義のため、最初の Azure CLI / SDK / data-plane 呼び出しより前に `[ERROR]` を出力して非ゼロ終了する。
直接接続、一時 ACI、retry、fallback を開始しない。
任意 JSON の別々の階層から承認を推測せず、固定 schema と対象 resource ID を検証できない限り blocked とする。現時点では固定 schema 未定義であり、任意 JSON parserを生成しない。

### `blocked` mode

blocker理由を `[ERROR]` として出力して非ゼロ終了する。Azure create / update、件数取得用の一時 ACI、データプレーン検証を開始しない。

## HVE-owned producer contract (Agent read-only)

- HVE は Agent session 開始前に `create-azure-data-resources-prep.sh`、`create-azure-data-resources.sh`、`data-registration-script.sh` を3本一組で処理する。generation status は `reused` / `regenerated` の2値だけとし、3本すべてが current validator を通る場合は前者、1本でも欠落・不適合なら全3本を決定論的に生成・検証・promoteして後者とする。
- HVE generatorだけがproduction生成を所有する。Agentはprivate builder、test fixture、canonical base64、decoded ASTを逆解析しない。これらの内部表現をPrompt、template、Agent tool callから復元しない。
- pre-session generation failure では Agent session を開始しない。HVE が sanitized failure を記録して Step を fail にし、Agent evidence / launcher request は存在しない。
- session開始後の launcher current-validation rejection では、Agentは返された事実をwork証跡へ記録し、producerを編集せず、別launcher・直接Bash・手動Azure CLIへfallbackしない。
- Agentはproducerを作成・変更・再生成・修復しない。許可される責務はread-only inspection、証跡、fixed launcher requestだけである。
- launcher は producer を生成・修復しない。安定読取した同一bytesを各stageのcurrent validatorへ渡し、成功時だけ実行するvalidate / execute onlyの境界とする。stage順序は`prep → create → registration → verify`に固定する。

## Step 1.3 DataDeploy network contract

deploy / registration / verify scripts は次の全キーを実際に consumeし、同じHVE launcher environmentから受け取る。別 mode への黙示 fallback、将来用の未使用キー、同義キー、別network設定ファイルを追加しない。DataDeploy callerは、これらnetwork契約キー（`private` modeでは下記11キー全て）とHVE導出の`DATA_VERIFY_ACI_IMAGE`を各launcher stageへ同じ値で渡す。`DATA_VERIFY_ACR_NAME`はprep stageにだけ渡す。`DATA_VERIFY_RUN_ID`はlauncherが生成する。`private` modeで必須値が欠落している場合、verifyはlauncher environment契約不整合としてAzure process開始前にfailする。

- `DATA_NETWORK_MODE`
- `DATA_VNET_NAME`
- `DATA_PRIVATE_ENDPOINT_SUBNET_ID`
- `DATA_ACI_SUBNET_ID`
- `DATA_NAT_GATEWAY_NAME`
- `DATA_DEPLOY_IDENTITY_ID`
- `DATA_DEPLOY_IDENTITY_CLIENT_ID`
- `SQL_PRIVATE_ENDPOINT_NAME`
- `COSMOS_PRIVATE_ENDPOINT_NAME`
- `SQL_PRIVATE_DNS_ZONE`
- `COSMOS_PRIVATE_DNS_ZONE`

### `private` mode

Azure write前にsubscription全体をread-only棚卸しし、人手承認済みの非重複CIDRだけを使う。Private Endpoint 専用 subnet と Azure Container Instances 専用 subnet を分離し、ACI subnetを委任してNAT Gatewayを関連付ける。

SQL / Cosmos の Private Endpoint、Private DNS zone、VNet link、DNS zone group、User-assigned Managed Identityを冪等に作成または再利用する。接続文字列、共有キー、長期 token を保存しない。各キーは次の責務でconsumeする。

- DATA_NETWORK_MODE を route 分岐に使う。
- DATA_VNET_NAME を VNet の作成または再利用に使う。
- DATA_PRIVATE_ENDPOINT_SUBNET_ID を Private Endpoint subnet に使う。
- DATA_ACI_SUBNET_ID を registration / verify ACI の --subnet に使う。
- DATA_NAT_GATEWAY_NAME を ACI subnet の NAT Gateway に使う。
- DATA_DEPLOY_IDENTITY_ID を --assign-identity に使う。
- DATA_DEPLOY_IDENTITY_CLIENT_ID を AZURE_CLIENT_ID に使う。
- SQL_PRIVATE_ENDPOINT_NAME / COSMOS_PRIVATE_ENDPOINT_NAME を Private Endpoint 名に使う。
- SQL_PRIVATE_DNS_ZONE / COSMOS_PRIVATE_DNS_ZONE を DNS zone・zone group・VNet link の作成または再利用に使う。

#### prep stage の検証イメージ契約

検証／登録 ACI が使うイメージは呼出し側から持ち込まず、prep stage が同じrunの中で作成する。prep は User-assigned Managed Identity を作成した後、`DATA_VERIFY_ACR_NAME` の Azure Container Registry を SKU `Basic` で冪等に作成し、repo 内の HVE 所有 build context `src/infra/azure/data-verify` から `DATA_VERIFY_ACI_IMAGE` を `az acr build` でビルドし、当該 identity へ registry scope の `acrpull` ロールを付与する。ロール付与は identity の `principalId` に対して行い、`id` を使わない。registry を public endpoint のまま使い、ACI subnet は NAT Gateway 経由で pull する。admin user、共有キー、pull secret、`docker login` を使用しない。ACR 名は global 一意・5〜50 文字・英数字のみという Azure の制約に従い、HVE が `RESOURCE_GROUP` と `RESOURCE_SUFFIX` から決定論的に導出する。Agent はこのイメージ参照を推測・上書き・再定義しない。

`DATA_VERIFY_ACR_NAME` を consume するのは prep stage だけであり、create / registration / verify stage へは渡さない。これらの stage は `DATA_VERIFY_ACI_IMAGE` だけを参照するため、未使用キーを配布しない原則を維持する。

registry 作成・ビルド・ロール付与はいずれも prep stage 内で完了させ、ACI を作成する create / registration / verify stage より前に順序を固定する。`az acr build` が subscription 種別や SKU 制約で拒否された場合は、別 SKU への自動引き上げ、admin user の有効化、ローカル build への切り替えを行わず prep を非ゼロ終了させる。

Azure Container Instances は system-assigned managed identity による ACR pull をサポートしないため、pull 用 identity は必ず user-assigned とし、`az container create` は `--acr-identity` と `--assign-identity` の両方へ同じ user-assigned identity のリソース ID を渡す。

公式根拠: Microsoft Learn「[Deploy to Azure Container Instances from Azure Container Registry using a managed identity](https://learn.microsoft.com/azure/container-instances/using-azure-container-registry-mi)」で system-assigned 非対応と `--acr-identity` / `acrpull` 付与手順を確認した。「[Naming rules and restrictions for Azure resources](https://learn.microsoft.com/azure/azure-resource-manager/management/resource-name-rules)」で registry 名が global・5〜50・英数字のみであることを確認した（確認日: 2026-07-27）。

登録は VNet 内の一時 ACI、件数検証は Step.1.2 verifier が所有する別の一時 ACIで直列実行する。Python実行イメージ`DATA_VERIFY_ACI_IMAGE`は同じHVE launcher environmentから渡す。SQLはACI内の`mssql-python`で `UID=$DATA_DEPLOY_IDENTITY_CLIENT_ID;Authentication=ActiveDirectoryMSI;Encrypt=yes;TrustServerCertificate=no` を使う。Cosmosは`azure-cosmos`を使い、`credential = DefaultAzureCredential(managed_identity_client_id=DATA_DEPLOY_IDENTITY_CLIENT_ID); client = CosmosClient(endpoint, credential=credential)` のように同じcredentialを明示的に渡す。

HVE launcherはcryptographically secureな32桁小文字16進の`DATA_CREATE_RUN_ID`、`DATA_REGISTER_RUN_ID`、`DATA_VERIFY_RUN_ID`を対象stageの子process開始前に生成する。Agentまたは外部環境からrun IDをexportしない。登録ACIは`aci_name="data-register-$DATA_REGISTER_RUN_ID"`とし、作成前に同名のACIが存在すれば非ゼロ終了する。`aci_created=0`をtrap前に初期化し、cleanupは`aci_created=1`の場合だけ`az container show --query "tags.hveRegisterRunId"`で同一run IDタグを再照合してから `az container delete --resource-group "$RESOURCE_GROUP" --name "$aci_name" --yes` を実行する。create失敗または応答不明時には既存ACIを削除してはならない。

`--tags hveRegisterRunId="$DATA_REGISTER_RUN_ID"`付きの `az container create --resource-group "$RESOURCE_GROUP" --name "$aci_name" --image "$DATA_VERIFY_ACI_IMAGE" --subnet "$DATA_ACI_SUBNET_ID" --acr-identity "$DATA_DEPLOY_IDENTITY_ID" --assign-identity "$DATA_DEPLOY_IDENTITY_ID" --restart-policy Never --os-type Linux --cpu 1 --memory 1 --command-line "$aci_command"` を1回だけ実行する。cleanup deleteの失敗で元の終了状態を上書きしない。

create直後に`aci_created=1`、`aci_wait_failed=0`をこの順で設定する。続けて`aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)" || aci_wait_failed=1`で最大600秒だけ完了を待ち、`aci_exit_code="$(az container show --resource-group "$RESOURCE_GROUP" --name "$aci_name" --query "containers[0].instanceView.currentState.exitCode" --output tsv)"`を取得する。ACI内canonical PythonはAuditRecordのwrite/no-opとresource commit完了後にだけ`HVE_AUDIT_REGISTRATION_OK`を1行出力する。wait失敗、exit codeが厳密に`0`でない、またはlog全体が厳密に`HVE_AUDIT_REGISTRATION_OK`でない場合は非ゼロ終了し、trapによるownership-safe cleanupへ進む。待機・exit code・success markerを確認せずcleanupまたはverifyへ進んではならない。

公式根拠: Microsoft Learn「[Run containerized tasks with restart policies](https://learn.microsoft.com/azure/container-instances/container-instances-restart-policy)」で`Never`がrun-once taskを最大1回実行し、完了後に`Terminated`となってlogsを取得できることを確認した。また「[Azure Container Instances states](https://learn.microsoft.com/azure/container-instances/container-state)」で`currentState`の`Terminated`にexit codeが伴い、ACI createが非同期であることを確認した（確認日: 2026-07-17）。

#### Step 1.3 AuditRecord registration contract

`data-registration-script.sh` は現在の設計から解決した `AuditRecord` storage modeに従い、登録ACIを次の固定契約で生成する。`DATA_REGISTER_ACI_IMAGE`等の同義キーを追加せず、検証ACIと共有する既存の`DATA_VERIFY_ACI_IMAGE`を登録ACIの`--image`にも使用する。

`data-registration-script.sh`はAuditRecord専用とする。APP-009の他11エンティティは選定リソースのcreateフロー内で登録し、全12件の最終実在はAC-3で検証する。1行目を厳密に`#!/usr/bin/env bash`、2行目を行頭完全一致の`# HVE-AUDIT-REGISTRATION-BEGIN`とし、AuditRecord用の専用ACI lifecycleを行頭完全一致の`# HVE-AUDIT-REGISTRATION-END`まで1回だけ囲む。BEGIN markerをBash shebang直後の固定位置へ置くことで、heredoc、function、条件分岐、loop、case、subshell、brace groupへ隠さない。END marker後はコメントまたは厳密に`printf '%s\n' '<single-quoted literal>'`の固定literalログ1形だけを許可し、`echo`、別形式の`printf`、redirection、その他の実行文を一切置かない。marker欠落・重複・逆順・空blockはfail-closedとする。`AUDIT_RECORD_JSON`、`auditEventId`、`SQL_AUDIT_TABLE`、`SQL_DB_SVC12`、`CONFIDENTIAL_LEDGER_COLLECTION`、SQL/ACLのAuditRecord payload writeはこのblock外へ重複実装しない。

静的artifact gateの保証範囲は、選択modeのAudit専用block、登録ACIのidentity / environment / ownership、およびblock内AuditRecordの固定冪等grammarまでとする。block外の実行文を全面禁止することで、自己再実行、Audit重複write、別wrapper、background / scheduler、一般process launcherをfail-closedにする。block外に他11エンティティの全処理が実在することや、再実行時に重複しないことを一般shell解析で推測しない。完全12エンティティ登録と冪等性はStep 1.3の実行証跡でも検証し、Runnerはregistry宣言された`AC-1`（verifier GREEN）、`AC-2`（create + registration再実行でエラー・重複なし）、`AC-3`（全対象件数がsample-data期待値と一致）をすべて完了条件として強制する。

AuditRecordは両modeとも、**同一writerによる逐次再実行**を冪等性の保証境界とする。同一`auditEventId` + 同一canonical payloadの再実行はno-op成功、同一`auditEventId` + 異なるcanonical payloadはfail-closed、未登録時だけ1件writeとする。重複実行を同時並行で開始しない。既存重複を検出した場合もfail-closedとし、重複を追加・更新・削除して隠さない。`auditEventId`は前後空白のない正規化済み文字列だけを受理し、payloadは`json.dumps(..., ensure_ascii=False, separators=(",", ":"), sort_keys=True)`を両mode共通の型保持canonical表現とする。

Runnerのpre-session deterministic gateは、現在の設計mode、入力`verify-data-resources.sh`、HVE-owned producer 3本をAgent session開始前に検査・必要時再生成する。session開始後も各launcher requestで同じdesign-aware current contractを再検査し、Agent writeに依存しない。

既存の保証境界用語では、これをRunnerのpre-main deterministic gateと呼ぶ。post-mainとstep-endのstatic gateはdefense-in-depthとしてcurrent contractを再確認するが、Agentセッション内でwriteが未実行だったことを遡及保証しない。その保証はproducer 3pathをAgent write集合から除外するpermission boundaryが担う。

- 最初のAzure CLIより前に、共通で`DATA_REGISTER_RUN_ID`、`RESOURCE_GROUP`、`DATA_ACI_SUBNET_ID`、`DATA_DEPLOY_IDENTITY_ID`、`DATA_DEPLOY_IDENTITY_CLIENT_ID`、`DATA_VERIFY_ACI_IMAGE`、`AUDIT_RECORD_JSON`を`: "${KEY:?}"`で必須化する。
- `sql-ledger-digest`では追加で`SQL_HOST`、`SQL_DB_SVC12`、`SQL_AUDIT_TABLE`を必須化し、`CONFIDENTIAL_LEDGER_COLLECTION`をguardまたはACI環境変数へ渡さない。`acl-direct`では追加で`CONFIDENTIAL_LEDGER_ENDPOINT`、`CONFIDENTIAL_LEDGER_COLLECTION`を必須化し、`SQL_DB_SVC12`と`SQL_AUDIT_TABLE`をguardまたはACI環境変数へ渡さない。
- marker blockのhost論理文は、先頭1回の`set -euo pipefail`、上記の固定guard列、固定ownership cleanup / collision guard / trap、1つの直接`aci_command` assignment、その直後の唯一のcanonical `az container create`、固定bounded wait / exit-code / success-marker判定だけを許可する。`set -x` / `xtrace`、任意の`printf` / `echo`、外部送信、追加host command、未知guardを加えない。
- `aci_command`は1つの直接double-quoted assignmentとし、その直後の論理文を唯一の`az container create`にする。createは`--image "$DATA_VERIFY_ACI_IMAGE"`、`--subnet "$DATA_ACI_SUBNET_ID"`、`--acr-identity "$DATA_DEPLOY_IDENTITY_ID"`、`--assign-identity "$DATA_DEPLOY_IDENTITY_ID"`、`--restart-policy Never --os-type Linux --cpu 1 --memory 1`、唯一のownership tag、末尾の`--command-line "$aci_command"`を完全一致で使用する。追加option / tag / parameter transformation / control operator、prefix / suffix / `|| true` / 再代入 / nested command substitutionを加えない。
- RunnerのStep 1.3 permission gateは、execution requestごとに現在のdesign-aware contractを再検査し、成功時だけApproveOnceとする。実行経路はHVE所有のbyte-pinned launcherだけであり、raw commandを厳密に`python -m hve.asdw_data_script_launcher prep`、`create`、`registration`、`verify`のいずれか1つに限定する。launcherは正規repo内のregular fileとvalidator依存input（design / sample-data）を安定読取し、取得した同一UTF-8/LF script bytesを対応validatorへ渡してから、再エンコードせず`bash --noprofile --norc -s`へstdinで入力する。実行後にパスを再openしない。Bash子プロセスはHVEが固定したsystem Bashとsystem runtime pathを使い、継承`PATH`、`BASH_ENV`、`ENV`、loader / shell-function / Azure CLI config injection変数を渡さない。prep/createは常に対で検査し、createはnon-Audit登録だけ、registrationはAuditRecordだけ、verifyは検証だけを担当する。HVE run内では、launcherがprep、create、registrationの各成功時だけrun root直下のHVE専用markerを記録し、後段は同一runの直前stage markerがない場合にAzure操作前で停止する。prepの再実行はprep/create/registration markerを、createの再実行はcreate/registration markerを、registrationの再実行はregistration markerを開始時に無効化する。いずれかのstageが非ゼロ終了またはstatic contract不適合なら、そのstage以降を許可しない。各stageは前段確認、marker無効化、validator、Bash実行、成功marker commitまでをHVE所有のrun-private非待機lockで直列化し、同一runの並行stage要求はAzure process起動前に拒否する。script間のchild実行は禁止する。`bash` / `./`による4スクリプト直接実行、`\`を`/`へ書き換える同一視、同一要求での書換え、`source` / `.`, `BASH_ENV`, shell変数 / glob / symlink alias、複数実行、wrapper / redirection / control operatorを拒否する。HVE GUI / local host transportとしてpermission requestに現れる例外は、厳密な`pwsh.exe -NoLogo -NoProfile -Command "<canonical command>"`だけである。permission requestは生成主体を示す改ざん不能なprovenanceを持たないため、この例外は権限を広げず、追加option・改行・入れ子引用符を拒否したうえで内側を固定preflight、固定inspection、または上記launcherとの完全一致で再判定するtransport正規化に限る。GUI transportでは`commands[].identifier`も外側の完全なtransport文字列と厳密一致しなければならず、`pwsh.exe`のbasename、任意path、または内側command identifierを許可しない。固定inspectionのpath metadataは内側のcanonical commandと一致する場合だけ許可する。Agentにこのwrapperの要求・組み立てを許可するものではない。Step 1.3のshell permissionはfail-closed allowlistとし、固定preflight（`az --version` / `az account show -o tsv` / `gh --version` / `gh auth status`）、固定inspection、および上記launcherだけを許可する。Python / Node.js / PowerShell / cmd / make / npm等の不透明なwrapperを既定承認しない。実行に必要な環境変数はHVE起動元または呼出し側が事前にexportし、permission境界内で任意の`source` / `export` wrapperを組み立てない。
- `AUDIT_RECORD_JSON`は唯一の`--secure-environment-variables`として`AUDIT_RECORD_JSON="$AUDIT_RECORD_JSON"`だけを渡す。通常の`--environment-variables`は先頭を`AZURE_CLIENT_ID="$DATA_DEPLOY_IDENTITY_CLIENT_ID"`とし、その後を選択modeのキーだけにする。各assignmentは空白なしの`NAME="$SOURCE"`とし、未知キー、proxy、bare token、追加option、反対modeキーを混在させない。
- ACI内Pythonはcanonical importを先頭に置き、未呼出helper、nested scope、別try、early exit、import alias、protected builtin / import名の再定義、resource / data-flow値の再代入、追加writeを含めない。全resourceはtry前の単一`ExitStack()`へ`closing(...)` / context managerとして登録し、同じtop-level `try/finally`の`resources.close()`で解放する。1つのcloseが失敗しても残りのclose / TLS directory cleanupを継続する。
- 両modeとも`AUDIT_RECORD_JSON`を`json.loads(os.environ["AUDIT_RECORD_JSON"])`で1回だけ読み、`isinstance(audit, dict)`、`isinstance(audit["auditEventId"], str)`、`audit_id = audit["auditEventId"].strip()`、non-empty `audit_id`、元IDと`audit_id`の完全一致をこの順でfail-closedに検証する。`null`、bool、array、object、空文字、空白だけ・前後空白付きのIDを文字列化または黙示正規化して受理しない。
- `sql-ledger-digest`: `mssql-python`で`SQL_DB_SVC12`へUAMI接続し、`SQL_AUDIT_TABLE`を`[A-Za-z_][A-Za-z0-9_]*`へ完全一致させる。唯一のSQL batchをparameterized実行し、`WITH (UPDLOCK, HOLDLOCK)`を使って同じ`audit_id`の範囲を逐次化し、未登録時だけ`INSERT INTO [dbo].[{audit_table}] (id, payload) VALUES (?, ?)`を実行する。同batchのread-backは`COUNT_BIG(*)`とcanonical payload一致件数を返し、結果が厳密に`(1, 1)`でなければ、欠落・既存重複・異payloadとしてfail-closedにする。その後だけ1回commitする。commit失敗時は未確定writeをconnection closeでrollbackし、SQL `execute` / `executemany`はこのconditional INSERT / count/read-back batchだけとする。Azure confidential ledger application entryへ登録・同期しない。
- `acl-direct`: `TemporaryDirectory()`配下のまだ存在しない`ledger_certificate.pem`を`ledger_certificate_path`へ渡し、`DefaultAzureCredential(managed_identity_client_id=client_id)`を`$DATA_DEPLOY_IDENTITY_CLIENT_ID`へ結び、同じcredentialで`CONFIDENTIAL_LEDGER_ENDPOINT`の`ConfidentialLedgerClient`を作る。`list_ledger_entries(collection_id=collection)`は`islice(..., 1001)`で最大1001件だけ遅延列挙し、1000件超はfail-closedにする。全entryが`collections.abc.Mapping`、`contents`が文字列、decode結果がJSON objectであることを要求し、不正entryを黙って除外しない。同じ`auditEventId`が2件以上ならfail-closed、1件なら保存`contents`と今回のcanonical payload文字列を完全比較してno-op、0件なら`begin_create_ledger_entry({"contents": payload}, collection_id=collection).result()`で未登録時だけappendする。したがって`begin_create_ledger_entry(...).result()`を厳密に1回だけ含める。SQL connect / cursor / execute / commitを含めない。

AC-2のlive証跡は同一writerで同じ入力を逐次2回実行し、2回とも成功・件数増加なしを確認する。異payload、既存重複、上限超過、不正entry、commit / cleanup失敗のfail-closed分岐はdeterministic static gateとlocal synthetic runtime testsの証跡を参照し、live環境へ不正データを作成して証明しない。同時並行実行の冪等性を主張しない。

TLS certificate path契約の根拠はMicrosoft Learn「Azure Confidential Ledger client library for Python - version 1.1.1」および`ConfidentialLedgerClient` constructor（`ledger_certificate_path`必須）とする。固定certificate、TLS検証無効化、certificate path省略へfallbackしない。

登録ACI cleanup完了後、HVE launcherは同じimmutable environment snapshotを使用してverify stageを開始し、`DATA_VERIFY_RUN_ID`だけをそのstage用に生成する。Agentまたは制御hostがnetwork key、image、resource名、run IDを再exportしてはならない。verifier自身に`source`/`.`を追加してはならない。検証ACIはStep.1.2 verifierが所有し、登録ACI内でverifierを実行しない。

private modeではローカル端末から SQL / Cosmos の data-plane へ直接接続しない。public endpoint / firewall rule / 共有キー / SAS / 秘密を含む接続文字列 / 長期 token への fallback を禁止する。

### `public` / `nsp` / `blocked` mode

#### `public` route

- `public` は Policy と入力設計の両方で許可された場合だけ使用する。
- public access enable、`AllowAzureServices`、firewall rule、Policy exemptionを、public access無効化Policyの検出後に作成またはretryしない。これらの方式は retry 候補から除外する。

#### `nsp` route

- 現時点では固定 schema 未定義のため、`nsp` は `blocked` として停止する。対象 Resource ID・association・access mode・承認根拠の共有 schema が実装されるまで NSP を自動作成しない。

#### `blocked` route

- 理由をwork証跡へ記録して停止し、Azure create / update、登録、検証を開始しない。
