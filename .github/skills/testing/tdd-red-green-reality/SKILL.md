---
name: tdd-red-green-reality
description: >
  プラットフォーム非依存の TDD RED/GREEN リアリティ原則。検証は実コマンド出力で
  FAIL→PASS を証明し、恒真式（常に真の主張）を禁止する。verify コマンドは対象
  プラットフォーム（Azure / AWS / GCP / Windows / iOS 等）ごとに実行時の公式
  ドキュメントから確定する。 USE FOR: TDD RED/GREEN reality, real-output verification,
  tautological assertion prohibition, platform-agnostic deploy verify. DO NOT USE FOR:
  test strategy pyramid (use test-strategy-template), test code generation (agents do that).
  WHEN: RED/GREEN を実出力で検証する、デプロイ/実装の実在を検証する、対象が Azure 以外。
metadata:
  origin: user
  version: 1.0.0
---

# tdd-red-green-reality

## 目的

TDD の RED/GREEN を「自己申告」ではなく **実コマンドの出力** で証明させるための、
**プラットフォーム非依存**の共通原則を一元管理する。対象が Azure か AWS か GCP か、
あるいは Windows / iOS アプリかに関わらず、本 Skill の原則は同一である。具体的な検証
コマンドのみが対象プラットフォームごとに変わる。

> 背景: 検証が「アカウントが存在する」「リソースが provisioning 成功」だけを見ると、
> モデル未デプロイ・設定未適用でも GREEN になる構造的欠陥が生じる。RED/GREEN は
> **目的の振る舞いが今 FAIL し、実装/デプロイ後に PASS する**ことを実出力で示す。

---

## Non-goals

- **テストピラミッド・テストダブル・カバレッジ方針** — Skill `test-strategy-template` が担当
- **テストコードの生成** — `Dev-*-TestCoding` 系 Agent が担当
- **CI/CD パイプライン組み込み** — Skill `github-actions-cicd` または Deploy 系 Agent が担当
- **特定プラットフォームの具体コマンドの網羅** — 実行時に公式ドキュメント（MCP / 公式 CLI ヘルプ）から確定する

---

## 1) RED/GREEN リアリティ原則（プラットフォーム非依存・必須）

1. **RED は実出力で示す**: 検証コマンド/テストを実行し、目的の振る舞いが **今は FAIL**
   であることを実際のコマンド出力（exit code / ログ）で確認する。「未実装だから FAIL のはず」
   という推測で代替しない。
2. **GREEN は同じ検証の再実行で示す**: 実装/デプロイ後、**RED で使ったのと同じ検証**を
   再実行し、PASS を実出力で確認する。検証内容を GREEN 用に緩めない。
3. **恒真式アサーション禁止**: 数学的・論理的に常に真となる主張（例: `count >= 0`、
   `Assert.True(true)`、空 try/catch の「例外が出なければ OK」を存在検証に流用）を、
   **存在性・基本 I/O の合否判定に使わない**。0 件でも PASS する検証は実在を保証しない。
   - 例外: 権限境界テストで「許可された操作が例外なく完了する（no-exception）」ことの確認は
     許容する（ただし件数の下限を主張する恒真式は使わない）。
4. **「利用可能」と「実在」を混同しない**: 「カタログに存在する / リージョンで利用可能」は
   「実際に作成・デプロイ済み」を意味しない。合否は **実在（デプロイ済みの実体）** で判定する。
5. **リアリティ証跡を残す**: 実 deploy / 実テスト実行の出力（GREEN ログの要点）を
   `ac-verification.md`（Deploy 系の AC 検証記録）または作業ログに貼り、後から再現可能にする。

---

## 1.5) TDD テスト結果レポート（CLI / GUI 共通・必須）

TDD RED/GREEN Step は、テストコード（`src/test/`）や仕様書（`docs/`）ではなく、
実行ごとのテスト結果をルート直下 `tests/` 配下へ記録する。`src/test/` はテストコード専用、
`tests/` はテスト結果レポート専用として扱う。

`tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md`

- `<step-id>` は `.` と `/` を `-` に正規化する（例: `4.1` → `step-4-1`）。
- `<target-key>` は fan-out key を優先し、無ければ serviceId / screenId / jobId / agentId、取得不能なら `default` とする。
- `<phase>` は初回標準では `RED` または `GREEN` のみを使う。
- raw log を保存する場合は秘密情報を含めない。保存できない場合はサニタイズ済みの抜粋を `Log-Excerpt` に記録する。

必須ラベル（Markdown 固定スキーマ）:

| ラベル | 必須値 / 役割 |
|---|---|
| `Schema-Version` | `1` |
| `Workflow` | workflow id |
| `Step` | step id |
| `Agent` | Custom Agent 名 |
| `Target-Key` | fan-out key 等 |
| `Phase` | `RED` / `GREEN` |
| `Test-Code-Path` | `src/test/...` または verify script path |
| `Timestamp-UTC` | ISO-8601 UTC |
| `Evidence-Status` | `EXECUTED` / `NOT_EXECUTED_ENV_BLOCKED` |
| `TDD-Judgement` | `PASS` / `FAIL` / `BLOCKED` |
| `Secret-Redaction` | `confirmed` |
| `Test-Files-Changed` | `yes` / `no` / `N/A` |

GREEN Step では `Evidence-Status: EXECUTED` を必須とし、`TDD-Judgement` は原則 `PASS`（テストが実際に GREEN）とする。
テスト側または共有設定側の確定ブロッカーにより実装だけでは GREEN 化できない場合に限り、`BLOCKED`（正直なブロッカー記録。Skill `tdd-green-retry-strategy` §4 参照）を許容する。実装未達など自ステップ起因の失敗は `FAIL` とし、これは gate で拒否される。
RED Step では exit code の一律判定をしない。Step 固有の期待結果（例: baseline test は即 PASS し得る、
Azure 未認証時は `NOT_EXECUTED_ENV_BLOCKED` を許容する等）を `Expected Outcome` に明記する。

固定スキーマは以下を使用する。HVE の TDD report gate はラベルを `- Label: value` 形式で検出するため、
`Label: value` のようなプレーン行にしない。見出し名も固定し、`## Result` / `## Observed Result` /
`## Actual Outcome` / `## Changed Test Files` などの代替名にしない。
`TDD-Judgement: PASS` は RED フェーズのテストが成功したという意味ではなく、RED 期待結果どおりの
証跡として妥当であることを表す。

```markdown
# TDD Test Report - <target-key> <phase>

<!-- validation-confirmed -->

- Schema-Version: 1
- Workflow: <workflow-id>
- Step: <step-id>
- Agent: <custom-agent-name>
- Target-Key: <target-key>
- Phase: <RED/GREEN>
- Test-Code-Path: <src/test/...>
- Timestamp-UTC: <ISO-8601 UTC timestamp>
- Evidence-Status: EXECUTED
- TDD-Judgement: <PASS/FAIL/BLOCKED>
- Secret-Redaction: confirmed
- Test-Files-Changed: <yes/no/N/A>

## Command

- CWD: `<repository-root>`
- Command: `<test command>`
- Exit-Code: <exit-code>

## Expected Outcome

- Expected: <RED/GREEN の期待結果>
- Reason: <期待結果の根拠>

## Actual Result

- Test-Suites: <summary>
- Tests: <summary>
- Summary: <actual summary>

## Evidence

- Log-Excerpt: <sanitized excerpt or N/A>
- Raw-Log-Path: <path or N/A>
- Secret-Redaction: confirmed

## Failure Analysis

- Root-Cause: <expected RED failure / GREEN failure root cause>
- Next-Action: <next step>

## Test Protection

- Test-Files-Changed: <yes/no/N/A>
- Allowed-Test-Changes: <changed test files or N/A>
```

> **ASDW-WEB Step 1.2（DataTestCoding）の追加契約**: 上記の共通ラベルに加えて、Step 1.2 は 3 状態を分離して機械検証する。`Artifact-Contract-Status`（syntax/static validator/lint）、`Live-RED-Status`（live Azure verifier の expected-fail 実行 / `NOT_RUN` / `BLOCKED`）、`Focused-Regression-Status`（required focused pytest の exit code）を各1件記録する。static contract の PASS を live RED 実行として偽らず、live 未実行は `NOT_RUN`（`EXECUTED`/`PASS` にしない）、focused pytest 非ゼロは `FAIL`（単一 PASS へ畳み込まない）。これら3ラベルは HVE 所有の `machine-verification.log`（tool 実行結果から HVE が生成する正本）と一致する必要があり、不一致は gate で拒否される。詳細は `Dev-Microservice-Azure-DataTestCoding.prompt.md` を参照。

---

## 1.6) 生成テストの実行環境契約

HVE が生成するテストコードは、次の契約に従う。

- **単体テスト / 実装コード向け TDD RED / TDD GREEN はローカル実行可能を既定**とする。外部 I/O は Mock / Stub / Emulator / Testcontainers 等に置き換え、`dotnet test` / `pytest` / `npm test` / `jest` / `playwright` などの標準コマンドで実行できる構造にする。
- **外部サービスを検証対象にする integration / post-deploy / E2E テスト**は、対象サービスが正しく作成・構成済みであることを前提にしてよい。ただし接続先・認証・base URL は環境変数またはテスト設定ファイルから取得し、ローカル端末・CI・デプロイ先のいずれでも同じ設定キーで実行できるようにする。
- **未構成の外部サービスを成功扱いしない**。必須の URL / Endpoint / Resource 名 / 認証経路が未設定の場合は、fake GREEN にせず `Expected Outcome` / `Failure Analysis` に環境ブロッカーとして記録する。
- **秘密情報をテストコード・README・ログへハードコードしない**。接続文字列、アカウントキー、SAS、Function Key、Bearer token は環境変数または実行環境の secret store から渡す。
- ローカル専用の mock テストと、構成済み外部サービスを使う integration テストを混同しない。どちらのカテゴリかを README / `tdd-test-report.md` に明記する。

---

## 2) 検証の 4 観点（マネージドサービス向け・プラットフォーム非依存）

デプロイ済みサービスの integration 検証は、最低限この 4 観点を各 1 件以上含める:

| 観点 | 意味 | 恒真式に陥らないための要点 |
|---|---|---|
| 接続性 | クライアント初期化・エンドポイント疎通 | 「初期化できた」だけでなく実エンドポイントへ到達したか |
| 権限境界 | 期待ロールで許可操作が成功（拒否操作が拒否される） | no-exception 確認は可。件数下限の恒真式は不可 |
| 基本 I/O | write→read 等のラウンドトリップ、または **実在の下限**（例: デプロイ済み単位が 1 件以上） | `>= 0` ではなく `>= 1` 等、実在を要求する下限 |
| 設定整合性 | 宣言した SKU / 構成 / 数量が実環境と一致 | 「宣言値を読んだ」ではなく実環境値と突き合わせる |

---

## 3) verify コマンドの確定（プラットフォーム別・実行時に公式ドキュメントから）

検証コマンドは **推測・捏造しない**。対象プラットフォームに応じ、実行時に公式情報源から確定する。

| 対象プラットフォーム | 一次情報源（実行時に参照） | 検証コマンド例（確定は実行時） |
|---|---|---|
| Azure | **Microsoft Learn MCP**（`.github/.mcp.json` の `microsoft-learn`）／ `az <group> <cmd> -h` | `az <service> show` / `az ... list`（実在の下限を確認） |
| AWS | 公式ドキュメント／ `aws <service> help` | `aws <service> describe-*` / `list-*` |
| Google Cloud | 公式ドキュメント／ `gcloud <group> --help` | `gcloud <service> describe` / `list` |
| Windows アプリ (.NET) | 公式ドキュメント／ `dotnet --help` | `dotnet test`（実テスト実行で PASS を確認） |
| iOS / macOS アプリ | 公式ドキュメント／ `xcodebuild -help` | `xcodebuild test`（実テスト実行で PASS を確認） |
| その他 | 当該プラットフォームの公式 CLI ヘルプ / 公式ドキュメント | 公式が示す「実在確認」コマンド |

- Azure は構成済みの **Microsoft Learn MCP** が利用可能なら必ず参照する。確定できない引数は `... -h` で最終確認する。
- Azure の verify コマンド、SDK、REST API、SKU、状態プロパティ、サンプルコードを確認した場合は、参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログ（work-status 系成果物）または AC 証跡に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。`az ... -h` / パッケージマネージャ / 公式 CLI help は補助確認として使う。
- いずれのプラットフォームでも、確定できない値は `TBD（要確認）` と明記し、捏造しない。

---

## 4) Deploy 系 gate との関係（HVE 固有）

- Deploy 系 Agent の `ac-verification.md` は、HVE の reality gate（`hve/artifact_validation.py` の
  `validate_deploy_ac_verification`）が `| AC-x | ... | 状態 | ... |` のテーブル行を解析し、
  実在系 AC が `❌` / `⏳` / `NEEDS-VERIFICATION` のままなら Step を fail に降格する。
- どの AC を実在系として強制するかは `StepDef.reality_gate_acs`（registry 宣言）で指定する。
  本 Skill の「実在で判定する」原則を、その AC のリアリティ証跡（GREEN ログ）で満たすこと。
- gate のテーブル解析・状態判定はプラットフォーム非依存である。プラットフォーム差は
  「どの検証コマンドで GREEN を得るか」だけに現れる。

---

## 参照元

- 検証パイプライン（Build/Lint/Test/Security/Diff）: Skill `harness-verification-loop`
- テスト設計の原則（ピラミッド・ダブル・カバレッジ）: Skill `test-strategy-template`
- 失敗時のリカバリ: Skill `harness-error-recovery`
