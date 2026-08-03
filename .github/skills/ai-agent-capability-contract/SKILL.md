---
name: ai-agent-capability-contract
description: >
  AAG / AAGD で生成する AI Agent の Goal Loop、検索ルーティング、REST Tool、MCP、Agent Skill の必須契約を提供する。 USE FOR: AI agent design, AI agent implementation, goal loop, agentic retrieval routing, REST tools, MCP integration, agent skills. DO NOT USE FOR: general web app implementation, generic MCP server development, non-agent workflow. WHEN: AAG または AAGD で AI Agent を設計・テスト・実装・デプロイするとき。
metadata:
  origin: user
  version: 1.0.0
---

# ai-agent-capability-contract

## 目的

AAG / AAGD の各Stepが、ユーザー目的、Read-only検索、REST mutation、MCP、Agent別Skill、自己改善を同じ契約IDで設計・実装・検証できるようにする。

## Non-goals（このスキルの範囲外）

- **全 Custom Agent への横断適用** — AAG / AAGD だけを対象とする。
- **特定providerのAPI実装リファレンス** — 実装時に公式技術情報を参照する。
- **MCP Serverの汎用実装** — API側Remote MCPは既存Web/API workflowの責務を再利用する。
- **Agent別Skillの無条件生成** — 3回ルールまたは明確な再利用要件がある場合だけ作成する。
- **hook / provider registry / Strategy / Factoryの追加** — 具体的要件がない限り作成しない。

## 適用手順

1. [共通能力契約](references/capability-contract.md) でAG-CAP-01〜06とフェーズ責務を確認する。
2. 対象Stepに応じて下表のreferenceだけを読む。
3. 不明項目を推測せず、理由付きTBDまたはN/Aとして上流Stepへ戻す。
4. 設計で選択した能力だけをテスト・実装・デプロイする。
5. 対象Stepのvalidator / TDD / deploy gateで実証する。

## Progressive Disclosure

| 対象 | 読むreference | 用途 |
|---|---|---|
| AAG Step 1 | `capability-contract.md`, `goal-self-improvement.md` | Mission、Mutation Intent、成功条件 |
| AAG Step 2 | `capability-contract.md`, `search-routing.md`, `tool-mcp-skill-packaging.md` | data / Tool / MCP / Agent境界 |
| AAG Step 3 | 3 referenceすべて | AG-CAP-01〜06の詳細設計 |
| AAGD Step 2.1 / 2.2 | 3 referenceすべて | 正常・境界・失敗テスト |
| AAGD Step 2.3 | 3 referenceすべて | 選択能力の最小実装 |
| AAGD Step 3 | `search-routing.md`, `tool-mcp-skill-packaging.md` | provider接続、認証、smoke test |
| HVE Self-Improve / gate | `capability-contract.md`, `goal-self-improvement.md` | criterion、証跡、停止条件 |

## 契約一覧

| ID | 固定見出し |
|---|---|
| AG-CAP-01 | `Goal Contract` |
| AG-CAP-02 | `Runtime Goal Loop` |
| AG-CAP-03 | `Knowledge & Structured Data Routing` |
| AG-CAP-04 | `REST CRUD Matrix` |
| AG-CAP-05 | `MCP Integration Plan` |
| AG-CAP-06 | `Skill Packaging Decision` |

全Agentは各契約を実装するか、理由と根拠付きN/Aを記録する。空欄や単語だけのN/Aは認めない。

## 入出力例

### 例1: 公開Webと業務更新を持つAgent

**入力:**

- 公開Webの最新情報を引用付きで検索する。
- 承認後に既存業務APIでケース状態を更新する。

**出力:**

- AG-CAP-03: Web IQのDesign statusとFoundry Web Search fallback。
- AG-CAP-04: REST PATCH、HITL、RBAC、冪等性。
- AG-CAP-05: retrieval MCPだけをclient利用。mutation迂回なし。
- AG-CAP-06: 手順が3回未満なら理由付きnot-required。

### 例2: 検索もmutationもない分類Agent

**入力:** ローカル入力をschemaに従って分類する。

**出力:**

- AG-CAP-01 / 02は必須。
- AG-CAP-03〜05は理由と根拠付きN/A。
- AG-CAP-06は再利用根拠がなければnot-required。

## 検証

- AAG detail: AG-CAP-01〜06、理由付きN/A、Contract source。
- AAGD test: 選択能力の正常・境界・失敗ケース。
- AAGD implementation: 設計→実装→testのContract IDトレース。
- HVE gate: LLMの自己申告ではなく成果物と実テストを検証。

## Related Skills

| Skill | 関係 | 用途 |
|---|---|---|
| `task-dag-planning` | 先行 | AAG/AAGDのStep分割と依存設計 |
| `test-strategy-template` | 依存 | Agent capability testのテスト戦略 |
| `mcp-server-design` | 補完 | API側Remote MCPとSkillの責務分離 |
| `harness-verification-loop` | 後続 | Build / Lint / Test / Security / Diff |
