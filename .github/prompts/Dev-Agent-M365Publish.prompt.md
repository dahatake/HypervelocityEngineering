# Dev-Agent-M365Publish

デプロイ済み AI Agent を Microsoft 365 Copilot Chat / Teams から呼べる状態にし、
公開手順と結果を成果物として残す。

## Skills 依存

- `ai-agent-capability-contract`（必須） — AG-CAP-09 `Distribution & Packaging` の Microsoft 365 / Teams チャネル契約。
- `agent-common-preamble`（共通ルール）

## 入力

| Workflow | Step | 必須入力 |
|---|---|---|
| `aagd` | 7 | `docs/ai-agent-catalog.md` / `docs/agent/agent-detail-{key}.md` |

推奨入力:

- `src/agent/{key}/`（デプロイ済み実装と `plugin.json`）
- `src/infra/azure/README-agent-deploy.md`（Deploy 手順。エンドポイントとリソース名の根拠）

## 出力

| Workflow | Step | 出力 |
|---|---|---|
| `aagd` | 7 | `docs/agent/m365-publish-report.md` |

## Non-goals

- Agent 実装・System Prompt・Tool 定義の変更
- 既存の認可スキーム・プロトコル設定の削除や置換
- Azure リソースの新規作成（公開に必要な最小限の設定を除く）
- 公開範囲の独断決定（`Channels` と `M365 publish` は設計が正本）

## 1. なぜこの Step が必要か

Agent を Foundry へデプロイしただけでは、利用者のチャットクライアントからは呼べない。
AG-CAP-09 が「実装したが呼び出せない」状態を防ぐ契約であり、本 Step はその Microsoft 365 側の実行を担う。

## 2. 手順

1. `docs/agent/agent-detail-{key}.md` の Section 7.8 `Distribution & Packaging` を読む。
2. `Channels` が `Microsoft 365` / `Teams` を採っていない場合、**公開作業を行わない**。
   採らなかった理由と再判定条件をレポートへ書き、判定を `NOT_SELECTED` とする。ここで終了する。
3. 採っている場合、`M365 publish` の公開範囲・認可スキーム・承認要否・版の採番規則を読む。
4. **Microsoft Learn MCP で公開手順の現行仕様を確認**する。参照 URL と確認日をレポートへ残す。
   API version / SKU / リージョン / リソース名は本 Prompt の記述から推測せず、取得した公式情報で確定する。
5. 公開を実行する。テナント全体への公開が管理者承認待ちになる場合は `PENDING_APPROVAL` とする。
6. 利用者が接続するために必要な操作を `Consumer-Setup` へ書く。

## 3. 判定語彙（4 値固定）

| 値 | 意味 |
|---|---|
| `PUBLISHED` | 公開が完了し、対象クライアントから呼べる |
| `PENDING_APPROVAL` | 公開要求は出したが管理者承認待ち |
| `NOT_SELECTED` | 設計が当該チャネルを採っていない |
| `FAILED` | 公開を試みたが失敗した（原因必須） |

## 4. レポートの固定フォーマット

HVE の artifact gate が機械検証する。

- 公開条件: `Schema-Version` / `Workflow` / `Step` / `Agent` / `Published-At` / `Publish-Scope` / `Auth-Scheme` / `Secret-Redaction`
- 公開表: `| Agent Key | Channel | Publish Scope | App Version | Judgement | Approval | Evidence |`（**1 行以上必須**）
- 結論: `- Conclusion:` と `- Rationale:`
- 利用者向け接続手順: `- Consumer-Setup:`

## 5. 禁止事項

- 公開していないのに `PUBLISHED` と書かない。
- **公開メタデータへ secret・API キー・接続文字列・内部 URL を入れない**（利用者に見えるため）。
- 既に公開した版と**同じ版を再利用しない**。更新時は版を上げる。
- 既存の認可スキーム・プロトコル設定を削除・置換しない。追加だけを行う。
- リソース名・SKU・API version・リージョンを推測で確定しない。

## 6. 完了条件

- `docs/agent/m365-publish-report.md` が作成されている
- 公開条件ラベル 8 件がすべて記載されている
- 公開表が 1 行以上あり、各行の判定が 4 値のいずれかである
- `Conclusion` / `Rationale` / `Consumer-Setup` が記載されている
