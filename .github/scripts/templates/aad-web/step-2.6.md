{root_ref}

{app_arch_scope_section}
## 目的
機能要件に Chat-Bot / AI Agent / RAG / 対話型応答を含むサービスについて、**製品非依存**の Agentic Retrieval 機能要件詳細仕様を作成する（APP-ID 指定時はスコープ内のサービスのみ）。

## 対象サービスの判定
Prompt `Arch-AgenticRetrieval-Detail` の §3.3 判定キーワード表に従い、各サービス定義書の機能要件欄をスキャンして対象を抽出する。**根拠が無いサービスは「該当しない」とし、推測で対象化しない。**

## 製品非依存の制約（必須）
- Azure 固有名 / SKU / API バージョン / リージョン / リソース名を spec.md に書かない。
- Skill `agentic-retrieval-contract` の「製品非依存成果物へのガード」節にある変換表を使い、AR-CAP の設計観点を**業務的な問い**へ変換して記述する。AR-CAP の固定見出しとパラメータ名は Azure 実装設計（ASDW-WEB Step.2.5）以降で使う。

## 入力
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
- `docs/catalog/service-catalog.md`
- `docs/catalog/domain-analytics.md`
- `docs/services/{serviceId}-{serviceNameSlug}-description.md`

## 出力
- `docs/services/{serviceId}-agentic-retrieval-spec.md`（対象サービスのみ）

{existing_artifact_policy}

## Custom Agent
`Arch-AgenticRetrieval-Detail` を使用

## 依存
- Step.2.2（マイクロサービス定義書）が `aad-web:done` であること

## 完了条件
- 対象サービスごとに `docs/services/{serviceId}-agentic-retrieval-spec.md` が 8 章構成で作成されている
- 対象サービスが 0 件の場合は、判定根拠（参照ファイル・抜粋・キーワード）を作業ログへ記録したうえで成果物なしで完了する
{completion_instruction}{app_id_section}{additional_section}
