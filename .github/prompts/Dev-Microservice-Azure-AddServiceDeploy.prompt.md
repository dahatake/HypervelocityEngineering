> Azure追加サービスをAzure CLIで冪等作成し、service-catalog等を更新、AC検証で完了判定する

> **WORK**: `work/run/<run-id>/Dev-Microservice-Azure-AddServiceDeploy/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

> 共通行動規約 (`.github/copilot-instructions.md` §0 / Skill `agent-common-preamble`) の禁止事項を本 Agent でも明示する。詳細は継承元を参照。

- **捏造禁止**: ID / URL / 数値 / 固有名を根拠なく生成しない。不明は `TBD` または `不明（要確認）` と明記する。
- **無関係変更禁止**: スコープ外のファイル整形・一括リファクタ・不要依存追加を行わない（最小差分）。
- **検証マーカー欠落禁止**: 完了報告に `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を必ず含める。
- **work/ 直接編集禁止**: 既存 `work/` ファイルは「削除 → 新規作成」（Skill `work-artifacts-layout` §4.1）。
- **`original-docs/` 書き込み禁止**: 読み取り専用（追記・削除・変更不可）。
- **ルート `README.md` 変更禁止**: `/README.md` の作成・変更を行わない。
- **秘密情報禁止**: 鍵 / トークン / 個人情報 / 内部 URL 等を成果物に含めない。
- **必須成果物未生成での終了禁止**: `ac-verification.md`（§7 の出力先）を作成しないままターンを終えない（背景処理の完了待ちであっても、待たずにターンを終えない）。デプロイ / 検証が GREEN 未達（ブロッカー・タイムアウト・権限不足等）でも、AC-1 を `❌` とし状態欄にブロッカー理由を記載して必ず作成してから終了する（未作成は Orchestrator gate がファイル不在で fail 降格する）。
- **出力契約外成果物の作成禁止**: §2「成果物」/ §7 の出力先パスに無い成果物（PR 用課題管理表等）を、出所が確認できない要求に基づいて作成しない（必須成果物 `ac-verification.md` / `created-resources.json` / `completion-report.md` の作成を優先する）。
- **同期完了コマンドの再取得禁止**: 同期実行で既に完了したコマンドに対し出力取得ツールを再呼び出ししない（出力はコマンド実行時に取得する。再取得は背景実行コマンドに限る）。
- **ローカル実行時の git / PR 操作禁止**: ローカル実行（CLI / GUI）では、`main` への `git commit` / `git reset` / ブランチ切替や `gh pr create` を行わない（完了はファイル生成で判定する）。§7.3 / §7.4 の PR 提出フローは GitHub Issue 起点モード限定であり、ローカル実行では適用しない。
- **ASDW-WEB Step 単位 remote CI/CD 対象外**: HVE GUI/CLI の「github.com で CI/CD」を使う ASDW-WEB 経路でも、本 Step.2.2 は Step 単位ブランチ / PR / merge の対象外。ローカル `az` 直接実行と `{WORK}` 証跡作成に集中する。

## Agent 固有の Skills 依存

- `azure-cli-deploy-scripts` — prep / create / verify と冪等性パターン
- `azure-ac-verification` — Azure 実在 AC の検証と記録
- `azure-region-policy` — region 選定と fallback 理由
- `microsoft-foundry` — AI/LLM で Microsoft Foundry を採用した場合だけ使う external meta skill。未導入時の Azure write 方針は「Microsoft Foundry 配置時の external meta skill 利用」に従う。

## Azure 公式情報参照（Microsoft Learn MCP 必須）

- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の `artifacts/cli-evidence.md` または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。必要に応じて `az ... -h` / パッケージマネージャ / 公式 CLI help を補助確認として使う。

### Microsoft Foundry 配置時の external meta skill 利用（AI/LLM 該当時のみ）

- `docs/azure/azure-services-additional.md` が Microsoft Foundry (Foundry Agent Service) を採用している場合だけ、この節を適用する。Foundry非該当なら `microsoft-foundry` meta skillの読込を要求しない。
1. session で公開済みの `microsoft-foundry` meta skillを必ず最初に読み、その指示に従って接続済み official MCP の利用可能な Foundry関連toolを最初に発見する。server名・tool名を推測しない。
2. meta skill 自身の routing に従い、resource / Project / model deploymentに一致する guidance だけを読む。HVE 側で sub-skill 名を推測・列挙しない。
3. meta skill が未導入または session に公開されていない場合は、最初の Azure write より前に block する。Azure write を実行せず `asdw-web:blocked` とし、未導入理由・再開前提を `{WORK}plan.md` と必須の `{WORK}ac-verification.md` に記録する。
4. generic `azure-prepare` / `azure-deploy` / `azure-validate` で代替してはならない。現行の Azure CLI script、AC-13 / AC-14、成果物 path の責務を維持する。
5. ASDW optional Foundry では MCP server を新規追加・接続構成変更しない。session へ既に接続済みの official MCP だけを discovery 対象とする。

### Microsoft Foundry 配置時の確認手順（AI/LLM 該当時のみ）

1. Microsoft Learn MCP の**検索結果から対象ページを特定**し、次のページを**全文取得**する。
  - resource / Project / モデル配置 quickstart: https://learn.microsoft.com/azure/foundry/tutorials/quickstart-create-foundry-resources
  - Project 作成: https://learn.microsoft.com/azure/foundry/how-to/create-projects
  - モデル配置と live catalog: https://learn.microsoft.com/azure/foundry/foundry-models/how-to/create-model-deployments
  - Model Router: https://learn.microsoft.com/azure/foundry/openai/how-to/model-router
  - モデル version / 更新方針: https://learn.microsoft.com/azure/foundry/foundry-models/concepts/model-versions
2. `az cognitiveservices account project create -h` / `project show -h` / `account list-models -h` / `account deployment create -h` で、現在の CLI 引数を確認する。
3. quickstart のモデル例は操作説明用であり、最新性・要件適合性を示さないため**選定根拠にしない**。
4. `{WORK}artifacts/cli-evidence.md` に `取得日（ISO）` / `対象 account` / `対象 region` / モデル名 / `モデルバージョン` / `デプロイ種別(sku-name)` / capacity / quota / title / URL / 確認事項を記録する。

## 0.1) スコープ
- `docs/azure/azure-services-additional.md` を根拠に、追加Azureサービスを **Azure CLI で冪等に作成**する。
- 作成結果（resourceId / endpoint / region など）を安定に取得し、以下を更新する：
  - `docs/catalog/service-catalog-matrix.md`
  - `{WORK}`（計画・根拠・成果物）

## 1) 入力（不足があれば最初に1回だけ確認）
Issue/依頼文から次を取得する（見つからない場合は `{WORK}plan.md` に「不足」と「質問」を書いて停止）：
- リソースグループ名: `{リソースグループ名}`
- （任意だが推奨）`subscription` / `tenant` / 優先リージョン / 命名規則

根拠ファイル（必読）：
- `docs/azure/azure-services-additional.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D10-API-Event-File-連携契約パック.md` — API/イベント/ファイル連携契約
- `knowledge/D15-非機能-運用-監視-DR-仕様書.md` — 非機能・運用・監視・DR
- `knowledge/D20-セキュア設計-実装ガードレール.md` — セキュア設計・実装ガードレール

## APP-ID スコープ → Skill `app-scope-resolution` を参照
## 2) 成果物（必ずこの場所へ）

### インフラ（Azure CLIスクリプト）
- `src/infra/azure/create-azure-additional-resources-prep.sh`
- `src/infra/azure/create-azure-additional-resources/create.sh`
- （複数サービスの場合）`src/infra/azure/create-azure-additional-resources/services/<service>.sh`
- （検証）`src/infra/azure/create-azure-additional-resources/verify-*.sh`（Secret 依存がある場合は `src/infra/azure/verify-secrets-expiry.sh` を呼び出す）

### 計画・根拠・出力（work）
- `{WORK}plan.md`（DAG+見積+AC定義+検証+分割判定）
- `{WORK}subissues.md`（分割が必要な場合のみ）
- `{WORK}onboarding.md`（入口不明のときのみ）
- `{WORK}contracts/additional-services.md`（作成対象一覧を固定化：サービス種別/必須パラメータ/命名）
- `{WORK}artifacts/created-resources.json`（作成/確認した値の機械可読ログ。各サービスの断片 `{WORK}artifacts/created-resources.d/<service>.json` を全 wave 完了後に結合して生成する。詳細は §3.3.1「サービス作成の並列実行方針」）
- `{WORK}artifacts/logs/<service>.log`（並列実行時の各サービスの実行ログ。標準出力混線防止のため個別ファイルに分離する）
- `{WORK}artifacts/cli-evidence.md`（`az ... -h` や実行結果の要点を短く抜粋して根拠化）
- `{WORK}ac-verification.md`（AC検証結果の記録。§3.3 Execute 実行時のみ生成。Orchestrator gate は `Issue-<識別子>` 直下を検査するため `artifacts/` 配下に置かない）

## 3) 実行フロー（必ずこの順番）
### 3.1 Preflight（最初にやる）
- `az version` / `az account show` / `az account list --query ...` で実行環境とアカウント状態を確認。
- 結果を `{WORK}artifacts/cli-evidence.md` に記録する（後続の AC 検証で参照するため）。
- 対象リソースグループが存在するか確認し、存在しない場合は冪等に作成する（`azure-cli-deploy-scripts` Skill §1.2 および `azure-region-policy` Skill §1 に準拠）。
- 未ログイン・権限不足・CLI未導入などで実行不能なら、**実行はしない**。
  - 代わりに「ユーザーが実行する手順」と「前提条件」を `src/infra/README.md` と `{WORK}plan.md` に残す。

### 3.2 Plan（実装前に必須）
`docs/azure/azure-services-additional.md` から「作成対象サービス一覧」を抽出し、
`{WORK}contracts/additional-services.md` に固定する（後続Subが迷わないため）。

その上で `{WORK}plan.md` を作成する（詳細は skills を使う）：
- `.github/skills/task-dag-planning/SKILL.md`
- `.github/skills/work-artifacts-layout/SKILL.md`
- **plan.md 作成時の必須手順（省略禁止）**:
  1. `task-dag-planning` SKILL.md §2.1.2 を read して手順を確認する
  2. plan.md の **1-4 行目** に以下の HTML コメントメタデータを記載する（YAML front matter より前）:
     ```
     <!-- task_scope: single|multi -->
     <!-- context_size: small|medium|large -->
     <!-- split_decision: PROCEED or SPLIT_REQUIRED -->
     <!-- subissues_count: N -->
     <!-- implementation_files: true or false -->
     ```
  3. plan.md 本文に `## 分割判定` セクションを含める（テンプレート: `.github/skills/task-dag-planning/references/plan-template.md` を参照）
  4. コミット前に `bash .github/scripts/bash/validate-plan.sh --path {WORK}plan.md` を execute で実行し、✅ PASS を確認する

#### 3.2.1 受け入れ条件（AC）の定義（plan.md 内に必須）

plan.md に `## 受け入れ条件（AC）` セクションを必ず含める。
Issue/依頼文から AC を抽出する。Issue に AC が明示されていない場合は以下のデフォルト AC を適用する。
Issue に AC が部分的に記載されている場合は、Issue の AC を優先し、不足分のみデフォルトから補完する（重複時は Issue 側を採用）。

**デフォルト AC（本 Agent 固有・番号順が優先度順）：**

| # | AC 項目 | 重要度 |
|---|---------|--------|
| **AC-1** | **スクリプト実行後に、Microsoft Azure 上に作成すべき全リソースが実際に作成されていること**（`az resource show` 等で `provisioningState: Succeeded` を確認） | **最重要** |
| AC-2 | `docs/azure/azure-services-additional.md` に記載された全サービスに対応するスクリプトが存在する（1スクリプトが複数サービスを扱う場合も可） | 必須 |
| AC-3 | 各スクリプトが冪等パターン（存在確認→作成/更新→結果取得）を実装している | 必須 |
| AC-4 | `created-resources.json` に全作成リソースの情報が記録されている（`resourceId` / `region` は必須。`endpoint` はサービスが提供する場合のみ） | 必須 |
| AC-5 | `docs/catalog/service-catalog-matrix.md` が更新され、重複行がない | 必須 |
| AC-6 | `src/infra/README.md` に実行手順と前提条件が記載されている | 必須 |
| AC-7 | 秘密情報（鍵・トークン・パスワード等）が成果物に含まれていない | 必須 |
| AC-8 | 破壊的変更（削除/置換）が行われていない | 必須 |
| AC-9 | **ロールバック手順 README が存在する** — `src/infra/azure/rollback/addservice-rollback.md` が存在し、テンプレ（`docs/templates/rollback-readme-template.md`）に定義された 4 必須セクション（直前バージョン特定 / ロールバック実行 / 検証スクリプト再実行 / service-catalog 巻き戻し）を満たすこと。新規サービス/リソース追加時はこの README も更新する。 | 必須 |
| AC-10 | NFR（性能/可用性/セキュリティ）のうち該当項目を `docs/templates/nfr-acceptance-template.md` から選択して検証する（非該当は N/A） | 必須 |
| AC-11 | Key Vault Secret 依存がある場合、期限切れ検出を `verify-*.sh` へ組み込む（依存なしは N/A） | 必須 |
| AC-12 | verify 項目と TestSpec の Test-ID が AC-ID で相互参照可能である | 必須 |
| **AC-13** | **AI/LLM（Microsoft Foundry）採用時、Foundry resource が `--allow-project-management` 明示で作成され、デプロイ済みモデルが 1 件以上存在する**（`az cognitiveservices account deployment list` で確認。**0 件は FAIL**。AI/LLM 非該当は N/A） | **最重要** |
| **AC-14** | **AI/LLM（Microsoft Foundry）採用時、Foundry Project 子リソースが実在し `provisioningState: Succeeded` である**（`az cognitiveservices account project show` で確認。親 account の存在を代用しない。AI/LLM 非該当は N/A） | **最重要** |

AC 定義後の変更は禁止（追加・修正は Issue 本文の更新を通じてのみ許可）。

#### 3.2.2 見積に AC 検証時間を含める

AC 検証時間の見積目安：
（目安：リソース数 × 0.5分 + 記録 1分）

根拠の扱い：
- **推測禁止**。必要な `az` コマンド/必須引数/SKU/制約は、原則として
  - `az <group> <command> -h`（CLIヘルプ）
  - `az provider show` / `az <service> list` / `az account list-locations`
  - リポジトリ内の設計/要件ファイル
  で確定し、`{WORK}artifacts/cli-evidence.md` に短く残す。

### 3.3 Execute（plan.md の判定結果が PROCEED の場合のみ）

> ⚠️ **前提条件（すべて満たすこと）**:
> 1. `plan.md` の `## 分割判定` で `判定結果: PROCEED` と記載済みであること
> 2. task_scope=single かつ context_size ≤ medium であること
> 3. `subissues.md` が不要であることを確認済みであること
>
> いずれか1つでも未達の場合、本セクションには進まない。
> plan.md と subissues.md のみを作成し、PR を [WIP] として提出する。

#### 3.3.0 Pre-flight（TDD サイクル必須）

以下を順に実行し、すべて成功した場合のみ Deploy に進む。いずれか失敗時は `{WORK}completion-report.md` に `<!-- fatal: pre-flight-failed: {理由} -->` を記載し、非ゼロ exit で Step を fail させる（`NEEDS-VERIFICATION` で逃げることは**禁止**）。

- `command -v az` / `az account show -o tsv`
- `command -v gh` / `gh auth status`

#### 3.3.1 RED → Deploy → GREEN（TDD サイクル）

- **RED（初回 deploy 時のみ）**: `verify-*.sh` を実行し、リソース未作成で FAIL を確認。冪等再実行時はスキップ可（`ac-verification.md` に明記）。
- **Deploy**: `prep.sh` → `create.sh` をローカル `az` 直接実行。HVE GUI/CLI の ASDW-WEB Step 単位 remote CI/CD は Step.3.4 / Step.4.3 のみを対象とするため、本 Step.2.2 では `gh workflow run` を発火しない。
- **GREEN**: `verify-*.sh` 再実行で全 TC PASS。出力ログを `ac-verification.md` の AC-1 行に証跡として貼る。

スクリプト実装方針（`azure-cli-deploy-scripts` Skill §1「3点セットテンプレート」および §2「冪等性パターン」に準拠）：
- `prep.sh`：依存確認（導入は最小）。秘密情報を扱わない。
- `create.sh`：全体オーケストレーション。**サービス別スクリプトはサブシェルのバックグラウンド実行（`&` + `wait`）で並列に呼ぶ**（詳細は下記「サービス作成の並列実行方針」）。
- `services/<service>.sh`：各サービスの作成を担当（Skill §2 冪等性パターン準拠）。並列実行される前提のため、他サービスの出力ファイルに書き込まない（自分専用の出力先のみに書き込む）。
- 破壊的変更（削除/置換）はしない（必要なら Plan に明記し、Sub化を優先）。

##### サービス作成の並列実行方針（必須）

`create.sh` は逐次実行ではなく、**バックグラウンドジョブによる並列実行**でサービス作成を行う（同時実行数の上限は設けず対象サービス全てを同時起動する。追加サービス数は少数〔目安10件未満〕のため、セマフォ等の同時実行数制御は導入しない）。

1. **2 waves 構成（実在する依存関係への対応）**: `docs/azure/azure-services-additional.md` に記載のとおり「ネットワーク境界」カテゴリ（Private Endpoint 等）は Wave A の他サービス（Foundry / Key Vault / データストア等）のリソースIDを参照するため、以下の2段階で実行する。
   - **Wave A（並列）**: 「ネットワーク境界」カテゴリ以外の全 `services/<service>.sh` を `bash "services/<service>.sh" > "{WORK}artifacts/logs/<service>.log" 2>&1 &` の形でバックグラウンド起動し、PID を配列変数に保持する（`bash` 経由で起動し、実行権限ビット `+x` の有無に依存しない。Windows 上で checkout した場合に実行ビットが失われるケースがあるため）。
   - **Wave A 完了待ち**: 保持した全 PID それぞれに `wait "$pid"` し、終了コードを集計する。
   - **Wave B（Wave A 全成功時のみ実行）**: 「ネットワーク境界」カテゴリの `services/<service>.sh` を同様に `bash` 経由で実行する（対象は通常1〜2個のため逐次でよい）。Wave A に1つでも失敗があれば Wave B は実行せず、`create.sh` を非ゼロ終了させる。
   - ネットワーク境界カテゴリの追加サービスが存在しない場合、Wave B はスキップし Wave A のみで完了する。
2. **ログ分離（必須）**: 並列実行時の標準出力混線を防ぐため、各 `services/<service>.sh` の出力は個別ログファイル（`{WORK}artifacts/logs/<service>.log`）にリダイレクトする。`create.sh` は全ジョブ完了後にサービスごとの PASS/FAIL 要約のみを標準出力へ出す（ログ全文は貼らない）。
3. **終了コード集約（必須）**: いずれかのサービスが失敗しても、他の並列ジョブの完了を待ってから（同一 wave 内の全ジョブ `wait` 後に）`create.sh` 全体を非ゼロ終了させる（フェイルファストで途中の他ジョブを kill しない。理由: 作成中の Azure リソースを中途半端な状態で放置しないため）。
4. **`created-resources.json` の並行書き込み衝突防止（必須）**: 各 `services/<service>.sh` は共有の `created-resources.json` に直接書き込まず、自分専用の断片ファイル（`{WORK}artifacts/created-resources.d/<service>.json` — 結合用の中間ファイルであり最終成果物ではない）にのみ結果を出力する。全 wave 完了後、`create.sh` が全断片を結合して最終成果物 `{WORK}artifacts/created-resources.json` を生成する（`jq` が利用可能なら `jq -s '.' {WORK}artifacts/created-resources.d/*.json` で結合し、`jq` 未導入環境では `python3` 標準ライブラリ `json` で同等の結合を行うフォールバックとする。`jq` は §3.3.0 Pre-flight の必須チェック対象に含めない）。

リトライ（必須）：
- 一時的失敗は指数バックオフで最大3回（create系のみ。各 `services/<service>.sh` 内で個別に実施し、並列実行中の他サービスに影響しない）

実行（可能な場合のみ）：
- `prep.sh` → `create.sh`
- 実行ログの要点を `{WORK}artifacts/cli-evidence.md` に残す（全文貼りは避ける。各サービスの詳細ログは `{WORK}artifacts/logs/<service>.log` を参照する旨を記載する）

#### 3.3.2 AI/LLM（Microsoft Foundry）サービスの追加デプロイ要件（必須）

`docs/azure/azure-services-additional.md` の採用 Azure サービスに **Microsoft Foundry (Foundry Agent Service)**（AI/LLM カテゴリ）が含まれる場合、**アカウント作成だけでは不十分**であり以下を必須とする。Project 未作成・モデル未デプロイのまま完了してはならない。AI/LLM 非該当時は本節を N/A とする。

1. **設計キーの事前検証**: `Foundry Project名` / `Project location` / `Project作成方針` / `モデル選択方式` / モデル名・version・format・SKU・capacity を読み取る。Project名が `TBD`、または live 確認が必要なモデル値を確定できない場合は Azure を変更せず `asdw-web:blocked` で停止する。
2. **Foundry resource を project 管理対応で作成**: `az cognitiveservices account create --kind AIServices --allow-project-management ...` のように **`--allow-project-management` を明示指定**する。既存 account は `account show` で `kind=AIServices` と location を確認する。Project 管理可否の応答プロパティは公式資料で存在が確認できた場合だけ使い、名前を推測しない。公式 `project show/create` が Project 管理非対応を返した場合は account を置換せず、応答を証跡にして block する。
3. **Foundry Project の存在確認**: 最初に次のコマンドで、設計された account 配下の Project を確認する。

  ```azurecli
  az cognitiveservices account project show --name <account> --resource-group <RG> --project-name <project>
  ```

  既存 Project は account / Project名 / Project location が設計値と一致し、親 account の location も設計された Project location と一致する場合だけ再利用する。`project show` の `location` と `account show` の location を別々に取得して比較し、不一致なら自動更新・置換せず block する。存在しない場合だけ次を実行する。

  ```azurecli
  az cognitiveservices account project create --name <account> --resource-group <RG> --project-name <project> --location <location>
  ```

  作成または再利用後、次のコマンドで再確認し `Succeeded` を確認する。旧 Azure AI CLI の project コマンド群は使用しない。

  ```azurecli
  az cognitiveservices account project show --name <account> --resource-group <RG> --project-name <project>
  ```

4. **モデル選択方式の確定**:
  - ユーザー／要件でモデル指定がある場合は `fixed` とし、live catalog と quota で配置可能性を確認する。
  - 指定がない一般用途は `model-router`（Balanced）の適合性を先に確認する。機能・region・SKU・quota・Agent tool 制約で不適合または利用不可の場合だけ `fixed` へ fallback する。
  - `az cognitiveservices account list-models` と usage / quota の公式コマンドで、対象 account / region の live 値を確認する。quota は subscription / region / SKU の利用可能上限、capacity は今回の deployment に割り当てる要求量として区別し、要求 capacity が利用可能 quota を超える選択肢を採用しない。モデル名・version・SKU・capacity を Prompt や quickstart の静的例から選ばない。
  - `model-router` は live catalog の `name=model-router` に一致する entry が返す format / version / 対応 SKU をそのまま使用し、variant 名や version を推測しない。Balanced は routing mode でありモデル名ではない。カスタム subset は要件がある場合だけ設定する。
  - `fixed` は対象環境で配置可能な最新互換 version を選び、モデル更新方針も記録する。
  - live 値を取得できない場合、公開値や過去値で代用せず block する。
5. **モデルデプロイの実行**: 確定した値を使い、`az cognitiveservices account deployment create --name <account> -g <RG> --deployment-name <名> --model-name <名> --model-version <版> --model-format <形式> --sku-name <種別> --sku-capacity <容量>` でモデルを冪等にデプロイする。先に `deployment show` で存在確認し、不一致の既存 deployment を黙って再利用しない。
6. **決定的 env 変数**: Project名 / Project location / モデル選択方式 / モデル名・version・format・SKU・capacity を `additional-resources.env.sh` 等へ定義する。秘密情報と静的 fallback モデル値は含めない。
7. **作成結果の記録**: `created-resources.d/<service>.json` の Foundry 項目に account resourceId、Project resource type `Microsoft.CognitiveServices/accounts/projects`、Project名、Project resourceId、location、provisioningState、Project endpoint（サービスが返す場合）、モデル選択方式、deployment名を記録する。Project endpoint が管理API応答に無い場合はプロパティ名を推測せず、公式手順で取得できる値だけを記録する。
8. **verify スクリプトの Project / モデル TC**:
  - `az cognitiveservices account project show` で Project が `Succeeded` であることを確認する（AC-14）。親 account の存在や `created-resources.json` だけで PASS にしない。
  - `az cognitiveservices account deployment list -n <account> -g <RG>` で**アカウントにデプロイ済みのモデル**が 1 件以上であることを確認する（AC-13、0 件は FAIL）。
9. **テスト仕様書**: `docs/test-specs/deploy-step2-additional-test-spec.md` に Project 実在 TC（AC-14）とモデル実在 TC（AC-13）を別 Test-ID で作成する。

## 4) ドキュメント更新（冪等・重複禁止）
### 4.1 service-catalog.md
`docs/catalog/service-catalog-matrix.md` の表を更新する（重複行は作らない）。
- 列（固定）：サービスID | サービス名 | Azureのサービス名 | 機能名 | 機能の種類 | AzureサービスのURL | リージョン
- "根拠"は近くに1行だけ（例：参照ファイルパス、endpoint取得コマンド）

### 4.2 src/infra/README.md
`src/infra/README.md` に最小追記だけ：
- 追加サービスの目的（1〜3行）
- 実行手順（prep → create、前提条件）
- 注意（資格情報は出力しない / リージョン差 / 再実行）

> ⚠️ **ルートの `/README.md` は変更しないこと。** インフラ手順は `src/infra/README.md` に集約する。

## 5) 大量生成・巨大出力になりそうなとき
- 生成物/抽出が巨大になりそうなら `.github/skills/output/large-output-chunking/SKILL.md` を使い、
  `{WORK}artifacts/<name>.index.md` + `part-0001.md...` で分割する。

## 6) 最終品質レビュー（単回インライン・セルフチェック）

### 6.1 セルフチェック契約

以下のドメイン固有観点は、通常時に1回のインライン・セルフチェックとしてまとめて確認し、敵対的レビューの発動条件ではない。

### 6.2 ドメイン固有観点
- **機能完全性・要件達成度**：copilot-instructions.md の要件（冪等性、秘密情報無し、破壊的変更無し）がすべて満たされ、service-catalog が更新されているか。§3.2.1 の AC-2〜AC-8 を概略確認し、詳細な合否と証跡は独立した §7 AC gate で検証する
- **ユーザー視点・実行可能性**：`src/infra/README.md` の手順が明確で、前提条件が正確で、環境がない場合の代替手段が示されているか
- **保守性・スケーラビリティ・信頼性**：スクリプトが冪等で、リトライ対応があり、cli-evidence に根拠が残り、再実行に耐えられるか

### 6.3 反映方法
確認結果は独立したレビュー成果物にせず、問題があれば主成果物を修正し、完了報告の検証結果へ簡潔に含める。

## 7) 受け入れ条件（AC）の検証と完了判定（必須 — 本 Agent 固有セクション）

> **位置付け**: §6 の単回インライン・セルフチェックとは別の、本 Agent 固有の最終ゲート。
> §6 のセルフチェック完了後に実行する。本セクションを通過しない限り PR を完了（Ready for Review）にしない。
>
> **分割モード時の扱い**: Skill task-dag-planning（分割モード）に入った場合、本セクションはスキップする（実装が存在しないため検証対象がない）。

### 7.1 AC 検証の実施（§6 完了後に必ず実行）

§3.2.1 で定義した AC の各項目を検証する。§6 のセルフチェックで既に確認済みの項目（AC-7 秘密情報、AC-8 破壊的変更等）は §6 の結果を証跡として引用してよい（再検証は不要）。

#### AC-1 の検証手順（最重要 — 省略禁止）

`contracts/additional-services.md` の全リソースに対して、`azure-ac-verification` Skill §3.2 の検証コマンドパターンに従いコマンドを実行する。

`provisioningState` の判定は `azure-ac-verification` Skill §3.3 に従う。

**Azure CLI 実行が不可能な場合**（§3.1 Preflight で実行不能と判定済み）：
Pre-flight 失敗時は §3.3.0 に従い Step を fail させる。**AC-1 を `⏳ NEEDS-VERIFICATION` として Step を success にしてはならない**（Orchestrator gate で fail に降格される）。

#### AC-13 の検証手順（AI/LLM 採用時は最重要 — 省略禁止）

AI/LLM（Microsoft Foundry）を採用している場合のみ実施する（非該当は N/A と明記）。§3.3.2 に従い、`az cognitiveservices account deployment list -n <account> -g <RG>` を実行し **デプロイ済みモデルが 1 件以上**であることを確認する（**0 件は FAIL**）。`verify-additional-resources.sh` のモデル検証 TC の GREEN ログを AC-13 行の証跡として貼る。Pre-flight 失敗時は AC-1 と同様に Step を fail させ、`⏳` で success にしてはならない。

#### AC-14 の検証手順（AI/LLM 採用時は最重要 — 省略禁止）

AI/LLM（Microsoft Foundry）を採用している場合のみ実施する（非該当は N/A と明記）。§3.3.2 に従い、`az cognitiveservices account project show --name <account> --resource-group <RG> --project-name <project>` を実行し、Project 子リソースの `provisioningState: Succeeded` を確認する。親 account の `account show` や `created-resources.json` だけで代用してはならない。

#### `ac-verification.md` のフォーマット要件（必須）

- 各 AC は 1 行 1 AC のテーブル行で記録（例: `| AC-1 | Azure 上に全リソース存在 | ✅ | <verify-*.sh GREEN ログ抜粋> |`）
- 状態欄: `✅` / `❌` / `⏳` / `N/A`。実在系 **AC-1 は `✅` のみ許容**。**AC-13 は AI/LLM 採用時は `✅` のみ許容**、**AC-14 も AI/LLM 採用時は `✅` のみ許容**する。AI/LLM 非該当時も `| AC-13 | ... | N/A | AI/LLM 非採用 |` と `| AC-14 | ... | N/A | AI/LLM 非採用 |` の2行を必ず残す（行ごと省略しない）。

#### AC-2〜AC-8 の検証

| AC | 検証方法 |
|----|----------|
| AC-2 | `contracts/additional-services.md` の各サービスに対応するスクリプトファイルの存在確認 |
| AC-3 | §6 の機能完全性・要件達成度観点の結果を引用（冪等パターンの実装確認） |
| AC-4 | `created-resources.json` の JSON 構造を読み取り、全リソースに `resourceId` / `region` があることを確認 |
| AC-5 | `docs/catalog/service-catalog-matrix.md` を読み取り、追加行の存在と重複なしを確認 |
| AC-6 | `src/infra/README.md` に実行手順セクションが存在することを確認 |
| AC-7 | §6 の機能完全性・要件達成度観点の結果を引用。追加で成果物全体に対し秘密情報パターン（`password`, `secret`, `key=`, Bearer トークン等）の grep を実施 |
| AC-8 | §6 の機能完全性・要件達成度観点の結果を引用（破壊的変更がないことの確認） |

### 7.2 証跡の記録

検証結果を `{WORK}ac-verification.md` に `azure-ac-verification` Skill §1 のテンプレートに従って記録する。AC-1 詳細（リソース名・種別・provisioningState・確認コマンド）も含めること。

### 7.3 完了判定（機械的に実行）

`azure-ac-verification` Skill §2 の統一ステータス名に従う。本 Agent 固有の対応付け：
- **PASS** = 全 AC が PASS → PR を Ready for Review として提出
- **NEEDS-VERIFICATION** = 実在系 AC-1 以外で `⏳` がある場合のみ許容（AC-1 は `⏳` 不許可）→ PR Ready for Review
- **FAIL** = AC-1 が `❌` または `⏳`、もしくは他 AC が `❌` → 修正して再検証（AC 検証起点で最大2回）。解消しなければ [WIP] で提出。Orchestrator gate が Step を fail に降格する。

### 7.4 PR description への反映（必須）

§6 の PR 必須記載（目的/変更点/影響範囲/検証結果/既知の制約/次にやるSub）の `検証結果` に、以下を統合して記載する：
- AC-1 の結果を最初に明記（PASS / FAIL / ⏳（手動実行待ち））
- 完了判定結果（PASS / NEEDS-VERIFICATION / FAIL）
- 詳細は `ac-verification.md` を参照する旨のリンク
- ⏳（手動実行待ち）の場合：ユーザーが実行すべき検証コマンド一覧（§7.1 AC-1 検証手順で使用したコマンドを転記）

### 7.5 禁止事項
- AC 検証を省略して PR を提出すること（→ 必ず §7.1 を実行してから提出する）
- `ac-verification.md` を作成しないままタスクを終えること（→ ブロッカー / タイムアウト時も未達 AC を `❌` で記録して必ず作成する。未作成は Orchestrator gate がファイル不在で fail 降格）
- 証跡なしで PASS と判定すること（→ 検証方法と結果を ac-verification.md に記録する）
- AC-1 が FAIL の状態で DONE と判定すること（→ 修正して再検証するか [WIP] で提出する）
- AC を事後的に緩和・削除して PASS にすること（→ AC 変更は Issue 本文の更新のみ）
- `created-resources.json` の記載のみで AC-1 を PASS とすること（→ JSON は自己申告。`az` コマンドによる実環境確認が必要。CLI 実行不可の場合は UNVERIFIABLE とする）
