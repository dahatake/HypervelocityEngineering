{root_ref}
## 目的
ドメイン分析結果とサービス一覧を根拠に、データモデル（概念モデル + 物理マッピング）を設計する。
本ステップは Web アプリのオンラインデータベースに加え、データフロー型アプリの**データソース／デスティネーション／中間データ**も同一データモデルに統合する。APP-ID 横断の単一の真実源（SoT）として、同一データの重複定義を防ぐ。

## データソース／デスティネーション統合観点
`docs/catalog/app-catalog.md` にデータフロー型 APP-ID が含まれる場合、当該 APP-ID が読み書きするデータも Entity Catalog に統合すること。同一の業務エンティティが複数 APP-ID から参照される場合は、エンティティを統合し「利用APP」欄に該当 APP-ID を全て列挙する（重複エンティティを作らない）。利用APP 欄の詳細は `## アプリケーション粒度` セクションに従う。
- データフロー上の役割（APP-ID 単位）として `ソース / デスティネーション / 中間` のいずれかを明記する（ステージングは「中間」に含める）。同一エンティティが APP-ID 毎に異なる役割を持つ場合は、APP-ID 毎の役割を併記する。
- 外部システム（外部 API・ファイル受信等）そのものを業務エンティティとして登録しない。外部システムから授受される業務データを Entity Catalog に登録し、外部システム名・API 名・ファイル名は物理マッピングまたは根拠欄に記載する。
- 不明な項目は推測せず `TBD` または `不明（要確認）` と明記する。

該当観点は、`Arch-DataModeling` Agent の既存 Entity Catalog・物理マッピングセクションに、根拠付きで反映すること。Agent の出力契約に「役割」「外部システム名」用の列が存在しない場合は、T4.3 で Entity Catalog または物理マッピングへ列追加を行う前提とする。

## 入力
- `docs/catalog/domain-analytics.md`
- `docs/catalog/service-catalog.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧）

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
- Step.2.2（サービス一覧抽出）が `aas:done` であること

## アプリケーション粒度
📋 `docs/catalog/app-catalog.md` のアプリケーション一覧（APP-ID）を参照し、Entity Catalog の各エンティティに「利用APP」（N:N）を記載すること。

## 完了条件
- `docs/catalog/data-model.md` が作成されている
- 分割時は canonical sidecar 3件がすべて作成され、親子の相互リンクが有効である
- 分割不要時は canonical sidecar 3件が残っていない（stale成果物を削除済みである）
- Sub-4 (B-1) で本ステップから `src/data/sample-data.json` の生成は Step 3.2 へ分離されている
{completion_instruction}{additional_section}
