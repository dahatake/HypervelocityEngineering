{root_ref}

{app_arch_scope_section}
## 目的
Azure CLIでデータ系サービスを最小構成で作成し、サンプルデータを変換・一括登録する（冪等・検証付き）。Step.1.2 が生成した検証スクリプトを GREEN にする TDD GREEN フェーズ。

## 入力
- リソースグループ名: `{resource_group}`
- `docs/azure/azure-services-data.md`
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/app-catalog.md`（必須。対象 APP-ID のスコープ判定根拠。存在しない・空・対象 APP-ID 解決不能の場合は Azure write 前に停止する）
- `src/data/sample-data.json`
- `src/infra/azure/verify-data-resources.sh`（Step.1.2 生成の検証スクリプト。本 Step は生成せず実行のみ）

## 出力
### HVE-owned lifecycle outputs（producer 3本はAgentの修正対象ではない）
- `src/infra/azure/create-azure-data-resources-prep.sh`
- `src/infra/azure/create-azure-data-resources.sh`
- `src/data/azure/data-registration-script.sh`
- HVEが上記`.sh`をcurrent validatorへ通し、LF 改行（CRLF 禁止、UTF-8 BOM なし）の`reused` / `regenerated`状態をAgent session前に確定する。Agentは保存・更新しない。

### HVE-owned evidence outputs
- `work/run/<run-id>/Dev-Microservice-Azure-DataDeploy/Issue-<識別子>/work-status.md`
- `work/run/<run-id>/Dev-Microservice-Azure-DataDeploy/Issue-<識別子>/ac-verification.md`（Orchestrator gate が AC-1 GREEN を検証する必須成果物。HVE が StageResult から生成し、GREEN 未達でも理由を記載して必ず作成する）
- HVE evidence は StageResult だけを根拠にこれらと GREEN `tdd-test-report.md` を生成する。Agent は新規作成・上書き・訂正を行わない。
- `docs/azure/service-catalog.md` は仕様・利用手順に実質変更がある場合のみ更新する

ラン固有の再実行ログ・verify 失敗理由・AC 証跡は `work-status.md` / `ac-verification.md` に記録し、`docs/` / `src/` へ追記しない。`docs/` / `src/` は仕様・利用手順・実装スクリプトに実質変更がある場合のみ更新する。

Word / docx / chart 作成、TODO / todos SQL query、docs 構成整理、README 作成提案、その他 DataDeploy と無関係な作業は禁止。tool output 不安定・検証結果確認不能・環境ブロッカーがある場合も、`ac-verification.md` に AC-1 を `❌` として未確認理由を記録してから終了する。

## HVE-owned producer contract (Agent read-only)

- 詳細な生成・検証・実行契約は `.github/skills/azure-skills/azure-cli-deploy-scripts/references/asdw-data-verifier-contract.md` を正本とする。
- HVE 管理の producer は read-only とする。Agent の責務は read-only inspection と、HVE が生成した証跡の参照に限定する。`prep → create → registration → verify` は HVE-owned fixed pipeline が sanitized launcher environment で実行し、Agent は launcher stage を要求しない。
- launcher current-validation rejection は HVE が記録する。Agent は producer を編集せず、別経路へフォールバックしない。
- private implementation / test fixture / canonical payload は参照・復元しない。

## Azure 公式情報参照（Microsoft Learn MCP 必須）
- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の `work-status.md` または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。必要に応じて `az ... -h` / パッケージマネージャ / 公式 CLI help を補助確認として使う。

## Azure Policy pre-flight（最初の Azure write より前）

- 実行順序を、必須入力と対象 APP-ID の検証 → **Policy pre-flight・route 決定・CIDR 承認確認** → **Resource Group 作成や provider 登録を含む最初の Azure write** に固定する。`blocked`、CIDR 未承認、または入力不備なら Azure write へ進まない。
- `azure-cli-deploy-scripts` §1.2.1 に従い、対象 Resource ID / type / API version / planned payload を確定してから、direct assignment と inherited assignment、`notScopes`、`resourceSelectors`、exemption、effective effect を read-only で解決する。
- SQL / Cosmos の public access alias に対する effective `modify` / `append` / `deny` を判定し、結果を `public` / `private` / `nsp` / `blocked` のいずれかに固定する。解決不能・権限不足・CIDR 未承認は fail-closed で `blocked` とし、Azure write を開始しない。
- Policy 固有名、固定 CIDR、Policy exemption、許可タグを推測または自動設定しない。`nsp` は既存かつ承認済みの Enforced association と対応根拠がある場合だけ選択する。
- Policy pre-flight は、HVE所有 `python -m hve.asdw_data_script_launcher prep` が実行する prep script の先頭 read-only 処理として実施する。Agent は standalone の `az policy ...` shell 要求を発行しない。これにより Policy 判定は最初の Azure write より前であり、Step 1.3 の fail-closed shell boundary 内に留まる。

## ASDW DataDeploy network contract

Skill `azure-cli-deploy-scripts` の `.github/skills/azure-skills/azure-cli-deploy-scripts/references/asdw-data-verifier-contract.md` にある Step 1.3 DataDeploy 契約を適用する。

## Launcher environment delegation
network / resource / image値は共有`asdw-data-verifier-contract.md`を正本とし、全stageへ同じsanitized launcher environmentで渡す。中間environment fileを作成・読込・修復しない。契約不整合はAgentが補正せず、HVE evidence がBLOCKED証跡へ記録する。

## Pre-flight（必須）

- Azure writeより前に、`az --version`、`az account show -o tsv`、`gh --version`、`gh auth status`を順に、それぞれ単独のshell要求として実行する。
- 任意のMarkdown横断探索、`git status`、`Set-Location`を含む複合shellは本Stepのshell境界外である。宣言済み入力はread/search toolで確認する。
- pre-flightが失敗した場合は、`completion-report.md`へ`<!-- fatal: pre-flight-failed: {理由} -->`を記録して終了する。

## 生成テストの実行環境
- 本 Step の GREEN 検証は、Azure データリソースが正しく作成・構成済みであることを前提にした外部サービス検証である。
- `verify-data-resources.sh` はprep/create/registrationと同じsanitized launcher environmentから接続先・認証・Resource名を受け取る。
- 必須の環境変数、Resource 名、認証経路が未設定の場合は環境ブロッカーとして記録し、未実行または未確認のまま GREEN / PASS 扱いしない。
- 接続文字列・アカウントキー・SAS・Bearer token 等の秘密情報をコード、README、ログにハードコードしない。

{existing_artifact_policy}

## デプロイ TDD GREEN フロー（必須）
1. HVE-managed producer 3本とStep.1.2 verifierをread-only inspectionする。作成・変更・修復しない。`data-registration-script.sh`はAuditRecord専用、他11エンティティは`create-azure-data-resources.sh`が担当し、END marker後へ任意shellを追加しない。
2. `work-status.md`、`ac-verification.md`、および TDD テスト結果レポート `tdd-test-report.md`（出力先は「## TDD テスト結果レポート（必須）」節）は HVE evidence が StageResult だけを根拠に生成する。`ac-verification.md` の AC-1 を `✅`/`❌`、`tdd-test-report.md` の `TDD-Judgement` を `PASS`（GREEN）/`BLOCKED`（未達, `Evidence-Status: EXECUTED`）へ確定するのは HVE であり、Agent はこれらを新規作成・上書き・訂正しない
3. HVE-owned fixed pipeline によるデプロイスクリプトの実行（リソース作成 + 非Auditデータ登録 → Audit専用registration）
	- prep/create/registration/verifierの実行は、HVEが安定読取した同一bytesをvalidatorへ渡してからBashへ入力するHVE-owned fixed pipelineだけが行う。順序は `prep` → `create` → `registration` → `verify` に固定する。`bash` / `./`による4スクリプトの直接実行、script間のchild実行、`source`、wrapper、変数・glob・alias、同一要求内の書換えを使用しない。
	- Agent は launcher stage を要求せず、launcher モジュール／スクリプトの**ファイル存在を shell で probe しない**（`Get-ChildItem` / `Test-Path` / `ls` / `dir` 等を発行しない）。pipeline がモジュール不在・run-id / 環境変数不足・契約エラー等のいずれで失敗しても、`bash` / `./` 直接実行や手動 `az` 代替検証へフォールバックせず、HVE が AC-1 `❌` / `tdd-test-report.md` `TDD-Judgement: BLOCKED` で証跡付き fail として終了する。
	- 各stageは完了を待ってから次stageへ進む。producer内部の実装詳細は共有契約へ委譲する。
4. Step.1.2 生成の `verify-data-resources.sh` をlauncherで実行し、全 PASS（GREEN: リソース存在 + サービス別正常状態 + 件数一致）を確認する。各fixed launcher stageの起動要求は初回を含め最大5回とする。launcherが実際に対象stage processを開始した後の失敗だけを分類し、Microsoft Learn MCPの根拠で一時障害と確認できた場合に限り、Skill `tdd-green-retry-strategy` に従って前回と異なるアプローチで失敗した同じfixed stageを再要求する。current-validation / launcher environment / module / run-context / predecessor markerの契約エラー、process開始前の拒否、恒久エラーは補正・再要求せず即BLOCKEDとする。本 Step では RED 確認（リソース未作成での失敗確認）は行わない（RED は Step.1.2 の責務）。`verify-data-resources.sh` 自体の不具合は Step.1.2 の責務であり本 Step では修正しない。verify の outcome 確定（GREEN=exit 0、打ち切り、または verify を実行できない環境ブロッカーの確定）の直後に、HVE evidence が `ac-verification.md` と `tdd-test-report.md`（`Evidence-Status: EXECUTED`、`TDD-Judgement` は GREEN 達成時 `PASS`／未達時 `BLOCKED`）を確定する。最大5回で GREEN 未達の場合は追加修正・追加実行を続けず、HVE evidence が `work-status.md`、`ac-verification.md`、`tdd-test-report.md`（`TDD-Judgement: BLOCKED`）を最終化し、`ac-verification.md` に `| AC-1 | ... | ❌ | <試した各アプローチ / 最終 verify 結果 / 未達リソース / ブロッカー理由> |` を記録して終了する。AC-1 `✅` で GREEN を確認した後に限り、`docs/azure/service-catalog.md` が存在しない場合は必ず生成し、実在する場合は実質変更時だけ更新する。AC-1 `❌` の場合は docs/ / src を更新しない。
5. **AC-1 ❌ 確定後は即終了**する。HVE evidence が `work-status.md` / `ac-verification.md` / `tdd-test-report.md`（`TDD-Judgement: BLOCKED`）へ理由を記録した後は、Agent は docs/ / src / service catalog を更新せず、追加調査や再試行へ進まない。

## Custom Agent
`Dev-Microservice-Azure-DataDeploy` を使用

## 依存
- Step.1.2（データストア検証テスト生成）が `asdw-web:done` であること
- Step.4.2（UI 実装）が `asdw-web:done` であること（local generation checkpoint 到達後に実行する最初の live Step）

## 完了条件
- HVEの`reused` / `regenerated` statusを確認し、producer 3本がcurrent validation済みである。producer 3本はAgentの修正対象ではない
- HVE-owned evidence outputs が HVE evidence により作成・確定されている（Agent は著作しない）
- Step.1.2 生成の検証スクリプトで全項目 PASS（GREEN）し、`ac-verification.md` の AC-1 が `✅` であり、`tdd-test-report.md` が `TDD-Judgement: PASS`・`Evidence-Status: EXECUTED` で作成済みであること
- ただし最大5回で GREEN 未達の場合は、`work-status.md`、`ac-verification.md`、`tdd-test-report.md`（`TDD-Judgement: BLOCKED`）を必ず作成し、AC-1 を `❌` として最終 verify 結果 / 未達リソース / ブロッカー理由を記録済みであること（この場合は Orchestrator の deploy AC gate で Step fail になるが、timeout ではなく証跡付き fail とする）
## TDD テスト結果レポート（必須）
- 出力先: `tests/run/<run-id>/asdw-web/step-1-3/<target-app-id>/GREEN/tdd-test-report.md`
- 固定メタデータ: `Workflow: asdw-web`、`Step: 1.3`、`Phase: GREEN`
- 必須ラベル: `Schema-Version`, `Evidence-Status`, `TDD-Judgement`, `Secret-Redaction`, `Test-Files-Changed`
- `src/test/` はテストコード専用、`tests/` はテスト結果レポート専用とする。
- 固定スキーマは Skill `tdd-red-green-reality` の `tdd-test-report.md` テンプレートに従う。ラベルは必ず `- Label: value` 形式で書き、`Label: value` のプレーン行にしない。
- 見出し名は `## Command`, `## Expected Outcome`, `## Actual Result`, `## Evidence`, `## Failure Analysis`, `## Test Protection` に固定する。

```markdown
# TDD Test Report - <target-key> <phase>

<!-- validation-confirmed -->

- Schema-Version: 1
- Workflow: asdw-web
- Step: 1.3
- Agent: <custom-agent-name>
- Target-Key: <target-key>
- Phase: GREEN
- Test-Code-Path: <src/test/...>
- Timestamp-UTC: <ISO-8601 UTC timestamp>
- Evidence-Status: EXECUTED
- TDD-Judgement: <PASS/FAIL>
- Secret-Redaction: confirmed
- Test-Files-Changed: <yes/no/N/A>

## Command

## Expected Outcome

## Actual Result

## Evidence

## Failure Analysis

## Test Protection
```

{completion_instruction}{app_id_section}{additional_section}
