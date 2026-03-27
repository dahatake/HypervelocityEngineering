{root_ref}
## 目的
ドメイン分析結果、サービス一覧、データモデルを根拠に画面一覧を設計する。

## 入力
- `docs/domain-analytics.md`
- `docs/service-list.md`
- `docs/data-model.md`
- `docs/app-list.md`（アプリケーション一覧）

## 出力
- `docs/screen-list.md`

## Custom Agent
`Arch-UI-List` を使用

## 依存
- Step.3（データカタログ）が `aad:done` であること（Step.3 がスキップ時は Step.2（データモデル）が `aad:done` であること）

## アプリケーション粒度
📋 `docs/app-list.md` のアプリケーション一覧（APP-ID）を参照し、各画面に「所属APP」（1:1）を記載すること。

## 完了条件
- `docs/screen-list.md` が作成されている
- 完了時に自身に `aad:done` ラベルを付与すること{additional_section}
