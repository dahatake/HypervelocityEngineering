{root_ref}
## 目的
TDD RED フェーズ: Agent 詳細設計書・テスト戦略書に基づき、Agent 用 TDD テスト仕様書を生成する（APP-ID 指定時はスコープ内の Agent のみ）。

## 必須テストカテゴリ（全5種を含めること）
1. **Agent I/O 契約テスト** — 入力（ユーザーメッセージ・コンテキスト）→ 期待出力（応答・アクション）の検証
2. **Tool モック統合テスト** — Tool 呼び出しのパラメータ・戻り値・エラー時の動作検証（Tool は全てモック化）
3. **Guardrails テスト** — 禁止操作・PII マスキング・ポリシー違反検出の検証
4. **状態遷移テスト** — 正常フロー・例外フロー・エスカレーションフローの検証
5. **プロンプト回帰テスト** — System Prompt 変更後の動作一貫性（期待出力のマッチング）検証

## 入力
- `docs/test-strategy.md`
- `docs/AI-Agents-list.md`
- `docs/agent/agent-detail-*.md`
- `docs/service-catalog.md`
- `docs/data-model.md`
- `docs/app-list.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- `docs/test-specs/{agentId}-test-spec.md`（Agent 別テスト仕様書）

## Custom Agent
`Arch-TDD-TestSpec` を使用

## 依存
- Step.2.6（AI Agent 構成設計）が `asdw:done` であること
- `docs/test-strategy.md` が存在すること

## 完了条件
- `docs/test-specs/` 配下に Agent 別テスト仕様書が生成されている
- テスト仕様書に上記5種のテストカテゴリが含まれている
- 完了時に自身に `asdw:done` ラベルを付与すること{app_id_section}{additional_section}