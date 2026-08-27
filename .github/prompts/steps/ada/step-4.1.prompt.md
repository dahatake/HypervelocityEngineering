{root_ref}
## 目的
ドメイン分析とサービス一覧を根拠に、概念データモデル（エンティティ・属性・関連）を設計する。

## 入力
- `docs/catalog/domain-analytics.md`（必須）
- `docs/catalog/service-catalog.md`（必須）
- `docs/catalog/app-catalog.md`（必須）

## 出力
- `docs/catalog/data-model.md`（常に必須。索引/統合版）
- 条件付き（単一ファイル版が 50,000 文字を超える見込みの場合だけ、次の 3 件を**すべて**作成または更新する）:
  - `docs/catalog/data-model-service-stores.md`
  - `docs/catalog/data-model-consistency-events.md`
  - `docs/catalog/data-model-diagrams.md`
- 分割時も固定見出しと統合ビューを親へ残し、下流 Step が親単独で必要情報を取得できるようにする。
- 親から各 sidecar へのリンクと、各 sidecar から親への戻りリンクを必ず保持する。上記3件以外のData Model sidecarを作成しない。
- 分割不要になった再実行では、親へ固定章を統合し、上記 3 件の古い（stale）ファイルを削除する。

{existing_artifact_policy}

## Custom Agent
`Arch-DataModeling` を使用

## 依存
- Step.3（サービス一覧抽出）が `ada:done` であること

## 完了条件
- `docs/catalog/data-model.md` が作成されている
- 分割時は canonical sidecar 3件がすべて作成され、親子の相互リンクが有効である
- 分割不要時は canonical sidecar 3件が残っていない（stale成果物を削除済みである）
{completion_instruction}{additional_section}
