---
name: tdd-red-green-reality
description: >
  TDD RED/GREEN を実際のコマンド出力で示すための短い原則。 USE FOR: RED/GREEN real-output verification, tautological assertion avoidance, deployed-vs-available distinction, HVE generated test policy references. DO NOT USE FOR: generic test strategy tutorial, test code generation, retry count ownership. WHEN: RED/GREEN を実出力で検証する、実在確認や HVE 生成テスト方針の所在を確認するとき。
metadata:
  origin: user
  version: 1.1.0
---

# tdd-red-green-reality

## 目的

- 実際のコマンド出力で FAIL → PASS を示す。
- 常に真になる assert を書かない。
- 理由: 合否を後から再現できるようにするため。

`§1.7` は HVE が生成・評価するテスト成果物に限定した採用方針であり、非 HVE プロジェクトへ一律適用する汎用標準ではない。

---

## 1) RED/GREEN リアリティ原則

1. RED は実出力で示す。検証コマンドまたはテストを実行し、目的の振る舞いが今は FAIL であることを exit code やログで確認する。
2. GREEN は同じ検証の再実行で示す。実装またはデプロイ後に、RED で使った検証を緩めず PASS を確認する。
3. 恒真式アサーション禁止。`count >= 0`、`Assert.True(true)`、空 try/catch の no-op など、常に真になる主張を存在性や基本 I/O の合否に使わない。
4. 「利用可能」と「実在」を混同しない。カタログに存在することやリージョンで使えることは、実際に作成・デプロイ済みであることを意味しない。

---

## 1.5) TDD テスト結果レポート

TDD RED/GREEN Step の結果は次に記録する。

`tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md`

レポートには `Schema-Version`、`Evidence-Status`、`TDD-Judgement`、`Secret-Redaction`、`Test-Files-Changed` を含める。
固定 Markdown スキーマは [`references/tdd-test-report.md`](references/tdd-test-report.md) を正本とする。

---

## 1.6) 生成テストの実行環境契約

HVE が生成するテストコードは、ローカル実行可能なテストと構成済み外部サービスを使うテストを分ける。
外部サービス未設定を fake GREEN にせず、秘密情報をテストコード、README、ログへハードコードしない。
詳細は [`references/generated-test-runtime.md`](references/generated-test-runtime.md) を参照する。

---

## 1.7) HVE 生成テスト方針

テストピラミッド、テストダブル、テストデータ、エッジケース、カバレッジ方針は
[`references/generated-test-policy.md`](references/generated-test-policy.md) を正本とする。
この節番号は他の指示から参照されるため保持する。

---

## 3) verify コマンドの確定

検証コマンドは対象プラットフォームの公式情報で確認する。

| 対象 | 公式情報源 | 例 |
|---|---|---|
| Azure | Skill `agent-common-preamble` に従い、Copilot CLI に登録済みの Microsoft Learn MCP（登録状態は `/mcp` で確認）または `az <group> <cmd> -h` | `az <service> show` / `az ... list` |
| AWS | 公式ドキュメントまたは `aws <service> help` | `aws <service> describe-*` |
| Google Cloud | 公式ドキュメントまたは `gcloud <group> --help` | `gcloud <service> describe` |
| Windows アプリ (.NET) | 公式ドキュメントまたは `dotnet --help` | `dotnet test` |
| iOS / macOS アプリ | 公式ドキュメントまたは `xcodebuild -help` | `xcodebuild test` |

- Azure は Microsoft Learn MCP が利用可能なら必ず参照する。
- Azure の verify コマンド、SDK、REST API、SKU、状態プロパティ、サンプルコードを確認した場合は、Microsoft Learn の title / URL / 確認事項を作業ログまたは AC 証跡に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。

---

## 参照元

- 検証完了判定: Skill `harness-verification-loop`
- GREEN リトライ上限: Skill `tdd-green-retry-strategy`
- 失敗時の原因・再試行条件・停止条件: Skill `harness-error-recovery`
