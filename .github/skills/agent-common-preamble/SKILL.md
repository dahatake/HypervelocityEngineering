---
name: agent-common-preamble
description: >
  全 Custom Agent が作業開始時に参照する共通プリアンブル。 USE FOR: agent start, common rules, work area, output language, Azure official info, generated app traceability routing. DO NOT USE FOR: implementation, detailed planning rules, review activation policy. WHEN: Custom Agent が作業を開始したとき、共通ルールの所在を確認したいとき。
metadata:
  origin: user
  version: 1.1.0
---

# agent-common-preamble

## 共通ルール

この Skill は、全 Agent が開始時に確認する共通の入口だけを置く。詳細は必要になった時点で
[`references/agent-playbook.md`](references/agent-playbook.md) を参照する。

- 作業領域: 通常の一時スクリプト、ログ、検証出力は `work/` 配下へ置く（Skill `work-artifacts-layout`）。
- HVE 自己テスト（FR-MAINT-12）では [tests/README.md](../../../tests/README.md) を優先し、controller 指定の元リポジトリの `tests/run/<run-id>/<task>/` を使う。
- 原本保護: `docs-original/` 配下の原本は読み取り専用として扱い、変更、削除、整形をしない。
- plan.md / subissues.md を作成または更新した場合の validator は [`references/agent-playbook.md`](references/agent-playbook.md) を参照する。

## 出力言語ルール

- 最終出力、成果物、計画、ツール委譲の説明は日本語で記述する。
- 英語の固有名詞、コマンド名、ファイルパス、コード識別子、引用文はそのまま英語でよい。

## Azure 公式情報

Azure サービス選定、Azure CLI、SDK、REST API、SKU、リージョン対応、状態プロパティ、サンプルコードは変わりやすい。
そのため Microsoft Learn MCP が利用可能なら必ず参照し、title / URL / 確認事項を根拠に残す。
未取得時は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。
Microsoft Learn Web redirect の単回再試行条件は
[`references/agent-playbook.md#Microsoft-Learn-Web-redirect-の単回再試行`](references/agent-playbook.md#microsoft-learn-web-redirect-の単回再試行)
を参照する。

## Azure External Skill の JIT ルーティング（必須）

- Azure または Microsoft Foundry を扱う active HVE Step は、`hve/skill_manifest.json` の `required_skills` / `optional_skills` を正本とする。
- required external Skill は正確な directory だけを session に渡す。optional candidate は、選定済み Azure サービスと実行操作に一致する candidate だけを読込み・利用する。
- `~/.agents/skills` 全体またはカテゴリ directory を渡して探索させてはならない。未導入 Skill の Azure write 許可や resource 操作の根拠にはしない。
- 設計・read-only 調査・review は、Microsoft Learn MCP を使い、未導入 Skill 名と未取得留保の有無を根拠に記録する。
- 選定済みサービスへの実装または Azure write で official external Skill candidate が未導入なら、Azure write を実行せず block する。generic な `azure-prepare` / `azure-deploy`、または active Step の read-only readiness review 候補として明示されていない `azure-validate` を代替にしない。
- AAGD `2.3` / `3` は `microsoft-foundry` meta skill を required とし、repository-pinned `azure` と `microsoft-learn` MCP の接続確認後に main turn を開始する。

## 生成アプリケーション要求トレーサビリティ

AAS / ADA / AAD-WEB / ASDW-WEB / ADFD / ADFDV / AAG / AAGD / AAR の 9 Workflow は、生成アプリケーション（APP）のスコープ確定と要求定義書参照を Skill `application-requirement-traceability` へルーティングする。

- 対象 APP-ID の解決は `app-scope-resolution`、要求定義書内の該当箇所検索は `markdown-query` を再利用する。
- canonical path（`docs/architectural-requirements-app-NNN.md`）と対象 APP-ID・Requirement ID だけを Prompt へ注入し、要求定義書全文を既定の入力にしない。

## Related Skills / 参照資料

| Skill / 資料 | 使う場面 |
|---|---|
| [`references/agent-playbook.md`](references/agent-playbook.md) | Windows、unique edit、Azure redirect、External Skill JIT、APP要求詳細、plan/subissues validator |
| `work-artifacts-layout` / `input-file-validation` | `work/` 配置、入力ファイル確認 |
| `app-scope-resolution` / `application-requirement-traceability` | APP-ID 解決、生成アプリ要求トレース |
| `large-output-chunking` / `harness-verification-loop` / `harness-safety-guard` / `harness-error-recovery` | 大量出力、対象検証、安全確認、エラー復旧 |
| `adversarial-review` / `docs-output-format` | 明示時のみの敵対的レビュー、`docs/` 成果物形式 |
